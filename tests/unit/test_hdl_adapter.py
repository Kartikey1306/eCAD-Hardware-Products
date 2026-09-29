"""The Icarus Verilog adapter on run_process, and run_process's output collection.

Nothing here runs Icarus. The process boundary is replaced where the
adapter meets it: ``subprocess.run`` and ``shutil.which`` as
ecad_validation.adapters.process sees them. Those are the modules
themselves, so anything else that runs a process meets the same fake. The
version probe runs through run_process too; the fake answers ``iverilog -V``
separately, records how it was called, and never counts it as a step. The
run_process tests that need a real child run ``sys.executable``.

Recorded texts, byte for byte:

- RECORDED_STDOUT: what vvp printed for the digital design's simulation file
  (``derived/digital/uart_loopback_001.v``, sha256 191bd8f1...3e84) run
  through this adapter, Icarus Verilog 13.0, macOS arm64, 2026-09-27: exit
  0, empty stderr, identical over two runs. Icarus 11.0 on ubuntu:22.04
  arm64 prints the same ECAD_METRIC lines and no ``$finish`` line.
- HARNESS_REPORT: lines 337-350 of that file, the block that declares and
  prints the nine metrics.
- VERILATOR_STDOUT: Verilator 5.052's stdout for the same harness, macOS
  arm64, 2026-09-27.
- ICARUS_13_BANNER and ICARUS_11_FIRST_LINE: ``iverilog -V``, exit 0.

A value written inline in a test (a ``nan``, a ``1_0``, a compiler message)
is constructed for that test and says so. Expected values are typed by hand
from these texts, never obtained by calling the code under test.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

# Icarus Verilog 13.0, macOS arm64, 2026-09-27 (see the module docstring).
RECORDED_STDOUT = (
    "ECAD_METRIC clock_period_s 2e-08\n"
    "ECAD_METRIC tx_idle_after_reset 1\n"
    "ECAD_METRIC tx_bit_cycles 434\n"
    "ECAD_METRIC tx_bit_rate_bd 115207.3732718894\n"
    "ECAD_METRIC tx_frame_cycles 4340\n"
    "ECAD_METRIC rx_bytes_received 2\n"
    "ECAD_METRIC rx_bit_errors 0\n"
    "ECAD_METRIC rx_framing_errors 0\n"
    "ECAD_METRIC outputs_unknown_after_reset 0\n"
    "derived/digital/uart_loopback_001.v:349: $finish called at 416720000 (1ps)\n"
)
# Lines 337-350 of the digital design's simulation file.
HARNESS_REPORT = (
    "        if (ecad_cycle == 20836) begin\n"
    '            $display("ECAD_METRIC clock_period_s %.17g", (ecad_second_rise - ecad_first_rise) / 1.0e9);\n'
    '            if (ecad_idle_after_reset >= 0) $display("ECAD_METRIC tx_idle_after_reset %0d", ecad_idle_after_reset);\n'
    "            if (ecad_start_rise >= 0) begin\n"
    '                $display("ECAD_METRIC tx_bit_cycles %0d", ecad_start_rise - ecad_start_fall);\n'
    '                $display("ECAD_METRIC tx_bit_rate_bd %.17g", 1.0e9 / (ecad_start_rise_at - ecad_start_fall_at));\n'
    "            end\n"
    '            if (ecad_busy_to >= 0) $display("ECAD_METRIC tx_frame_cycles %0d", ecad_busy_to - ecad_busy_from);\n'
    '            $display("ECAD_METRIC rx_bytes_received %0d", ecad_received);\n'
    '            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors);\n'
    '            $display("ECAD_METRIC rx_framing_errors %0d", ecad_framing_errors);\n'
    '            if (ecad_unknown_after_reset >= 0) $display("ECAD_METRIC outputs_unknown_after_reset %0d", ecad_unknown_after_reset);\n'
    "            $finish;\n"
    "        end\n"
)
# Verilator 5.052, macOS arm64, 2026-09-27.
VERILATOR_STDOUT = (
    "ECAD_METRIC clock_period_s 2e-08\n"
    "ECAD_METRIC tx_idle_after_reset 1\n"
    "ECAD_METRIC tx_bit_cycles 434\n"
    "ECAD_METRIC tx_bit_rate_bd 115207.3732718894\n"
    "ECAD_METRIC tx_frame_cycles 4340\n"
    "ECAD_METRIC rx_bytes_received 2\n"
    "ECAD_METRIC rx_bit_errors 0\n"
    "ECAD_METRIC rx_framing_errors 0\n"
    "ECAD_METRIC outputs_unknown_after_reset 0\n"
    "- committed.v:349: Verilog $finish\n"
    "- S i m u l a t i o n   R e p o r t: Verilator 5.052 2026-09-05\n"
    "- Verilator: $finish at 417us; walltime 0.004 s; speed 116.175 ms/s\n"
    "- Verilator: cpu 0.004 s on 1 threads; allocated 2 MB\n"
)
# The first lines of `iverilog -V`: Icarus 13.0, macOS arm64, 2026-09-27; and
# the first line of Icarus 11.0 (apt 11.0-1.1, ubuntu:22.04 arm64, 2026-09-27).
ICARUS_13_BANNER = (
    "Icarus Verilog version 13.0 (stable) (v13_0)\n"
    "\n"
    "Copyright (c) 2000-2026 Stephen Williams (steve@icarus.com)\n"
)
ICARUS_11_FIRST_LINE = "Icarus Verilog version 11.0 (stable) ()\n"

# The nine values, typed from RECORDED_STDOUT.
RECORDED_METRICS = {
    "clock_period_s": 2e-08,
    "tx_idle_after_reset": 1.0,
    "tx_bit_cycles": 434.0,
    "tx_bit_rate_bd": 115207.3732718894,
    "tx_frame_cycles": 4340.0,
    "rx_bytes_received": 2.0,
    "rx_bit_errors": 0.0,
    "rx_framing_errors": 0.0,
    "outputs_unknown_after_reset": 0.0,
}
NINE = ["clock_period_s", "tx_idle_after_reset", "tx_bit_cycles", "tx_bit_rate_bd", "tx_frame_cycles",
        "rx_bytes_received", "rx_bit_errors", "rx_framing_errors", "outputs_unknown_after_reset"]
SOURCE = "derived/digital/x.v"
# Constructed: what the fake compiler writes as simulation.vvp.
PROGRAM_BYTES = b'#! /fake/vvp\n:ivl_version "13.0 (stable)" "(v13_0)";\n'
COMPILE_ARGV = ["/fake/iverilog", "-g2012", "-o", "simulation.vvp", SOURCE]
RUN_ARGV = ["/fake/vvp", "simulation.vvp"]
VERSION = "Icarus Verilog version 13.0 (stable) (v13_0)"
# run_process's environment: its own five keys, the Windows system variables
# it passes through, and the two it sets on Windows.
SCRUBBED = {"PATH", "HOME", "TMPDIR", "LC_ALL", "LANG", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"}
CALLER_ONLY = {"ECAD_TEST_SECRET": "leak", "IVERILOG_ICONFIG": "/nonexistent/iconfig.txt",
               "IVERILOG_VPI_MODULE_PATH": "/nonexistent/vpi", "IVERILOG_DUMPER": "lxt2"}
FOUR_MIB = 4194304
# The receipt schema's reason_code rule, read from the contract, not from the adapter.
RECEIPT_REASON = re.compile(json.loads(
    (REPO_ROOT / "schemas" / "hardware-validation" / "v1" / "validation-receipt.schema.json").read_text(encoding="utf-8")
)["definitions"]["checkResult"]["properties"]["reason_code"]["pattern"])


class _Tools:
    """iverilog, vvp and `iverilog -V`, as run_process and the version probe call them.

    The compiler writes PROGRAM_BYTES as simulation.vvp into its working
    directory (or what ``program`` writes), vvp reads it back, and every step
    records its argv, keyword arguments and the files its workspace held.
    """

    def __init__(self, banner: str = ICARUS_13_BANNER, compiled: Sequence[Any] = (0, "", ""),
                 executed: Sequence[Any] = (0, RECORDED_STDOUT, ""), raises: Optional[Dict[str, BaseException]] = None,
                 program: Any = None, installed: Sequence[str] = ("iverilog", "vvp")):
        self.banner = banner
        self.compiled = compiled
        self.executed = executed
        self.raises = raises or {}
        self.program = program if program is not None else (lambda cwd: (cwd / "simulation.vvp").write_bytes(PROGRAM_BYTES))
        self.installed = set(installed)
        self.steps: List[Dict[str, Any]] = []
        self.probes: List[List[str]] = []
        self.probe_calls: List[Dict[str, Any]] = []
        self._patches = [mock.patch("ecad_validation.adapters.process.subprocess.run", side_effect=self.run),
                         mock.patch("ecad_validation.adapters.process.shutil.which", side_effect=self.which)]

    def __enter__(self) -> "_Tools":
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        for patch in reversed(self._patches):
            patch.stop()

    def which(self, name: str) -> Optional[str]:
        tool = Path(name).name
        return f"/fake/{tool}" if tool in self.installed else None

    def run(self, argv: List[str], **kwargs: Any) -> subprocess.CompletedProcess:
        tool = Path(argv[0]).name
        if argv[1:] == ["-V"]:
            self.probes.append(list(argv))
            self.probe_calls.append(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout=self.banner, stderr="")
        cwd = Path(kwargs["cwd"])
        step: Dict[str, Any] = {"tool": tool, "argv": list(argv), "kwargs": kwargs,
                                "files": sorted(p.relative_to(cwd).as_posix() for p in cwd.rglob("*") if p.is_file())}
        self.steps.append(step)
        if tool in self.raises:
            raise self.raises[tool]
        if tool == "iverilog":
            self.program(cwd)
            return subprocess.CompletedProcess(argv, self.compiled[0], stdout=self.compiled[1], stderr=self.compiled[2])
        program = cwd / "simulation.vvp"
        step["program"] = program.read_bytes() if program.is_file() else None
        return subprocess.CompletedProcess(argv, self.executed[0], stdout=self.executed[1], stderr=self.executed[2])


def _product(root: Path, texts: Sequence[str] = (HARNESS_REPORT,)) -> List[Path]:
    """A product directory holding one Verilog input per text; returns the inputs."""
    inputs = []
    for index, text in enumerate(texts):
        path = root / "product" / (SOURCE if index == 0 else f"derived/digital/x{index}.v")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        inputs.append(path)
    return inputs


def _run(inputs: Sequence[Path], arguments: Sequence[str] = (), timeout: int = 17):
    from ecad_validation.adapters.base import AdapterRequest
    from ecad_validation.adapters.hdl import HDLAdapter

    return HDLAdapter().run(AdapterRequest(case_id="case", product_root=inputs[0].parents[2] if inputs else Path("."),
                                           input_files=list(inputs), arguments=list(arguments), timeout_seconds=timeout))


def _only_the_probe():
    """run_process as the adapter sees it, failing the test on anything but the version probe, ``iverilog -V``."""
    from ecad_validation.adapters.process import run_process

    def probe_only(request):
        if request.argv[1:] != ["-V"]:
            raise AssertionError(f"ran {request.argv}")
        return run_process(request)

    return mock.patch("ecad_validation.adapters.hdl.run_process", side_effect=probe_only)


def _outcome(result) -> tuple:
    return (result.verdict.value, result.execution_status.value, result.reason_code)


class TestTheTwoSteps(unittest.TestCase):
    def test_both_icarus_steps_run_through_run_process_with_the_scrubbed_environment(self):
        """ARCH-10: the compile and the run step each get run_process's workspace,
        scrubbed environment, empty stdin, timeout and no shell."""
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, CALLER_ONLY), _Tools() as tools:
            [source] = _product(Path(directory))
            product = source.parents[2]
            result = _run([source])
        self.assertEqual([step["argv"] for step in tools.steps], [COMPILE_ARGV, RUN_ARGV])
        compile_step, run_step = tools.steps
        for step in tools.steps:
            with self.subTest(step["tool"]):
                kwargs = step["kwargs"]
                environment = kwargs["env"]
                self.assertLessEqual(set(environment), SCRUBBED)
                self.assertFalse(set(environment) & set(CALLER_ONLY), environment)
                self.assertEqual(Path(environment["HOME"]).parent, Path(kwargs["cwd"]))
                self.assertEqual(Path(environment["TMPDIR"]).parent, Path(kwargs["cwd"]))
                self.assertNotEqual(Path(kwargs["cwd"]).resolve(), product.resolve())
                self.assertIs(kwargs["shell"], False)
                self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(kwargs["timeout"], 17)
                self.assertIs(kwargs["capture_output"], True)
        self.assertNotEqual(compile_step["kwargs"]["cwd"], run_step["kwargs"]["cwd"])
        self.assertEqual(compile_step["files"], [SOURCE])
        self.assertEqual(run_step["files"], ["simulation.vvp"])
        self.assertEqual(tools.probes, [["/fake/iverilog", "-V"]])
        # Review CS-6: the version probe, too, sees only run_process's environment, in a workspace of its own.
        [probe] = tools.probe_calls
        self.assertLessEqual(set(probe["env"]), SCRUBBED)
        self.assertFalse(set(probe["env"]) & set(CALLER_ONLY), probe["env"])
        self.assertEqual(Path(probe["env"]["HOME"]).parent, Path(probe["cwd"]))
        self.assertNotIn(Path(probe["cwd"]).resolve(), {product.resolve(), Path.cwd().resolve()})
        self.assertIs(probe["stdin"], subprocess.DEVNULL)
        self.assertEqual(probe["timeout"], 30)
        self.assertEqual(_outcome(result), ("PASS", "completed", "RTL_TESTBENCH_PASSED"))
        self.assertEqual(result.metrics, RECORDED_METRICS)
        self.assertEqual(result.summary, "committed RTL testbench executed: 9 of 9 declared metrics read")
        self.assertEqual((result.command, result.tool_version, result.stdout, result.stderr, result.output_files),
                         (RUN_ARGV, VERSION, RECORDED_STDOUT, "", []))

    def test_both_steps_are_capped_at_the_process_output_limit(self):
        from ecad_validation.adapters.process import MAX_CAPTURE_BYTES

        # Constructed: a compiler that fails with 5 MiB of stderr.
        noise = "e" * (5 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as directory, _Tools(compiled=(1, "", noise)) as tools:
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("FAIL", "completed", "RTL_COMPILE_FAILED"))
        self.assertEqual(result.command, COMPILE_ARGV)
        self.assertEqual(result.stderr, "e" * FOUR_MIB + "\n[output truncated]")
        self.assertEqual(len(tools.steps), 1)

        # Constructed: the recorded stdout behind enough blank lines that the cap
        # falls inside "4340", and 5 MiB of stderr.
        cut = RECORDED_STDOUT.index("4340") + len("434")
        stdout = "\n" * (MAX_CAPTURE_BYTES - cut) + RECORDED_STDOUT
        with tempfile.TemporaryDirectory() as directory, _Tools(executed=(0, stdout, noise)):
            result = _run(_product(Path(directory)))
        self.assertTrue(result.stdout.endswith("\nECAD_METRIC tx_frame_cycles 434\n[output truncated]"))
        self.assertEqual(len(result.stdout), FOUR_MIB + len("\n[output truncated]"))
        self.assertEqual(result.stderr, "e" * FOUR_MIB + "\n[output truncated]")
        # What reading it anyway would give: a frame ten times too short.
        from ecad_validation.adapters.hdl import parse_metrics
        self.assertEqual(parse_metrics(result.stdout, ["tx_frame_cycles"]), ({"tx_frame_cycles": 434.0}, {}))
        self.assertEqual(_outcome(result), ("INCONCLUSIVE", "completed", "OUTPUT_TRUNCATED"))
        self.assertEqual(result.metrics, {})
        self.assertEqual(result.summary, "vvp output was truncated, so no metric was read from it")

    def test_the_compiled_program_is_carried_to_the_run_step(self):
        with tempfile.TemporaryDirectory() as directory, _Tools() as tools:
            result = _run(_product(Path(directory)))
        self.assertEqual(tools.steps[1]["program"], PROGRAM_BYTES)
        self.assertEqual(_outcome(result), ("PASS", "completed", "RTL_TESTBENCH_PASSED"))

        def directory_instead(cwd: Path) -> None:
            (cwd / "simulation.vvp").mkdir()

        for label, program, problem in (("not written", lambda cwd: None, "not produced"),
                                        ("a directory", directory_instead, "not a regular file; not copied")):
            with self.subTest(label), tempfile.TemporaryDirectory() as directory, _Tools(program=program) as tools:
                result = _run(_product(Path(directory)))
                self.assertEqual([step["tool"] for step in tools.steps], ["iverilog"])
                self.assertEqual(_outcome(result), ("INCONCLUSIVE", "completed", "RTL_PROGRAM_MISSING"))
                self.assertEqual(result.summary, f"RTL compilation exited 0 but simulation.vvp was not kept ({problem}), "
                                                 "so vvp was not run")
                self.assertEqual((result.command, result.tool_version, result.metrics), (COMPILE_ARGV, VERSION, {}))


class TestRefusals(unittest.TestCase):
    def test_case_arguments_never_reach_a_command_line(self):
        """-N writes a file, -m loads native code, and -s picks another top."""
        for arguments in (["-N/tmp/x"], ["-mevil"], ["-s", "b"]):
            with self.subTest(arguments), tempfile.TemporaryDirectory() as directory, _Tools() as tools, \
                    _only_the_probe():
                result = _run(_product(Path(directory)), arguments)
                self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "RTL_ARGUMENTS_REFUSED"))
                self.assertEqual(result.summary,
                                 f"case arguments are not passed to Icarus Verilog and nothing was run: {arguments!r}")
                self.assertEqual((tools.steps, result.command, result.metrics), ([], [], {}))

    def test_an_oversized_input_is_neither_read_nor_run(self):
        limit = 1048576  # 1 MiB
        at_limit = HARNESS_REPORT + "\n" * (limit - len(HARNESS_REPORT))
        self.assertEqual(len(at_limit.encode()), limit)
        for label, texts, oversized in (("the only input", [at_limit + "\n"], SOURCE),
                                        ("the second input", [HARNESS_REPORT, at_limit + "\n"], "derived/digital/x1.v")):
            with self.subTest(label), tempfile.TemporaryDirectory() as directory, _Tools() as tools, \
                    mock.patch.object(Path, "read_bytes", side_effect=AssertionError("an input was read")):
                result = _run(_product(Path(directory), texts))
                self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "RTL_INPUT_TOO_LARGE"))
                self.assertEqual(result.summary, f"RTL input {oversized} is larger than 1048576 bytes and was not run")
                self.assertEqual((tools.steps, result.metrics), ([], {}))
        # One byte less is read and run.
        with tempfile.TemporaryDirectory() as directory, _Tools() as tools:
            result = _run(_product(Path(directory), [at_limit]))
        self.assertEqual(len(tools.steps), 2)
        self.assertEqual((result.verdict.value, result.metrics), ("PASS", RECORDED_METRICS))


class TestMetrics(unittest.TestCase):
    def test_declared_metrics_are_read_once_each_and_nothing_else(self):
        from ecad_validation.adapters.hdl import declared_metrics, parse_metrics

        self.assertEqual(declared_metrics([HARNESS_REPORT]), (NINE, []))
        self.assertEqual(parse_metrics(RECORDED_STDOUT, NINE), (RECORDED_METRICS, {}))
        # Recorded: Icarus 13's $finish line and Verilator's report lines are not metrics.
        self.assertEqual(parse_metrics(VERILATOR_STDOUT, NINE), (RECORDED_METRICS, {}))
        # A name that is not declared is ignored, whatever stdout says; one that is
        # declared but not printed is named.
        eight = {name: value for name, value in RECORDED_METRICS.items() if name != "outputs_unknown_after_reset"}
        self.assertEqual(parse_metrics(RECORDED_STDOUT + "ECAD_METRIC foo 1\n", list(eight)), (eight, {}))
        self.assertEqual(parse_metrics(RECORDED_STDOUT, [*NINE, "absent"]), (RECORDED_METRICS, {"absent": "not reported"}))

        # Constructed declarations: only the two exact format strings declare a metric.
        for label, text, expected in (
            ("%d", '$display("ECAD_METRIC x %d", v);\n', ([], [])),
            ("two values", '$display("ECAD_METRIC x %0d %0d", v, w);\n', ([], [])),
            ("$write", '$write("ECAD_METRIC x %0d", v);\n', ([], [])),
            ("upper-case name", '$display("ECAD_METRIC Xname %0d", v);\n', ([], [])),
            ("%.17g", '$display("ECAD_METRIC x %.17g", v);\n', (["x"], [])),
            ("twice in one input", '$display("ECAD_METRIC x %0d", v);\n$display("ECAD_METRIC x %.17g", v);\n', ([], ["x"])),
        ):
            with self.subTest(label):
                self.assertEqual(declared_metrics([text]), expected)
        self.assertEqual(declared_metrics([HARNESS_REPORT, '$display("ECAD_METRIC tx_bit_cycles %0d", n);\n']),
                         ([name for name in NINE if name != "tx_bit_cycles"], ["tx_bit_cycles"]))

        # Constructed report lines.
        self.assertEqual(parse_metrics("ECAD_METRIC x 1\nECAD_METRIC x 1\n", ["x"]), ({}, {"x": "reported more than once"}))
        for token, problem in (("x", "not a number: x"), ("z", "not a number: z"), ("nan", "not a number: nan"),
                               ("-nan", "not a number: -nan"), ("inf", "not a number: inf"),
                               ("infinity", "not a number: infinity"), ("1_0", "not a number: 1_0"),
                               ("0x10", "not a number: 0x10"), ("1e999", "not finite"), ("-1e999", "not finite")):
            with self.subTest(token):
                self.assertEqual(parse_metrics(f"ECAD_METRIC v {token}\n", ["v"]), ({}, {"v": problem}))
        for token, value in (("-3", -3.0), ("+5", 5.0), (".5", 0.5), ("7.", 7.0), ("1.5e-3", 0.0015)):
            with self.subTest(token):
                self.assertEqual(parse_metrics(f"ECAD_METRIC v {token}\n", ["v"]), ({"v": value}, {}))
        for line in ("ECAD_METRIC  v 1", "ECAD_METRIC v  1", " ECAD_METRIC v 1", "ECAD_METRIC v 1 ",
                     "ECAD_METRIC v 1 2", "x.v:3: ECAD_METRIC v 1", "ECAD_METRICv 1", "ecad_metric v 1"):
            with self.subTest(line):
                self.assertEqual(parse_metrics(line + "\n", ["v"]), ({}, {"v": "not reported"}))

        # Through the adapter: a name declared in two inputs is named, and both inputs are compiled in order.
        second = '$display("ECAD_METRIC tx_bit_cycles %0d", n);\n'
        with tempfile.TemporaryDirectory() as directory, _Tools() as tools:
            result = _run(_product(Path(directory), [HARNESS_REPORT, second]))
        self.assertEqual(tools.steps[0]["argv"], [*COMPILE_ARGV, "derived/digital/x1.v"])
        self.assertEqual(result.metrics, {name: value for name, value in RECORDED_METRICS.items() if name != "tx_bit_cycles"})
        self.assertEqual(result.summary, "committed RTL testbench executed: 8 of 9 declared metrics read; "
                                         "tx_bit_cycles: declared more than once")

    def test_a_failed_run_reports_no_metrics(self):
        with tempfile.TemporaryDirectory() as directory, _Tools(executed=(1, RECORDED_STDOUT, "")):
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("FAIL", "completed", "RTL_TESTBENCH_FAILED"))
        self.assertEqual(result.metrics, {})
        self.assertEqual(result.summary, "committed RTL testbench exited 1, so no metric was read")
        self.assertEqual((result.command, result.tool_version, result.stdout), (RUN_ARGV, VERSION, RECORDED_STDOUT))


class TestProcessOutcomes(unittest.TestCase):
    def test_timeouts_and_crashes_name_the_step_that_failed(self):
        # Constructed partial outputs; TimeoutExpired carries bytes even under text=True.
        for tool, argv, step, calls in (("iverilog", COMPILE_ARGV, "RTL compilation", ["iverilog"]),
                                        ("vvp", RUN_ARGV, "RTL testbench execution", ["iverilog", "vvp"])):
            expired = subprocess.TimeoutExpired(cmd=argv, timeout=17, output=b"ECAD_METRIC tx_bit_cycles 434\n")
            with self.subTest(f"{tool} timed out"), tempfile.TemporaryDirectory() as directory, \
                    _Tools(raises={tool: expired}) as tools:
                result = _run(_product(Path(directory)))
                self.assertEqual(_outcome(result), ("INCONCLUSIVE", "timed_out", "RTL_EXECUTION_TIMED_OUT"))
                self.assertEqual((result.command, result.summary), (argv, f"{step} timed out"))
                self.assertIsInstance(result.stdout, str)
                self.assertEqual((result.stdout, result.metrics), ("ECAD_METRIC tx_bit_cycles 434\n", {}))
                self.assertEqual([s["tool"] for s in tools.steps], calls)
            with self.subTest(f"{tool} could not start"), tempfile.TemporaryDirectory() as directory, \
                    _Tools(raises={tool: PermissionError(13, "Permission denied")}):
                result = _run(_product(Path(directory)))
                self.assertEqual(_outcome(result), ("INCONCLUSIVE", "crashed", "RTL_EXECUTION_ERROR"))
                self.assertEqual((result.command, result.summary, result.stderr),
                                 (argv, f"{step}: the tool could not execute", "[Errno 13] Permission denied"))

    def test_unavailable_paths_keep_their_reason_codes(self):
        from ecad_validation.adapters.base import Capability

        with tempfile.TemporaryDirectory() as directory, _Tools(installed=()) as tools:
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "TOOL_NOT_INSTALLED"))
        self.assertEqual(result.summary, "Icarus Verilog execution capability is unavailable: TOOL_NOT_INSTALLED")
        self.assertEqual((tools.probes, tools.steps), ([], []))

        with tempfile.TemporaryDirectory() as directory, _Tools(installed=("iverilog",)) as tools:
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "VVP_NOT_INSTALLED"))
        self.assertEqual(result.summary, "Icarus Verilog execution capability is unavailable: VVP_NOT_INSTALLED")
        self.assertEqual(tools.steps, [])

        # The domain-adapter fixture's reason passes through unchanged.
        fixture = Capability(adapter="iverilog", available=False, reason="IVERILOG_NOT_INSTALLED")
        with tempfile.TemporaryDirectory() as directory, _Tools() as tools, \
                mock.patch("ecad_validation.adapters.hdl.probe_iverilog", return_value=fixture):
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "IVERILOG_NOT_INSTALLED"))
        self.assertEqual(tools.steps, [])

        with _Tools() as tools:
            result = _run([])
        self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "RTL_INPUT_MISSING"))
        self.assertEqual(tools.steps, [])

        # Constructed compiler message.
        with tempfile.TemporaryDirectory() as directory, _Tools(compiled=(2, "", "x.v:1: syntax error\n")) as tools:
            result = _run(_product(Path(directory)))
        self.assertEqual(_outcome(result), ("FAIL", "completed", "RTL_COMPILE_FAILED"))
        self.assertEqual((result.command, result.stderr, result.tool_version, result.metrics),
                         (COMPILE_ARGV, "x.v:1: syntax error\n", VERSION, {}))
        self.assertEqual([step["tool"] for step in tools.steps], ["iverilog"])

        # A tool that disappears between the probe and its step is not installed.
        for vanished, calls in (("iverilog", []), ("vvp", ["iverilog"])):
            tools = _Tools()

            def uninstall(cwd: Path, name: str = vanished, tools: _Tools = tools) -> None:
                (cwd / "simulation.vvp").write_bytes(PROGRAM_BYTES)
                tools.installed.discard(name)

            with self.subTest(vanished), tempfile.TemporaryDirectory() as directory, tools:
                if vanished == "iverilog":
                    fixed = Capability(adapter="iverilog", available=True, executable="/fake/iverilog", version=VERSION)
                    tools.installed.discard("iverilog")
                    with mock.patch("ecad_validation.adapters.hdl.probe_iverilog", return_value=fixed):
                        result = _run(_product(Path(directory)))
                else:
                    tools.program = uninstall
                    result = _run(_product(Path(directory)))
                self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", "TOOL_NOT_INSTALLED"))
                self.assertEqual([step["tool"] for step in tools.steps], calls)

    def test_a_version_probe_failure_gives_a_reason_the_receipt_accepts(self):
        """The raw probe reasons for an OSError and a signal are not reason codes;
        a receipt carrying one fails its schema and is not written."""
        from ecad_validation.adapters.hdl import _receipt_reason

        cases = (
            ("permission denied", {"side_effect": PermissionError(13, "Permission denied")},
             "VERSION_PROBE_ERROR", "VERSION_PROBE_ERROR:[Errno 13] Permission denied"),
            ("killed by a signal", {"return_value": subprocess.CompletedProcess(["iverilog", "-V"], -9, "", "")},
             "VERSION_PROBE_EXIT_NONZERO", "VERSION_PROBE_EXIT_-9"),
            ("non-zero exit", {"return_value": subprocess.CompletedProcess(["iverilog", "-V"], 1, "", "")},
             "VERSION_PROBE_EXIT_1", "VERSION_PROBE_EXIT_1"),
            ("timed out", {"side_effect": subprocess.TimeoutExpired(["iverilog", "-V"], 30)},
             "VERSION_PROBE_TIMED_OUT", "VERSION_PROBE_TIMED_OUT"),
        )
        for label, probe, code, raw in cases:
            with self.subTest(label), tempfile.TemporaryDirectory() as directory, \
                    mock.patch("ecad_validation.adapters.capabilities.shutil.which", return_value="/fake/iverilog"), \
                    mock.patch("ecad_validation.adapters.capabilities.subprocess.run", **probe), \
                    _only_the_probe():
                result = _run(_product(Path(directory)))
                self.assertEqual(_outcome(result), ("BLOCKED", "unavailable", code))
                self.assertRegex(result.reason_code, RECEIPT_REASON)
                self.assertEqual(result.summary, f"Icarus Verilog execution capability is unavailable: {raw}")
        for raw, code in (("VERSION_PROBE_ERROR:[Errno 8] Exec format error", "VERSION_PROBE_ERROR"),
                          ("VERSION_PROBE_EXIT_-11", "VERSION_PROBE_EXIT_NONZERO"), (None, "TOOL_NOT_INSTALLED"),
                          ("VVP_NOT_INSTALLED", "VVP_NOT_INSTALLED"), ("not a code: at all", "TOOL_UNAVAILABLE")):
            with self.subTest(raw=raw):
                self.assertEqual(_receipt_reason(raw), code)
                self.assertRegex(code, RECEIPT_REASON)

    def test_the_version_is_the_first_line_of_iverilog_V(self):
        from ecad_validation.adapters.capabilities import VERSION_PATTERNS
        from ecad_validation.adapters.hdl import HDLAdapter
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        self.assertNotIn("iverilog", VERSION_PATTERNS)
        for banner, version in ((ICARUS_13_BANNER, "Icarus Verilog version 13.0 (stable) (v13_0)"),
                                (ICARUS_11_FIRST_LINE, "Icarus Verilog version 11.0 (stable) ()")):
            with self.subTest(version), _Tools(banner=banner):
                capability = HDLAdapter().capability()
                self.assertEqual((capability.available, capability.executable, capability.version, capability.reason),
                                 (True, "/fake/iverilog", version, None))

        # A tool that ran but did not say which version it is cannot PASS.
        for banner, verdict, reason, tool, version in (
                (ICARUS_13_BANNER, "PASS", "GOLDEN_COMPARISON_PASSED", "iverilog", VERSION),
                ("", "BLOCKED", "TOOL_VERSION_UNAVAILABLE", "ecad-validator", "")):
            with self.subTest(banner=banner[:22]), tempfile.TemporaryDirectory() as directory, _Tools(banner=banner):
                [source] = _product(Path(directory))
                product = source.parents[2]
                (product / "validation" / "golden").mkdir(parents=True)
                (product / "validation" / "golden" / "cases.json").write_bytes(json.dumps({
                    "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json",
                    "contract_version": "1.0.0", "gate": "V3", "cases": [{
                        "id": "bit-cycles", "adapter": "iverilog", "domain": "system_design", "inputs": [SOURCE],
                        "requirement_ids": ["POLICY:V3-GOLDEN"],
                        "expected_metrics": {"tx_bit_cycles": {"value": 434, "absolute_tolerance": 0}}}]}).encode("utf-8"))
                [check] = execute_cases(product, GateLevel.V3, "golden")
                self.assertEqual((check.verdict.value, check.reason_code, check.tool_id, check.tool_version),
                                 (verdict, reason, tool, version))


class TestRunProcessCollection(unittest.TestCase):
    """ARCH-2, the output-copy half: run_process copies declared files out before deleting its workspace."""

    @staticmethod
    def _symlinks() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.symlink(__file__, os.path.join(directory, "probe"))
            except (OSError, NotImplementedError):
                return False
        return True

    def test_run_process_collects_only_declared_regular_files(self):
        from ecad_validation.adapters.process import ProcessRequest, run_process

        links = self._symlinks()
        script = (
            "import os, sys\n"
            "open('out.txt', 'w').write('result')\n"
            "open('undeclared.txt', 'w').write('not asked for')\n"
            "os.mkdir('folder')\n"
            "open('big.bin', 'wb').write(b'x' * 17)\n"
            "open('edge.bin', 'wb').write(b'y' * 16)\n"
            "if sys.argv[1] != '-': os.symlink(sys.argv[1], 'link.txt')\n"
            "sys.exit(3)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tool.py").write_text(script, encoding="utf-8")
            (root / "outside.txt").write_text("outside the workspace", encoding="utf-8")
            kept = root / "kept"
            kept.mkdir()
            with mock.patch("ecad_validation.adapters.process.MAX_COLLECT_BYTES", 16):
                result = run_process(ProcessRequest(
                    argv=[sys.executable, "tool.py", str(root / "outside.txt") if links else "-"], input_root=root,
                    input_files=[root / "tool.py"], collect=("out.txt", "folder", "big.bin", "edge.bin", "absent.txt",
                                                             "link.txt"), collect_into=kept))
            self.assertEqual((result.execution_status.value, result.returncode), ("completed", 3))
            self.assertEqual(result.collected, [kept / "out.txt", kept / "edge.bin"])
            self.assertEqual(sorted(path.name for path in kept.iterdir()), ["edge.bin", "out.txt"])
            self.assertEqual(((kept / "out.txt").read_text(encoding="utf-8"), (kept / "edge.bin").read_bytes()),
                             ("result", b"y" * 16))
            expected = {"folder": "not a regular file; not copied", "big.bin": "larger than 16 bytes; not copied",
                        "absent.txt": "not produced"}
            self.assertEqual({name: problem for name, problem in result.collect_problems.items() if name != "link.txt"},
                             expected)
            with self.subTest("a symbolic link"):
                if not links:
                    self.skipTest("this platform cannot create symbolic links")
                self.assertEqual(result.collect_problems["link.txt"], "a symbolic link; not copied")

    def test_a_file_swapped_for_a_link_after_its_check_is_copied_as_the_link(self):
        """Review HT-3: a name is checked with lstat, then copied with follow_symlinks=False, so a file replaced
        by a symbolic link between the two is copied as that link, never as the file it points at, and
        run_process refuses the copy as an input. The swap is simulated by letting the lstat check see a
        regular file where the workspace holds a link to a file outside it."""
        from types import SimpleNamespace

        from ecad_validation.adapters.process import ProcessRequest, run_process

        if not self._symlinks():
            self.skipTest("this platform cannot create symbolic links")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tool.py").write_text("import os, sys\nos.symlink(sys.argv[1], 'out.txt')\n", encoding="utf-8")
            outside = root / "outside.txt"
            outside.write_text("outside the workspace", encoding="utf-8")
            kept = root / "kept"
            kept.mkdir()
            regular = SimpleNamespace(S_ISLNK=lambda mode: False, S_ISREG=lambda mode: True)
            with mock.patch("ecad_validation.adapters.process.stat", regular):
                result = run_process(ProcessRequest(argv=[sys.executable, "tool.py", str(outside)], input_root=root,
                                                    input_files=[root / "tool.py"], collect=("out.txt",),
                                                    collect_into=kept))
            self.assertEqual((result.execution_status.value, result.collected, result.collect_problems),
                             ("completed", [kept / "out.txt"], {}))
            self.assertTrue((kept / "out.txt").is_symlink(), "the file the link points at was copied")
            self.assertEqual(os.readlink(kept / "out.txt"), str(outside))
            # The link leads out of the directory it was copied to, so run_process refuses it before its own
            # symbolic-link check.
            with self.assertRaisesRegex(ValueError, "adapter input escapes product root: .*out.txt"):
                run_process(ProcessRequest(argv=[sys.executable, "-c", "pass"], input_root=kept,
                                           input_files=[kept / "out.txt"]))

    def test_nothing_is_collected_from_a_run_that_timed_out_or_crashed(self):
        from ecad_validation.adapters.process import ProcessRequest, run_process

        for label, error in (("timed out", subprocess.TimeoutExpired(["tool"], 1, output=b"partial")),
                             ("crashed", PermissionError(13, "Permission denied"))):
            def partial(argv: List[str], error: BaseException = error, **kwargs: Any) -> None:
                (Path(kwargs["cwd"]) / "out.txt").write_text("partial", encoding="utf-8")
                raise error

            with self.subTest(label), tempfile.TemporaryDirectory() as directory, \
                    mock.patch("ecad_validation.adapters.process.shutil.which", return_value="/fake/tool"), \
                    mock.patch("ecad_validation.adapters.process.subprocess.run", side_effect=partial):
                kept = Path(directory)
                result = run_process(ProcessRequest(argv=["tool"], input_root=kept, input_files=[],
                                                    collect=("out.txt",), collect_into=kept))
                self.assertEqual(result.execution_status.value, label.replace(" ", "_"))
                self.assertEqual((result.collected, result.collect_problems), ([], {}))
                self.assertEqual(list(kept.iterdir()), [])
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(ProcessRequest(argv=["ecad-tool-that-does-not-exist"], input_root=Path(directory),
                                                input_files=[], collect=("out.txt",), collect_into=Path(directory)))
        self.assertEqual((result.execution_status.value, result.collected, result.collect_problems), ("unavailable", [], {}))

    def test_a_collect_name_that_is_not_one_plain_file_name_is_refused_before_running(self):
        from ecad_validation.adapters.process import ProcessRequest, run_process

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch("ecad_validation.adapters.process.shutil.which", return_value="/fake/tool"), \
                mock.patch("ecad_validation.adapters.process.subprocess.run", side_effect=AssertionError("ran")):
            root = Path(directory)
            for name in ("", ".", "..", "a/b", "a\\b", "/abs", "C:x", "C:\\x", "nul\0byte"):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "not one plain file name"):
                    run_process(ProcessRequest(argv=["tool"], input_root=root, input_files=[], collect=(name,),
                                               collect_into=root))
            for label, into in (("no collect_into", None), ("not a directory", root / "missing")):
                with self.subTest(label), self.assertRaisesRegex(ValueError, "collect needs collect_into"):
                    run_process(ProcessRequest(argv=["tool"], input_root=root, input_files=[], collect=("out.txt",),
                                               collect_into=into))

    def test_a_request_that_collects_nothing_behaves_as_before(self):
        from ecad_validation.adapters.process import ProcessRequest, run_process

        request = ProcessRequest(argv=[sys.executable, "-c", "open('out.txt', 'w').write('result')"],
                                 input_root=Path("."), input_files=[])
        self.assertEqual((request.collect, request.collect_into, request.stdin_devnull), ((), None, False))
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(ProcessRequest(argv=request.argv, input_root=Path(directory), input_files=[]))
        self.assertEqual((result.execution_status.value, result.returncode), ("completed", 0))
        self.assertEqual((result.collected, result.collect_problems, result.outputs), ([], {}, [Path("out.txt")]))

    def test_only_a_request_that_asks_for_it_gets_an_empty_stdin(self):
        from ecad_validation.adapters.process import ProcessRequest, run_process

        for flag, expected in ((True, subprocess.DEVNULL), (False, None)):
            completed = subprocess.CompletedProcess(["/fake/tool"], 0, stdout="", stderr="")
            with self.subTest(stdin_devnull=flag), tempfile.TemporaryDirectory() as directory, \
                    mock.patch("ecad_validation.adapters.process.shutil.which", return_value="/fake/tool"), \
                    mock.patch("ecad_validation.adapters.process.subprocess.run", return_value=completed) as run:
                run_process(ProcessRequest(argv=["tool"], input_root=Path(directory), input_files=[], stdin_devnull=flag))
                self.assertIs(run.call_args.kwargs["stdin"], expected)


class TestDocumentationExamples(unittest.TestCase):
    """QUALITY.md: every public function's example must be one that was actually run."""

    def test_examples_in_the_hdl_and_process_modules(self):
        import doctest
        import importlib

        for name in ("hdl", "process"):
            with self.subTest(name):
                module = importlib.import_module(f"ecad_validation.adapters.{name}")
                result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
                self.assertGreater(result.attempted, 0, f"{name} has no runnable examples")
                self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
