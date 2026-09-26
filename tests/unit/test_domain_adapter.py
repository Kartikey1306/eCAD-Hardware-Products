"""The domain adapter protocol, exercised by an artefact-first domain.

The only production adapter is mechanical, whose engineering model is built
from a STEP assembly. The protocol claims more: that a domain whose artefact
*is* its structure -- HDL, a netlist -- plugs into the same runner without
the runner knowing it. This test-only adapter reads a Verilog file, so it
needs no CAD kernel and no simulator, and proves the claim on a sample with
no STEP file:

- the base types carry a non-CAD source, and build writes a schema-valid
  model and manifest;
- domain status comes from the registry: the fixture's domain is AVAILABLE,
  mechanical is NOT_APPLICABLE (an adapter exists, but the sample has no STEP),
  every other domain NOT_IMPLEMENTED;
- check reproduces the derivation, validate writes a schema-valid receipt;
- without the adapter registered, build refuses and validate is BLOCKED.

It is a fixture, not a digital domain: it validates nothing about the HDL.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ecad_model.domains import REGISTRY, CaseTarget, DerivedFile, Extraction, Metric, SourceArtifact  # noqa: E402
from ecad_model.quantity import Status, quantity, source  # noqa: E402

MECHANICAL_ITEM = REPO_ROOT / "datasets" / "cad" / "robotic_joint_001"
VERILOG = """module blinker (input clk, input rst, output reg led);
  always @(posedge clk) led <= rst ? 1'b0 : ~led;
endmodule
"""


class VerilogFixtureAdapter:
    """Reads module names and port counts from Verilog. Test-only."""

    domain = "digital"
    formats = frozenset({"verilog"})
    description = "fixture: module port counts read from Verilog (test-only)"

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
                       "sources": [{"path": repo_path, "format": "verilog",
                                    "sha256": hashlib.sha256((root / hdl.path).read_bytes()).hexdigest()}]},
            "components": components, "joints": [], "relationships": [], "unknowns": [],
        }
        return Extraction(model=model)

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]:
        modules = {c["component_id"]: c["domains"]["digital"]["port_count"]["value"] for c in model["components"]}
        return [DerivedFile(path=f"derived/digital/{sample_id}.modules.json",
                            data=(json.dumps(modules, indent=2, sort_keys=True) + "\n").encode(),
                            role="domain_model", media_type="application/json", producer="fixture",
                            version="0", derived_from=("derived/engineering_model.json",))]

    def case_target(self, sample_id: str) -> CaseTarget:
        return CaseTarget(adapter="iverilog", inputs=("source/blinker.v",), arguments=lambda scenario: [])

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
        raise ValueError(f"unknown derivation {derivation!r}")

    def metrics(self) -> Dict[str, Metric]:
        return {}

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
        return []

    def reference_inputs(self, model: Dict[str, Any], derivation: str, scenario: Dict[str, Any]) -> List[str]:
        return []

    def check_requirements(self, requirements: Dict[str, Any]) -> None:
        if requirements["reference_values"] or requirements["requirements"]:
            raise ValueError("the fixture implements no scenarios")

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]:
        return []


def _digital_sample(directory: str) -> Path:
    """A sample whose only source is Verilog: no STEP file anywhere."""
    item = Path(directory) / "blinker_001"
    (item / "source").mkdir(parents=True)
    (item / "design").mkdir()
    (item / "requirements").mkdir()
    (item / "source" / "blinker.v").write_text(VERILOG)
    provenance = json.loads((MECHANICAL_ITEM / "source" / "provenance.json").read_text())
    provenance.pop("generator")  # the fixture has no authoring script
    provenance.update(domain="digital", artifacts=[{"path": "source/blinker.v", "format": "verilog"}],
                      artifact_type="hdl_source", units="none", coordinate_system="none",
                      description="Test fixture: a one-module Verilog design.")
    (item / "source" / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (item / "design" / "annotations.json").write_text(json.dumps({
        "$schema": "https://embeddedos.org/schemas/engineering-model/v1/design-annotations.schema.json",
        "annotations_version": "1.0.0", "design_id": "blinker_001", "materials": {}, "parts": {},
        "joints": [], "attachments": [], "components_without_cad": [], "relationships": []}, indent=2) + "\n")
    (item / "requirements" / "requirements.json").write_text(json.dumps({
        "$schema": "https://embeddedos.org/schemas/engineering-model/v1/engineering-requirements.schema.json",
        "requirements_version": "1.0.0", "design_id": "blinker_001",
        "reference_values": [], "requirements": []}, indent=2) + "\n")
    return item


class TestArtefactFirstDomain(unittest.TestCase):
    def setUp(self):
        self.registry = {**REGISTRY, "digital": VerilogFixtureAdapter()}

    def test_a_sample_with_no_step_file_builds_checks_and_validates(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import build, check, validate
        from ecad_model.schemas import validate as validate_schema

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _digital_sample(directory)
            written = build(item, self.registry)
            self.assertIn("derived/digital/blinker_001.modules.json", written)
            self.assertFalse(list(item.rglob("*.step")))
            model = json.loads((item / "derived" / "engineering_model.json").read_text())
            validate_schema(model, "engineering-model/v1/engineering-model")
            self.assertEqual([c["component_id"] for c in model["components"]], ["blinker"])
            manifest = json.loads((item / "dataset-item.json").read_text())
            validate_schema(manifest, "cad-dataset/v1/dataset-item")
            status = {d["domain"]: d["status"] for d in manifest["domains"]}
            self.assertEqual(status.pop("digital"), "AVAILABLE")
            self.assertEqual(status.pop("mechanical"), "NOT_APPLICABLE")
            self.assertEqual(set(status.values()), {"NOT_IMPLEMENTED"})
            self.assertEqual(manifest["source"]["artifacts"][0]["format"], "verilog")

            self.assertEqual(check(item, self.registry), [])
            with tempfile.TemporaryDirectory() as output:
                receipt = validate(item, Path(output) / "run", self.registry)
            validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
            checks = {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}
            for check_id in ("v0.dataset-schemas-and-hashes", "v1.digital.extraction-and-sanity",
                             "v2.dataset-reproduction", "v2.digital.model-invariants"):
                with self.subTest(check_id):
                    self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
            # No references or requirements: nothing to run, and the receipt says so.
            self.assertEqual(checks["v3.golden-cases"]["verdict"], "BLOCKED")
            self.assertFalse(receipt["eligible_for_ebuild"])

    def test_a_requirement_of_another_domain_is_refused_not_compiled(self):
        from ecad_model.dataset import build

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _digital_sample(directory)
            path = item / "requirements" / "requirements.json"
            requirements = json.loads(path.read_text())
            mechanical = json.loads((MECHANICAL_ITEM / "requirements" / "requirements.json").read_text())
            requirements["requirements"] = mechanical["requirements"][:1]
            path.write_text(json.dumps(requirements, indent=2) + "\n")
            with self.assertRaisesRegex(ValueError, "requirements for mechanical cannot be compiled by the digital adapter"):
                build(item, self.registry)

    def test_without_its_adapter_the_domain_is_not_implemented(self):
        from ecad_model.dataset import build, validate

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _digital_sample(directory)
            with self.assertRaisesRegex(ValueError, "digital is NOT_IMPLEMENTED"):
                build(item)
            with tempfile.TemporaryDirectory() as output:
                receipt = validate(item, Path(output) / "run")
            v1 = next(c for g in receipt["gates"] for c in g["checks"] if c["check_id"].startswith("v1."))
            self.assertEqual((v1["check_id"], v1["verdict"], v1["reason_code"]),
                             ("v1.digital.extraction-and-sanity", "BLOCKED", "DOMAIN_NOT_IMPLEMENTED"))


if __name__ == "__main__":
    unittest.main()
