"""CAD extraction and end-to-end V0-V4 on datasets/cad/robotic_joint_001.

These need the OpenCASCADE kernel (cadquery-ocp) and MuJoCo, listed in
tools/requirements-cad.txt. Without them the tests skip and say why. With
ECAD_REQUIRE_CAD_TOOLS=1 -- set by the CI job that installs them -- a missing
tool is a failure instead, so the skip can never go silent where it matters.

Expected geometry is computed by hand from the design dimensions in
source/generate_step.py, never by calling the extractor.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

ITEM = REPO_ROOT / "datasets" / "cad" / "robotic_joint_001"
STEP = ITEM / "source" / "robotic_joint_001.step"


def require(*modules: str) -> None:
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if not missing:
        return
    message = f"needs {', '.join(missing)} (pip install -r tools/requirements-cad.txt)"
    if os.environ.get("ECAD_REQUIRE_CAD_TOOLS") == "1":
        raise AssertionError(f"ECAD_REQUIRE_CAD_TOOLS=1 but this environment {message}")
    raise unittest.SkipTest(message)


def mujoco_on_path() -> None:
    """The mujoco adapter probes `python3` on PATH, not the running interpreter."""
    require("mujoco")
    probe = subprocess.run(["python3", "-c", "import mujoco"], capture_output=True)
    if probe.returncode != 0:
        message = "python3 on PATH cannot import mujoco (run with the tools' interpreter first on PATH)"
        if os.environ.get("ECAD_REQUIRE_CAD_TOOLS") == "1":
            raise AssertionError(message)
        raise unittest.SkipTest(message)


class TestStepExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require("OCP")
        from ecad_model.importers import importer_for

        cls.extraction = importer_for(STEP).extract(STEP, REPO_ROOT)
        cls.parts = {part["name"]: part for part in cls.extraction["parts"]}

    def test_extraction_conforms_to_its_schema_and_binds_the_bytes(self):
        import hashlib

        from ecad_model.schemas import validate

        validate(self.extraction, "cad-dataset/v1/cad-extraction")
        self.assertEqual(self.extraction["source"]["sha256"], hashlib.sha256(STEP.read_bytes()).hexdigest())
        self.assertEqual(self.extraction["length_unit"], "mm")

    def test_volumes_match_the_design_dimensions(self):
        expected = {
            "base_plate": 420 * 100 * 20,
            "pillar": 60 * 50 * 210 - math.pi * 6.5**2 * 50,  # 50 mm deep bore, r 6.5
            "shaft": math.pi * 6.0**2 * 100,
            "link": 340 * 20 * 30 - math.pi * 6.0**2 * 20,  # 20 mm deep bore, r 6
            "payload": 40 * 24 * 40,
        }
        self.assertEqual(sorted(self.parts), sorted(expected))
        for name, volume in expected.items():
            with self.subTest(name):
                self.assertAlmostEqual(self.parts[name]["volume"], volume, delta=volume * 1e-9)

    def test_placements_are_the_assembly_transforms(self):
        self.assertEqual(self.parts["link"]["translation"], [0.0, 33.0, 200.0])
        self.assertEqual(self.parts["payload"]["translation"], [275.0, 31.0, 215.0])
        rotation = self.parts["shaft"]["rotation"]
        expected = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]  # local +Z onto assembly +Y
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(rotation[i][j], expected[i][j], places=12)

    def test_unit_density_inertia_is_about_the_centre_of_mass(self):
        """Verified convention: OCCT's MatrixOfInertia is about the centre of mass."""
        payload = self.parts["payload"]
        volume, (a, b, c) = 40 * 24 * 40, (40, 24, 40)
        diagonal = [volume * (b * b + c * c) / 12, volume * (a * a + c * c) / 12, volume * (a * a + b * b) / 12]
        for axis in range(3):
            self.assertAlmostEqual(payload["inertia_about_com_unit_density_local"][axis][axis],
                                   diagonal[axis], delta=diagonal[axis] * 1e-9)

    def test_joint_axis_is_recovered_from_the_shaft_geometry(self):
        from ecad_model.builder import build_engineering_model

        annotations = json.loads((ITEM / "design" / "annotations.json").read_text())
        model = build_engineering_model(
            self.extraction, annotations, design_name="x", revision="1", extraction_ref="x",
            annotations_ref="x", annotations_sha256="0" * 64,
        )
        joint = model["joints"][0]
        self.assertEqual(joint["axis"]["value"], [0.0, 1.0, 0.0])
        self.assertEqual(joint["axis"]["status"], "DERIVED")
        for got, want in zip(joint["origin"]["value"], [0.0, 0.015, 0.2]):
            self.assertAlmostEqual(got, want, places=12)


class TestUnitConversion(unittest.TestCase):
    """Regression: GetLengthUnit_s returns only a bool in cadquery-ocp 8.0. Reading
    that as metres-per-unit would have scaled every mass by 1e9. The document unit
    is now pinned instead; the same cube written in three units must agree."""

    def test_the_same_cube_in_three_units_extracts_identically(self):
        require("OCP")
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.Interface import Interface_Static
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_AsIs
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Pnt

        from ecad_model.importers import importer_for

        self.addCleanup(Interface_Static.SetCVal_s, "write.step.unit", "MM")  # process-global state
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            root = Path(directory)
            for unit, raw in (("MM", "10."), ("M", "1.E-02"), ("INCH", "0.393700787")):
                document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
                tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
                assembly = tool.NewShape()
                part = tool.AddShape(BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10.0, 10.0, 10.0).Shape(), False)
                TDataStd_Name.Set_s(part, TCollection_ExtendedString("cube"))
                tool.AddComponent(assembly, part, TopLoc_Location())
                tool.UpdateAssemblies()
                Interface_Static.SetCVal_s("write.step.unit", unit)
                writer = STEPCAFControl_Writer()
                writer.Transfer(document, STEPControl_AsIs)
                path = root / f"cube_{unit}.step"
                writer.Write(str(path))
                with self.subTest(unit):
                    self.assertIn(raw, path.read_text(), "the file must store unit-scaled coordinates")
                    extraction = importer_for(path).extract(path, REPO_ROOT)
                    self.assertAlmostEqual(extraction["parts"][0]["volume"], 1000.0, places=6)


class TestIsolation(unittest.TestCase):
    def test_a_corrupt_step_file_fails_cleanly_in_the_child(self):
        require("OCP")
        from ecad_model.importers import importer_for

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            path = Path(directory) / "corrupt.step"
            path.write_bytes(b"ISO-10303-21;\nHEADER;\n" + b"\x00\xff garbage " * 200)
            from ecad_model.importers import ExtractionError

            with self.assertRaises(ExtractionError) as caught:
                importer_for(path).extract(path, REPO_ROOT)
            # Unreadable content is a decisive refusal, not "unavailable".
            self.assertEqual(caught.exception.kind, "rejected")
            self.assertIn("could not read the file as STEP", str(caught.exception))


class TestDatasetItem(unittest.TestCase):
    def setUp(self):
        require("OCP")

    def copy(self, directory: str) -> Path:
        # Inside the repository, so repository-relative paths still resolve.
        target = Path(directory) / "robotic_joint_001"
        shutil.copytree(ITEM, target, ignore=shutil.ignore_patterns("__pycache__"))
        return target

    def test_committed_item_is_intact_and_reproducible(self):
        from ecad_model.dataset import check

        self.assertEqual(check(ITEM), [])

    def test_a_changed_cad_file_breaks_integrity(self):
        from ecad_model.dataset import Item, integrity

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = self.copy(directory)
            step = item / "source" / "robotic_joint_001.step"
            step.write_bytes(step.read_bytes().replace(b"'payload'", b"'payloaD'", 1))
            self.assertIn("source/robotic_joint_001.step: bytes do not match the recorded hash",
                          integrity(Item(item)))

    def test_an_edited_derived_value_no_longer_reproduces(self):
        from ecad_model.dataset import Item, reproducibility

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = self.copy(directory)
            path = item / "derived" / "engineering_model.json"
            model = json.loads(path.read_text())
            link = next(c for c in model["components"] if c["component_id"] == "link")
            link["physical"]["mass"]["value"] *= 1.01
            path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
            problems = reproducibility(Item(item))
            self.assertTrue(any("engineering_model.json" in problem and "mass" in problem for problem in problems),
                            problems)


class TestCaseScript(unittest.TestCase):
    """Properties of simulation/joint_dynamics.py that the nominal design cannot exercise."""

    def test_collision_proxies_never_push_on_the_dynamics(self):
        """At poses where the proxies penetrate, holding torque is still pure gravity.

        The nominal design has no contacts, so without this test the contact
        disable in the dynamics scenarios could be deleted with everything green.
        """
        require("mujoco")
        import importlib.util as util
        import re

        import mujoco

        sys.dont_write_bytecode = True  # keep __pycache__ out of the dataset item
        spec = util.spec_from_file_location("joint_dynamics", ITEM / "simulation" / "joint_dynamics.py")
        script = util.module_from_spec(spec)
        spec.loader.exec_module(script)

        xml = (ITEM / "derived" / "mechanical" / "robotic_joint_001.mjcf.xml").read_text()
        widened = re.sub(r'range="([^ ]+) [^"]+"', lambda m: f'range="{m.group(1)} {math.radians(40)}"', xml)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widened.xml"
            path.write_text(widened)
            model = mujoco.MjModel.from_xml_path(str(path))
            data = mujoco.MjData(model)
            data.qpos[0] = math.radians(40)
            mujoco.mj_forward(model, data)
            self.assertGreater(data.ncon, 0, "the fixture must actually put the proxies into contact")
            metrics = script.static_sweep(script.load(str(path), {}), {})
            gravity_only = mujoco.MjModel.from_xml_path(str(path))
            gravity_only.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONTACT
            reference = mujoco.MjData(gravity_only)
            worst = 0.0
            for q in __import__("numpy").linspace(*gravity_only.jnt_range[0], script.SWEEP_SAMPLES):
                reference.qpos[0], reference.qvel[:], reference.qacc[:] = q, 0.0, 0.0
                mujoco.mj_inverse(gravity_only, reference)
                worst = max(worst, abs(float(reference.qfrc_bias[0])))
        self.assertAlmostEqual(metrics["static_torque_max_abs_nm"], worst, places=9)

    def _script(self):
        require("mujoco")
        import importlib.util as util

        sys.dont_write_bytecode = True  # keep __pycache__ out of the dataset item
        spec = util.spec_from_file_location("joint_dynamics", ITEM / "simulation" / "joint_dynamics.py")
        script = util.module_from_spec(spec)
        spec.loader.exec_module(script)
        return script

    def _model_file(self, directory: str, edit) -> str:
        xml = (ITEM / "derived" / "mechanical" / "robotic_joint_001.mjcf.xml").read_text()
        path = Path(directory) / "model.xml"
        path.write_text(edit(xml))
        return str(path)

    def test_the_free_swing_period_does_not_depend_on_the_time_step(self):
        """The zero crossings are interpolated within a step. Quantised to the
        step instead, the period at a 2 ms step is off by about 7e-5 s, beyond
        the golden's tolerance; interpolated it stays within it."""
        import re

        from ecad_model.domains.mechanical import reference_value

        script = self._script()
        model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        requirements = json.loads((ITEM / "requirements" / "requirements.json").read_text())
        golden = next(r for r in requirements["reference_values"] if r["derivation"] == "small_oscillation_period")
        expected = reference_value(model, "small_oscillation_period", golden["scenario"])[0]
        with tempfile.TemporaryDirectory() as directory:
            path = self._model_file(directory, lambda xml: re.sub(r'timestep="[^"]+"', 'timestep="0.002"', xml))
            period = script.free_swing(script.load(path, {}), golden["scenario"])["small_oscillation_period_s"]
        self.assertLessEqual(abs(period - expected), golden["absolute_tolerance"])

    def test_a_joint_pair_that_cannot_be_checked_reports_no_clearance(self):
        """When the joint's own parent-child pair is excluded -- a joint realised by
        its own child -- the clearance cannot be measured, and the script says so
        instead of reporting a clearance for the other pairs."""
        script = self._script()
        with tempfile.TemporaryDirectory() as directory:
            path = self._model_file(directory, lambda xml: xml.replace(
                "<contact>", '<contact>\n    <exclude body1="base_plate" body2="link"/>', 1))
            metrics = script.rom_sweep(script.load(path, {}), {})
        self.assertEqual(metrics, {"rom_joint_pair_unchecked": 1.0})


class TestEndToEnd(unittest.TestCase):
    """The full pipeline, and proof that its checks can fail."""

    @classmethod
    def setUpClass(cls):
        require("OCP")
        mujoco_on_path()

    def run_item(self, item: Path) -> dict:
        from ecad_model.dataset import validate

        with tempfile.TemporaryDirectory() as output:
            receipt = validate(item, Path(output) / "run")
            self.assertTrue((Path(output) / "run" / "report.md").is_file())
        return {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]} | {"_receipt": receipt}

    def copy_and_rebuild(self, directory: str, mutate) -> Path:
        from ecad_model.dataset import build

        target = Path(directory) / "robotic_joint_001"
        shutil.copytree(ITEM, target, ignore=shutil.ignore_patterns("__pycache__"))
        mutate(target)
        build(target)
        return target

    def test_committed_item_meets_every_measurable_check(self):
        from ecad_validation.contract import validate_document

        checks = self.run_item(ITEM)
        receipt = checks.pop("_receipt")
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        requirements = json.loads((ITEM / "requirements" / "requirements.json").read_text())
        references = [f"v3.{r['reference_id']}" for r in requirements["reference_values"]]
        limited = {f"v4.{r['requirement_id']}": r["illustrative"]
                   for r in requirements["requirements"] if "value" in r["limit"]}
        measurable = [*references, *limited]
        self.assertGreaterEqual(len(measurable), 14)
        for check_id in ("v0.dataset-schemas-and-hashes", "v0.dataset-input-immutability",
                         "v1.mechanical.extraction-and-sanity", "v2.dataset-reproduction",
                         "v2.mechanical.model-invariants", *references):
            with self.subTest(check_id):
                self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
        for check_id, illustrative in limited.items():
            with self.subTest(check_id):
                # Every limit met; one that is illustrative is advisory, not a pass.
                expected = ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT") if illustrative else ("PASS", "CORNER_LIMITS_PASSED")
                self.assertEqual((checks[check_id]["verdict"], checks[check_id]["reason_code"]), expected,
                                 checks[check_id]["findings"])
        for check_id in measurable:
            with self.subTest(binding=check_id):
                # The receipt binds each executed check to the engineering
                # requirement it implements, not only to the gate policy.
                self.assertIn(check_id.split(".", 1)[1], checks[check_id]["requirement_ids"])

        tools = {tool["tool_id"]: tool for tool in receipt["tools"]}
        validator = tools["ecad-validator"]["invocation"]
        self.assertEqual(validator[1:3], ["tools/cad_dataset.py", "validate"])
        self.assertTrue((REPO_ROOT / validator[1]).is_file())
        extraction = json.loads((ITEM / "derived" / "cad_extraction.json").read_text())
        self.assertEqual(tools["opencascade"]["version"], extraction["importer"]["kernel_version"])
        # One record per tool: what every mujoco check shares, not the last check's scenario.
        mujoco = tools["mujoco"]
        self.assertTrue(mujoco["invocation"][-1].endswith(".mjcf.xml"), mujoco["invocation"])
        self.assertFalse(any("--scenario" in part or part.startswith("{") for part in mujoco["invocation"]))

    def test_only_a_real_requirement_can_pass(self):
        """An illustrative limit met is WARNING, which blocks ebuild eligibility;
        the same limit marked as a real requirement is PASS."""
        def make_real(target):
            def mutate(requirements):
                next(r for r in requirements["requirements"] if r["requirement_id"] == "REQ-MECH-001")["illustrative"] = False
            _edit_json(target / "requirements" / "requirements.json", mutate)

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            checks = self.run_item(self.copy_and_rebuild(directory, make_real))
        self.assertEqual(checks["v4.REQ-MECH-001"]["verdict"], "PASS")
        self.assertEqual((checks["v4.REQ-MECH-002"]["verdict"], checks["v4.REQ-MECH-002"]["reason_code"]),
                         ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT"))
        gates = {g["gate"]: g["verdict"] for g in checks["_receipt"]["gates"]}
        self.assertEqual(gates["V4"], "BLOCKED")
        self.assertFalse(checks["_receipt"]["eligible_for_ebuild"])

    def test_the_cross_domain_requirement_is_blocked_on_its_unknown(self):
        checks = self.run_item(ITEM)
        blocked = checks["v4.REQ-XD-001"]
        self.assertEqual(blocked["verdict"], "BLOCKED")
        self.assertEqual(blocked["reason_code"], "MISSING_REQUIRED_INPUT")
        self.assertIn("REQ-XD-001", blocked["requirement_ids"])
        self.assertEqual(checks["_receipt"]["gates"][4]["verdict"], "BLOCKED")
        self.assertFalse(checks["_receipt"]["eligible_for_ebuild"])

    def test_widening_the_joint_limit_into_the_base_plate_fails_clearance(self):
        def widen(item: Path) -> None:
            path = item / "design" / "annotations.json"
            annotations = json.loads(path.read_text())
            annotations["joints"][0]["limits"]["upper"]["value"] = math.radians(35)
            path.write_text(json.dumps(annotations, indent=2) + "\n")

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            checks = self.run_item(self.copy_and_rebuild(directory, widen))
        clearance = checks["v4.REQ-MECH-005"]
        self.assertEqual(clearance["verdict"], "FAIL")
        self.assertLess(clearance["metrics"]["rom_min_clearance_m"], 0.0)

    def test_a_heavier_payload_fails_the_holding_torque_requirement(self):
        def heavier(item: Path) -> None:
            path = item / "design" / "annotations.json"
            annotations = json.loads(path.read_text())
            annotations["materials"]["steel_1045"]["density"]["value"] = 7850.0 * 3
            path.write_text(json.dumps(annotations, indent=2) + "\n")

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            checks = self.run_item(self.copy_and_rebuild(directory, heavier))
        self.assertEqual(checks["v4.REQ-MECH-001"]["verdict"], "FAIL")

    def test_goldens_catch_a_mechanical_model_writer_defect_the_drift_check_cannot(self):
        """A bug in the MJCF writer reproduces consistently, so V2 passes; only the
        independent closed-form goldens can see that the physics is wrong."""
        import re
        from unittest import mock

        import ecad_model.domains.mechanical as mechanical_module
        from ecad_model.mjcf import build_mjcf

        def heavy_payload_writer(model, **kwargs):
            text = build_mjcf(model, **kwargs)
            head, tail = text.split('<body name="payload">', 1)
            tail = re.sub(r'mass="([^"]+)"', lambda m: f'mass="{float(m.group(1)) * 1.5:.12g}"', tail, count=1)
            return head + '<body name="payload">' + tail

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            with mock.patch.object(mechanical_module, "build_mjcf", heavy_payload_writer):
                checks = self.run_item(self.copy_and_rebuild(directory, lambda item: None))
        # The drift check cannot see it: the writer is wrong both times.
        self.assertEqual(checks["v2.dataset-reproduction"]["verdict"], "PASS")
        self.assertEqual(checks["v2.mechanical.model-invariants"]["verdict"], "PASS")
        for golden in ("v3.REF-MECH-001", "v3.REF-MECH-002", "v3.REF-MECH-003"):
            with self.subTest(golden):
                self.assertEqual(checks[golden]["verdict"], "FAIL")



def _copy_item(directory: str) -> Path:
    target = Path(directory) / "robotic_joint_001"
    shutil.copytree(ITEM, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _edit_json(path: Path, mutate) -> None:
    document = json.loads(path.read_text())
    mutate(document)
    path.write_text(json.dumps(document, indent=2) + "\n")


def _null_quantities(unit: str) -> dict:
    """One quantity per null status, each carrying what its status requires.

    UNSPECIFIED cites a real repository file by its real hash -- the eServo-200
    product sheet, which is silent on the actuator -- so V0's cited-source
    check stays green and only the missing value is under test.
    """
    import hashlib

    sheet = "eRobotics_CAD_Design/robot_components/product_datasheet.md"
    return {
        "UNKNOWN": {"value": None, "unit": unit, "status": "UNKNOWN",
                    "source": {"kind": "design_annotation", "ref": "fixture"}, "note": "not selected"},
        "UNSPECIFIED": {"value": None, "unit": unit, "status": "UNSPECIFIED",
                        "source": {"kind": "product_specification", "ref": sheet,
                                   "sha256": hashlib.sha256((REPO_ROOT / sheet).read_bytes()).hexdigest()},
                        "note": "the product sheet is silent on it"},
        "NOT_AVAILABLE": {"value": None, "unit": unit, "status": "NOT_AVAILABLE",
                          "source": {"kind": "datasheet", "ref": "a manufacturer datasheet this project may not use"},
                          "note": "licence terms forbid redistribution"},
    }


class TestGatesFail(unittest.TestCase):
    """Every gate is shown failing on a precise, targeted input."""

    @classmethod
    def setUpClass(cls):
        require("OCP")
        mujoco_on_path()

    def run_copy(self, mutate, rebuild=False):
        from ecad_model.dataset import build, validate

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            mutate(item)
            if rebuild:
                build(item)
            with tempfile.TemporaryDirectory() as output:
                receipt = validate(item, Path(output) / "run")
        return {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]} | {"_gates": {
            g["gate"]: g["verdict"] for g in receipt["gates"]}}

    def test_v0_fails_on_a_hash_mismatch(self):
        def whitespace(item):
            path = item / "requirements" / "requirements.json"
            path.write_text(path.read_text() + "\n")  # still valid JSON and schema-valid
        checks = self.run_copy(whitespace)
        self.assertEqual(checks["v0.dataset-schemas-and-hashes"]["verdict"], "FAIL")
        self.assertTrue(any("requirements.json" in f for f in checks["v0.dataset-schemas-and-hashes"]["findings"]))

    def test_v1_fails_on_impossible_joint_limits(self):
        def invert(item):
            _edit_json(item / "design" / "annotations.json", lambda a: a["joints"][0]["limits"]["lower"].update(value=1.0))
        checks = self.run_copy(invert, rebuild=True)
        self.assertEqual(checks["v1.mechanical.extraction-and-sanity"]["verdict"], "FAIL")
        self.assertIn("lower limit is not below the upper limit", " ".join(checks["v1.mechanical.extraction-and-sanity"]["findings"]))

    def test_v2_fails_on_a_hand_edited_derived_file_even_with_its_hash_updated(self):
        import hashlib

        def forge(item):
            path = item / "derived" / "engineering_model.json"
            _edit_json(path, lambda m: next(c for c in m["components"] if c["component_id"] == "link")[
                "physical"]["mass"].update(value=0.6))
            data = path.read_bytes()
            def rehash(manifest):
                entry = next(e for e in manifest["derived"] if e["artifact"]["path"] == "derived/engineering_model.json")
                entry["artifact"].update(sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
            _edit_json(item / "dataset-item.json", rehash)
        checks = self.run_copy(forge)
        self.assertEqual(checks["v0.dataset-schemas-and-hashes"]["verdict"], "PASS", "integrity is satisfied by the forged hash")
        self.assertEqual(checks["v2.dataset-reproduction"]["verdict"], "FAIL")

    def test_a_positive_clearance_below_the_requirement_fails(self):
        """Regression: clearance was only tested with penetration, so a contact-only
        metric would pass a 2.3 mm gap against the 5 mm requirement."""
        def lower(item):
            _edit_json(item / "design" / "annotations.json",
                       lambda a: a["joints"][0]["limits"]["upper"].update(value=math.radians(31)))
        checks = self.run_copy(lower, rebuild=True)
        clearance = checks["v4.REQ-MECH-005"]
        self.assertEqual(clearance["verdict"], "FAIL")
        self.assertGreater(clearance["metrics"]["rom_min_clearance_m"], 0.0)
        self.assertLess(clearance["metrics"]["rom_min_clearance_m"], 0.005)
        self.assertEqual(clearance["metrics"]["rom_colliding_poses"], 0.0)


class TestManifestAndCitations(unittest.TestCase):
    def setUp(self):
        require("OCP")

    def test_a_hand_edited_domain_status_is_caught(self):
        from ecad_model.dataset import Item, manifest_problems

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            _edit_json(item / "dataset-item.json",
                       lambda m: next(d for d in m["domains"] if d["domain"] == "electrical").update(status="implemented"))
            self.assertTrue(any("domains" in p for p in manifest_problems(Item(item))))

    def test_an_edited_simulation_script_breaks_integrity(self):
        from ecad_model.dataset import Item, integrity

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            script = item / "simulation" / "joint_dynamics.py"
            script.write_text(script.read_text() + "\n# edited\n")
            self.assertIn("simulation/joint_dynamics.py: bytes do not match the recorded hash", integrity(Item(item)))

    def test_an_unrecorded_file_breaks_integrity(self):
        from ecad_model.dataset import Item, integrity

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            (item / "simulation" / "extra.py").write_text("print('{}')\n")
            self.assertTrue(any("not recorded" in p and "simulation/extra.py" in p for p in integrity(Item(item))))

    def test_a_cited_datasheet_that_changed_is_caught(self):
        from ecad_model.dataset import Item, cited_source_problems

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            def stale(annotations):
                drive = next(c for c in annotations["components_without_cad"] if c["component_id"] == "drive")
                drive["domains"]["electrical"]["supply_voltage"]["source"]["sha256"] = "0" * 64
            _edit_json(item / "design" / "annotations.json", stale)
            self.assertTrue(any("has changed since it was cited" in p for p in cited_source_problems(Item(item))))

    def test_a_citation_outside_the_repository_is_not_read(self):
        import hashlib

        from ecad_model.dataset import Item, cited_source_problems

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory, \
                tempfile.TemporaryDirectory() as outside:
            host_file = Path(outside) / "host-file.md"
            host_file.write_text("not part of the repository\n")
            item = _copy_item(directory)
            for ref in (str(host_file), os.path.relpath(host_file, REPO_ROOT)):
                def escape(annotations):
                    drive = next(c for c in annotations["components_without_cad"] if c["component_id"] == "drive")
                    source = drive["domains"]["electrical"]["supply_voltage"]["source"]
                    source["ref"] = ref
                    source["sha256"] = hashlib.sha256(host_file.read_bytes()).hexdigest()
                _edit_json(item / "design" / "annotations.json", escape)
                with self.subTest(ref=ref):
                    self.assertTrue(any("lies outside the repository" in p
                                        for p in cited_source_problems(Item(item))))

    def test_building_without_provenance_is_refused(self):
        from ecad_model.dataset import build

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            (item / "source" / "provenance.json").unlink()
            with self.assertRaisesRegex(ValueError, "licence and origin are never assumed"):
                build(item)


class TestHonestOutcomes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require("OCP")
        mujoco_on_path()

    def test_an_unavailable_simulator_gives_a_blocked_receipt_not_a_crash(self):
        """Regression: with MuJoCo missing, validate raised and wrote no receipt."""
        from unittest import mock

        from ecad_model.dataset import validate
        from ecad_validation.adapters.base import Capability

        missing = Capability(adapter="mujoco", available=False, reason="MUJOCO_NOT_INSTALLED")
        with tempfile.TemporaryDirectory() as output, \
                mock.patch("ecad_validation.adapters.mujoco.detect_mujoco", return_value=missing):
            receipt = validate(ITEM, Path(output) / "run")
        gates = {g["gate"]: g["verdict"] for g in receipt["gates"]}
        self.assertEqual((gates["V3"], gates["V4"]), ("BLOCKED", "BLOCKED"))
        self.assertFalse(receipt["eligible_for_ebuild"])

    def test_a_cross_domain_limit_is_blocked_while_unknown_and_numeric_once_known(self):
        """Decay-proof: the rule is exercised on copies, not on the sample's current gap."""
        from ecad_model.dataset import build, validate

        def with_torque(value):
            def mutate(annotations):
                actuator = next(c for c in annotations["components_without_cad"] if c["component_id"] == "actuator")
                actuator["domains"]["mechanical"]["continuous_output_torque"] = (
                    _null_quantities("N*m")[value] if isinstance(value, str) else
                    {"value": value, "unit": "N*m", "status": "SPECIFIED", "source": {"kind": "datasheet", "ref": "fixture"}})
            return mutate

        # Every null status blocks; REQ-XD-001 is illustrative, so meeting it is WARNING, never PASS.
        for value, expected in (("UNKNOWN", "BLOCKED"), ("UNSPECIFIED", "BLOCKED"), ("NOT_AVAILABLE", "BLOCKED"),
                                (5.0, "WARNING"), (3.0, "FAIL")):
            with self.subTest(torque=value), tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as d:
                item = _copy_item(d)
                _edit_json(item / "design" / "annotations.json", with_torque(value))
                build(item)
                with tempfile.TemporaryDirectory() as output:
                    receipt = validate(item, Path(output) / "run")
                check = {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}["v4.REQ-XD-001"]
                self.assertEqual(check["verdict"], expected)
                self.assertIn("REQ-XD-001", check["requirement_ids"])
                if isinstance(value, str):
                    self.assertEqual(check["reason_code"], "MISSING_REQUIRED_INPUT")
                    self.assertEqual(check["findings"],
                                     [f"{value}: components/actuator/domains/mechanical/continuous_output_torque"])

    def test_the_trace_names_both_sides_for_clearance_and_marks_illustrative_limits(self):
        from ecad_model.dataset import validate

        with tempfile.TemporaryDirectory() as output:
            validate(ITEM, Path(output) / "run")
            trace = {row["requirement_id"]: row for row in json.loads((Path(output) / "run" / "trace.json").read_text())}
            report = (Path(output) / "run" / "report.md").read_text()
        clearance = trace["REQ-MECH-005"]["cad_components"]
        self.assertTrue(any(c.startswith("pillar") for c in clearance) and any(c.startswith("link") for c in clearance))
        self.assertFalse(any(c.startswith("pillar") for c in trace["REQ-MECH-001"]["cad_components"]))
        self.assertEqual(trace["REQ-MECH-001"]["kind"], "illustrative requirement")
        self.assertEqual(trace["REF-MECH-001"]["kind"], "reference")
        self.assertIn("illustrative requirement", report)


class TestImporterRefusals(unittest.TestCase):
    """Every refusal in the STEP importer, exercised with a generated file."""

    def setUp(self):
        require("OCP")

    def write(self, directory, build_parts):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_AsIs
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Pnt, gp_Trsf

        document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        assembly = tool.NewShape()

        def add(name, parent=assembly, transform=None):
            part = tool.AddShape(BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 1.0, 1.0, 1.0).Shape(), False)
            TDataStd_Name.Set_s(part, TCollection_ExtendedString(name))
            tool.AddComponent(parent, part, TopLoc_Location(transform or gp_Trsf()))

        build_parts(tool, assembly, add, gp_Trsf, TDataStd_Name, TCollection_ExtendedString, TopLoc_Location)
        tool.UpdateAssemblies()
        writer = STEPCAFControl_Writer()
        writer.SetNameMode(True)
        writer.Transfer(document, STEPControl_AsIs)
        path = Path(directory) / "case.step"
        writer.Write(str(path))
        return path

    def assert_refused(self, build_parts, message):
        from ecad_model.importers import importer_for

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            path = self.write(directory, build_parts)
            with self.assertRaisesRegex(ValueError, message):
                importer_for(path).extract(path, REPO_ROOT)

    def test_duplicate_part_names(self):
        def parts(tool, assembly, add, *rest):
            add("same")
            add("same")
        self.assert_refused(parts, "unique non-empty names")

    def test_a_mirrored_placement(self):
        def parts(tool, assembly, add, gp_Trsf, *rest):
            from OCP.gp import gp_Pnt
            mirror = gp_Trsf()
            mirror.SetMirror(gp_Pnt(0, 0, 0))
            add("mirrored", transform=mirror)
        self.assert_refused(parts, "scaled or mirrored")

    def test_a_nested_sub_assembly(self):
        def parts(tool, assembly, add, gp_Trsf, TDataStd_Name, Text, TopLoc_Location):
            sub = tool.NewShape()
            TDataStd_Name.Set_s(sub, Text("sub"))
            add("inner", parent=sub)
            tool.AddComponent(assembly, sub, TopLoc_Location(gp_Trsf()))
        self.assert_refused(parts, "nested sub-assemblies")


class TestUntrustedInput(unittest.TestCase):
    """Security review regressions, one per reachable path."""

    def setUp(self):
        require("OCP")

    def test_external_document_references_are_refused_before_parsing(self):
        """Path: a STEP DOCUMENT_FILE naming ../ or an absolute path -> OCCT loads
        that file at transfer -> geometry from outside the hashed file enters the model."""
        from ecad_model.importers import ExtractionError, importer_for

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            outside = Path(tempfile.mkdtemp())
            (outside / "secret.stp").write_bytes(STEP.read_bytes())
            text = STEP.read_text()
            injected = text.replace(
                "DATA;\n", f"DATA;\n#99999 = DOCUMENT_FILE('{outside}/secret.stp','',$,#99998,'',$);\n", 1)
            path = Path(directory) / "external.step"
            path.write_text(injected)
            with self.assertRaises(ExtractionError) as caught:
                importer_for(path).extract(path, REPO_ROOT)
            shutil.rmtree(outside)
        self.assertEqual(caught.exception.kind, "rejected")
        self.assertIn("external document references are not supported", str(caught.exception))

    def test_external_files_the_reader_loads_are_refused_after_transfer(self):
        """Second layer: a multi-file assembly that evades the pre-parse scan is
        still refused, because the reader reports the part file it loaded."""
        from unittest import mock

        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.STEPControl import STEPControl_AsIs
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopLoc import TopLoc_Location
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Trsf

        from ecad_model.importers import step_ocp

        document = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        assembly = tool.NewShape()
        TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("assembly"))
        part = tool.AddShape(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), False)
        TDataStd_Name.Set_s(part, TCollection_ExtendedString("cube"))
        tool.AddComponent(assembly, part, TopLoc_Location(gp_Trsf()))
        tool.UpdateAssemblies()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            main = Path(directory) / "main.step"
            writer = STEPCAFControl_Writer()
            writer.Transfer(document, STEPControl_AsIs, "part_")  # multi-file: one external file per part
            writer.Write(str(main))
            self.assertTrue(list(Path(directory).glob("part_*")), "the writer must have produced an external part")
            self.assertTrue(step_ocp.external_references(main.read_bytes()), "the first layer sees it")
            with mock.patch.object(step_ocp, "external_references", return_value=[]):
                with self.assertRaisesRegex(ValueError, "the reader loaded external files"):
                    step_ocp._extract_in_process(main, "main.step")

    def test_a_fifo_among_the_inputs_is_refused_without_blocking(self):
        """Path: design/annotations.json is a FIFO -> check opens it -> blocks forever."""
        import threading

        from ecad_model.dataset import check
        from ecad_model.importers import UnsupportedFormat

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            fifo = item / "design" / "annotations.json"
            fifo.unlink()
            os.mkfifo(fifo)

            def release():
                # A regression blocks in open(); opening the write end releases
                # it, so the test fails instead of hanging the suite.
                try:
                    os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
                except OSError:
                    pass

            timer = threading.Timer(10.0, release)
            timer.daemon = True
            timer.start()
            try:
                with self.assertRaisesRegex(UnsupportedFormat, "not a regular file"):
                    check(item)
            finally:
                timer.cancel()

    def test_check_refuses_a_symlinked_directory_before_reading_through_it(self):
        """Path: design/ is a symlink -> every annotation read is redirected outside the
        item, and each file there is still a regular file, so a per-file guard passes.
        Both check and validate refuse it."""
        from ecad_model.dataset import check, validate

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            outside = Path(tempfile.mkdtemp())
            shutil.move(str(item / "design"), outside / "design")
            (item / "design").symlink_to(outside / "design", target_is_directory=True)
            try:
                for name, run in (("check", lambda: check(item)),
                                  ("validate", lambda: validate(item, Path(outside) / "run"))):
                    with self.subTest(name), self.assertRaisesRegex(ValueError, "dataset items may not contain symlinks"):
                        run()
            finally:
                shutil.rmtree(outside)

    def test_build_does_not_write_through_a_symlink(self):
        """Path: a committed item whose derived/ is a symlink -> build writes through it."""
        from ecad_model.dataset import build

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = _copy_item(directory)
            victim = Path(tempfile.mkdtemp())
            shutil.rmtree(item / "derived")
            (item / "derived").symlink_to(victim, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                build(item)
            self.assertEqual(list(victim.iterdir()), [], "nothing may be written outside the item")
            shutil.rmtree(victim)

    def test_an_item_git_cannot_enumerate_is_refused_not_skipped(self):
        """Path: an item under an ignored directory -> files() lists nothing -> the
        symlink refusal and immutability digest silently cover nothing."""
        from ecad_model.dataset import Item

        ignored = REPO_ROOT / "build"
        created = not ignored.exists()
        try:
            with tempfile.TemporaryDirectory(dir=ignored if not created else None) as _:
                pass
            ignored.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=ignored) as directory:
                item = _copy_item(directory)
                with self.assertRaisesRegex(ValueError, "git-ignored"):
                    Item(item).files()
                # check refuses it before the native STEP parser ever runs on it.
                from unittest import mock

                from ecad_model.dataset import check
                with mock.patch("ecad_model.domains.mechanical.importer_for", side_effect=AssertionError("parsed")):
                    with self.assertRaisesRegex(ValueError, "git-ignored"):
                        check(item)
        finally:
            if created and ignored.exists():
                shutil.rmtree(ignored)

    def test_a_fifo_is_refused_without_blocking(self):
        import os

        from ecad_model.dataset import Item
        from ecad_model.importers import UnsupportedFormat

        with tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
            item = Path(directory) / "fifo_item"
            (item / "source").mkdir(parents=True)
            provenance = json.loads((ITEM / "source" / "provenance.json").read_text())
            provenance["artifacts"] = [{"path": "source/part.step", "format": "step"}]
            (item / "source" / "provenance.json").write_text(json.dumps(provenance))
            os.mkfifo(item / "source" / "part.step")
            with self.assertRaisesRegex(UnsupportedFormat, "not a regular file"):
                Item(item)


class TestExtractionFailureVerdicts(unittest.TestCase):
    """Security review: every failure used to read as 'unavailable'."""

    @classmethod
    def setUpClass(cls):
        require("OCP")
        mujoco_on_path()

    def test_a_missing_input_is_blocked_not_a_design_failure(self):
        """A part whose material density has no value cannot be simulated: that
        is BLOCKED with MISSING_REQUIRED_INPUT, not a FAIL of the design, for
        every null status."""
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import validate

        for status, density in _null_quantities("kg/m^3").items():
            with self.subTest(status=status), \
                    tempfile.TemporaryDirectory(dir=REPO_ROOT, prefix="tmp-cad-dataset-test-") as directory:
                item = _copy_item(directory)
                _edit_json(item / "design" / "annotations.json",
                           lambda annotations: annotations["materials"]["steel_1045"].update(density=density))
                with tempfile.TemporaryDirectory() as output:
                    receipt = validate(item, Path(output) / "run")
                validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
                v1 = next(c for g in receipt["gates"] for c in g["checks"] if c["check_id"].startswith("v1."))
                self.assertEqual((v1["verdict"], v1["reason_code"]), ("BLOCKED", "MISSING_REQUIRED_INPUT"), v1["findings"])
                self.assertTrue(any(status in finding for finding in v1["findings"]), v1["findings"])

    def test_each_failure_kind_has_its_own_verdict(self):
        from unittest import mock

        from ecad_model.dataset import validate
        from ecad_model.importers import ExtractionError
        from ecad_model.importers.step_ocp import StepImporter

        expected = {
            "rejected": ("FAIL", "completed", "SOURCE_REJECTED"),
            "crashed": ("INCONCLUSIVE", "crashed", "EXTRACTION_CRASHED"),
            "timed_out": ("INCONCLUSIVE", "timed_out", "EXTRACTION_TIMED_OUT"),
            "unavailable": ("BLOCKED", "unavailable", "EXTRACTOR_UNAVAILABLE"),
        }
        for kind, (verdict, status, reason) in expected.items():
            with self.subTest(kind), tempfile.TemporaryDirectory() as output, \
                    mock.patch.object(StepImporter, "extract", side_effect=ExtractionError(kind, f"fixture {kind}")):
                receipt = validate(ITEM, Path(output) / "run")
            v1 = next(c for g in receipt["gates"] for c in g["checks"] if c["check_id"].startswith("v1."))
            self.assertEqual((v1["verdict"], v1["execution_status"], v1["reason_code"]), (verdict, status, reason))
            self.assertFalse(receipt["eligible_for_ebuild"])

class TestDocumentationExamples(unittest.TestCase):
    """Examples in the modules that need the CAD kernel and MuJoCo to run."""

    def test_examples_in_kernel_dependent_modules(self):
        require("OCP")
        mujoco_on_path()
        import doctest
        import importlib

        for name in ("dataset", "cli", "importers.step_ocp"):
            with self.subTest(name):
                module = importlib.import_module(f"ecad_model.{name}")
                result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
                self.assertGreater(result.attempted, 0, f"{name} has no runnable examples")
                self.assertEqual(result.failed, 0)

if __name__ == "__main__":
    unittest.main()
