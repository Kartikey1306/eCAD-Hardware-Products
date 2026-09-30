"""Failure semantics for external validation tool adapters."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ecad_validation.adapters.base import AdapterRequest  # noqa: E402
from ecad_validation.adapters import hdl  # noqa: E402
from ecad_validation.adapters.process import (  # noqa: E402
    ProcessRequest,
    captured_text,
    run_process,
)
from ecad_validation.adapters.python_control import PythonControlAdapter  # noqa: E402
from ecad_validation.models import ExecutionStatus, Verdict  # noqa: E402


class TestProcessRunner(unittest.TestCase):
    def test_missing_executable_is_unavailable_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_process(
                ProcessRequest(
                    argv=["ecad-tool-that-does-not-exist"],
                    input_root=root,
                    input_files=[],
                )
            )
        self.assertEqual(result.execution_status, ExecutionStatus.UNAVAILABLE)
        self.assertEqual(result.reason_code, "TOOL_NOT_INSTALLED")
        self.assertIsNone(result.returncode)

    def test_timeout_is_not_reported_as_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "slow.py"
            script.write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
            result = run_process(
                ProcessRequest(
                    argv=[sys.executable, "slow.py"],
                    input_root=root,
                    input_files=[script],
                    timeout_seconds=1,
                )
            )
        self.assertEqual(result.execution_status, ExecutionStatus.TIMED_OUT)
        self.assertEqual(result.reason_code, "TOOL_TIMED_OUT")

    def test_timeout_after_output_is_reported_not_raised(self):
        """A tool that prints before hanging must still time out cleanly.

        ``TimeoutExpired.stdout`` is bytes even under ``text=True``, so the
        silent script in the test above never exercised the decode path. Every
        real solver prints a banner before it hangs.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "noisy_slow.py"
            script.write_text(
                "import sys, time\n"
                "print('transient analysis started')\n"
                "sys.stdout.flush()\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            result = run_process(
                ProcessRequest(
                    argv=[sys.executable, "noisy_slow.py"],
                    input_root=root,
                    input_files=[script],
                    timeout_seconds=1,
                )
            )
        self.assertEqual(result.execution_status, ExecutionStatus.TIMED_OUT)
        self.assertEqual(result.reason_code, "TOOL_TIMED_OUT")
        self.assertIsInstance(result.stdout, str)
        self.assertIn("transient analysis started", result.stdout)

    def test_captured_text_decodes_bytes_and_none(self):
        self.assertEqual(captured_text(b"banner\n"), "banner\n")
        self.assertEqual(captured_text("banner\n"), "banner\n")
        self.assertEqual(captured_text(None), "")
        self.assertIsInstance(captured_text(b"\xff\xfe"), str)


class TestHDLAdapterTimeout(unittest.TestCase):
    def test_timeout_output_is_text_not_bytes(self):
        """vvp prints a VCD banner before a testbench with no $finish hangs."""
        capability = hdl.Capability(
            adapter="iverilog", available=True, executable="iverilog", version="12.0"
        )
        expired = subprocess.TimeoutExpired(
            cmd=["iverilog"], timeout=1, output=b"VCD info: dumpfile waves.vcd opened\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tb.v"
            source.write_text("module tb; endmodule\n", encoding="utf-8")
            # Both Icarus steps run through run_process, so the boundary is its
            # subprocess.run, and its shutil.which must find the compiler.
            with mock.patch.object(hdl.HDLAdapter, "capability", return_value=capability), \
                 mock.patch("ecad_validation.adapters.process.shutil.which", return_value="/fake/iverilog"), \
                 mock.patch("ecad_validation.adapters.process.subprocess.run", side_effect=expired):
                result = hdl.HDLAdapter().run(
                    AdapterRequest(
                        case_id="hanging-testbench",
                        product_root=root,
                        input_files=[source],
                        timeout_seconds=1,
                    )
                )
        self.assertEqual(result.execution_status, ExecutionStatus.TIMED_OUT)
        self.assertEqual(result.reason_code, "RTL_EXECUTION_TIMED_OUT")
        self.assertIsInstance(result.stdout, str)
        self.assertIn("VCD info", result.stdout)


class TestPythonControlAdapter(unittest.TestCase):
    def test_json_metrics_are_required_for_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "model.py"
            script.write_text('print("not metrics")\n', encoding="utf-8")
            result = PythonControlAdapter().run(
                AdapterRequest(
                    case_id="missing-metrics",
                    product_root=root,
                    input_files=[script],
                )
            )
        self.assertEqual(result.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(result.reason_code, "METRICS_JSON_INVALID")

    def test_deterministic_json_metrics_can_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "model.py"
            script.write_text('print("{\\"current_a\\": 1.25}")\n', encoding="utf-8")
            result = PythonControlAdapter().run(
                AdapterRequest(
                    case_id="golden-current",
                    product_root=root,
                    input_files=[script],
                    seed=7,
                )
            )
        self.assertEqual(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.metrics, {"current_a": 1.25})


if __name__ == "__main__":
    unittest.main()
