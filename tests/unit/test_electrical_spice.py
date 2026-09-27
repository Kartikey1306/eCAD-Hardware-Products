"""The electrical domain against real ngspice: datasets/cad/servo_supply_001.

These run ngspice, installed as a system package (brew install ngspice, apt
install ngspice), and need its `--version` banner to name a version. Without
it the tests skip and say why. With ECAD_REQUIRE_SPICE_TOOLS=1 -- set by the
CI job that installs ngspice -- a missing or unidentified ngspice is a
failure instead, so the skip can never go silent where it matters.

Expected values are typed by hand from the netlist and the closed forms of
the design (and, for the two FAIL copies, from ngspice-47's own output on
macOS arm64, 2026-09-27, which the tolerances are wide of), never obtained by
calling the code under test.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

ITEM = REPO_ROOT / "datasets" / "cad" / "servo_supply_001"
NETLIST = "source/servo_supply_001.cir"
DECK = "derived/electrical/servo_supply_001.cir"
# ngspice's progress report: the simulated time it had reached and a CR,
# written over a blank line of stdout when a run is slow. Observed on
# ngspice-47, 2026-09-27: each of 28 runs made in parallel printed one or
# more; the design's two lone runs printed none. run_process reads stdout as
# text, so the CR arrives as a line end.
PROGRESS = re.compile(r"^ Reference value : +\S+$")
# The closed forms of the design (§5.3), to 12 significant figures, and each
# reference's absolute tolerance, from requirements/requirements.json.
CLOSED_FORMS = {
    "inrush_peak_current_a": (4.71663002764, 1e-4),
    "inrush_i2t_a2s": (0.0533907676223, 1e-4),
    "bus_charge_time_s": (0.0109244343789, 1e-6),
    "bus_voltage_at_bypass_v": (47.9147188794, 1e-3),
    "bus_peak_voltage_v": (47.9999999986, 1e-3),
    "steady_bus_voltage_v": (47.8750415236, 1e-3),
    "steady_input_current_a": (4.16667004787, 1e-4),
    "steady_fuse_power_w": (0.347222785757, 1e-5),
    "fault_input_current_a": (372.464522495, 1e-2),
}


def require_ngspice() -> Any:
    """The installed ngspice's capability, if it is available and names its version.

    Otherwise the test is skipped with the reason, or fails when
    ECAD_REQUIRE_SPICE_TOOLS=1, so an environment that must run these tests
    cannot pass by skipping them.
    """
    from ecad_validation.adapters.ngspice import NgspiceAdapter

    capability = NgspiceAdapter().capability()
    if capability.available and capability.version:
        return capability
    message = (f"needs ngspice whose --version names its version (brew install ngspice; apt install ngspice): "
               f"available={capability.available}, version={capability.version!r}, reason={capability.reason!r}")
    if os.environ.get("ECAD_REQUIRE_SPICE_TOOLS") == "1":
        raise AssertionError(f"ECAD_REQUIRE_SPICE_TOOLS=1 but {message}")
    raise unittest.SkipTest(message)


def _scratch():
    return tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-")


def _copy(directory: str, edits: Optional[Dict[str, Tuple[str, str]]] = None) -> Path:
    """A copy of the sample with one text replacement in each named file, rebuilt."""
    from ecad_model.dataset import build

    item = Path(directory) / "servo_supply_001"
    shutil.copytree(ITEM, item)
    for relative, (old, new) in (edits or {}).items():
        path = item / relative
        data = path.read_bytes()
        if data.count(old.encode()) != 1:
            raise AssertionError(f"{relative}: expected {old!r} once")
        path.write_bytes(data.replace(old.encode(), new.encode()))
    build(item)
    return item


def _add_requirements(item: Path, *requirements: Dict[str, Any]) -> None:
    from ecad_model.dataset import build

    path = item / "requirements" / "requirements.json"
    document = json.loads(path.read_bytes())
    document["requirements"] += list(requirements)
    path.write_bytes((json.dumps(document, indent=2) + "\n").encode())
    build(item)


def _requirement(requirement_id: str, component: str, metric: str, operator: str, limit: float,
                 unit: str, **extra: Any) -> Dict[str, Any]:
    return {"requirement_id": requirement_id, "title": f"test fixture {requirement_id}", "domain": "electrical",
            "component": component, "metric": metric, "scenario": {"name": "startup"}, "operator": operator,
            "limit": {"value": limit}, "unit": unit, "illustrative": True,
            "source": {"kind": "requirement", "ref": "tests/unit/test_electrical_spice.py: a boundary fixture"},
            **extra}


def _validate(item: Path, keep: Callable[[Path], Any] = lambda run: None) -> Tuple[Dict[str, Any], Dict[str, Any], Any]:
    from ecad_model.dataset import validate

    with tempfile.TemporaryDirectory() as output:
        run = Path(output) / "run"
        receipt = validate(item, run)
        results = json.loads((run / "results.json").read_bytes())
        kept = keep(run)
    return receipt, results, kept


def _checks(receipt: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}


def _verdicts(checks: Dict[str, Dict[str, Any]], prefix: str) -> Dict[str, Tuple[str, str]]:
    return {check_id: (c["verdict"], c["reason_code"]) for check_id, c in checks.items() if check_id.startswith(prefix)}


class TestRealNgspice(unittest.TestCase):
    def setUp(self):
        self.capability = require_ngspice()

    def test_ngspice_reproduces_the_closed_forms(self):
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.ngspice import NgspiceAdapter

        runs = [NgspiceAdapter().run(AdapterRequest(case_id=f"run{n}", product_root=ITEM, input_files=[ITEM / DECK]))
                for n in (1, 2)]
        for result in runs:
            with self.subTest(result.summary):
                self.assertEqual((result.verdict.value, result.reason_code), ("PASS", "TOOL_EXITED_ZERO"))
                self.assertEqual(result.stderr, "")
                self.assertNotIn("/", result.stdout, "no host path in the hash-bound stdout")
                self.assertEqual(set(result.metrics), set(CLOSED_FORMS))
                for metric, (expected, tolerance) in CLOSED_FORMS.items():
                    self.assertLessEqual(abs(result.metrics[metric] - expected), tolerance, metric)
        # .options noacct removes the run statistics; what can still differ is
        # the progress report, whose presence and value depend on wall-clock time.
        steady = [[line for line in result.stdout.splitlines() if line.strip() and not PROGRESS.match(line)]
                  for result in runs]
        self.assertEqual(steady[0], steady[1], "stdout is identical run to run apart from progress reports and blank lines")

    def test_the_committed_sample_validates_as_designed(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import regenerate_results
        from ecad_model.schemas import validate as validate_schema

        def kept(run: Path) -> Any:
            evidence = [(e["sha256"], hashlib.sha256((run / e["path"]).read_bytes()).hexdigest())
                        for g in json.loads((run / "receipt.json").read_bytes())["gates"]
                        for c in g["checks"] for e in c["evidence"]]
            return evidence, regenerate_results(ITEM, run) == (run / "results.json").read_bytes()

        receipt, results, (evidence, regenerated) = _validate(ITEM, kept)
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _checks(receipt)
        for check_id in ("v0.dataset-schemas-and-hashes", "v0.dataset-input-immutability",
                         "v1.electrical.extraction-and-sanity", "v2.dataset-reproduction",
                         "v2.electrical.model-invariants"):
            with self.subTest(check_id):
                self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
        gates = {g["gate"]: g["verdict"] for g in receipt["gates"]}
        self.assertEqual((gates["V1"], gates["V2"], gates["V3"], gates["V4"]), ("PASS", "PASS", "PASS", "BLOCKED"))
        self.assertEqual(_verdicts(checks, "v3."), {f"v3.REF-EL-00{n}": ("PASS", "GOLDEN_COMPARISON_PASSED")
                                                    for n in range(1, 10)})
        self.assertEqual(_verdicts(checks, "v4."), {
            **{f"v4.REQ-EL-00{n}": ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT") for n in (1, 2, 3, 4)},
            **{f"v4.REQ-EL-00{n}": ("BLOCKED", "MISSING_REQUIRED_INPUT") for n in (5, 6, 7)}})
        self.assertEqual((receipt["overall_verdict"], receipt["eligible_for_ebuild"]), ("BLOCKED", False))
        self.assertEqual(len(results["results"]), 16)
        [tool] = [t for t in receipt["tools"] if t["tool_id"] == "ngspice"]
        self.assertEqual(tool["version"], self.capability.version)
        self.assertRegex(tool["version"], r"^\d")
        for row in results["results"]:
            with self.subTest(row["check_id"]):
                self.assertEqual(row["model_fidelity"], "SIMPLIFIED")
                if row["status"] != "BLOCKED":
                    self.assertEqual((row["simulator"], row["simulator_version"]), ("ngspice", self.capability.version))
        for recorded, actual in evidence:
            self.assertEqual(actual, recorded)
        self.assertTrue(regenerated, "regenerate_results rebuilds the bytes the run wrote")

    def test_an_undersized_precharge_resistor_fails_the_inrush_requirement(self):
        """R_PRE 10 -> 1 ohm: the FAIL is the design's, not the simulator's --
        every closed form still agrees with ngspice."""
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: ("R_PRE n_f n_bus 10\n", "R_PRE n_f n_bus 1\n")})
            receipt, _, _ = _validate(item)
        checks = _checks(receipt)
        inrush = checks["v4.REQ-EL-001"]
        self.assertEqual((inrush["verdict"], inrush["reason_code"]), ("FAIL", "CORNER_LIMITS_FAILED"))
        # ngspice-47 printed 4.06812e+01; the closed form is 40.6811962.
        self.assertLessEqual(abs(inrush["metrics"]["inrush_peak_current_a"] - 40.6812), 1e-3)
        self.assertEqual(_verdicts(checks, "v3."), {f"v3.REF-EL-00{n}": ("PASS", "GOLDEN_COMPARISON_PASSED")
                                                    for n in range(1, 10)})

    def test_a_bypass_that_closes_before_the_bus_is_charged_fails(self):
        """The bypass commanded at 5 ms: the bus is at 31.2 V, and the charge-time
        form does not apply, since the rail would reach 90 % only after the bypass."""
        with _scratch() as directory:
            item = _copy(directory, {NETLIST: ("V_BYP n_byp 0 PWL(0 0 30m 0 30.001m 5)",
                                              "V_BYP n_byp 0 PWL(0 0 5m 0 5.001m 5)")})
            receipt, _, _ = _validate(item)
        checks = _checks(receipt)
        bypass = checks["v4.REQ-EL-002"]
        self.assertEqual((bypass["verdict"], bypass["reason_code"]), ("FAIL", "CORNER_LIMITS_FAILED"))
        # ngspice-47 printed 3.12169e+01.
        self.assertLessEqual(abs(bypass["metrics"]["bus_voltage_at_bypass_v"] - 31.2169), 1e-3)
        charge = checks["v3.REF-EL-003"]
        self.assertEqual((charge["verdict"], charge["reason_code"]), ("BLOCKED", "REFERENCE_NOT_APPLICABLE"))
        self.assertIn("after the bypass is commanded", charge["summary"])

    def test_the_inrush_limit_at_its_boundary_with_real_ngspice(self):
        """Margins of at least 3.4e-3 over the 2.8e-8 numerical error of the
        inrush peak (4.71663 against the closed form 4.71663002764)."""
        with _scratch() as directory:
            item = _copy(directory)
            _add_requirements(
                item,
                _requirement("REQ-EL-101", "r_pre", "inrush_peak_current_a", "<=", 4.72, "A"),
                _requirement("REQ-EL-102", "r_pre", "inrush_peak_current_a", "<=", 4.71, "A"),
                _requirement("REQ-EL-103", "r_pre", "inrush_peak_current_a", "<=", 4.71, "A", tolerance=0.01))
            receipt, _, _ = _validate(item)
        checks = _checks(receipt)
        self.assertEqual({check_id: checks[check_id]["verdict"] for check_id in
                          ("v4.REQ-EL-101", "v4.REQ-EL-102", "v4.REQ-EL-103")},
                         {"v4.REQ-EL-101": "WARNING", "v4.REQ-EL-102": "FAIL", "v4.REQ-EL-103": "WARNING"})

    def test_the_parser_reads_every_value_form_as_ngspice_does(self):
        """Differential: 1 V across each resistor, one per accepted value spelling;
        the current ngspice computes is 1 / the value the parser reads."""
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.ngspice import NgspiceAdapter

        from ecad_model.spice import parse_value

        forms = ["10", "+10", "2.2k", "1meg", "1.5g", "0.002t", "20m", "470u", "4700000n", "4700000000p", ".5", "5.",
                 "2.5e3", "2.5E3", "1e+3", "25e-1", "0.47", "007", "3.3meg"]
        lines = ["* every value form this grammar reads"]
        for n, form in enumerate(forms, start=1):
            lines += [f"V{n} n{n} 0 DC 1", f"R{n} n{n} 0 {form}"]
        lines += [".options noacct", ".tran 1e-07 2e-06 0.0 1e-07"]
        lines += [f".meas tran i{n} FIND par('-i(V{n})') AT=1e-06" for n in range(1, len(forms) + 1)]
        with tempfile.TemporaryDirectory() as directory:
            deck = Path(directory) / "forms.cir"
            deck.write_bytes(("\n".join([*lines, ".end"]) + "\n").encode())
            result = NgspiceAdapter().run(AdapterRequest(case_id="forms", product_root=Path(directory),
                                                         input_files=[deck]))
        self.assertEqual(result.verdict.value, "PASS", result.summary)
        for n, form in enumerate(forms, start=1):
            with self.subTest(form):
                expected = 1 / parse_value(form, "forms.cir")
                # ngspice prints six significant digits.
                self.assertLessEqual(abs(result.metrics[f"i{n}"] - expected), 1e-5 * expected)

    def test_a_measurement_ngspice_cannot_make_is_named(self):
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.ngspice import NgspiceAdapter
        from ecad_validation.cases import execute_cases
        from ecad_validation.models import GateLevel

        deck = ("* a crossing that never happens\nV1 a 0 PWL(0 0 1u 1)\nR1 a 0 1k\n.options noacct\n"
                ".tran 1e-07 2e-06 0.0 1e-07\n.meas tran never WHEN v(a)=2 RISE=1\n"
                ".meas tran top MAX v(a) FROM=0 TO=2e-06\n.end\n")
        with tempfile.TemporaryDirectory() as directory:
            product = Path(directory) / "product"
            (product / "validation" / "golden").mkdir(parents=True)
            (product / "never.cir").write_bytes(deck.encode())
            (product / "validation" / "golden" / "cases.json").write_bytes(json.dumps({
                "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json",
                "contract_version": "1.0.0", "gate": "V3", "cases": [
                    {"id": "needs-never", "adapter": "ngspice", "domain": "eda_circuit", "inputs": ["never.cir"],
                     "requirement_ids": ["POLICY:V3-GOLDEN"],
                     "expected_metrics": {"never": {"value": 1e-06, "absolute_tolerance": 1e-07}}}]}).encode())
            result = NgspiceAdapter().run(AdapterRequest(case_id="never", product_root=product,
                                                         input_files=[product / "never.cir"]))
            [check] = execute_cases(product, GateLevel.V3, "golden")
        self.assertEqual((result.verdict.value, result.metrics), ("PASS", {"top": 1.0}))
        self.assertRegex(result.summary, r"1 of 2 declared measurements read; never: failed: \.meas tran never when")
        self.assertEqual((check.verdict.value, check.reason_code), ("INCONCLUSIVE", "GOLDEN_METRICS_INCONCLUSIVE"))
        self.assertIn("never: adapter produced no finite numeric metric", check.findings)


if __name__ == "__main__":
    unittest.main()
