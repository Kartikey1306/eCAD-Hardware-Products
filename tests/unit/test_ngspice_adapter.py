"""The ngspice adapter: batch invocation, `.meas` capture, version and probe reasons.

Nothing here runs ngspice. The process boundary (run_process, or
subprocess.run under the version probe) is replaced by recorded output, so
these tests run on every machine. The recorded texts below are byte-for-byte
copies of what ngspice-47 printed on macOS arm64 on 2026-09-27, with each
deck they came from:

- RECORDED_DECK / RECORDED_STDOUT: the servo_supply_001 deck as committed on
  2026-09-27, with nine measurements (exit 0, empty stderr, stdout identical
  over two runs). The committed deck has since gained a tenth,
  startup_peak_current_a; test_electrical_domain.py follows it, and these
  recordings stay what 47, 36 and 44.2 printed for the nine;
- FAILING_DECK / FAILING_STDOUT / FAILING_STDERR: a measurement outside the
  simulated interval, which ngspice reports on stderr while still exiting 0;
- DUPLICATE_DECK / DUPLICATE_STDOUT: a name declared twice, printed twice;
- BANNER: the output of `ngspice --version`.

Two other versions, as the logs of arm64 containers recorded them on the same
day: ngspice 36+ds-1ubuntu0.1 from the apt of ubuntu:22.04 (the release the
CI runner uses) and 44.2+ds-1 from that of python:3.12-slim (Debian 13). For
RECORDED_DECK they give NGSPICE_36_STDOUT with NGSPICE_36_STDERR, and
NGSPICE_44_STDOUT with an empty stderr (each exit 0, stdout identical over two
runs); BANNER_36 and BANNER_44 are the first three lines of their banners.

A value written inline in a test (a `nan`, a `1_0`, a kicad-cli version) is
constructed for that test and says so. Expected values are typed by hand from
these texts, never obtained by calling the code under test.
"""

from __future__ import annotations

import json
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

# ngspice-47, macOS arm64, 2026-09-27.
RECORDED_DECK = (
    "* servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "* written by ecad_model.domains.electrical 1.0.0 from derived/engineering_model.json; regenerate with build, never edit\n"
    "V_IN n_in 0 PWL(0.0 0.0 0.0001 48.0)\n"
    "R_F1 n_in n_f 0.02\n"
    "R_PRE n_f n_bus 10.0\n"
    "S_BYP n_f n_bus n_byp 0 SW_BYP\n"
    "V_BYP n_byp 0 PWL(0.0 0.0 0.03 0.0 0.030001 5.0)\n"
    "C_BULK n_bus n_esr 0.00047\n"
    "R_ESR n_esr 0 0.05\n"
    "I_LOAD n_bus 0 PWL(0.0 0.0 0.04 0.0 0.0401 4.16667)\n"
    "S_FLT n_bus 0 n_fc 0 SW_FLT\n"
    "V_FLT n_fc 0 PWL(0.0 0.0 0.1 0.0 0.100001 5.0)\n"
    ".model SW_BYP SW(RON=0.01 ROFF=1000000000.0 VT=2.5 VH=0.0)\n"
    ".model SW_FLT SW(RON=0.1 ROFF=1000000000.0 VT=2.5 VH=0.0)\n"
    ".options noacct\n"
    ".tran 1e-06 0.11 0.0 1e-06\n"
    ".meas tran inrush_peak_current_a MAX par('-i(V_IN)') FROM=0.0 TO=0.03\n"
    ".meas tran inrush_i2t_a2s INTEG par('i(V_IN)*i(V_IN)') FROM=0.0 TO=0.03\n"
    ".meas tran bus_charge_time_s WHEN v(n_bus)=43.2 RISE=1\n"
    ".meas tran bus_voltage_at_bypass_v FIND v(n_bus) AT=0.03\n"
    ".meas tran bus_peak_voltage_v MAX v(n_bus) FROM=0.0 TO=0.1\n"
    ".meas tran steady_bus_voltage_v FIND v(n_bus) AT=0.1\n"
    ".meas tran steady_input_current_a FIND par('-i(V_IN)') AT=0.1\n"
    ".meas tran steady_fuse_power_w FIND par('(v(n_in)-v(n_f))*(-i(V_IN))') AT=0.1\n"
    ".meas tran fault_input_current_a FIND par('-i(V_IN)') AT=0.11\n"
    ".end\n"
)
RECORDED_DECK_SHA256 = "2840fc040b30a626891a347bb447a242f81ce97cd23aa415a6e32c7ef4451d30"
# ngspice-47, macOS arm64, 2026-09-27: `ngspice -b` on RECORDED_DECK.
RECORDED_STDOUT = (
    "\n"
    "Note: No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * servo_supply_001: 48 v servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "Using SPARSE 1.3 as Direct Linear Solver\n"
    "\n"
    "No. of Data Rows : 110053\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "inrush_peak_current_a=  4.71663e+00 at=  1.00000e-04\n"
    "inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02\n"
    "bus_charge_time_s   =   1.09244e-02\n"
    "bus_voltage_at_bypass_v=  4.79147e+01\n"
    "bus_peak_voltage_v  =  4.80000e+01 at=  4.00000e-02\n"
    "steady_bus_voltage_v=  4.78750e+01\n"
    "steady_input_current_a=  4.16667e+00\n"
    "steady_fuse_power_w =  3.47223e-01\n"
    "fault_input_current_a=  3.72465e+02\n"
    "\n"
    "\n"
)
# The nine values, typed from the lines above.
RECORDED_METRICS = {
    "inrush_peak_current_a": 4.71663,
    "inrush_i2t_a2s": 0.0533906,
    "bus_charge_time_s": 0.0109244,
    "bus_voltage_at_bypass_v": 47.9147,
    "bus_peak_voltage_v": 48.0,
    "steady_bus_voltage_v": 47.875,
    "steady_input_current_a": 4.16667,
    "steady_fuse_power_w": 0.347223,
    "fault_input_current_a": 372.465,
}
# ngspice-47, macOS arm64, 2026-09-27.
FAILING_DECK = (
    "* f\n"
    "V1 a 0 DC 1\n"
    "R1 a 0 1\n"
    ".tran 1u 10u\n"
    ".meas tran late FIND v(a) AT=50u\n"
    ".meas tran ok FIND v(a) AT=5u\n"
    ".end\n"
)
FAILING_STDOUT = (
    "\n"
    "Note: No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * f\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "Using SPARSE 1.3 as Direct Linear Solver\n"
    "\n"
    "Initial Transient Solution\n"
    "--------------------------\n"
    "\n"
    "Node                                   Voltage\n"
    "----                                   -------\n"
    "a                                            1\n"
    "v1#branch                                   -1\n"
    "\n"
    "\n"
    "No. of Data Rows : 59\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "ok                  =  1.00000e+00\n"
    "\n"
    "\n"
    "Total analysis time (seconds) = 0.000352\n"
    "\n"
    "Total elapsed time (seconds) = 0.003 \n"
    "\n"
    "Total DRAM available = 16384.000 MB.\n"
    "DRAM currently available = 3001.312 MB.\n"
    "Maximum ngspice program size =    9.844 MB.\n"
    "Current ngspice program size =    9.844 MB.\n"
    "\n"
)
FAILING_STDERR = (
    "\n"
    "Error: measure  late  find(AT) : out of interval\n"
    " .meas tran late find v(a) at=50u failed!\n"
    "\n"
)
# ngspice-47, macOS arm64, 2026-09-27.
DUPLICATE_DECK = (
    "* d\n"
    "V1 a 0 DC 1\n"
    "R1 a 0 1\n"
    ".tran 1u 10u\n"
    ".meas tran dup FIND v(a) AT=5u\n"
    ".meas tran dup FIND v(a) AT=6u\n"
    ".end\n"
)
DUPLICATE_STDOUT = (
    "\n"
    "Note: No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * d\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "Using SPARSE 1.3 as Direct Linear Solver\n"
    "\n"
    "Initial Transient Solution\n"
    "--------------------------\n"
    "\n"
    "Node                                   Voltage\n"
    "----                                   -------\n"
    "a                                            1\n"
    "v1#branch                                   -1\n"
    "\n"
    "\n"
    "No. of Data Rows : 59\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "dup                 =  1.00000e+00\n"
    "dup                 =  1.00000e+00\n"
    "\n"
    "\n"
    "Total analysis time (seconds) = 0.000316\n"
    "\n"
    "Total elapsed time (seconds) = 0.003 \n"
    "\n"
    "Total DRAM available = 16384.000 MB.\n"
    "DRAM currently available = 3050.891 MB.\n"
    "Maximum ngspice program size =    9.812 MB.\n"
    "Current ngspice program size =    9.812 MB.\n"
    "\n"
)
# ngspice-47, macOS arm64, 2026-09-27: `ngspice --version`, exit 0, empty stderr.
BANNER = (
    "******\n"
    "** ngspice-47 : Circuit level simulation program\n"
    "** Compiled with KLU Direct Linear Solver\n"
    "** The U. C. Berkeley CAD Group\n"
    "** Copyright 1985-1994, Regents of the University of California.\n"
    "** Copyright 2001-2026, The ngspice team.\n"
    "** Please get your ngspice manual from https://ngspice.sourceforge.io/docs.html\n"
    "** Please file your bug-reports at http://ngspice.sourceforge.net/bugrep.html\n"
    "******\n"
)
# ngspice 36+ds-1ubuntu0.1, ubuntu:22.04 arm64, 2026-09-27: `ngspice -b` on RECORDED_DECK.
NGSPICE_36_STDOUT = (
    "\n"
    "No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * servo_supply_001: 48 v servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "\n"
    "No. of Data Rows : 110053\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "inrush_peak_current_a=  4.716630e+00 at=  1.000000e-04\n"
    "inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02\n"
    "bus_charge_time_s   =   1.09244e-02\n"
    "bus_voltage_at_bypass_v=  4.791472e+01\n"
    "bus_peak_voltage_v  =  4.800000e+01 at=  4.000000e-02\n"
    "steady_bus_voltage_v=  4.787504e+01\n"
    "steady_input_current_a=  4.166670e+00\n"
    "steady_fuse_power_w =  3.472228e-01\n"
    "fault_input_current_a=  3.724645e+02\n"
    "\n"
    "\n"
)
NGSPICE_36_STDERR = (
    "Warning: i_load: no DC value, transient time 0 value used\n"
    "Warning: v_flt: no DC value, transient time 0 value used\n"
    "Warning: v_byp: no DC value, transient time 0 value used\n"
    "Warning: v_in: no DC value, transient time 0 value used\n"
)
# ngspice 44.2+ds-1, python:3.12-slim (Debian 13) arm64, 2026-09-27: `ngspice -b` on RECORDED_DECK.
NGSPICE_44_STDOUT = (
    "\n"
    "Note: No compatibility mode selected!\n"
    "\n"
    "\n"
    "Circuit: * servo_supply_001: 48 v servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load\n"
    "\n"
    "Doing analysis at TEMP = 27.000000 and TNOM = 27.000000\n"
    "\n"
    "Using SPARSE 1.3 as Direct Linear Solver\n"
    "\n"
    "No. of Data Rows : 110053\n"
    "\n"
    "  Measurements for Transient Analysis\n"
    "\n"
    "inrush_peak_current_a=  4.716630e+00 at=  1.000000e-04\n"
    "inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02\n"
    "bus_charge_time_s   =   1.09244e-02\n"
    "bus_voltage_at_bypass_v=  4.791472e+01\n"
    "bus_peak_voltage_v  =  4.800000e+01 at=  4.000000e-02\n"
    "steady_bus_voltage_v=  4.787504e+01\n"
    "steady_input_current_a=  4.166670e+00\n"
    "steady_fuse_power_w =  3.472228e-01\n"
    "fault_input_current_a=  3.724645e+02\n"
    "\n"
    "\n"
)
# The nine values both print, typed from the lines above: seven of them to
# seven significant digits, where ngspice-47 prints six.
SEVEN_DIGIT_METRICS = {
    "inrush_peak_current_a": 4.71663,
    "inrush_i2t_a2s": 0.0533906,
    "bus_charge_time_s": 0.0109244,
    "bus_voltage_at_bypass_v": 47.91472,
    "bus_peak_voltage_v": 48.0,
    "steady_bus_voltage_v": 47.87504,
    "steady_input_current_a": 4.16667,
    "steady_fuse_power_w": 0.3472228,
    "fault_input_current_a": 372.4645,
}
# The first three lines of `ngspice --version`: 36+ds-1ubuntu0.1 and 44.2+ds-1, as above.
BANNER_36 = (
    "******\n"
    "** ngspice-36 : Circuit level simulation program\n"
    "** The U. C. Berkeley CAD Group\n"
)
BANNER_44 = (
    "******\n"
    "** ngspice-44.2 : Circuit level simulation program\n"
    "** Compiled with KLU Direct Linear Solver\n"
)
# Icarus Verilog 13.0 and Verilator 5.052, macOS arm64, 2026-09-27: the first
# lines of `iverilog -V` and the whole of `verilator --version`, both exit 0.
ICARUS_BANNER = (
    "Icarus Verilog version 13.0 (stable) (v13_0)\n"
    "\n"
    "Copyright (c) 2000-2026 Stephen Williams (steve@icarus.com)\n"
)
VERILATOR_BANNER = "Verilator 5.052 2026-09-05 rev vUNKNOWN-built20260905\n"

DECK_PATH = "derived/electrical/x.cir"
NINE = list(RECORDED_METRICS)
# The receipt schema's reason_code rule, read from the contract, not from the adapter.
RECEIPT_REASON = re.compile(json.loads(
    (REPO_ROOT / "schemas" / "hardware-validation" / "v1" / "validation-receipt.schema.json").read_text(encoding="utf-8")
)["definitions"]["checkResult"]["properties"]["reason_code"]["pattern"])


def _product(root: Path, deck: str, cases: Sequence[Dict[str, Any]] = (), gate: str = "V3") -> Path:
    """A product directory holding one deck and, when given, one case document."""
    product = root / "product"
    (product / "derived" / "electrical").mkdir(parents=True)
    (product / DECK_PATH).write_bytes(deck.encode("utf-8"))
    if cases:
        directory = "golden" if gate == "V3" else "corners"
        (product / "validation" / directory).mkdir(parents=True)
        (product / "validation" / directory / "cases.json").write_bytes(json.dumps({
            "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json",
            "contract_version": "1.0.0", "gate": gate, "cases": list(cases)}).encode("utf-8"))
    return product


def _golden(case_id: str, expected: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    return {"id": case_id, "adapter": "ngspice", "domain": "system_design", "inputs": [DECK_PATH],
            "requirement_ids": ["POLICY:V3-GOLDEN"], "expected_metrics": expected}


def _installed(version: Optional[str] = "47"):
    """An installed ngspice, as the adapter's capability probe reports it."""
    from ecad_validation.adapters.base import Capability

    return mock.patch("ecad_validation.adapters.ngspice.probe_executable", return_value=Capability(
        adapter="ngspice", available=True, executable="/usr/bin/ngspice", version=version))


def _process(stdout: str = "", stderr: str = "", returncode: Optional[int] = 0, status: Optional[str] = None,
             reason: Optional[str] = None):
    """run_process replaced by one recorded outcome; the mock keeps the request it was given."""
    from ecad_validation.adapters.process import ProcessResult
    from ecad_validation.models import ExecutionStatus

    execution = ExecutionStatus(status) if status else ExecutionStatus.COMPLETED
    code = reason or ("TOOL_EXITED_ZERO" if returncode == 0 else "TOOL_EXITED_NONZERO")

    def completed(request):
        return ProcessResult(execution_status=execution, reason_code=code, argv=list(request.argv),
                             returncode=returncode, stdout=stdout, stderr=stderr)

    return mock.patch("ecad_validation.adapters.ngspice.run_process", side_effect=completed)


def _run(product: Path, arguments: Sequence[str] = ()):
    from ecad_validation.adapters.base import AdapterRequest
    from ecad_validation.adapters.ngspice import NgspiceAdapter

    return NgspiceAdapter().run(AdapterRequest(case_id="case", product_root=product,
                                               input_files=[product / DECK_PATH], arguments=list(arguments)))


def _probe(stdout: str = "", stderr: str = "", returncode: int = 0, raises: Optional[BaseException] = None,
           executable: Optional[str] = "/usr/bin/tool"):
    """The version probe's process boundary: which() finds the tool, and it prints what it is given."""
    which = mock.patch("ecad_validation.adapters.capabilities.shutil.which", return_value=executable)
    run = mock.patch("ecad_validation.adapters.capabilities.subprocess.run",
                     side_effect=raises if raises is not None else
                     (lambda argv, **_: subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)))
    return which, run


class TestInvocation(unittest.TestCase):
    def test_ngspice_runs_in_batch_mode_with_no_log_rawfile_or_case_arguments(self):
        """-r disables .meas in batch mode and -o sends the results to a deleted log;
        a case's arguments would let a case document choose either."""
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(RECORDED_STDOUT) as run_process:
            product = _product(Path(directory), RECORDED_DECK)
            result = _run(product, ["-r", "ngspice.raw", "-o", "ngspice.log", "-i"])
        [call] = run_process.call_args_list
        request = call.args[0]
        self.assertEqual(request.argv, ["/usr/bin/ngspice", "-b", "derived/electrical/x.cir"])
        self.assertEqual((request.input_root, request.input_files), (product, [product / DECK_PATH]))
        self.assertEqual(result.command, ["/usr/bin/ngspice", "-b", "derived/electrical/x.cir"])
        self.assertEqual(result.verdict.value, "PASS")


class TestMeasurements(unittest.TestCase):
    def test_measurements_are_read_as_ngspice_47_prints_them(self):
        import hashlib

        from ecad_validation.adapters.ngspice import declared_measurements, parse_measurements

        self.assertEqual(hashlib.sha256(RECORDED_DECK.encode()).hexdigest(), RECORDED_DECK_SHA256)
        self.assertEqual(declared_measurements(RECORDED_DECK), (NINE, []))
        self.assertEqual(parse_measurements(RECORDED_STDOUT, "", NINE), (RECORDED_METRICS, {}))
        for label, line, name, value in (
            ("unpadded name, at=", "inrush_peak_current_a=  4.71663e+00 at=  1.00000e-04", "inrush_peak_current_a", 4.71663),
            ("padded name, from= to=", "inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02",
             "inrush_i2t_a2s", 0.0533906),
            ("padded name, no window", "bus_charge_time_s   =   1.09244e-02", "bus_charge_time_s", 0.0109244),
            ("padded name, at=", "bus_peak_voltage_v  =  4.80000e+01 at=  4.00000e-02", "bus_peak_voltage_v", 48.0),
        ):
            with self.subTest(label):
                self.assertEqual(parse_measurements(line + "\n", "", [name]), ({name: value}, {}))
        # "TEMP = 27.000000", the node table and the title are not measurements,
        # even for a deck that declared those names.
        names = ["doing", "temp", "tnom", "no", "circuit", "note", "a", "v1", "total"]
        self.assertEqual(parse_measurements(RECORDED_STDOUT + FAILING_STDOUT, "", names),
                         ({}, {name: "not reported" for name in names}))

        with tempfile.TemporaryDirectory() as directory, _installed(), _process(RECORDED_STDOUT):
            result = _run(_product(Path(directory), RECORDED_DECK))
        self.assertEqual((result.verdict.value, result.reason_code), ("PASS", "TOOL_EXITED_ZERO"))
        self.assertEqual(result.metrics, RECORDED_METRICS)
        self.assertEqual(result.summary, "ngspice batch run completed: 9 of 9 declared measurements read")
        self.assertEqual((result.stdout, result.stderr, result.tool_version), (RECORDED_STDOUT, "", "47"))

    def test_measurements_are_read_as_ngspice_36_and_44_print_them(self):
        """Seven significant digits, other header lines, and on 36 a warning on
        stderr for each PWL source, which is not a failed measurement."""
        from ecad_validation.adapters.ngspice import parse_measurements
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        for version, stdout, stderr in (("36", NGSPICE_36_STDOUT, NGSPICE_36_STDERR), ("44.2", NGSPICE_44_STDOUT, "")):
            with self.subTest(version):
                self.assertEqual(parse_measurements(stdout, stderr, NINE), (SEVEN_DIGIT_METRICS, {}))
                with tempfile.TemporaryDirectory() as directory, _installed(version), _process(stdout, stderr):
                    # 47.91472 to within 1e-6: a reader that kept six digits (47.9147) fails it.
                    product = _product(Path(directory), RECORDED_DECK, [_golden(
                        "at-bypass", {"bus_voltage_at_bypass_v": {"value": 47.91472, "absolute_tolerance": 1e-6}})])
                    result = _run(product)
                    [check] = execute_cases(product, GateLevel.V3, "golden")
                self.assertEqual((result.verdict.value, result.reason_code, result.metrics),
                                 ("PASS", "TOOL_EXITED_ZERO", SEVEN_DIGIT_METRICS))
                self.assertEqual(result.summary, "ngspice batch run completed: 9 of 9 declared measurements read")
                self.assertEqual((result.stderr, result.tool_version), (stderr, version))
                self.assertEqual((check.verdict.value, check.reason_code, check.tool_version),
                                 ("PASS", "GOLDEN_COMPARISON_PASSED", version))
                # The case engine keeps what ngspice said on stderr among the check's findings.
                self.assertEqual(stderr in check.findings, bool(stderr))

    def test_a_declared_measurement_that_failed_is_absent_and_named(self):
        from ecad_validation.adapters.ngspice import declared_measurements, parse_measurements
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        self.assertEqual(declared_measurements(FAILING_DECK), (["late", "ok"], []))
        self.assertEqual(parse_measurements(FAILING_STDOUT, FAILING_STDERR, ["late", "ok"]),
                         ({"ok": 1.0}, {"late": "failed: .meas tran late find v(a) at=50u failed!"}))
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(FAILING_STDOUT, FAILING_STDERR):
            product = _product(Path(directory), FAILING_DECK, [
                _golden("needs-late", {"late": {"value": 1.0, "absolute_tolerance": 0.001}}),
                _golden("needs-ok", {"ok": {"value": 1.0, "absolute_tolerance": 0.001}}),
            ])
            result = _run(product)
            late, ok = execute_cases(product, GateLevel.V3, "golden")
        self.assertEqual((result.verdict.value, result.reason_code), ("PASS", "TOOL_EXITED_ZERO"))
        self.assertEqual(result.metrics, {"ok": 1.0})
        self.assertEqual(result.summary, "ngspice batch run completed: 1 of 2 declared measurements read; "
                                         "late: failed: .meas tran late find v(a) at=50u failed!")
        # The comparator, not the adapter, decides what the missing metric means.
        self.assertEqual((late.verdict.value, late.reason_code), ("INCONCLUSIVE", "GOLDEN_METRICS_INCONCLUSIVE"))
        self.assertIn("late: adapter produced no finite numeric metric", late.findings)
        self.assertIn(FAILING_STDERR, late.findings)
        self.assertEqual((ok.verdict.value, ok.reason_code), ("PASS", "GOLDEN_COMPARISON_PASSED"))

    def test_duplicated_non_numeric_or_non_finite_values_are_not_metrics(self):
        from ecad_validation.adapters.ngspice import parse_measurements
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        # Recorded: ngspice prints a name declared twice twice.
        self.assertEqual(parse_measurements(DUPLICATE_STDOUT, "", ["dup"]), ({}, {"dup": "reported more than once"}))
        # Recorded: a failed measurement is never read as a value.
        self.assertEqual(parse_measurements(FAILING_STDOUT, FAILING_STDERR, ["late"]),
                         ({}, {"late": "failed: .meas tran late find v(a) at=50u failed!"}))
        # Constructed: the recorded line format carrying values Python's float()
        # would accept but a SPICE number is not, or that are not finite.
        for token, problem in (("failed", "not a number: failed"), ("nan", "not a number: nan"),
                               ("-nan", "not a number: -nan"), ("inf", "not a number: inf"),
                               ("infinity", "not a number: infinity"), ("1_0", "not a number: 1_0"),
                               ("0x1p3", "not a number: 0x1p3"), ("1e999", "not finite"), ("-1e999", "not finite")):
            with self.subTest(token):
                self.assertEqual(parse_measurements(f"x                   =  {token}\n", "", ["x"]), ({}, {"x": problem}))

        deck = ("* constructed\n.tran 1u 10u\n.meas tran big FIND v(a) AT=5u\n.meas tran odd FIND v(a) AT=6u\n"
                ".meas tran fine FIND v(a) AT=7u\n.end\n")
        stdout = "big                 =  1e999\nodd                 =  1_0\nfine                =  2.50000e+00\n"
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(stdout):
            product = _product(Path(directory), deck, [
                _golden("needs-big", {"big": {"value": 1.0, "absolute_tolerance": 0.001}}),
                _golden("needs-odd", {"odd": {"value": 10.0, "absolute_tolerance": 0.001}}),
            ])
            big, odd = execute_cases(product, GateLevel.V3, "golden")
        for check, name in ((big, "big"), (odd, "odd")):
            with self.subTest(name):
                self.assertEqual((check.verdict.value, check.reason_code), ("INCONCLUSIVE", "GOLDEN_METRICS_INCONCLUSIVE"))
                self.assertEqual(check.metrics, {"fine": 2.5})
                # The execution record was written: its bytes are the evidence the check cites.
                [(path, record)] = check.generated_evidence.items()
                self.assertTrue(path.startswith("generated/"))
                self.assertEqual(json.loads(record)["metrics"], {"fine": 2.5})

    def test_the_summary_names_at_most_ten_unread_measurements(self):
        """Twelve declared names, none reported: the summary names the first ten,
        in deck order, and still counts all twelve."""
        names = [f"m{n:02d}" for n in range(1, 13)]
        deck = "* twelve\n" + "".join(f".meas tran {name} FIND v(a) AT=1u\n" for name in names) + ".end\n"
        with tempfile.TemporaryDirectory() as directory, _installed(), _process("no measurement here\n"):
            result = _run(_product(Path(directory), deck))
        self.assertEqual((result.verdict.value, result.metrics), ("PASS", {}))
        self.assertEqual(result.summary, "ngspice batch run completed: 0 of 12 declared measurements read; "
                         + "; ".join(f"{name}: not reported" for name in names[:10]))

    def test_names_the_deck_does_not_declare_are_ignored(self):
        from ecad_validation.adapters.ngspice import declared_measurements, parse_measurements

        # Constructed: a line of the recorded format for a name the deck never declared.
        self.assertEqual(parse_measurements(RECORDED_STDOUT + "foo = 1.0\n", "", NINE), (RECORDED_METRICS, {}))
        # Recorded: the ninth result is printed, but a deck without its
        # declaration does not get it.
        eight = {name: value for name, value in RECORDED_METRICS.items() if name != "fault_input_current_a"}
        self.assertEqual(parse_measurements(RECORDED_STDOUT, "", list(eight)), (eight, {}))

        self.assertEqual(declared_measurements(DUPLICATE_DECK), ([], ["dup"]))
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(DUPLICATE_STDOUT):
            result = _run(_product(Path(directory), DUPLICATE_DECK))
        self.assertEqual((result.verdict.value, result.metrics), ("PASS", {}))
        self.assertEqual(result.summary,
                         "ngspice batch run completed: 0 of 1 declared measurements read; dup: declared more than once")


class TestProcessOutcomes(unittest.TestCase):
    def test_truncated_output_yields_no_metrics(self):
        from ecad_validation.adapters.ngspice import parse_measurements
        from ecad_validation.adapters.process import MAX_CAPTURE_BYTES, _limited

        # Output long enough that run_process's cap falls inside the last value.
        cut = RECORDED_STDOUT.index("3.72465e+02") + len("3.72465e+0")
        stdout = _limited("\n" * (MAX_CAPTURE_BYTES - cut) + RECORDED_STDOUT)
        self.assertTrue(stdout.endswith("\nfault_input_current_a=  3.72465e+0\n[output truncated]"))
        # What reading it anyway would give: a current a hundred times too small.
        self.assertEqual(parse_measurements(stdout, "", ["fault_input_current_a"]), ({"fault_input_current_a": 3.72465}, {}))
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(stdout):
            result = _run(_product(Path(directory), RECORDED_DECK))
        self.assertEqual((result.verdict.value, result.reason_code, result.metrics), ("INCONCLUSIVE", "OUTPUT_TRUNCATED", {}))
        self.assertEqual(result.summary, "ngspice output was truncated, so no measurement was read from it")

    def test_a_nonzero_exit_fails_with_no_metrics(self):
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(RECORDED_STDOUT, returncode=1):
            result = _run(_product(Path(directory), RECORDED_DECK))
        self.assertEqual((result.verdict.value, result.reason_code, result.metrics), ("FAIL", "TOOL_EXITED_NONZERO", {}))
        self.assertEqual(result.summary, "ngspice batch run did not pass")
        self.assertEqual(result.stdout, RECORDED_STDOUT)

    def test_other_process_outcomes_keep_their_verdicts(self):
        from ecad_validation.adapters.base import Capability

        for label, status, reason, verdict in (("timed out", "timed_out", "TOOL_TIMED_OUT", "INCONCLUSIVE"),
                                               ("crashed", "crashed", "TOOL_EXECUTION_ERROR", "INCONCLUSIVE")):
            with self.subTest(label), tempfile.TemporaryDirectory() as directory, _installed(), \
                    _process(RECORDED_STDOUT, returncode=None, status=status, reason=reason):
                result = _run(_product(Path(directory), RECORDED_DECK))
                self.assertEqual((result.verdict.value, result.reason_code, result.metrics), (verdict, reason, {}))
        # The real run_process, given an executable that no longer exists by the time it runs.
        vanished = Capability(adapter="ngspice", available=True, executable="ecad-tool-that-does-not-exist", version="47")
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch("ecad_validation.adapters.ngspice.probe_executable", return_value=vanished):
            result = _run(_product(Path(directory), RECORDED_DECK))
        self.assertEqual((result.verdict.value, result.reason_code, result.execution_status.value, result.metrics),
                         ("BLOCKED", "TOOL_NOT_INSTALLED", "unavailable", {}))

    def test_an_oversized_deck_is_neither_read_nor_run(self):
        limit = 1048576  # 1 MiB
        padding = "*\n" * ((limit - len(RECORDED_DECK)) // 2)
        at_limit = padding + RECORDED_DECK
        self.assertEqual(len(at_limit.encode()), limit)
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(RECORDED_STDOUT) as run_process, \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("the deck was read")):
            result = _run(_product(Path(directory), at_limit + "*"))
        run_process.assert_not_called()
        self.assertEqual((result.verdict.value, result.reason_code, result.execution_status.value),
                         ("BLOCKED", "NETLIST_INPUT_TOO_LARGE", "unavailable"))
        self.assertEqual((result.metrics, result.tool_version), ({}, "47"))
        # One byte less is read and run.
        with tempfile.TemporaryDirectory() as directory, _installed(), _process(RECORDED_STDOUT) as run_process:
            result = _run(_product(Path(directory), at_limit))
        run_process.assert_called_once()
        self.assertEqual((result.verdict.value, result.metrics), ("PASS", RECORDED_METRICS))


class TestVersionProbe(unittest.TestCase):
    def test_the_ngspice_version_comes_from_its_banner(self):
        from ecad_validation.adapters.capabilities import probe_executable
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        for label, banner, version in (
            ("recorded ngspice-47", BANNER, "47"),
            ("recorded ngspice-36, ubuntu:22.04", BANNER_36, "36"),
            ("recorded ngspice-44.2, python:3.12-slim", BANNER_44, "44.2"),
            ("constructed: the same banner for 36", "******\n** ngspice-36 : Circuit level simulation program\n******\n", "36"),
            ("constructed: no ngspice-<version>", "******\n** Circuit level simulation program\n******\n", None),
        ):
            which, run = _probe(stdout=banner)
            with self.subTest(label), which, run:
                capability = probe_executable("ngspice", ("ngspice", "--version"))
                self.assertEqual((capability.available, capability.version, capability.reason), (True, version, None))

        # A tool that ran but did not say which version it is cannot PASS.
        for banner, verdict, reason, tool in ((BANNER, "PASS", "GOLDEN_COMPARISON_PASSED", "ngspice"),
                                              ("******\n", "BLOCKED", "TOOL_VERSION_UNAVAILABLE", "ecad-validator")):
            which, run = _probe(stdout=banner, executable="/usr/bin/ngspice")
            with self.subTest(banner=banner[:20]), tempfile.TemporaryDirectory() as directory, which, run, \
                    _process(RECORDED_STDOUT):
                product = _product(Path(directory), RECORDED_DECK, [
                    _golden("peak", {"inrush_peak_current_a": {"value": 4.71663, "absolute_tolerance": 0.0001}})])
                [check] = execute_cases(product, GateLevel.V3, "golden")
                self.assertEqual((check.verdict.value, check.reason_code, check.tool_id), (verdict, reason, tool))
                self.assertEqual(check.tool_version, "47" if tool == "ngspice" else "")

    def test_probes_of_other_tools_still_take_their_first_line(self):
        from ecad_validation.adapters.capabilities import detect_capabilities, probe_executable

        # kicad-cli prints its bare version; this one is constructed in that form.
        outputs = {"kicad-cli": "8.0.1\n", "ngspice": BANNER, "iverilog": ICARUS_BANNER, "verilator": VERILATOR_BANNER}
        for adapter, command, expected in (("kicad", "kicad-cli", "8.0.1"),
                                           ("iverilog", "iverilog", "Icarus Verilog version 13.0 (stable) (v13_0)"),
                                           ("verilator", "verilator", "Verilator 5.052 2026-09-05 rev vUNKNOWN-built20260905")):
            which, run = _probe(stdout=outputs[command])
            with self.subTest(adapter), which, run:
                capability = probe_executable(adapter, (command, "--version"))
                self.assertEqual((capability.available, capability.version), (True, expected))

        def installed(name: str) -> Optional[str]:
            return f"/usr/bin/{name}" if name in outputs else None  # no openscad, no python3

        def prints(argv: List[str], **_: Any) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(argv, 0, stdout=outputs[Path(argv[0]).name], stderr="")

        with mock.patch("ecad_validation.adapters.capabilities.shutil.which", side_effect=installed), \
                mock.patch("ecad_validation.adapters.capabilities.subprocess.run", side_effect=prints):
            found = detect_capabilities()
        self.assertEqual({name: (c.available, c.version, c.reason) for name, c in found.items()}, {
            "kicad": (True, "8.0.1", None),
            "ngspice": (True, "47", None),
            "verilator": (True, "Verilator 5.052 2026-09-05 rev vUNKNOWN-built20260905", None),
            "iverilog": (True, "Icarus Verilog version 13.0 (stable) (v13_0)", None),
            "openscad": (False, None, "TOOL_NOT_INSTALLED"),
            "mujoco": (False, None, "PYTHON_NOT_INSTALLED"),
        })

    def test_a_version_probe_failure_gives_a_reason_the_receipt_accepts(self):
        """The raw probe reasons for an OSError and a signal are not reason codes;
        a receipt carrying one fails its schema and is not written."""
        cases = (
            ("permission denied", {"raises": PermissionError(13, "Permission denied")},
             "VERSION_PROBE_ERROR", "VERSION_PROBE_ERROR:[Errno 13] Permission denied"),
            ("killed by a signal", {"returncode": -9}, "VERSION_PROBE_EXIT_NONZERO", "VERSION_PROBE_EXIT_-9"),
            ("non-zero exit", {"returncode": 1}, "VERSION_PROBE_EXIT_1", "VERSION_PROBE_EXIT_1"),
            ("timed out", {"raises": subprocess.TimeoutExpired(["ngspice", "--version"], 30)},
             "VERSION_PROBE_TIMED_OUT", "VERSION_PROBE_TIMED_OUT"),
            ("not installed", {"executable": None}, "TOOL_NOT_INSTALLED", "TOOL_NOT_INSTALLED"),
        )
        for label, probe, code, raw in cases:
            which, run = _probe(**probe)
            with self.subTest(label), tempfile.TemporaryDirectory() as directory, which, run, \
                    _process(RECORDED_STDOUT) as run_process:
                result = _run(_product(Path(directory), RECORDED_DECK))
                self.assertEqual((result.verdict.value, result.execution_status.value, result.reason_code),
                                 ("BLOCKED", "unavailable", code))
                self.assertRegex(result.reason_code, RECEIPT_REASON)
                self.assertEqual(result.summary, f"ngspice is unavailable: {raw}")
                run_process.assert_not_called()


class TestDocumentationExamples(unittest.TestCase):
    """QUALITY.md: every public function's example must be one that was actually run."""

    def test_examples_in_the_ngspice_and_capabilities_modules(self):
        import doctest
        import importlib

        for name in ("ngspice", "capabilities"):
            with self.subTest(name):
                module = importlib.import_module(f"ecad_validation.adapters.{name}")
                result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
                self.assertGreater(result.attempted, 0, f"{name} has no runnable examples")
                self.assertEqual(result.failed, 0)

    def test_every_function_the_electrical_domain_wrote_here_has_an_example(self):
        # The functions these modules gained or had rewritten for the
        # electrical domain; the others predate it and are not held here.
        import doctest
        import importlib

        written = {"ngspice": ("declared_measurements", "parse_measurements", "NgspiceAdapter.run"),
                   "capabilities": ("version_from_output",)}
        for name, functions in written.items():
            module = importlib.import_module(f"ecad_validation.adapters.{name}")
            examples = {test.name: len(test.examples) for test in doctest.DocTestFinder().find(module)}
            for function in functions:
                with self.subTest(f"{name}.{function}"):
                    self.assertGreater(examples.get(f"{module.__name__}.{function}", 0), 0)


if __name__ == "__main__":
    unittest.main()
