"""Icarus Verilog adapter that compiles and executes committed RTL testbenches.

Both steps run through run_process, so each sees only its own copied
inputs, a scrubbed environment (no IVERILOG_ICONFIG, IVERILOG_VPI_MODULE_PATH
or secret of the caller), an empty stdin, a capped output and the case's
timeout: ``iverilog -g2012 -o simulation.vvp <inputs>`` in one workspace,
whose program is collected out of it, then ``vvp simulation.vvp`` in a second
workspace holding only that program. Case arguments are refused, never put on
either command line: ``-s``, ``-D``, ``-y``, ``-c`` or ``-f`` would compile
something other than the inputs, and ``-m`` or ``-L`` load native code.

The metrics are the ``ECAD_METRIC <name> <value>`` lines the inputs declare
with ``$display("ECAD_METRIC <name> %0d", ...)`` or ``%.17g``, read from vvp's
stdout. A name declared twice, not printed, printed twice, or whose value is
not a finite plain-decimal number is named in the summary and left out, so the
case engine's comparator, not this adapter, decides what a missing metric
means. Truncated output gives no metric at all, and neither does a failed run.
"""

from __future__ import annotations

import math
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from ..models import ExecutionStatus, Verdict
from .base import Adapter, AdapterRequest, AdapterResult, Capability
from .capabilities import probe_executable
from .process import ProcessRequest, ProcessResult, relative_input_path, run_process

MAX_INPUT_BYTES = 1 << 20
PROGRAM = "simulation.vvp"
# A metric an input declares: the whole format string of one $display.
DECLARED = re.compile(r'\$display\("ECAD_METRIC ([a-z][a-z0-9_]*) %(?:0d|\.17g)"')
# A metric line as vvp prints it: one space either side of the name, nothing after the value.
REPORTED = re.compile(r"^ECAD_METRIC ([a-z][a-z0-9_]*) (\S+)$")
# Checked before float(), which also reads "1_0", "nan" and "infinity".
NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
TRUNCATED = "[output truncated]"  # what process._limited appends to a capture it cut
RECEIPT_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")  # the receipt schema's reason_code pattern
MAX_SUMMARY_PROBLEMS = 10


def declared_metrics(texts: Sequence[str]) -> Tuple[List[str], List[str]]:
    """The names of the metrics a set of Verilog inputs declares.

    A declaration is a ``$display`` whose format string is exactly
    ``"ECAD_METRIC <name> %0d"`` or ``"ECAD_METRIC <name> %.17g"``. A name
    declared twice, in one input or across two, has no single value and is
    never read.

    Args:
        texts: The inputs' texts, in compile order.

    Returns:
        The names declared exactly once, in order of declaration; and the
        names declared more than once, in order of first declaration.

    Example:
        >>> declared_metrics([
        ...     '$display("ECAD_METRIC tx_bit_cycles %0d", fall - rise);\\n'
        ...     '$display("ECAD_METRIC clock_period_s %.17g", period);\\n'
        ...     '$display("ECAD_METRIC wrong_format %d", x);\\n',
        ...     'if (ok) $display("ECAD_METRIC tx_bit_cycles %0d", n);\\n'])
        (['clock_period_s'], ['tx_bit_cycles'])
    """
    counts: Dict[str, int] = {}
    for text in texts:
        for match in DECLARED.finditer(text):
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return ([name for name, count in counts.items() if count == 1],
            [name for name, count in counts.items() if count > 1])


def parse_metrics(stdout: str, declared: Sequence[str]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Read the declared metrics from vvp's standard output.

    A declared name becomes a metric only if exactly one stdout line is
    ``ECAD_METRIC <name> <value>`` and the value is a finite number in plain
    decimal notation. Names the inputs do not declare are ignored, whatever
    stdout says, and so is every other line.

    Args:
        stdout: vvp's standard output.
        declared: The names to read (from declared_metrics).

    Returns:
        The metrics as floats, in the order of ``declared``; and for every
        other declared name why it is not one: "not reported", "reported
        more than once", "not a number: <token>" (``%0d`` of an unknown value
        prints ``x``, and ``%.17g`` of NaN prints ``nan``) or "not finite".

    Example:
        >>> stdout = ("ECAD_METRIC tx_bit_cycles 434\\nECAD_METRIC clock_period_s 2e-08\\n"
        ...           "ECAD_METRIC rx_data x\\nECAD_METRIC undeclared 1\\n"
        ...           "committed.v:349: $finish called at 416720000 (1ps)\\n")
        >>> metrics, problems = parse_metrics(stdout, ["tx_bit_cycles", "clock_period_s", "rx_data", "absent"])
        >>> metrics
        {'tx_bit_cycles': 434.0, 'clock_period_s': 2e-08}
        >>> problems
        {'rx_data': 'not a number: x', 'absent': 'not reported'}
    """
    reported: Dict[str, List[str]] = {}
    for line in stdout.splitlines():
        found = REPORTED.match(line)
        if found:
            reported.setdefault(found.group(1), []).append(found.group(2))
    metrics: Dict[str, float] = {}
    problems: Dict[str, str] = {}
    for name in declared:
        values = reported.get(name, [])
        if not values:
            problems[name] = "not reported"
        elif len(values) > 1:
            problems[name] = "reported more than once"
        elif not NUMBER.match(values[0]):
            problems[name] = f"not a number: {values[0]}"
        elif not math.isfinite(float(values[0])):
            problems[name] = "not finite"
        else:
            metrics[name] = float(values[0])
    return metrics, problems


def _receipt_reason(reason: Optional[str]) -> str:
    """A capability reason as a code the receipt schema accepts (^[A-Z][A-Z0-9_]*$).

    probe_executable reports an OSError as ``VERSION_PROBE_ERROR:<message>``
    and a signal as ``VERSION_PROBE_EXIT_-<n>``. Neither is a reason code, and
    a receipt that fails its own schema is not written at all. This is the
    ngspice adapter's mapping, copied so that no other adapter's error path
    changes; both copies go when probe_executable itself reports codes
    (fix/version-probe-reason-codes).

    Example:
        >>> [_receipt_reason(r) for r in ("VVP_NOT_INSTALLED", "VERSION_PROBE_ERROR:[Errno 13] Permission denied",
        ...                               "VERSION_PROBE_EXIT_-9", None)]
        ['VVP_NOT_INSTALLED', 'VERSION_PROBE_ERROR', 'VERSION_PROBE_EXIT_NONZERO', 'TOOL_NOT_INSTALLED']
    """
    if reason is None:
        return "TOOL_NOT_INSTALLED"
    if RECEIPT_CODE.match(reason):
        return reason
    if reason.startswith("VERSION_PROBE_ERROR:"):
        return "VERSION_PROBE_ERROR"
    if reason.startswith("VERSION_PROBE_EXIT_"):
        return "VERSION_PROBE_EXIT_NONZERO"
    return "TOOL_UNAVAILABLE"


class HDLAdapter(Adapter):
    name = "iverilog"

    def capability(self) -> Capability:
        compiler = probe_executable("iverilog", ("iverilog", "-V"))
        if not compiler.available:
            return compiler
        if shutil.which("vvp") is None:
            return Capability(
                adapter=self.name,
                available=False,
                executable=compiler.executable,
                version=compiler.version,
                reason="VVP_NOT_INSTALLED",
            )
        return compiler

    def _blocked(self, reason_code: str, summary: str) -> AdapterResult:
        return AdapterResult(
            adapter=self.name,
            execution_status=ExecutionStatus.UNAVAILABLE,
            verdict=Verdict.BLOCKED,
            reason_code=reason_code,
            summary=summary,
        )

    def _unfinished(self, step: str, process: ProcessResult) -> Optional[AdapterResult]:
        """The result of a step that did not run to completion, or None if it completed."""
        if process.execution_status is ExecutionStatus.COMPLETED:
            return None
        if process.execution_status is ExecutionStatus.UNAVAILABLE:
            verdict, reason_code, summary = Verdict.BLOCKED, "TOOL_NOT_INSTALLED", f"{step}: the tool was not found"
        elif process.execution_status is ExecutionStatus.TIMED_OUT:
            verdict, reason_code, summary = Verdict.INCONCLUSIVE, "RTL_EXECUTION_TIMED_OUT", f"{step} timed out"
        else:
            verdict, reason_code, summary = Verdict.INCONCLUSIVE, "RTL_EXECUTION_ERROR", f"{step}: the tool could not execute"
        return AdapterResult(
            adapter=self.name,
            execution_status=process.execution_status,
            verdict=verdict,
            reason_code=reason_code,
            summary=summary,
            command=process.argv,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def run(self, request: AdapterRequest) -> AdapterResult:
        capability = self.capability()
        if not capability.available:
            return self._blocked(
                _receipt_reason(capability.reason),
                f"Icarus Verilog execution capability is unavailable: {capability.reason or 'no reason reported'}",
            )
        if not request.input_files:
            return self._blocked("RTL_INPUT_MISSING", "RTL sources and testbench are missing")
        if request.arguments:
            return self._blocked(
                "RTL_ARGUMENTS_REFUSED",
                f"case arguments are not passed to Icarus Verilog and nothing was run: {list(request.arguments)!r}",
            )
        relatives = [relative_input_path(request.product_root, source).as_posix() for source in request.input_files]
        for source, relative in zip(request.input_files, relatives):
            if source.stat().st_size > MAX_INPUT_BYTES:
                return self._blocked(
                    "RTL_INPUT_TOO_LARGE",
                    f"RTL input {relative} is larger than {MAX_INPUT_BYTES} bytes and was not run",
                )
        declared, twice = declared_metrics(
            [source.read_bytes().decode("utf-8", errors="replace") for source in request.input_files])
        compile_command = [capability.executable or "iverilog", "-g2012", "-o", PROGRAM, *relatives]
        with tempfile.TemporaryDirectory(prefix="ecad-hdl-") as stage:
            compiled = run_process(ProcessRequest(
                argv=compile_command, input_root=request.product_root, input_files=request.input_files,
                timeout_seconds=request.timeout_seconds, stdin_devnull=True,
                collect=(PROGRAM,), collect_into=Path(stage)))
            unfinished = self._unfinished("RTL compilation", compiled)
            if unfinished is not None:
                return unfinished
            if compiled.returncode != 0:
                return AdapterResult(
                    adapter=self.name,
                    execution_status=ExecutionStatus.COMPLETED,
                    verdict=Verdict.FAIL,
                    reason_code="RTL_COMPILE_FAILED",
                    summary="RTL compilation failed",
                    command=compiled.argv,
                    tool_version=capability.version,
                    stdout=compiled.stdout,
                    stderr=compiled.stderr,
                )
            if not compiled.collected:
                return AdapterResult(
                    adapter=self.name,
                    execution_status=ExecutionStatus.COMPLETED,
                    verdict=Verdict.INCONCLUSIVE,
                    reason_code="RTL_PROGRAM_MISSING",
                    summary=f"RTL compilation exited 0 but {PROGRAM} was not kept "
                            f"({compiled.collect_problems.get(PROGRAM, 'not collected')}), so vvp was not run",
                    command=compiled.argv,
                    tool_version=capability.version,
                    stdout=compiled.stdout,
                    stderr=compiled.stderr,
                )
            executed = run_process(ProcessRequest(
                argv=["vvp", PROGRAM], input_root=Path(stage), input_files=list(compiled.collected),
                timeout_seconds=request.timeout_seconds, stdin_devnull=True))
        unfinished = self._unfinished("RTL testbench execution", executed)
        if unfinished is not None:
            return unfinished
        verdict = Verdict.PASS if executed.returncode == 0 else Verdict.FAIL
        reason_code = "RTL_TESTBENCH_PASSED" if verdict is Verdict.PASS else "RTL_TESTBENCH_FAILED"
        summary = f"committed RTL testbench exited {executed.returncode}, so no metric was read"
        metrics: Dict[str, object] = {}
        if verdict is Verdict.PASS:
            if executed.stdout.endswith(TRUNCATED):
                # A line cut short, such as "ECAD_METRIC tx_frame_cycles 43", would read as the wrong number.
                verdict, reason_code = Verdict.INCONCLUSIVE, "OUTPUT_TRUNCATED"
                summary = "vvp output was truncated, so no metric was read from it"
            else:
                values, problems = parse_metrics(executed.stdout, declared)
                problems.update((name, "declared more than once") for name in twice)
                metrics = dict(values)
                summary = (f"committed RTL testbench executed: {len(values)} of {len(declared) + len(twice)} "
                           "declared metrics read")
                if problems:
                    summary += "; " + "; ".join(
                        f"{name}: {problem}" for name, problem in list(problems.items())[:MAX_SUMMARY_PROBLEMS])
        return AdapterResult(
            adapter=self.name,
            execution_status=ExecutionStatus.COMPLETED,
            verdict=verdict,
            reason_code=reason_code,
            summary=summary,
            command=executed.argv,
            tool_version=capability.version,
            stdout=executed.stdout,
            stderr=executed.stderr,
            metrics=metrics,
        )
