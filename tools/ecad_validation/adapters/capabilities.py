"""Capability discovery that never equates a missing tool with success."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Dict, Iterable, Optional

from .base import Capability

TOOL_COMMANDS = {
    "kicad": ("kicad-cli", "--version"),
    "ngspice": ("ngspice", "--version"),
    "verilator": ("verilator", "--version"),
    "iverilog": ("iverilog", "-V"),
    "openscad": ("openscad", "--version"),
}

# A tool whose probe does not state its version on the first line of its
# output. ngspice-47 opens its banner with "******" and names itself on the
# second line: "** ngspice-47 : Circuit level simulation program".
VERSION_PATTERNS: Dict[str, re.Pattern[str]] = {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)")}


def version_from_output(adapter: str, output: str) -> Optional[str]:
    """The version a tool's probe output states, or None if it states none.

    Args:
        adapter: The adapter the probe is for; it selects a VERSION_PATTERNS entry.
        output: The probe's stdout and stderr, stripped.

    Returns:
        The pattern's match for a tool that has one, and None when it does
        not match, since a version nobody reported is never invented; for
        every other tool the first line of the output, or None if empty.

    Example:
        >>> version_from_output("ngspice", "******\\n** ngspice-47 : Circuit level simulation program\\n******")
        '47'
        >>> version_from_output("ngspice", "******") is None
        True
        >>> version_from_output("iverilog", "Icarus Verilog version 13.0 (stable) (v13_0)\\n\\nCopyright (c) 2000-2026")
        'Icarus Verilog version 13.0 (stable) (v13_0)'
    """
    pattern = VERSION_PATTERNS.get(adapter)
    if pattern is None:
        return output.splitlines()[0].strip() if output else None
    match = pattern.search(output)
    return match.group(1) if match else None


def probe_executable(adapter: str, command: Iterable[str]) -> Capability:
    argv = list(command)
    executable = shutil.which(argv[0])
    if executable is None:
        return Capability(adapter=adapter, available=False, reason="TOOL_NOT_INSTALLED")
    try:
        completed = subprocess.run(
            [executable, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return Capability(
            adapter=adapter,
            available=False,
            executable=executable,
            reason="VERSION_PROBE_TIMED_OUT",
        )
    except OSError as exc:
        return Capability(
            adapter=adapter,
            available=False,
            executable=executable,
            reason=f"VERSION_PROBE_ERROR:{exc}",
        )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    version_line = version_from_output(adapter, output)
    if completed.returncode != 0 and not version_line:
        return Capability(
            adapter=adapter,
            available=False,
            executable=executable,
            reason=f"VERSION_PROBE_EXIT_{completed.returncode}",
        )
    return Capability(
        adapter=adapter,
        available=True,
        executable=executable,
        version=version_line,
    )


def detect_mujoco() -> Capability:
    python = shutil.which("python3") or shutil.which("python")
    if python is None:
        return Capability(adapter="mujoco", available=False, reason="PYTHON_NOT_INSTALLED")
    try:
        completed = subprocess.run(
            [python, "-c", "import mujoco; print(mujoco.__version__)"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return Capability(adapter="mujoco", available=False, executable=python, reason="VERSION_PROBE_TIMED_OUT")
    except OSError as exc:
        return Capability(adapter="mujoco", available=False, executable=python, reason=f"VERSION_PROBE_ERROR:{exc}")
    if completed.returncode != 0:
        return Capability(adapter="mujoco", available=False, executable=python, reason="MUJOCO_NOT_INSTALLED")
    return Capability(
        adapter="mujoco",
        available=True,
        executable=python,
        version=completed.stdout.strip(),
    )


def detect_capabilities() -> Dict[str, Capability]:
    capabilities = {
        name: probe_executable(name, command)
        for name, command in TOOL_COMMANDS.items()
    }
    capabilities["mujoco"] = detect_mujoco()
    return capabilities
