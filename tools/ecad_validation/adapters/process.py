"""Hardened subprocess execution shared by all external-tool adapters."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from ..models import ExecutionStatus

MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_COLLECT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ProcessRequest:
    argv: List[str]
    input_root: Path
    input_files: List[Path]
    timeout_seconds: int = 180
    environment: Mapping[str, str] = field(default_factory=dict)
    # Files the tool writes into its workspace that the caller needs after the
    # workspace is deleted: plain file names, copied to collect_into.
    collect: Tuple[str, ...] = ()
    collect_into: Optional[Path] = None
    # The child reads os.devnull instead of inheriting the caller's stdin, so
    # a tool that prompts (vvp at a $stop) cannot wait on a terminal.
    stdin_devnull: bool = False


@dataclass
class ProcessResult:
    execution_status: ExecutionStatus
    reason_code: str
    argv: List[str]
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    workspace: Optional[Path] = None
    outputs: List[Path] = field(default_factory=list)
    collected: List[Path] = field(default_factory=list)
    collect_problems: Dict[str, str] = field(default_factory=dict)


def captured_text(value: Union[bytes, str, None]) -> str:
    """Normalise captured subprocess output to text.

    ``subprocess.TimeoutExpired`` carries the raw accumulated *bytes* even when
    ``subprocess.run`` was given ``text=True``: the exception is raised from
    ``Popen._communicate`` before newline translation runs. Passing those bytes
    to :func:`_limited` raises ``AttributeError``, which no caller catches, so
    the timeout path must decode before truncating.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _limited(text: str) -> str:
    data = text.encode("utf-8", errors="replace")
    if len(data) <= MAX_CAPTURE_BYTES:
        return text
    return data[:MAX_CAPTURE_BYTES].decode("utf-8", errors="replace") + "\n[output truncated]"


def relative_input_path(root: Path, source: Path) -> Path:
    """Return a contained lexical path, tolerating Windows 8.3 path aliases."""
    resolved_root = root.resolve()
    resolved_source = source.resolve()
    relative = Path(
        os.path.relpath(
            os.path.abspath(str(source)),
            os.path.abspath(str(root)),
        )
    )
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"adapter input escapes product root: {source}")
    ancestor = resolved_source
    for _part in relative.parts:
        ancestor = ancestor.parent
    try:
        contained = os.path.samefile(ancestor, resolved_root)
    except OSError:
        contained = False
    if not contained:
        raise ValueError(f"adapter input escapes product root: {source}")
    return relative


def _plain_file_name(name: str) -> bool:
    """Whether a collect name is one file name directly inside the workspace,
    on POSIX and on Windows (no separator, drive, "." or "..")."""
    return (name not in ("", ".", "..") and "\0" not in name
            and PurePosixPath(name).name == name and PureWindowsPath(name).name == name)


def _collect(workspace: Path, names: Sequence[str], destination: Path) -> Tuple[List[Path], Dict[str, str]]:
    """Copy each named regular file out of the workspace; name why any other is not copied."""
    collected: List[Path] = []
    problems: Dict[str, str] = {}
    for name in names:
        candidate = workspace / name
        try:
            status = candidate.lstat()
        except FileNotFoundError:
            problems[name] = "not produced"
            continue
        if stat.S_ISLNK(status.st_mode):
            problems[name] = "a symbolic link; not copied"
        elif not stat.S_ISREG(status.st_mode):
            problems[name] = "not a regular file; not copied"
        elif status.st_size > MAX_COLLECT_BYTES:
            problems[name] = f"larger than {MAX_COLLECT_BYTES} bytes; not copied"
        else:
            # follow_symlinks=False: a file swapped for a link after the lstat
            # is copied as a link, which run_process refuses as an input.
            shutil.copyfile(candidate, destination / name, follow_symlinks=False)
            collected.append(destination / name)
    return collected, problems


def run_process(request: ProcessRequest) -> ProcessResult:
    """Run without a shell in a temporary workspace containing copied inputs.

    The child sees only the copied inputs, a scrubbed environment (PATH, a
    HOME and TMPDIR inside the workspace, a C.UTF-8 locale, the Windows
    system variables, then request.environment), and each captured stream is
    cut at MAX_CAPTURE_BYTES. The workspace is deleted before this returns.

    Args:
        request: The command (argv[0] is looked up on PATH), the inputs and
            the root they are copied relative to, the timeout, any extra
            environment, the files to collect and where to, and whether the
            child's stdin is os.devnull.

    Returns:
        The outcome: UNAVAILABLE when argv[0] is not found, TIMED_OUT,
        CRASHED when it cannot be started, otherwise COMPLETED with its exit
        status and output. Only a COMPLETED run, whatever its exit status,
        collects: each name of request.collect that the workspace holds as a
        regular file of at most MAX_COLLECT_BYTES is copied to
        request.collect_into and listed in ``collected``; every other name is
        in ``collect_problems`` with the reason. A partial output of a run
        that did not complete is not a result.

    Raises:
        ValueError: before anything runs, for an empty argv, an input that is
            a symbolic link or escapes input_root, a collect name that is not
            one plain file name, or collect without an existing collect_into.

    Example:
        >>> import sys, tempfile
        >>> script = "open('out.txt', 'w').write('result')"
        >>> with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as kept:
        ...     result = run_process(ProcessRequest(
        ...         argv=[sys.executable, "-c", script], input_root=Path(root), input_files=[],
        ...         collect=("out.txt", "missing.txt"), collect_into=Path(kept)))
        ...     copied = [(path.name, path.read_text()) for path in result.collected]
        >>> (result.execution_status.value, result.returncode, copied, result.collect_problems)
        ('completed', 0, [('out.txt', 'result')], {'missing.txt': 'not produced'})
    """
    if not request.argv:
        raise ValueError("process argv must not be empty")
    if request.collect:
        if request.collect_into is None or not request.collect_into.is_dir():
            raise ValueError("collect needs collect_into, an existing directory")
        for name in request.collect:
            if not _plain_file_name(name):
                raise ValueError(f"collect name is not one plain file name: {name!r}")
    with tempfile.TemporaryDirectory(prefix="ecad-validation-") as temporary:
        workspace = Path(temporary)
        input_relatives = set()
        for source in request.input_files:
            resolved = source.resolve()
            relative = relative_input_path(request.input_root, source)
            if source.is_symlink():
                raise ValueError(f"adapter inputs may not be symbolic links: {relative}")
            input_relatives.add(relative)
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(resolved, target)

        executable = shutil.which(request.argv[0])
        if executable is None:
            return ProcessResult(
                execution_status=ExecutionStatus.UNAVAILABLE,
                reason_code="TOOL_NOT_INSTALLED",
                argv=request.argv,
            )

        environment: Dict[str, str] = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workspace / ".home"),
            "TMPDIR": str(workspace / ".tmp"),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if key in os.environ:
                environment[key] = os.environ[key]
        environment.update({str(key): str(value) for key, value in request.environment.items()})
        Path(environment["HOME"]).mkdir(parents=True, exist_ok=True)
        Path(environment["TMPDIR"]).mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            environment["TEMP"] = environment["TMPDIR"]
            environment["TMP"] = environment["TMPDIR"]
        argv = [executable, *request.argv[1:]]
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                shell=False,
                stdin=subprocess.DEVNULL if request.stdin_devnull else None,
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessResult(
                execution_status=ExecutionStatus.TIMED_OUT,
                reason_code="TOOL_TIMED_OUT",
                argv=argv,
                stdout=_limited(captured_text(exc.stdout)),
                stderr=_limited(captured_text(exc.stderr)),
            )
        except OSError as exc:
            return ProcessResult(
                execution_status=ExecutionStatus.CRASHED,
                reason_code="TOOL_EXECUTION_ERROR",
                argv=argv,
                stderr=str(exc),
            )

        outputs = [
            path.relative_to(workspace)
            for path in workspace.rglob("*")
            if path.is_file() and path.relative_to(workspace) not in input_relatives
        ]
        collected: List[Path] = []
        collect_problems: Dict[str, str] = {}
        if request.collect and request.collect_into is not None:
            collected, collect_problems = _collect(workspace, request.collect, request.collect_into)
        return ProcessResult(
            execution_status=ExecutionStatus.COMPLETED,
            reason_code="TOOL_EXITED_ZERO" if completed.returncode == 0 else "TOOL_EXITED_NONZERO",
            argv=argv,
            returncode=completed.returncode,
            stdout=_limited(completed.stdout or ""),
            stderr=_limited(completed.stderr or ""),
            outputs=outputs,
            collected=collected,
            collect_problems=collect_problems,
        )
