"""The domain adapter protocol, exercised by an artefact-first domain.

The only production adapter is mechanical, whose engineering model is built
from a STEP assembly. The protocol claims more: that a domain whose artefact
*is* its structure -- HDL, a netlist -- plugs into the same runner without
the runner knowing it. This test-only adapter reads a Verilog file, so it
needs no CAD kernel and no simulator, and proves the claim on a sample with
no STEP file:

- the base types carry a non-CAD source, and build writes a schema-valid
  model and manifest, which names the fixture as the model's producer;
- domain status comes from the registry: the fixture's domain is AVAILABLE,
  mechanical and electrical are NOT_APPLICABLE (an adapter exists, but it
  does not run for this sample), every other domain NOT_IMPLEMENTED;
- check reproduces the derivation, validate writes a schema-valid receipt;
- a requirement compiles through the fixture's metric vocabulary into a case
  the existing engine runs with the Icarus adapter (reported not installed,
  so the outcome does not depend on the machine), and the per-requirement
  result is generated from it;
- without the adapter registered, build refuses and validate is BLOCKED.

It is a fixture, not a digital domain: it validates nothing about the HDL.
The same fast fixture also carries the runner's untrusted-input and
honest-outcome regressions that need no CAD kernel.
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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ecad_model.domains import (  # noqa: E402
    REGISTRY, CaseTarget, DerivedFile, Extraction, Metric, SourceArtifact, domain_status,
)
from ecad_model.quantity import Status, quantity, source  # noqa: E402

MECHANICAL_ITEM = REPO_ROOT / "datasets" / "cad" / "robotic_joint_001"
VERILOG = """module blinker (input clk, input rst, output reg led);
  always @(posedge clk) led <= rst ? 1'b0 : ~led;
endmodule
"""
REFERENCE = {
    "reference_id": "REF-DIG-001", "title": "The model holds the port count the HDL declares",
    "domain": "digital", "metric": "port_count", "scenario": {"name": "none"}, "unit": "1",
    "absolute_tolerance": 0.5, "derivation": "declared_ports",
    "source": {"kind": "computation", "ref": "fixture: exercises the V3 half of the adapter protocol"},
}
REQUIREMENT = {
    "requirement_id": "REQ-DIG-001", "title": "The blinker exposes its clock, reset and LED",
    "domain": "digital", "component": "blinker", "metric": "port_count", "scenario": {"name": "none"},
    "operator": ">=", "limit": {"value": 3}, "unit": "1", "illustrative": True,
    "source": {"kind": "requirement", "ref": "fixture: exercises the V4 half of the adapter protocol"},
}


class VerilogFixtureAdapter:
    """Reads module names and port counts from Verilog. Test-only."""

    domain = "digital"
    formats = frozenset({"verilog"})
    description = "fixture: module port counts read from Verilog (test-only)"
    comparator = "json"
    source_format = "verilog"

    def extract(self, root: Path, sources: Sequence[SourceArtifact], annotations: Dict[str, Any],
                refs: Dict[str, str]) -> Extraction:
        [hdl] = [s for s in sources if s.format == "verilog"]
        text = (root / hdl.path).read_text()
        repo_path = f"{refs['sample']}/{hdl.path}"
        parser = source("computation", "tests/unit/test_domain_adapter.py")
        components = [
            {"component_id": name, "name": name, "kind": "other", "cad_ref": None, "material": None,
             "geometry": None, "physical": None, "placement": None,
             "domains": {"digital": {"port_count": quantity(
                 len([p for p in ports.split(",") if p.strip()]), "1", Status.DERIVED, parser, derived_from=[repo_path])}}}
            for name, ports in re.findall(r"module\s+(\w+)\s*\(([^)]*)\)", text)
        ]
        model = {
            "$schema": "https://embeddedos.org/schemas/engineering-model/v1/engineering-model.schema.json",
            "model_version": "1.0.0",
            "design": {"design_id": annotations["design_id"], "name": "blinker", "revision": "1.0",
                       "sources": [{"path": repo_path, "format": self.source_format,
                                    "sha256": hashlib.sha256((root / hdl.path).read_bytes()).hexdigest()}]},
            "components": components, "joints": [], "relationships": [], "unknowns": [],
        }
        return Extraction(model=model, producer=("tests.unit.test_domain_adapter", "0"))

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]:
        modules = {c["component_id"]: c["domains"]["digital"]["port_count"]["value"] for c in model["components"]}
        return [DerivedFile(path=f"derived/digital/{sample_id}.modules.json",
                            data=(json.dumps(modules, indent=2, sort_keys=True) + "\n").encode(),
                            role="domain_model", media_type="application/json", producer="fixture",
                            version="0", derived_from=("derived/engineering_model.json",),
                            comparator=self.comparator)]

    def case_target(self, sample_id: str) -> CaseTarget:
        return CaseTarget(adapter="iverilog", inputs=("source/blinker.v",), arguments=lambda scenario: [])

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
        from ecad_model.builder import resolve
        from ecad_model.quantity import is_null
        from ecad_model.requirements import ReferenceBlocked

        if derivation != "declared_ports":
            raise ValueError(f"unknown derivation {derivation!r}")
        paths = [f"components/{c['component_id']}/domains/digital/port_count" for c in model["components"]]
        missing = [{"path": path, "status": resolve(model, path)["status"]} for path in paths
                   if is_null(resolve(model, path)["status"])]
        if missing:
            raise ReferenceBlocked("declared_ports needs port counts that have no value", missing)
        return float(sum(resolve(model, path)["value"] for path in paths)), paths

    def metrics(self) -> Dict[str, Metric]:
        return {"port_count": Metric("1", "SIMPLIFIED", "fixture: ports counted in the HDL text")}

    def sanity_problems(self, model: Dict[str, Any]) -> List[str]:
        return [] if model["components"] else ["no module found"]

    def invariant_problems(self, model: Dict[str, Any], extraction_files: Dict[str, Any],
                           domain_models: Dict[str, bytes]) -> List[str]:
        [modules] = domain_models.values()
        names = set(json.loads(modules))
        return [] if names == {c["component_id"] for c in model["components"]} else ["modules differ"]

    def simulation_files(self, root: Path) -> List[str]:
        return []

    def document_schemas(self) -> Dict[str, str]:
        return {}

    def dependencies(self, model: Dict[str, Any], metric: str, scenario: Dict[str, Any]) -> List[str]:
        return [f"components/{c['component_id']}/domains/digital/port_count" for c in model["components"]]

    def reference_inputs(self, model: Dict[str, Any], derivation: str, scenario: Dict[str, Any]) -> List[str]:
        from ecad_model.requirements import ReferenceBlocked

        try:
            return self.reference_value(model, derivation, scenario)[1]
        except ReferenceBlocked as exc:
            return [missing["path"] for missing in exc.paths]

    def check_requirements(self, requirements: Dict[str, Any]) -> None:
        for reference in requirements["reference_values"]:
            if reference["derivation"] != "declared_ports":
                raise ValueError(f"the fixture implements no derivation {reference['derivation']!r}")
        for entry in (*requirements["reference_values"], *requirements["requirements"]):
            if entry["scenario"] != {"name": "none"}:
                raise ValueError("the fixture implements only the scenario 'none'")

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]:
        return sorted(c["component_id"] for c in model["components"])


def _digital_sample(directory: str, requirements: Sequence[Dict[str, Any]] = (),
                    extra_artifacts: Sequence[Dict[str, str]] = (), origin: Dict[str, Any] = None,
                    licence: Dict[str, Any] = None) -> Path:
    """A sample whose primary source is Verilog: no STEP file unless one is added."""
    item = Path(directory) / "blinker_001"
    (item / "source").mkdir(parents=True)
    (item / "design").mkdir()
    (item / "requirements").mkdir()
    (item / "source" / "blinker.v").write_text(VERILOG)
    for artefact in extra_artifacts:
        (item / artefact["path"]).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n")
    provenance = json.loads((MECHANICAL_ITEM / "source" / "provenance.json").read_text())
    provenance.pop("generator")  # the fixture has no authoring script
    provenance.update(domain="digital", artifacts=[{"path": "source/blinker.v", "format": "verilog"}, *extra_artifacts],
                      artifact_type="hdl_source", units="none", coordinate_system="none",
                      description="Test fixture: a one-module Verilog design.")
    if origin is not None:
        provenance["origin"] = origin
    if licence is not None:
        provenance["license"].update(licence)
    (item / "source" / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (item / "design" / "annotations.json").write_text(json.dumps({
        "$schema": "https://embeddedos.org/schemas/engineering-model/v1/design-annotations.schema.json",
        "annotations_version": "1.0.0", "design_id": "blinker_001", "materials": {}, "parts": {},
        "joints": [], "attachments": [], "components_without_cad": [], "relationships": []}, indent=2) + "\n")
    _write_requirements(item, requirements)
    return item


def _write_requirements(item: Path, requirements: Sequence[Dict[str, Any]], references: Sequence[Dict[str, Any]] = ()) -> None:
    (item / "requirements" / "requirements.json").write_text(json.dumps({
        "$schema": "https://embeddedos.org/schemas/engineering-model/v1/engineering-requirements.schema.json",
        "requirements_version": "1.0.0", "design_id": "blinker_001",
        "reference_values": list(references), "requirements": list(requirements)}, indent=2) + "\n")


def _passing_icarus(port_count: float = 3.0):
    """A stand-in for the Icarus adapter that 'runs' every case and reports
    port_count, so the engine's PASS paths run deterministically. Test-only."""
    from ecad_validation.adapters.base import Adapter, AdapterResult, Capability
    from ecad_validation.models import ExecutionStatus, Verdict

    class StandInIcarus(Adapter):
        name = "iverilog"

        def capability(self):
            return Capability(adapter="iverilog", available=True, version="stand-in 0")

        def run(self, request):
            return AdapterResult(adapter="iverilog", execution_status=ExecutionStatus.COMPLETED, verdict=Verdict.PASS,
                                 reason_code="SIMULATION_COMPLETED", summary="stand-in run",
                                 command=["iverilog", "stand-in"], tool_version="stand-in 0",
                                 metrics={"port_count": port_count})

    return mock.patch.dict("ecad_validation.cases.ADAPTERS", {"iverilog": StandInIcarus})


def _no_icarus():
    """The Icarus adapter, reporting itself not installed wherever the test runs."""
    from ecad_validation.adapters.base import Capability

    return mock.patch("ecad_validation.adapters.hdl.probe_executable",
                      return_value=Capability(adapter="iverilog", available=False, reason="IVERILOG_NOT_INSTALLED"))


def _checks(receipt: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}


def _scratch():
    return tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-")


def _parses_but_cannot_be_printed() -> Optional[int]:
    """A list depth this Python's json parses but repr cannot print, or None
    when the two limits are too close to build one reliably. Measured, not
    assumed: CPython 3.14 parses about 116 000 levels and prints about 70 000;
    3.12 stops both at about 10 000."""
    def deepest(works: Callable[[int], object]) -> int:
        low, high = 1, 1 << 18
        while low < high:
            middle = (low + high + 1) // 2
            try:
                works(middle)
                low = middle
            except RecursionError:
                high = middle - 1
        return low

    def nested(depth: int) -> List[Any]:
        value: List[Any] = []
        for _ in range(depth):
            value = [value]
        return value

    parsed = deepest(lambda depth: json.loads("[" * depth + "]" * depth))
    printed = deepest(lambda depth: repr(nested(depth)))
    return (parsed + printed) // 2 if parsed - printed > 1000 else None


class TestArtefactFirstDomain(unittest.TestCase):
    def setUp(self):
        self.registry = {**REGISTRY, "digital": VerilogFixtureAdapter()}

    def test_a_sample_with_no_step_file_builds_checks_and_validates(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import build, check, validate
        from ecad_model.schemas import validate as validate_schema

        with _scratch() as directory:
            item = _digital_sample(directory, [REQUIREMENT])
            written = build(item, self.registry)
            self.assertIn("derived/digital/blinker_001.modules.json", written)
            self.assertFalse(list(item.rglob("*.step")))
            model = json.loads((item / "derived" / "engineering_model.json").read_text())
            validate_schema(model, "engineering-model/v1/engineering-model")
            self.assertEqual([c["component_id"] for c in model["components"]], ["blinker"])
            manifest = json.loads((item / "dataset-item.json").read_text())
            validate_schema(manifest, "cad-dataset/v1/dataset-item")
            self.assertEqual(manifest["domain"], "digital")
            status = {d["domain"]: d["status"] for d in manifest["domains"]}
            self.assertEqual(status.pop("digital"), "AVAILABLE")
            self.assertEqual(status.pop("mechanical"), "NOT_APPLICABLE")
            self.assertEqual(status.pop("electrical"), "NOT_APPLICABLE")
            self.assertEqual(set(status.values()), {"NOT_IMPLEMENTED"})
            self.assertEqual(manifest["source"]["artifacts"][0]["format"], "verilog")
            lineage = {d["artifact"]["path"]: d["derived_from"] for d in manifest["derived"]}
            # No extraction file stands between the HDL and the model: the model names the HDL itself.
            self.assertEqual(lineage["derived/engineering_model.json"], ["source/blinker.v", "design/annotations.json"])

            self.assertEqual(check(item, self.registry), [])
            with tempfile.TemporaryDirectory() as output, _no_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
                results = json.loads((Path(output) / "run" / "results.json").read_text())
            validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
            checks = _checks(receipt)
            for check_id in ("v0.dataset-schemas-and-hashes", "v1.digital.extraction-and-sanity",
                             "v2.dataset-reproduction", "v2.digital.model-invariants"):
                with self.subTest(check_id):
                    self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
            # No references: nothing to run at V3, and the receipt says so.
            self.assertEqual(checks["v3.golden-cases"]["verdict"], "BLOCKED")
            # The requirement compiled into a case the engine ran with the Icarus
            # adapter, which is not installed: BLOCKED, never a guessed verdict.
            self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                             ("BLOCKED", "IVERILOG_NOT_INSTALLED"))
            self.assertIn("REQ-DIG-001", checks["v4.REQ-DIG-001"]["requirement_ids"])
            self.assertFalse(receipt["eligible_for_ebuild"])
            validate_schema(results, "engineering-model/v1/validation-results")
            [row] = results["results"]
            self.assertEqual((row["check_id"], row["status"], row["reason_code"]),
                             ("v4.REQ-DIG-001", "BLOCKED", "IVERILOG_NOT_INSTALLED"))
            self.assertEqual((row["model_fidelity"], row["simulator"], row["simulator_version"]),
                             ("SIMPLIFIED", "iverilog", None))
            self.assertEqual(row["inputs"], [{"path": "components/blinker/domains/digital/port_count", "status": "DERIVED"}])
            self.assertEqual((row["expected_value"], row["applied_bound"]), (3, {"minimum": 3}))

    def test_the_manifest_names_the_fixture_as_its_model_producer(self):
        """The adapter that built a model names its producer. The runner used to
        record the mechanical builder for every model, whatever built it."""
        from ecad_model.dataset import build

        # No default: an adapter that names no producer cannot inherit one.
        without_producer: Dict[str, Any] = {"model": {}}
        with self.assertRaisesRegex(TypeError, "producer"):
            Extraction(**without_producer)
        with _scratch() as directory:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            manifest = json.loads((item / "dataset-item.json").read_text())
        [model] = [d for d in manifest["derived"] if d["artifact"]["path"] == "derived/engineering_model.json"]
        self.assertEqual((model["role"], model["producer"]),
                         ("engineering_model", {"tool": "tests.unit.test_domain_adapter", "version": "0"}))
        self.assertEqual(manifest["versions"]["engineering_model"], "0")
        # The mechanical adapter names the builder, so the committed mechanical
        # manifest, which check regenerates, still says what it said.
        mechanical = json.loads((MECHANICAL_ITEM / "dataset-item.json").read_text())
        [model] = [d for d in mechanical["derived"] if d["artifact"]["path"] == "derived/engineering_model.json"]
        self.assertEqual(model["producer"], {"tool": "ecad_model.builder", "version": "1.0.0"})
        self.assertEqual(mechanical["versions"]["engineering_model"], "1.0.0")

    def test_a_requirement_of_another_domain_is_refused_not_compiled(self):
        from ecad_model.dataset import build

        mechanical = json.loads((MECHANICAL_ITEM / "requirements" / "requirements.json").read_text())
        for label, requirements, references in (("requirement", mechanical["requirements"][:1], []),
                                                ("reference", [], mechanical["reference_values"][:1])):
            with self.subTest(label), _scratch() as directory:
                item = _digital_sample(directory)
                _write_requirements(item, requirements, references)
                with self.assertRaisesRegex(ValueError, "requirements for mechanical cannot be compiled by the digital adapter"):
                    build(item, self.registry)

    def test_without_its_adapter_the_domain_is_not_implemented_and_nothing_runs(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)  # the committed case documents exist
            with self.assertRaisesRegex(ValueError, "digital is NOT_IMPLEMENTED"):
                build(item)
            with tempfile.TemporaryDirectory() as output, \
                    mock.patch("ecad_validation.adapters.hdl.HDLAdapter.run", side_effect=AssertionError("ran")):
                receipt = validate(item, Path(output) / "run")
                report = (Path(output) / "run" / "report.md").read_text()
                self.assertFalse((Path(output) / "run" / "results.json").exists())
            checks = _checks(receipt)
            self.assertEqual((checks["v1.digital.extraction-and-sanity"]["verdict"],
                              checks["v1.digital.extraction-and-sanity"]["reason_code"]),
                             ("BLOCKED", "DOMAIN_NOT_IMPLEMENTED"))
            # The committed case is not run for a domain V1 calls NOT_IMPLEMENTED.
            self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                             ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))
            self.assertIn("No per-requirement results were written: no digital adapter is registered", report)

    def test_only_the_sample_s_primary_domain_is_available(self):
        """A second artefact another adapter could read does not make its domain
        AVAILABLE: only the primary domain's adapter ever runs."""
        from ecad_model.dataset import build

        self.assertEqual(
            {s["domain"]: s["status"] for s in domain_status(
                "digital", [SourceArtifact("source/blinker.v", "verilog"), SourceArtifact("source/case.step", "step")],
                [], self.registry)}["mechanical"], "NOT_APPLICABLE")
        with _scratch() as directory:
            item = _digital_sample(directory, extra_artifacts=[{"path": "source/case.step", "format": "step"}])
            build(item, self.registry)
            manifest = json.loads((item / "dataset-item.json").read_text())
        statuses = {d["domain"]: d for d in manifest["domains"]}
        lineage = {d["artifact"]["path"]: d["derived_from"] for d in manifest["derived"]}
        self.assertEqual(lineage["derived/engineering_model.json"], ["source/blinker.v", "design/annotations.json"],
                         "the STEP file is recorded and hashed, but the digital model was not derived from it")
        self.assertEqual(statuses["digital"]["status"], "AVAILABLE")
        self.assertEqual(statuses["mechanical"]["status"], "NOT_APPLICABLE")
        self.assertIn("runs only for samples whose primary domain is mechanical", statuses["mechanical"]["reason"])

    def test_a_third_party_sample_records_its_source_url(self):
        from ecad_model.dataset import build
        from ecad_model.schemas import validate as validate_schema

        url = "https://example.org/blinker.v"
        with _scratch() as directory:
            item = _digital_sample(
                directory, origin={"kind": "third_party", "author": "someone", "url": url,
                                   "modifications": "none"},
                licence={"verified_by": "a named reviewer", "verified_at": "2026-09-26"})
            build(item, self.registry)
            manifest = json.loads((item / "dataset-item.json").read_text())
        self.assertEqual(manifest["source_url"], url)
        manifest["source_url"] = None
        with self.assertRaisesRegex(ValueError, "self_authored"):
            validate_schema(manifest, "cad-dataset/v1/dataset-item")

    def test_an_exact_comparator_compares_bytes(self):
        from ecad_model.dataset import Item, _derive, build, reproducibility

        for comparator, differs in (("json", False), ("exact", True)):
            with self.subTest(comparator), _scratch() as directory:
                adapter = VerilogFixtureAdapter()
                adapter.comparator = comparator
                registry = {**REGISTRY, "digital": adapter}
                item = _digital_sample(directory)
                build(item, registry)
                modules = item / "derived" / "digital" / "blinker_001.modules.json"
                modules.write_text(json.dumps(json.loads(modules.read_text())) + "\n")  # same JSON, other bytes
                problems = reproducibility(Item(item), _derive(Item(item), registry))
                self.assertEqual(bool(problems), differs, problems)

    def test_a_source_the_provenance_does_not_declare_is_a_divergence(self):
        from ecad_model.dataset import Item, _derive, _reference_problems

        with _scratch() as directory:
            adapter = VerilogFixtureAdapter()
            adapter.source_format = "vhdl"
            item = _digital_sample(directory)
            fresh = _derive(Item(item), {**REGISTRY, "digital": adapter})
            problems = _reference_problems(Item(item), fresh.model, json.loads(
                (item / "requirements" / "requirements.json").read_text()))
        self.assertTrue(any("which the provenance does not declare" in p for p in problems), problems)

    def test_a_model_whose_lineage_cannot_be_followed_is_not_built(self):
        from ecad_model.dataset import build

        class Dangling(VerilogFixtureAdapter):
            def extract(self, *args, **kwargs):
                extraction = super().extract(*args, **kwargs)
                port_count = extraction.model["components"][0]["domains"]["digital"]["port_count"]
                port_count["derived_from"].append("components/ghost/domains/digital/port_count")
                return extraction

        with _scratch() as directory:
            item = _digital_sample(directory)
            with self.assertRaisesRegex(ValueError, "lineage cannot be followed"):
                build(item, {**REGISTRY, "digital": Dangling()})


class TestHonestOutcomesWithoutCad(unittest.TestCase):
    """validate writes a receipt that says what happened when the inputs cannot be built into a
    model, when the requirements cannot be read or compiled, and when committed files have drifted
    from the inputs or do not parse."""

    def setUp(self):
        self.registry = {**REGISTRY, "digital": VerilogFixtureAdapter()}

    def test_an_error_the_item_provokes_is_its_fault_not_a_missing_domain(self):
        from ecad_model.dataset import validate

        class Crashing(VerilogFixtureAdapter):
            def extract(self, *args, **kwargs):
                raise KeyError("a lookup the item's inputs broke")

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory)
            receipt = validate(item, Path(output) / "run", {**REGISTRY, "digital": Crashing()})
        v1 = _checks(receipt)["v1.digital.extraction-and-sanity"]
        self.assertEqual((v1["verdict"], v1["reason_code"]), ("FAIL", "DATASET_INPUT_INVALID"))
        self.assertIn("KeyError", v1["findings"][0])

    def test_an_arithmetic_error_the_item_provokes_still_gives_a_receipt(self):
        """Review finding CS-3: a zero capacitance made the electrical closed forms
        divide by zero during the derivation, and validate wrote no receipt."""
        from ecad_model.dataset import validate

        for error in (ZeroDivisionError("float division by zero"), OverflowError("(34, 'Result too large')")):
            class Dividing(VerilogFixtureAdapter):
                def reference_value(self, *args, **kwargs):
                    raise error

            with self.subTest(type(error).__name__), _scratch() as directory, tempfile.TemporaryDirectory() as output:
                item = _digital_sample(directory)
                _write_requirements(item, [], [REFERENCE])
                receipt = validate(item, Path(output) / "run", {**REGISTRY, "digital": Dividing()})
                self.assertTrue((Path(output) / "run" / "receipt.json").is_file())
                v1 = _checks(receipt)["v1.digital.extraction-and-sanity"]
                self.assertEqual((v1["verdict"], v1["reason_code"]), ("FAIL", "DATASET_INPUT_INVALID"))
                self.assertEqual(v1["findings"], [f"{type(error).__name__}: {error}"])

    def test_a_requirement_that_cannot_compile_still_gives_a_receipt(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [{**REQUIREMENT, "unit": "N*m"}])
            with self.assertRaisesRegex(ValueError, "unit N\\*m != the unit of port_count"):
                build(item, self.registry)
            receipt = validate(item, Path(output) / "run", self.registry)
            self.assertTrue((Path(output) / "run" / "receipt.json").is_file())
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        checks = _checks(receipt)
        self.assertEqual((checks["v1.digital.extraction-and-sanity"]["verdict"],
                          checks["v1.digital.extraction-and-sanity"]["reason_code"]), ("FAIL", "DATASET_INPUT_INVALID"))
        self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                         ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))

    def test_a_refused_entry_on_a_built_item_still_gives_a_receipt_and_results(self):
        """The committed model is there, so results are built from it; the
        adapter cannot evaluate an entry V1 refused, and says so in the row."""
        from ecad_model.dataset import validate
        from ecad_model.schemas import validate as validate_schema

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = Path(directory) / "robotic_joint_001"
            shutil.copytree(MECHANICAL_ITEM, item, ignore=shutil.ignore_patterns("__pycache__"))
            path = item / "requirements" / "requirements.json"
            requirements = json.loads(path.read_text())
            speed = next(r for r in requirements["reference_values"] if r["derivation"] == "min_jerk_peak_speed")
            requirements["reference_values"].append({**speed, "reference_id": "REF-PROBE-001", "scenario": {"name": "static_sweep"}})
            path.write_text(json.dumps(requirements, indent=2) + "\n")
            # V1 refuses the requirements before any CAD kernel runs.
            receipt = validate(item, Path(output) / "run")
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _checks(receipt)
        self.assertEqual(checks["v1.mechanical.extraction-and-sanity"]["reason_code"], "DATASET_INPUT_INVALID")
        self.assertEqual((checks["v3.REF-PROBE-001"]["verdict"], checks["v3.REF-PROBE-001"]["reason_code"]),
                         ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))
        probe = next(r for r in results["results"] if r["requirement"] == "REF-PROBE-001")
        self.assertEqual(probe["inputs"], [])
        self.assertTrue(any(f.startswith("the inputs could not be established: KeyError") for f in probe["findings"]),
                        probe["findings"])

    def test_a_metric_the_domain_does_not_produce_has_no_fidelity(self):
        from ecad_model.dataset import validate
        from ecad_model.schemas import validate as validate_schema

        from ecad_model.dataset import build

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)  # the committed model the results read
            _write_requirements(item, [{**REQUIREMENT, "metric": "made_up_metric"}])
            receipt = validate(item, Path(output) / "run", self.registry)
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        validate_schema(results, "engineering-model/v1/validation-results")
        self.assertEqual(_checks(receipt)["v1.digital.extraction-and-sanity"]["reason_code"], "DATASET_INPUT_INVALID")
        [row] = results["results"]
        self.assertEqual((row["status"], row["model_fidelity"]), ("BLOCKED", None))

    def test_an_unusable_committed_model_gives_a_receipt_without_results(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            model = item / "derived" / "engineering_model.json"
            for label, content in (("not JSON", "{"), ("not a model", json.dumps({"components": "x"}))):
                with self.subTest(label):
                    model.write_text(content)
                    run = Path(output) / label.replace(" ", "-")
                    with _no_icarus():
                        receipt = validate(item, run, self.registry)
                    checks = _checks(receipt)
                    self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                                     ("BLOCKED", "COMMITTED_MODEL_INVALID"))
                    self.assertEqual(checks["v2.dataset-reproduction"]["verdict"], "FAIL")
                    self.assertFalse((run / "results.json").exists())
                    self.assertIn("No per-requirement results were written: the committed engineering model cannot be used",
                                  (run / "report.md").read_text())

    def test_committed_files_that_do_not_parse_are_divergences_not_crashes(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / "validation" / "corners" / "cases.json").write_text("{")
            (item / "dataset-item.json").write_text(json.dumps({"item_id": "blinker_001"}))
            with _no_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
        checks = _checks(receipt)
        findings = " ".join(checks["v2.dataset-reproduction"]["findings"])
        self.assertIn("validation/corners/cases.json: the committed file cannot be read as its producer wrote it", findings)
        self.assertIn("dataset-item.json: does not have the shape build writes", findings)
        self.assertEqual(checks["v4.REQ-DIG-001"]["reason_code"], "COMMITTED_CASE_MISSING")

    def test_a_stale_case_in_a_document_still_compiled_is_not_counted(self):
        """The fresh derivation still compiles the corner document, but one of
        its committed cases is stale: for an entry now blocked, or one that no
        longer exists. The engine runs the whole document; the stale case must
        not be counted beside, or instead of, what the fresh derivation says."""
        from ecad_model.dataset import build, validate

        class Unknowable(VerilogFixtureAdapter):
            def extract(self, *args, **kwargs):
                extraction = super().extract(*args, **kwargs)
                for component in extraction.model["components"]:
                    component["domains"]["digital"]["port_count"] = quantity(
                        None, "1", Status.UNKNOWN, source("computation", "fixture"), note="no longer read")
                return extraction

        limited = {**REQUIREMENT, "requirement_id": "REQ-DIG-002",
                   "limit": {"quantity": "components/blinker/domains/digital/port_count"}}
        for label, registry, requirements in (
                ("now blocked", {**REGISTRY, "digital": Unknowable()}, [REQUIREMENT, limited]),
                ("no longer required", self.registry, [REQUIREMENT])):
            with self.subTest(label), _scratch() as directory, tempfile.TemporaryDirectory() as output:
                item = _digital_sample(directory, [REQUIREMENT, limited])
                build(item, self.registry)  # the committed document holds REQ-DIG-001 and REQ-DIG-002
                _write_requirements(item, requirements)
                with _passing_icarus():
                    receipt = validate(item, Path(output) / "run", registry)
                ids = [c["check_id"] for g in receipt["gates"] for c in g["checks"] if c["check_id"].startswith("v4.")]
                self.assertEqual(ids.count("v4.REQ-DIG-001"), 1)
                if label == "now blocked":
                    [stale] = [c for g in receipt["gates"] for c in g["checks"] if c["check_id"] == "v4.REQ-DIG-002"]
                    self.assertEqual((stale["verdict"], stale["reason_code"]), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
                else:
                    self.assertNotIn("v4.REQ-DIG-002", ids, "a requirement that no longer exists has no check")

    def test_a_committed_case_the_requirements_no_longer_compile_to_is_not_counted(self):
        """Same id, different content: a limit or tolerance edited without a
        rebuild. The committed case would still pass; the requirement as it now
        stands says nothing about it, so the check is BLOCKED, not PASS."""
        from ecad_model.dataset import build, validate
        from ecad_model.schemas import validate as validate_schema

        real = {**REQUIREMENT, "illustrative": False}
        for label, edited in (("limit tightened", {**real, "limit": {"value": 10}}),
                              ("tolerance added", {**real, "tolerance": 0.5})):
            with self.subTest(label), _scratch() as directory, tempfile.TemporaryDirectory() as output:
                item = _digital_sample(directory, [real])
                build(item, self.registry)
                _write_requirements(item, [edited])
                with _passing_icarus():
                    receipt = validate(item, Path(output) / "run", self.registry)
                results = json.loads((Path(output) / "run" / "results.json").read_text())
                validate_schema(results, "engineering-model/v1/validation-results")
                check = _checks(receipt)["v4.REQ-DIG-001"]
                self.assertEqual((check["verdict"], check["reason_code"]), ("BLOCKED", "COMMITTED_CASE_STALE"))
                self.assertIn("metric_limits", " ".join(check["findings"]))
                [row] = results["results"]
                self.assertEqual((row["status"], row["applied_bound"], row["configuration"]["seed"]), ("BLOCKED", None, None),
                                 "nothing was compiled for the requirement as it stands, so no bound is claimed")

    def test_a_case_document_the_engine_cannot_run_still_gives_a_receipt(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import build, validate

        def nested_adapter(text, depth):
            # Parses, then overflows the engine's schema check. Built as text:
            # json itself cannot build a list this deep on every Python.
            document = json.loads(text)
            document["cases"][0]["adapter"] = None
            text = json.dumps(document)
            self.assertEqual(text.count('"adapter": null'), 1)
            return text.replace('"adapter": null', '"adapter": ' + "[" * depth + "]" * depth)

        for label in ("not UTF-8", "a metric that is not a finite number", "nested too deeply to parse",
                      "nested too deeply to check"):
            with self.subTest(label), _scratch() as directory, tempfile.TemporaryDirectory() as output:
                item = _digital_sample(directory, [REQUIREMENT])
                build(item, self.registry)
                corners = item / "validation" / "corners" / "cases.json"
                if label == "not UTF-8":
                    corners.write_bytes(corners.read_text().encode("utf-16"))  # still JSON to json.loads
                elif label == "nested too deeply to parse":
                    corners.write_text("[" * 1000000 + "]" * 1000000)
                elif label == "nested too deeply to check":
                    depth = _parses_but_cannot_be_printed()
                    if depth is None:
                        self.skipTest("this Python parses JSON barely deeper than it can print it, so no "
                                      "document both parses and overflows the check")
                    corners.write_text(nested_adapter(corners.read_text(), depth))
                with _passing_icarus(float("nan")):
                    receipt = validate(item, Path(output) / "run", self.registry)
                validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
                checks = _checks(receipt)
                self.assertEqual(checks["v4.REQ-DIG-001"]["verdict"] in ("INCONCLUSIVE", "BLOCKED"), True)
                if label in ("not UTF-8", "a metric that is not a finite number"):
                    self.assertEqual(
                        (checks["v4.corners-manifest"]["verdict"], checks["v4.corners-manifest"]["reason_code"]),
                        ("INCONCLUSIVE", "CASE_ENGINE_ERROR"))
                    # The engine returns nothing for the document: the entry has no
                    # verdict, which is not the same as a missing input.
                    self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["execution_status"],
                                      checks["v4.REQ-DIG-001"]["reason_code"]),
                                     ("INCONCLUSIVE", "crashed", "CASE_ENGINE_ERROR"))

    def test_an_input_relabelled_without_a_rebuild_is_judged_by_what_it_is_now(self):
        """The committed model says DERIVED; the sources now say AI_ASSUMPTION.
        The stricter status decides, whichever model holds it."""
        from ecad_model.dataset import build, validate

        class Assuming(VerilogFixtureAdapter):
            def extract(self, *args, **kwargs):
                extraction = super().extract(*args, **kwargs)
                for component in extraction.model["components"]:
                    count = component["domains"]["digital"]["port_count"]
                    component["domains"]["digital"]["port_count"] = quantity(
                        count["value"], "1", Status.AI_ASSUMPTION, source("ai", "fixture"), note="proposed")
                return extraction

        real = {**REQUIREMENT, "illustrative": False}
        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [real])
            build(item, self.registry)
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", {**REGISTRY, "digital": Assuming()})
            [row] = json.loads((Path(output) / "run" / "results.json").read_text())["results"]
        check = _checks(receipt)["v4.REQ-DIG-001"]
        self.assertEqual((check["verdict"], check["reason_code"]), ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION"))
        # The result lists the inputs the verdict rests on, as the run recorded them.
        self.assertIn({"path": "components/blinker/domains/digital/port_count", "status": "AI_ASSUMPTION"}, row["inputs"])

    def test_a_case_document_that_breaks_its_schema_is_not_read_for_results(self):
        from ecad_model.dataset import build, validate
        from ecad_model.requirements import CASES_SCHEMA

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / "validation" / "corners" / "cases.json").write_text(json.dumps(
                {"$schema": CASES_SCHEMA, "gate": "V4", "cases": [{"id": "REQ-DIG-001", "metric_limits": "x"}]}))
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
            [row] = json.loads((Path(output) / "run" / "results.json").read_text())["results"]
        self.assertEqual(_checks(receipt)["v4.REQ-DIG-001"]["reason_code"], "COMMITTED_CASE_STALE")
        self.assertEqual((row["status"], row["applied_bound"]), ("BLOCKED", None))

    def test_json_nested_too_deeply_is_malformed_input_not_a_crash(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / "design" / "annotations.json").write_text("[" * 100000 + "]" * 100000)
            receipt = validate(item, Path(output) / "run", self.registry)
        checks = _checks(receipt)
        self.assertEqual(checks["v0.dataset-schemas-and-hashes"]["verdict"], "FAIL")
        self.assertIn("nested too deeply", " ".join(checks["v0.dataset-schemas-and-hashes"]["findings"]))
        self.assertEqual(checks["v1.digital.extraction-and-sanity"]["reason_code"], "DATASET_INPUT_INVALID")

    def test_the_command_line_says_when_the_receipt_was_written_without_its_results(self):
        from ecad_model import cli
        from ecad_model.dataset import build

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            with _no_icarus(), mock.patch.dict(REGISTRY, {"digital": VerilogFixtureAdapter()}), \
                    mock.patch("ecad_model.dataset._results", side_effect=RuntimeError("fixture defect")):
                status = cli.main(["validate", str(item), "--output", str(Path(output) / "run")])
            self.assertEqual(status, 3, "exit 1 means no receipt, 2 is argparse's usage error; here a receipt was written")
            self.assertTrue((Path(output) / "run" / "receipt.json").is_file())

    def test_a_case_whose_derived_input_no_longer_reproduces_is_not_counted(self):
        """The case object still matches, but the domain model it runs on was
        edited: a verdict from it would be about a model the inputs no longer
        produce."""
        from ecad_model.dataset import build, validate

        class ModelFed(VerilogFixtureAdapter):
            def case_target(self, sample_id):
                return CaseTarget(adapter="iverilog",
                                  inputs=("source/blinker.v", f"derived/digital/{sample_id}.modules.json"),
                                  arguments=lambda scenario: [])

        registry = {**REGISTRY, "digital": ModelFed()}
        real = {**REQUIREMENT, "illustrative": False}
        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [real])
            build(item, registry)
            (item / "derived" / "digital" / "blinker_001.modules.json").write_text('{"blinker": 9}\n')
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", registry)
        check = _checks(receipt)["v4.REQ-DIG-001"]
        self.assertEqual((check["verdict"], check["reason_code"]), ("BLOCKED", "COMMITTED_CASE_STALE"))
        self.assertIn("its input derived/digital/blinker_001.modules.json no longer reproduces", " ".join(check["findings"]))

    def test_a_case_document_the_engine_refuses_is_named_not_called_missing(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            corners = item / "validation" / "corners" / "cases.json"
            corners.write_bytes(b"\xef\xbb\xbf" + corners.read_bytes())  # a UTF-8 BOM: JSON to us, not to the engine
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
        checks = _checks(receipt)
        self.assertEqual(checks["v4.corners-manifest"]["reason_code"], "CASE_MANIFEST_INVALID")
        self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                         ("BLOCKED", "CASE_DOCUMENT_REFUSED"))

    def test_a_committed_case_under_a_gate_level_id_is_not_counted(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            corners = item / "validation" / "corners" / "cases.json"
            document = json.loads(corners.read_text())
            document["cases"].append({**document["cases"][0], "id": "corners-manifest"})
            corners.write_text(json.dumps(document))
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
        checks = _checks(receipt)
        self.assertNotIn("v4.corners-manifest", checks, "no requirement states that case's limits")
        self.assertEqual(checks["v4.REQ-DIG-001"]["reason_code"], "WITHIN_ILLUSTRATIVE_LIMIT")

    def test_a_reference_whose_adapter_crashed_still_shows_its_compiled_bound(self):
        from ecad_validation.adapters.base import Adapter, Capability

        from ecad_model.dataset import build, validate

        class CrashingIcarus(Adapter):
            name = "iverilog"

            def capability(self):
                return Capability(adapter="iverilog", available=True, version="stand-in 0")

            def run(self, request):
                raise ValueError("fixture: the simulator refused the case")

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            _write_requirements(item, [REQUIREMENT], [REFERENCE])
            build(item, self.registry)
            with mock.patch.dict("ecad_validation.cases.ADAPTERS", {"iverilog": CrashingIcarus}):
                receipt = validate(item, Path(output) / "run", self.registry)
            rows = {r["requirement"]: r for r in json.loads((Path(output) / "run" / "results.json").read_text())["results"]}
        self.assertEqual(_checks(receipt)["v3.REF-DIG-001"]["reason_code"], "ADAPTER_EXECUTION_ERROR")
        self.assertEqual((rows["REF-DIG-001"]["expected_value"], rows["REF-DIG-001"]["applied_bound"]),
                         (3.0, {"value": 3.0, "absolute_tolerance": 0.5}),
                         "the case ran and crashed; what it was compiled to compare is still what it was")

    def test_a_manifest_nested_too_deeply_is_a_divergence_not_a_crash(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            path = item / "dataset-item.json"
            manifest = json.loads(path.read_text())
            path.write_text(json.dumps(manifest)[:-1] + ', "source_url": ' + "[" * 100000 + "]" * 100000 + "}")
            with _no_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
        self.assertEqual(_checks(receipt)["v2.dataset-reproduction"]["verdict"], "FAIL")

    def test_a_failure_to_build_the_results_still_leaves_the_receipt(self):
        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            run = Path(output) / "run"
            with _no_icarus(), mock.patch("ecad_model.dataset._results", side_effect=RuntimeError("fixture defect")), \
                    self.assertRaisesRegex(RuntimeError, "fixture defect"):
                validate(item, run, self.registry)
            self.assertTrue((run / "receipt.json").is_file())
            self.assertTrue((run / "evidence-index.json").is_file())
            self.assertIn("generating them failed: RuntimeError: fixture defect", (run / "report.md").read_text())

    def test_unreadable_requirements_still_give_a_receipt(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import build, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / "requirements" / "requirements.json").write_text("{")
            receipt = validate(item, Path(output) / "run", self.registry)
            report = (Path(output) / "run" / "report.md").read_text()
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        checks = _checks(receipt)
        for check_id in ("v3.golden-cases", "v4.corners-cases"):
            with self.subTest(check_id):
                self.assertEqual((checks[check_id]["verdict"], checks[check_id]["reason_code"]),
                                 ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))
        self.assertIn("No per-requirement results were written", report)

    def test_a_run_that_wrote_no_results_has_none_to_regenerate(self):
        from ecad_model.dataset import build, regenerate_results, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / "requirements" / "requirements.json").write_text("{")
            validate(item, Path(output) / "run", self.registry)
            with self.assertRaisesRegex(ValueError, "the run wrote no results to regenerate: "
                                                    "requirements/requirements.json could not be read"):
                regenerate_results(item, Path(output) / "run", self.registry)

    def test_a_case_document_the_requirements_no_longer_compile_is_removed_and_never_run(self):
        from ecad_model.dataset import Item, _derive, build, reproducibility, validate

        with _scratch() as directory:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            corners = item / "validation" / "corners" / "cases.json"
            stale = corners.read_bytes()
            _write_requirements(item, [])
            build(item, self.registry)
            self.assertFalse(corners.exists(), "build removes a case document it no longer compiles")
            corners.write_bytes(stale)
            self.assertIn("validation/corners/cases.json: committed, but a fresh derivation compiles no such document",
                          reproducibility(Item(item), _derive(Item(item), self.registry)))
            with tempfile.TemporaryDirectory() as output, \
                    mock.patch("ecad_validation.adapters.hdl.HDLAdapter.run", side_effect=AssertionError("ran")):
                receipt = validate(item, Path(output) / "run", self.registry)
        checks = _checks(receipt)
        self.assertNotIn("v4.REQ-DIG-001", checks)
        self.assertEqual((checks["v4.corners-cases"]["verdict"], checks["v4.corners-cases"]["reason_code"]),
                         ("BLOCKED", "CORNERS_EVIDENCE_MISSING"))
        self.assertEqual(checks["v2.dataset-reproduction"]["verdict"], "FAIL")

    def test_a_result_names_the_check_that_stood_in_when_none_could_be_named(self):
        """Ids that collide cannot each have a check of their own: one gate-level
        check stands in, and each result names it."""
        from ecad_model.dataset import validate

        from ecad_model.dataset import build

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)  # the committed model the results read
            _write_requirements(item, [REQUIREMENT, REQUIREMENT])
            receipt = validate(item, Path(output) / "run", self.registry)
            rows = json.loads((Path(output) / "run" / "results.json").read_text())["results"]
        stand_in = _checks(receipt)["v4.corners-cases"]
        self.assertEqual((stand_in["verdict"], stand_in["reason_code"]), ("BLOCKED", "DERIVATION_NOT_AVAILABLE"))
        self.assertEqual([(r["check_id"], r["status"]) for r in rows], [("v4.corners-cases", "BLOCKED")] * 2)

    def test_a_requirement_added_without_a_rebuild_is_blocked_not_lost(self):
        from ecad_model.dataset import build, validate
        from ecad_model.schemas import validate as validate_schema

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            _write_requirements(item, [REQUIREMENT, {**REQUIREMENT, "requirement_id": "REQ-DIG-002"}])
            with _no_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _checks(receipt)
        self.assertEqual((checks["v4.REQ-DIG-002"]["verdict"], checks["v4.REQ-DIG-002"]["reason_code"]),
                         ("BLOCKED", "COMMITTED_CASE_MISSING"))
        self.assertEqual(checks["v2.dataset-reproduction"]["verdict"], "FAIL")
        self.assertEqual({r["requirement"]: r["check_id"] for r in results["results"]},
                         {"REQ-DIG-001": "v4.REQ-DIG-001", "REQ-DIG-002": "v4.REQ-DIG-002"})

    def test_a_stale_case_for_a_requirement_now_blocked_is_discarded_not_duplicated(self):
        from ecad_model.dataset import build, validate

        class Unknowable(VerilogFixtureAdapter):
            """The same HDL, read by a parser that no longer establishes a port count."""

            def extract(self, *args, **kwargs):
                extraction = super().extract(*args, **kwargs)
                for component in extraction.model["components"]:
                    component["domains"]["digital"]["port_count"] = quantity(
                        None, "1", Status.UNKNOWN, source("computation", "fixture"), note="no longer read")
                return extraction

        limited = {**REQUIREMENT, "limit": {"quantity": "components/blinker/domains/digital/port_count"}}
        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [limited])
            build(item, self.registry)  # compiles a case for REQ-DIG-001
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", {**REGISTRY, "digital": Unknowable()})
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        checks = [c for g in receipt["gates"] for c in g["checks"] if c["check_id"] == "v4.REQ-DIG-001"]
        self.assertEqual(len(checks), 1, "one check per requirement, never a stale one beside the fresh one")
        self.assertEqual((checks[0]["verdict"], checks[0]["reason_code"]), ("BLOCKED", "MISSING_REQUIRED_INPUT"))
        self.assertIn("validation/corners/cases.json still holds a case REQ-DIG-001, compiled before; "
                      "it was not counted", checks[0]["findings"])
        [row] = results["results"]
        self.assertEqual((row["status"], row["expected_value"], row["applied_bound"]), ("BLOCKED", None, None),
                         "the fresh derivation found the limit without a value; the result does not claim one")


class TestBothGatesThroughTheAdapter(unittest.TestCase):
    """The V3 half of the protocol, and the engine's PASS paths, through a
    stand-in for the Icarus adapter."""

    def setUp(self):
        self.registry = {**REGISTRY, "digital": VerilogFixtureAdapter()}

    def test_a_reference_and_a_requirement_run_and_give_their_results(self):
        from ecad_model.dataset import build, validate
        from ecad_model.schemas import validate as validate_schema

        tolerant = {**REQUIREMENT, "requirement_id": "REQ-DIG-002", "tolerance": 0.5}
        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT, tolerant])
            _write_requirements(item, [REQUIREMENT, tolerant], [REFERENCE])
            build(item, self.registry)
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _checks(receipt)
        self.assertEqual((checks["v3.REF-DIG-001"]["verdict"], checks["v3.REF-DIG-001"]["reason_code"]),
                         ("PASS", "GOLDEN_COMPARISON_PASSED"))
        self.assertEqual((checks["v4.REQ-DIG-001"]["verdict"], checks["v4.REQ-DIG-001"]["reason_code"]),
                         ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT"))
        rows = {r["requirement"]: r for r in results["results"]}
        reference = rows["REF-DIG-001"]
        self.assertEqual((reference["kind"], reference["status"], reference["operator"], reference["applied_bound"]),
                         ("reference", "PASS", "within", {"value": 3.0, "absolute_tolerance": 0.5}))
        self.assertEqual((reference["simulator"], reference["simulator_version"], reference["measured_value"]),
                         ("iverilog", "stand-in 0", 3.0))
        self.assertEqual(reference["inputs"], [{"path": "components/blinker/domains/digital/port_count", "status": "DERIVED"}])
        self.assertEqual(reference["cad_components"], ["blinker"])
        self.assertEqual((rows["REQ-DIG-001"]["operator"], rows["REQ-DIG-001"]["tolerance"],
                          rows["REQ-DIG-001"]["applied_bound"]), (">=", 0.0, {"minimum": 3}))
        # A tolerance moves the bound the comparator applied, and the result says so.
        self.assertEqual((rows["REQ-DIG-002"]["tolerance"], rows["REQ-DIG-002"]["applied_bound"],
                          rows["REQ-DIG-002"]["expected_value"]), (0.5, {"minimum": 2.5}, 3))

    def test_a_null_input_blocks_a_reference_as_it_blocks_a_requirement(self):
        """The committed model the cases ran on says an input has no value: the
        stand-in's PASS is not a result, in V3 as in V4."""
        from ecad_model.dataset import build, validate
        from ecad_model.schemas import validate as validate_schema

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            _write_requirements(item, [REQUIREMENT], [REFERENCE])
            build(item, self.registry)
            path = item / "derived" / "engineering_model.json"
            model = json.loads(path.read_text())
            model["components"][0]["domains"]["digital"]["port_count"] = quantity(
                None, "1", Status.UNKNOWN, source("computation", "fixture"), note="hand edit")
            path.write_text(json.dumps(model, indent=2) + "\n")
            with _passing_icarus():
                receipt = validate(item, Path(output) / "run", self.registry)
            results = json.loads((Path(output) / "run" / "results.json").read_text())
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _checks(receipt)
        for check_id in ("v3.REF-DIG-001", "v4.REQ-DIG-001"):
            with self.subTest(check_id):
                self.assertEqual((checks[check_id]["verdict"], checks[check_id]["reason_code"]),
                                 ("BLOCKED", "MISSING_REQUIRED_INPUT"))
                self.assertIn("UNKNOWN: components/blinker/domains/digital/port_count", checks[check_id]["findings"])


class TestResultRules(unittest.TestCase):
    """build_results on a hand-made run: what each result may and may not claim."""

    def test_a_measurement_is_borrowed_only_by_a_requirement_blocked_on_its_limit(self):
        from ecad_model.results import build_results

        origin = source("computation", "fixture")
        model = {
            "model_version": "1.0.0", "design": {"design_id": "blinker_001"}, "joints": [], "relationships": [],
            "unknowns": [], "components": [{"component_id": "blinker", "domains": {"digital": {
                "port_count": quantity(3, "1", Status.DERIVED, origin, derived_from=["fixture:blinker.v"]),
                "max_ports": quantity(None, "1", Status.UNKNOWN, origin, note="not chosen"),
            }}}],
        }
        requirements = {"reference_values": [], "requirements": [
            {**REQUIREMENT, "requirement_id": "MEASURED"},
            {**REQUIREMENT, "requirement_id": "CRASHED"},
            {**REQUIREMENT, "requirement_id": "TEXT"},
            {**REQUIREMENT, "requirement_id": "UNSET", "operator": "<=",
             "limit": {"quantity": "components/blinker/domains/digital/max_ports"}},
        ]}

        def check(entry_id, verdict, metrics):
            return {"check_id": f"v4.{entry_id}", "verdict": verdict, "reason_code": "FIXTURE", "findings": [],
                    "metrics": metrics, "evidence": []}

        def run(checks):
            receipt = {"gates": [{"gate": "V4", "checks": checks}], "completed_at": "2026-09-26T00:00:00Z",
                       "source": {"input_sha256": "0" * 64, "dirty": False}}
            case = {"arguments": [], "seed": 0, "metric_limits": {"port_count": {"minimum": 3}}}
            document = build_results(
                sample_id="blinker_001", receipt=receipt, receipt_sha256="0" * 64, requirements=requirements,
                model=model, model_sha256="0" * 64, adapter=VerilogFixtureAdapter(),
                cases={("V4", "MEASURED"): case, ("V4", "CRASHED"): case, ("V4", "TEXT"): case},
                # Only a check that ran its case has an execution record, and only
                # such a check can lend a measurement.
                executions={f"v4.{entry_id}": {"adapter": "iverilog", "case_id": entry_id, "command": [],
                                               "tool_version": "stand-in 0"} for entry_id in ("MEASURED", "CRASHED", "TEXT")},
                environment_record={})
            return {row["requirement"]: row for row in document["results"]}

        rows = run([check("MEASURED", "PASS", {"port_count": 3}), check("CRASHED", "INCONCLUSIVE", {}),
                    check("TEXT", "INCONCLUSIVE", {"port_count": "three"}), check("UNSET", "BLOCKED", {})])
        self.assertEqual((rows["MEASURED"]["measured_value"], rows["MEASURED"]["measured_by"]), (3, "v4.MEASURED"))
        # Its own run produced nothing: another check's number is not its measurement.
        self.assertEqual((rows["CRASHED"]["measured_value"], rows["CRASHED"]["measured_by"]), (None, None))
        self.assertEqual((rows["TEXT"]["measured_value"], rows["TEXT"]["measured_by"]), (None, None))
        self.assertIn("metric port_count is not a number: 'three'", rows["TEXT"]["findings"])
        # Blocked only because its limit has no value: what was measured still stands, and by whom.
        self.assertEqual((rows["UNSET"]["measured_value"], rows["UNSET"]["measured_by"]), (3, "v4.MEASURED"))
        self.assertIsNone(rows["UNSET"]["expected_value"])
        with self.assertRaisesRegex(ValueError, "no check in the receipt decided UNSET"):
            run([check("MEASURED", "PASS", {"port_count": 3}), check("CRASHED", "INCONCLUSIVE", {}),
                 check("TEXT", "INCONCLUSIVE", {})])


class TestUntrustedRunsAndItems(unittest.TestCase):
    """A dataset item and a run directory can both come from elsewhere."""

    def setUp(self):
        self.registry = {**REGISTRY, "digital": VerilogFixtureAdapter()}

    def _run(self, directory: str, output: str) -> Tuple[Path, Path]:
        from ecad_model.dataset import build, validate

        item = _digital_sample(directory, [REQUIREMENT])
        build(item, self.registry)
        run = Path(output) / "run"
        with _no_icarus():
            validate(item, run, self.registry)
        return item, run

    def test_results_regenerate_identically_anywhere_from_what_the_run_recorded(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            written = (run / "results.json").read_bytes()
            receipt = json.loads((run / "receipt.json").read_text())
            self.assertEqual(regenerate_results(item, run, self.registry), written)
            with mock.patch("platform.system", return_value="Plan9"), \
                    mock.patch("platform.python_version", return_value="2.7.18"):
                self.assertEqual(regenerate_results(item, run, self.registry), written,
                                 "the environment is the run's, not the regenerating process's")
        [row] = json.loads(written)["results"]
        self.assertEqual(row["environment"]["tools"], {t["tool_id"]: t["version"] for t in receipt["tools"]})
        constraints = REPO_ROOT / "tools" / "constraints-cad.txt"
        self.assertEqual(row["environment"]["constraints_sha256"], hashlib.sha256(constraints.read_bytes()).hexdigest())

    def test_an_item_changed_after_the_run_is_not_regenerated(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            path = item / "requirements" / "requirements.json"
            document = json.loads(path.read_text())
            document["requirements"][0]["title"] = "edited after the run"
            path.write_text(json.dumps(document, indent=2) + "\n")
            with self.assertRaisesRegex(ValueError, "has changed since the run"):
                regenerate_results(item, run, self.registry)

    def test_forged_or_misplaced_evidence_is_refused(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            receipt = json.loads((run / "receipt.json").read_bytes())

            def is_execution_record(evidence):
                try:
                    return "case_id" in json.loads((run / evidence["path"]).read_bytes())
                except ValueError:
                    return False

            execution = next(e for e in _checks(receipt)["v4.REQ-DIG-001"]["evidence"] if is_execution_record(e))
            stored = run / execution["path"]
            original = stored.read_bytes()
            record = json.loads(original)
            stored.write_bytes(json.dumps({**record, "tool_version": "9.9.9"}).encode())
            with self.assertRaisesRegex(ValueError, "do not match the digest"):
                regenerate_results(item, run, self.registry)
            stored.write_bytes(original)
            # A path the receipt schema accepts, holding the right bytes, but not
            # the content address of the digest: refused, not followed.
            (run / "evidence" / "elsewhere.json").write_bytes(original)
            execution["path"] = "evidence/elsewhere.json"
            (run / "receipt.json").write_bytes(json.dumps(receipt).encode())
            with self.assertRaisesRegex(ValueError, "is not its content address"):
                regenerate_results(item, run, self.registry)
            del receipt["gates"]
            (run / "receipt.json").write_bytes(json.dumps(receipt).encode())
            with self.assertRaises(ValueError, msg="a receipt is schema-checked before it is used"):
                regenerate_results(item, run, self.registry)

    def test_a_receipt_nested_too_deeply_is_refused_not_a_crash(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            receipt = json.loads((run / "receipt.json").read_bytes())
            receipt["gates"][0]["checks"][0]["summary"] = "x"
            text = json.dumps(receipt)
            (run / "receipt.json").write_text(text.replace('"summary": "x"', '"summary": ' + "[" * 100000 + "]" * 100000, 1))
            with self.assertRaises(ValueError):
                regenerate_results(item, run, self.registry)

    def test_a_malformed_environment_record_is_refused(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            receipt = json.loads((run / "receipt.json").read_bytes())
            pinned = _checks(receipt)["v0.pinned-clean-source"]
            [entry] = pinned["evidence"]
            record = json.loads((run / entry["path"]).read_bytes())
            del record["environment"]["os"]
            data = json.dumps(record).encode()
            digest = hashlib.sha256(data).hexdigest()
            (run / "evidence" / "sha256" / digest).write_bytes(data)
            entry.update(path=f"evidence/sha256/{digest}", sha256=digest, size_bytes=len(data))
            (run / "receipt.json").write_bytes(json.dumps(receipt).encode())
            with self.assertRaisesRegex(ValueError, "environment record is malformed"):
                regenerate_results(item, run, self.registry)

    def test_a_forged_case_document_is_not_read_for_results(self):
        """A run directory whose receipt cites, with a consistent digest, a case
        document that breaks its schema: the results do not read it."""
        from ecad_model.dataset import regenerate_results
        from ecad_model.requirements import CASES_SCHEMA

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            receipt = json.loads((run / "receipt.json").read_bytes())

            def is_case_document(evidence):
                try:
                    return json.loads((run / evidence["path"]).read_bytes()).get("$schema") == CASES_SCHEMA
                except ValueError:
                    return False

            [cited] = [e for e in _checks(receipt)["v4.REQ-DIG-001"]["evidence"] if is_case_document(e)]
            data = json.dumps({"$schema": CASES_SCHEMA, "gate": "V4",
                               "cases": [{"id": "REQ-DIG-001", "metric_limits": "x", "seed": "y"}]}).encode()
            digest = hashlib.sha256(data).hexdigest()
            (run / "evidence" / "sha256" / digest).write_bytes(data)
            cited.update(path=f"evidence/sha256/{digest}", sha256=digest, size_bytes=len(data))
            (run / "receipt.json").write_bytes(json.dumps(receipt).encode())
            [row] = json.loads(regenerate_results(item, run, self.registry))["results"]
        self.assertEqual((row["applied_bound"], row["configuration"]["seed"]), (None, None))

    def test_a_model_outside_the_receipt_s_digest_is_not_regenerated_from(self):
        from ecad_model.dataset import build, regenerate_results, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT])
            build(item, self.registry)
            (item / ".gitignore").write_text("derived/engineering_model.json\n")
            with _no_icarus():
                validate(item, Path(output) / "run", self.registry)
            with self.assertRaisesRegex(ValueError, "not among the files the receipt's digest covers"):
                regenerate_results(item, Path(output) / "run", self.registry)

    def test_a_record_is_the_execution_of_the_check_that_cites_it_or_nothing(self):
        from ecad_model.dataset import build, regenerate_results, validate

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item = _digital_sample(directory, [REQUIREMENT, {**REQUIREMENT, "requirement_id": "REQ-DIG-002"}])
            build(item, self.registry)
            run = Path(output) / "run"
            with _no_icarus():
                receipt = validate(item, run, self.registry)
            checks = _checks(receipt)

            def record_of(check_id):
                for evidence in checks[check_id]["evidence"]:
                    try:
                        if "case_id" in json.loads((run / evidence["path"]).read_bytes()):
                            return evidence
                    except ValueError:
                        continue
                raise AssertionError(check_id)

            own, other = record_of("v4.REQ-DIG-001"), record_of("v4.REQ-DIG-002")
            own.update(path=other["path"], sha256=other["sha256"], size_bytes=other["size_bytes"])
            (run / "receipt.json").write_bytes(json.dumps(receipt).encode())
            rows = {r["requirement"]: r for r in json.loads(regenerate_results(item, run, self.registry))["results"]}
        self.assertEqual(rows["REQ-DIG-002"]["simulator"], "iverilog")
        self.assertIsNone(rows["REQ-DIG-001"]["simulator"], "another check's execution is not this one's")

    def test_a_run_of_one_item_is_not_regenerated_for_another(self):
        from ecad_model.dataset import regenerate_results

        with _scratch() as directory, tempfile.TemporaryDirectory() as output:
            item, run = self._run(directory, output)
            twin = Path(directory) / "blinker_002"
            shutil.copytree(item, twin)  # the same files, so the same input digest
            with self.assertRaisesRegex(ValueError, "the receipt is for datasets:blinker_001, not datasets:blinker_002"):
                regenerate_results(twin, run, self.registry)

    def test_a_manifest_path_outside_the_item_is_not_read(self):
        from ecad_model.dataset import Item, build, integrity

        with _scratch() as directory:
            item = _digital_sample(directory)
            build(item, self.registry)
            licence = REPO_ROOT / "LICENSE"
            manifest_path = item / "dataset-item.json"
            manifest = json.loads(manifest_path.read_text())
            for path in (str(licence), os.path.relpath(licence, item)):
                forged = json.loads(json.dumps(manifest))
                forged["source"]["artifacts"].append({
                    "path": path, "format": "text", "media_type": "text/plain",
                    "sha256": hashlib.sha256(licence.read_bytes()).hexdigest(), "size_bytes": licence.stat().st_size})
                manifest_path.write_text(json.dumps(forged, indent=2) + "\n")
                with self.subTest(path=path):
                    self.assertIn(f"{path}: recorded in dataset-item.json outside the item; it is not read",
                                  integrity(Item(item)))

    def test_an_item_is_refused_before_it_is_read(self):
        from ecad_model.dataset import Item

        with _scratch() as directory:
            item = _digital_sample(directory)
            link = Path(directory) / "linked_001"
            link.symlink_to(item, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "the item directory is a symlink"):
                Item(link)
            provenance = json.loads((item / "source" / "provenance.json").read_text())
            provenance["artifacts"].append({"path": "source/missing.v", "format": "verilog"})
            (item / "source" / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
            with self.assertRaisesRegex(ValueError, "declares source/missing.v, which does not exist"):
                Item(item)
        with tempfile.TemporaryDirectory() as outside:
            item = _digital_sample(outside)
            with self.assertRaisesRegex(ValueError, "resolves outside the repository"):
                Item(item)

    def test_a_source_git_does_not_list_is_refused_not_skipped(self):
        from ecad_model.dataset import Item

        with _scratch() as directory:
            item = _digital_sample(directory)
            (item / ".gitignore").write_text("*.v\n")
            with self.assertRaisesRegex(ValueError, "git does not list the item's own sources"):
                Item(item).files()


if __name__ == "__main__":
    unittest.main()
