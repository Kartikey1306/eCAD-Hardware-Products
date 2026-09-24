"""Executable golden and corner case tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ecad_validation.adapters.base import AdapterResult, Capability  # noqa: E402
from ecad_validation.adapters.ngspice import NgspiceAdapter  # noqa: E402
from ecad_validation.adapters.python_control import PythonControlAdapter  # noqa: E402
from ecad_validation.cases import execute_cases  # noqa: E402
from ecad_validation.models import ExecutionStatus, GateLevel, Verdict  # noqa: E402


class TestExecutableCases(unittest.TestCase):
    def _product(self, root: Path, directory: str, case: dict) -> Path:
        product = root / "product"
        (product / "simulation").mkdir(parents=True)
        (product / "validation" / directory).mkdir(parents=True)
        (product / "simulation" / "model.py").write_text(
            'print("{\\"temperature_c\\": 42.5}")\n', encoding="utf-8"
        )
        case.setdefault(
            "domain",
            "system_design" if directory == "golden" else "integrated_physics",
        )
        case.setdefault(
            "requirement_ids",
            ["POLICY:V3-GOLDEN" if directory == "golden" else "POLICY:V4-CORNER"],
        )
        (product / "validation" / directory / "cases.json").write_text(
            json.dumps(
                {
                    "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json",
                    "contract_version": "1.0.0",
                    "gate": "V3" if directory == "golden" else "V4",
                    "cases": [case],
                }
            ),
            encoding="utf-8",
        )
        return product

    def test_golden_case_compares_real_adapter_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "thermal-reference",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": {
                        "temperature_c": {"value": 42.0, "absolute_tolerance": 0.5}
                    },
                    "requirement_ids": ["POLICY:V3-GOLDEN"],
                },
            )
            result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.reason_code, "GOLDEN_COMPARISON_PASSED")
        self.assertEqual(result.requirement_ids, ["POLICY:V3-GOLDEN"])
        generated = [item for item in result.evidence if item.path.startswith("generated/")]
        self.assertEqual(len(generated), 1)
        payload = result.generated_evidence[generated[0].path]
        self.assertEqual(json.loads(payload)["metrics"], {"temperature_c": 42.5})

    GOLDEN = {"temperature_c": {"value": 42.0, "absolute_tolerance": 0.5}}

    def test_unknown_requirement_id_fails_the_case_before_execution(self):
        """A case may only cite requirements the catalog defines.

        Otherwise the receipt references an ID no requirements document
        contains, and the producer emits a bundle its own verifier rejects.
        The case would otherwise PASS, so this is not a lucky failure.
        """
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "made-up-requirement",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": self.GOLDEN,
                    "requirement_ids": ["PRODUCT:MADE-UP-REQ"],
                },
            )
            result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertEqual(result.reason_code, "CASE_REQUIREMENT_UNKNOWN")
        self.assertTrue(result.evidence, "a FAIL must carry evidence")
        self.assertTrue(any("PRODUCT:MADE-UP-REQ" in item for item in result.findings))
        self.assertEqual(result.metrics, {}, "the adapter must not have run")

    def test_unavailable_adapter_is_attributed_to_the_validator(self):
        """The tool that never ran cannot be the tool that decided the verdict."""
        unavailable = Capability(adapter="ngspice", available=False, reason="TOOL_NOT_INSTALLED")
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "spice-reference",
                    "adapter": "ngspice",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": self.GOLDEN,
                },
            )
            with mock.patch.object(NgspiceAdapter, "capability", return_value=unavailable):
                result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.BLOCKED)
        self.assertEqual(result.tool_id, "ecad-validator")
        self.assertTrue(any("ngspice" in item for item in result.findings))

    def test_passing_tool_without_a_version_is_not_a_pass(self):
        """Every invoked tool must record its exact version; none may be invented.

        The receipt schema requires a non-empty version for every registered
        tool, so a PASS from a tool that reported none cannot be recorded
        honestly under that tool. It is blocked rather than misattributed.
        """
        versionless = AdapterResult(
            adapter="python_control",
            execution_status=ExecutionStatus.COMPLETED,
            verdict=Verdict.PASS,
            reason_code="TOOL_EXITED_ZERO",
            summary="model executed",
            command=["python", "simulation/model.py"],
            tool_version=None,
            metrics={"temperature_c": 42.5},
        )
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "versionless-reference",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": self.GOLDEN,
                },
            )
            with mock.patch.object(PythonControlAdapter, "run", return_value=versionless):
                result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.BLOCKED)
        self.assertEqual(result.reason_code, "TOOL_VERSION_UNAVAILABLE")
        self.assertEqual(result.tool_id, "ecad-validator")

    def test_golden_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "thermal-reference",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": {
                        "temperature_c": {"value": 40.0, "absolute_tolerance": 0.1}
                    },
                },
            )
            result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertEqual(result.reason_code, "GOLDEN_COMPARISON_FAILED")

    def test_corner_outside_limit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "corners",
                {
                    "id": "hot-corner",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "metric_limits": {"temperature_c": {"maximum": 40.0}},
                },
            )
            result = execute_cases(product, GateLevel.V4, "corners")[0]
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertEqual(result.reason_code, "CORNER_LIMITS_FAILED")

    def test_duplicate_case_ids_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            product = self._product(
                root,
                "golden",
                {
                    "id": "duplicate",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "expected_metrics": {
                        "temperature_c": {"value": 42.5, "absolute_tolerance": 0.1}
                    },
                },
            )
            manifest = product / "validation" / "golden" / "cases.json"
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["cases"].append(dict(document["cases"][0]))
            manifest.write_text(json.dumps(document), encoding="utf-8")

            result = execute_cases(product, GateLevel.V3, "golden")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].verdict, Verdict.FAIL)
        self.assertEqual(result[0].reason_code, "DUPLICATE_CASE_ID")

    def test_invalid_timeout_is_rejected_by_case_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "invalid-timeout",
                    "adapter": "python_control",
                    "inputs": ["simulation/model.py"],
                    "timeout_seconds": "not-an-integer",
                    "expected_metrics": {"temperature_c": {"value": 42.5, "absolute_tolerance": 0}},
                },
            )
            result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertEqual(result.reason_code, "CASE_SCHEMA_INVALID")

    def test_missing_case_input_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            product = self._product(
                Path(directory),
                "golden",
                {
                    "id": "missing-model",
                    "adapter": "python_control",
                    "inputs": ["simulation/not-there.py"],
                    "expected_metrics": {"x": {"value": 1, "absolute_tolerance": 0}},
                },
            )
            result = execute_cases(product, GateLevel.V3, "golden")[0]
        self.assertEqual(result.verdict, Verdict.BLOCKED)
        self.assertEqual(result.reason_code, "CASE_INPUT_MISSING_OR_UNSAFE")


if __name__ == "__main__":
    unittest.main()
