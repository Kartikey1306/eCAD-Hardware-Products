"""ngspice batch adapter for declared circuit simulations.

ngspice runs as ``ngspice -b <deck>`` and nothing else: with ``-r`` batch
mode performs no ``.meas`` at all, and with ``-o`` the results go to a log
inside the workspace that run_process deletes. Case arguments never reach the
command line. The metrics are the ``.meas`` results the deck declares, read
from stdout; a measurement that ngspice could not make, that is printed
twice, or whose value is not a finite number is named in the summary and
left out, so the case engine's comparator, not this adapter, decides what a
missing metric means.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from ..models import ExecutionStatus, Verdict
from .base import Adapter, AdapterRequest, AdapterResult, Capability
from .capabilities import probe_executable
from .process import ProcessRequest, relative_input_path, run_process

MAX_DECK_BYTES = 1 << 20
# A measurement a deck declares. `.meas op` is not an analysis ngspice
# measures ("unrecognized analysis type", ngspice-47).
DECLARED = re.compile(r"^[ \t]*\.meas(?:ure)?[ \t]+(?:tran|dc|ac)[ \t]+([A-Za-z][A-Za-z0-9_]*)[ \t]",
                      re.IGNORECASE | re.MULTILINE)
# A result line as ngspice-47 prints it: the lower-cased name, padded to 20
# characters (a longer name has no space before "="), the value, then the
# `at=`, or `from=` and `to=`, of the measurement's window. ngspice-36 and
# 44.2 print the same form, some values to seven significant digits, not six.
REPORTED = re.compile(r"^([a-z][a-z0-9_]*)[ \t]*=[ \t]*(\S+)(?:[ \t]+(?:at|from|to)=[ \t]*\S+)*[ \t]*$")
# Checked before float(), which also reads "1_0", "nan" and "infinity".
NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
# A measurement ngspice could not make: absent from stdout, named on stderr,
# and the exit status is still 0.
FAILED = re.compile(r"^[ \t]*\.meas(?:ure)?[ \t]+\S+[ \t]+([a-z][a-z0-9_]*)\b.*\bfailed!\s*$",
                    re.IGNORECASE | re.MULTILINE)
TRUNCATED = "[output truncated]"  # what process._limited appends to a capture it cut
RECEIPT_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")  # the receipt schema's reason_code pattern
MAX_SUMMARY_PROBLEMS = 10


def declared_measurements(deck: str) -> Tuple[List[str], List[str]]:
    """The names of the measurements a deck declares, as ngspice prints them.

    ngspice lower-cases a name and prints one result line per declaration, so
    a name declared twice has no single value and is never read.

    Args:
        deck: The deck's text.

    Returns:
        The names declared exactly once, lower-cased, in deck order; and the
        names declared more than once, in order of first declaration.

    Example:
        >>> declared_measurements(
        ...     "* title\\n.tran 1u 10u\\n.meas tran Peak MAX v(a)\\n.measure TRAN t1 FIND v(a) AT=2u\\n"
        ...     "* .meas tran commented FIND v(a) AT=1u\\n.meas tran t1 FIND v(a) AT=5u\\n")
        (['peak'], ['t1'])
    """
    counts: Dict[str, int] = {}
    for match in DECLARED.finditer(deck):
        name = match.group(1).lower()
        counts[name] = counts.get(name, 0) + 1
    return ([name for name, count in counts.items() if count == 1],
            [name for name, count in counts.items() if count > 1])


def parse_measurements(stdout: str, stderr: str, declared: Sequence[str]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Read the declared measurements from ngspice's batch output.

    A declared name becomes a metric only if exactly one stdout line reports
    it and its value is a finite number in SPICE's plain decimal notation.
    Names the deck does not declare are ignored, whatever stdout says.

    Args:
        stdout: ngspice's standard output.
        stderr: ngspice's standard error, where a failed measurement is named.
        declared: The names to read, lower-cased (from declared_measurements).

    Returns:
        The metrics, in the order of ``declared``; and for every other
        declared name why it is not one: "failed: <stderr line>", "not
        reported", "reported more than once", "not a number: <token>" or "not
        finite".

    Example:
        >>> stdout = ("inrush_peak_current_a=  4.71663e+00 at=  1.00000e-04\\n"
        ...           "bus_charge_time_s   =   1.09244e-02\\nundeclared = 1.0\\n")
        >>> stderr = " .meas tran late find v(a) at=50u failed!\\n"
        >>> metrics, problems = parse_measurements(stdout, stderr, ["inrush_peak_current_a", "bus_charge_time_s",
        ...                                                         "late", "absent"])
        >>> metrics
        {'inrush_peak_current_a': 4.71663, 'bus_charge_time_s': 0.0109244}
        >>> problems
        {'late': 'failed: .meas tran late find v(a) at=50u failed!', 'absent': 'not reported'}
    """
    failed: Dict[str, str] = {}
    for match in FAILED.finditer(stderr):
        failed.setdefault(match.group(1).lower(), match.group(0).strip())
    reported: Dict[str, List[str]] = {}
    for line in stdout.splitlines():
        found = REPORTED.match(line)
        if found:
            reported.setdefault(found.group(1), []).append(found.group(2))
    metrics: Dict[str, float] = {}
    problems: Dict[str, str] = {}
    for name in declared:
        values = reported.get(name, [])
        if name in failed:
            problems[name] = f"failed: {failed[name]}"
        elif not values:
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
    a receipt that fails its own schema is not written at all. This mapping is
    local to ngspice so that no other adapter's error path changes; it goes
    when probe_executable itself reports codes (fix/version-probe-reason-codes).

    Example:
        >>> [_receipt_reason(r) for r in ("VERSION_PROBE_TIMED_OUT", "VERSION_PROBE_ERROR:[Errno 13] Permission denied",
        ...                               "VERSION_PROBE_EXIT_-9", None)]
        ['VERSION_PROBE_TIMED_OUT', 'VERSION_PROBE_ERROR', 'VERSION_PROBE_EXIT_NONZERO', 'TOOL_NOT_INSTALLED']
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


class NgspiceAdapter(Adapter):
    name = "ngspice"

    def capability(self) -> Capability:
        return probe_executable(self.name, ("ngspice", "--version"))

    def run(self, request: AdapterRequest) -> AdapterResult:
        """Run the case's deck as ``ngspice -b <deck>`` and read the measurements it declares.

        Args:
            request: The case. Its first input file is the deck; its
                arguments never reach ngspice.

        Returns:
            BLOCKED, with nothing run, when ngspice is unavailable (the probe's
            reason as a receipt reason code, the raw reason in the summary),
            when there is no deck, or when the deck is over MAX_DECK_BYTES.
            Otherwise the process's verdict, and on PASS the metrics
            parse_measurements reads, with every declared name it could not
            read named in the summary; stdout that was cut short gives
            INCONCLUSIVE OUTPUT_TRUNCATED and no metrics.

        Example:
            >>> from pathlib import Path
            >>> class Unavailable(NgspiceAdapter):
            ...     def capability(self):
            ...         return Capability(adapter="ngspice", available=False, reason="VERSION_PROBE_EXIT_-9")
            >>> result = Unavailable().run(AdapterRequest(case_id="c", product_root=Path("."), input_files=[]))
            >>> result.verdict.value, result.reason_code, result.summary, result.command
            ('BLOCKED', 'VERSION_PROBE_EXIT_NONZERO', 'ngspice is unavailable: VERSION_PROBE_EXIT_-9', [])
        """
        capability = self.capability()
        if not capability.available:
            return AdapterResult(
                adapter=self.name,
                execution_status=ExecutionStatus.UNAVAILABLE,
                verdict=Verdict.BLOCKED,
                reason_code=_receipt_reason(capability.reason),
                summary=f"ngspice is unavailable: {capability.reason or 'no reason reported'}",
            )
        if not request.input_files:
            return AdapterResult(
                adapter=self.name,
                execution_status=ExecutionStatus.UNAVAILABLE,
                verdict=Verdict.BLOCKED,
                reason_code="NETLIST_INPUT_MISSING",
                summary="SPICE netlist is missing",
                tool_version=capability.version,
            )
        netlist = request.input_files[0]
        if netlist.stat().st_size > MAX_DECK_BYTES:
            return AdapterResult(
                adapter=self.name,
                execution_status=ExecutionStatus.UNAVAILABLE,
                verdict=Verdict.BLOCKED,
                reason_code="NETLIST_INPUT_TOO_LARGE",
                summary=f"SPICE netlist is larger than {MAX_DECK_BYTES} bytes and was not run",
                tool_version=capability.version,
            )
        relative = relative_input_path(request.product_root, netlist).as_posix()
        declared, duplicated = declared_measurements(netlist.read_bytes().decode("utf-8", errors="replace"))
        process = run_process(
            ProcessRequest(
                argv=[capability.executable or "ngspice", "-b", relative],
                input_root=request.product_root,
                input_files=request.input_files,
                timeout_seconds=request.timeout_seconds,
            )
        )
        verdict = (
            Verdict.BLOCKED
            if process.execution_status is ExecutionStatus.UNAVAILABLE
            else Verdict.INCONCLUSIVE
            if process.execution_status is not ExecutionStatus.COMPLETED
            else Verdict.PASS
            if process.returncode == 0
            else Verdict.FAIL
        )
        reason_code = process.reason_code
        summary = "ngspice batch run completed" if verdict is Verdict.PASS else "ngspice batch run did not pass"
        metrics: Dict[str, object] = {}
        if verdict is Verdict.PASS:
            if process.stdout.endswith(TRUNCATED):
                # A line cut short, such as "3.72465e+0", would read as the wrong number.
                verdict, reason_code = Verdict.INCONCLUSIVE, "OUTPUT_TRUNCATED"
                summary = "ngspice output was truncated, so no measurement was read from it"
            else:
                values, problems = parse_measurements(process.stdout, process.stderr, declared)
                problems.update((name, "declared more than once") for name in duplicated)
                metrics = dict(values)
                summary = (f"{summary}: {len(values)} of {len(declared) + len(duplicated)} "
                           "declared measurements read")
                if problems:
                    summary += "; " + "; ".join(
                        f"{name}: {problem}" for name, problem in list(problems.items())[:MAX_SUMMARY_PROBLEMS])
        return AdapterResult(
            adapter=self.name,
            execution_status=process.execution_status,
            verdict=verdict,
            reason_code=reason_code,
            summary=summary,
            command=process.argv,
            tool_version=capability.version,
            stdout=process.stdout,
            stderr=process.stderr,
            metrics=metrics,
            output_files=process.outputs,
        )
