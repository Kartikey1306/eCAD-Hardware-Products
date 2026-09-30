"""Engineering model, MJCF and requirement compilation -- no CAD kernel needed.

Fixtures are synthetic extractions with hand-computed expectations, plus the
committed derived model of datasets/cad/robotic_joint_001, which is plain JSON.
Expected values are derived by hand in each test, never by calling the code
under test.
"""

from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ecad_model.builder import (  # noqa: E402
    STANDARD_GRAVITY,
    build_engineering_model,
    canonical_direction,
    index_unknowns,
    resolve,
)
from ecad_model.dataset import same_content, same_text  # noqa: E402
from ecad_model.domains import adapter_for  # noqa: E402
from ecad_model.domains.mechanical import inertia_problems, reference_value  # noqa: E402
from ecad_model.importers import UnsupportedFormat, detect_format, importer_for  # noqa: E402
from ecad_model.importers import base as importer_base  # noqa: E402
from ecad_model.mjcf import ModelIncomplete, build_mjcf, rotation_to_quaternion  # noqa: E402
from ecad_model.quantity import NULL_STATUSES, Status, is_null, quantity, source, unknown  # noqa: E402
from ecad_model.requirements import ReferenceBlocked, compile_cases  # noqa: E402
from ecad_model.schemas import validate  # noqa: E402

ITEM = REPO_ROOT / "datasets" / "cad" / "robotic_joint_001"
IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
ANNOTATION = source("design_annotation", "fixture")
MECHANICAL = adapter_for("mechanical")


def compile_mechanical(model, requirements):
    """compile_cases for the mechanical domain, as the dataset runner calls it."""
    return compile_cases(model, requirements, MECHANICAL.case_target("fixture"),
                         MECHANICAL.reference_value, MECHANICAL.metrics())
CITED = source("datasheet", "fixture.md", "0" * 64)


def null_quantity(unit, status):
    """A quantity with the given null status, carrying what that status requires."""
    return quantity(None, unit, status, CITED if status is Status.UNSPECIFIED else ANNOTATION, note=f"fixture {status.value}")


def box_part(name, dims_mm, translation_mm, cylinders=()):
    """A synthetic extracted box with its corner at the local origin."""
    a, b, c = dims_mm
    volume = a * b * c
    return {
        "name": name,
        "occurrence": f"{name}:1",
        "translation": list(translation_mm),
        "rotation": copy.deepcopy(IDENTITY),
        "solid_count": 1,
        "face_count": 6,
        "volume": volume,
        "surface_area": 2 * (a * b + b * c + a * c),
        "center_of_mass_local": [a / 2, b / 2, c / 2],
        "inertia_about_com_unit_density_local": [
            [volume * (b * b + c * c) / 12, 0.0, 0.0],
            [0.0, volume * (a * a + c * c) / 12, 0.0],
            [0.0, 0.0, volume * (a * a + b * b) / 12],
        ],
        "bounding_box_local": {"min": [0.0, 0.0, 0.0], "max": [a, b, c]},
        "cylindrical_faces": list(cylinders),
    }


def pendulum(bob_material="water"):
    """A 20 mm cube bob whose centre is 100 mm from a joint axis along +Y through (30, *, 50) mm.

    The bob carries the joint's cylindrical face itself, so the moving group is
    the bob alone and every expectation is closed-form. The axis deliberately
    misses the world origin: through the origin, a lever arm computed from the
    centre of mass alone would equal the correct one and no test could tell.
    """
    frame = box_part("frame", (40, 40, 40), (10, -20, -10))
    axis_face = {"axis_origin_local": [-90.0, 10.0, 10.0], "axis_direction_local": [0.0, 1.0, 0.0], "radius": 2.0}
    bob = box_part("bob", (20, 20, 20), (120, -10, 40), cylinders=[axis_face])
    extraction = {
        "source": {"path": "fixture.step", "sha256": "0" * 64, "format": "step"},
        "length_unit": "mm",
        "parts": [frame, bob],
    }
    annotations = {
        "design_id": "pendulum",
        "materials": {
            "water": {"name": "water", "density": quantity(1000.0, "kg/m^3", Status.SPECIFIED, ANNOTATION)},
        },
        "parts": {
            "frame": {"component_id": "frame", "kind": "structure", "material": "water"},
            "bob": {"component_id": "bob", "kind": "payload", "material": bob_material},
        },
        "joints": [{
            "joint_id": "j1", "type": "revolute", "parent": "frame", "child": "bob", "realized_by": "bob",
            "axis_sense": [0.0, 1.0, 0.0],
            "limits": {
                "lower": quantity(-1.0, "rad", Status.SPECIFIED, ANNOTATION),
                "upper": quantity(1.0, "rad", Status.SPECIFIED, ANNOTATION),
            },
        }],
        "attachments": [],
        "components_without_cad": [],
        "relationships": [],
    }
    return extraction, annotations


def build(extraction, annotations):
    return build_engineering_model(
        extraction, annotations, design_name="fixture", revision="1.0",
        extraction_ref="fixture.json", annotations_ref="fixture.json", annotations_sha256="0" * 64,
    )


def component(model, cid):
    return next(c for c in model["components"] if c["component_id"] == cid)


class TestQuantity(unittest.TestCase):
    def test_unknown_if_and_only_if_null(self):
        with self.assertRaisesRegex(ValueError, "null if and only if"):
            quantity(None, "kg", Status.SPECIFIED, ANNOTATION)
        with self.assertRaisesRegex(ValueError, "null if and only if"):
            quantity(1.0, "kg", Status.UNKNOWN, ANNOTATION)

    def test_every_null_status_has_a_null_value_and_nothing_else_does(self):
        self.assertEqual(NULL_STATUSES, {Status.UNKNOWN, Status.UNSPECIFIED, Status.NOT_AVAILABLE})
        for status in Status:
            with self.subTest(status=status.value):
                self.assertEqual(is_null(status), status in NULL_STATUSES)
                self.assertEqual(is_null(status.value), status in NULL_STATUSES)
        for status in NULL_STATUSES:
            with self.subTest(null=status.value), self.assertRaisesRegex(ValueError, "null if and only if"):
                quantity(1.0, "kg", status, CITED, note="x")

    def test_each_status_carries_what_makes_it_checkable(self):
        refused = {
            "UNKNOWN without a note": lambda: quantity(None, "kg", Status.UNKNOWN, ANNOTATION),
            "NOT_AVAILABLE without a note": lambda: quantity(None, "kg", Status.NOT_AVAILABLE, ANNOTATION),
            "ESTIMATED without a note": lambda: quantity(1.0, "kg", Status.ESTIMATED, source("estimation", "x")),
            "UNSPECIFIED without the silent document's hash": lambda: quantity(None, "kg", Status.UNSPECIFIED, ANNOTATION, note="x"),
            "MEASURED from a datasheet": lambda: quantity(1.0, "kg", Status.MEASURED, source("datasheet", "x")),
            "SIMULATED from a datasheet": lambda: quantity(1.0, "kg", Status.SIMULATED, source("datasheet", "x")),
            "AI_ASSUMPTION from a datasheet": lambda: quantity(1.0, "kg", Status.AI_ASSUMPTION, source("datasheet", "x")),
        }
        for label, build_it in refused.items():
            with self.subTest(label), self.assertRaises(ValueError):
                build_it()
        for status in NULL_STATUSES:
            self.assertIsNone(null_quantity("kg", status)["value"])
        self.assertEqual(quantity(1.0, "kg", Status.MEASURED, source("measurement", "scale.csv"))["status"], "MEASURED")

    def test_derived_must_name_its_inputs(self):
        with self.assertRaisesRegex(ValueError, "must name"):
            quantity(1.0, "kg", Status.DERIVED, ANNOTATION)

    def test_non_finite_values_are_refused(self):
        for bad in (math.nan, math.inf, [1.0, math.nan], True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                quantity(bad, "1", Status.SPECIFIED, ANNOTATION)

    def test_an_unverified_licence_permits_neither_redistribution_nor_training(self):
        """Spec: if licence status is unclear, license_verified = false and
        redistribution is not assumed."""
        from ecad_model.schemas import validate

        provenance = json.loads((REPO_ROOT / "datasets/cad/robotic_joint_001/source/provenance.json").read_text())
        validate(provenance, "cad-dataset/v1/source-provenance")
        provenance["license"]["license_verified"] = False
        for field in ("redistribution_permitted", "training_use_permitted"):
            with self.subTest(field):
                with self.assertRaisesRegex(ValueError, field):
                    validate(provenance, "cad-dataset/v1/source-provenance")
                provenance["license"][field] = False
        validate(provenance, "cad-dataset/v1/source-provenance")

    def test_a_verified_licence_cites_its_text_and_a_third_party_one_its_verifier(self):
        provenance = json.loads((REPO_ROOT / "datasets/cad/robotic_joint_001/source/provenance.json").read_text())
        validate(provenance, "cad-dataset/v1/source-provenance")
        unverifiable = copy.deepcopy(provenance)
        del unverifiable["license"]["license_text"]
        with self.assertRaisesRegex(ValueError, "license_text"):
            validate(unverifiable, "cad-dataset/v1/source-provenance")
        third = copy.deepcopy(provenance)
        third["origin"] = {"kind": "third_party", "author": "someone", "url": "https://example.org/part.step",
                           "modifications": "none"}
        with self.assertRaisesRegex(ValueError, "verified_by"):
            validate(third, "cad-dataset/v1/source-provenance")
        third["license"]["verified_by"] = "a named reviewer"
        with self.assertRaisesRegex(ValueError, "verified_at"):
            validate(third, "cad-dataset/v1/source-provenance")
        third["license"]["verified_at"] = "2026-09-26"
        validate(third, "cad-dataset/v1/source-provenance")
        unverified = copy.deepcopy(third)
        unverified["license"].update(license_verified=False, redistribution_permitted=False, training_use_permitted=False)
        for field in ("verified_by", "verified_at", "license_text"):
            del unverified["license"][field]
        # Even unverified, a third-party artefact says which licence text governs it.
        with self.assertRaisesRegex(ValueError, "license_text"):
            validate(unverified, "cad-dataset/v1/source-provenance")

    def test_schema_enforces_the_same_rules(self):
        """A hand-written document cannot bypass the constructor's rules."""
        base = {"value": 1.0, "unit": "kg", "status": "SPECIFIED", "source": ANNOTATION}
        cases = {
            # Each carries everything else its status requires, so it fails
            # only on the rule its label names.
            "unknown with a value": {**base, "status": "UNKNOWN", "note": "x"},
            "unspecified with a value": {**base, "status": "UNSPECIFIED", "source": CITED, "note": "x"},
            "not available with a value": {**base, "status": "NOT_AVAILABLE", "note": "x"},
            "null claimed as specified": {**base, "value": None},
            "derived without inputs": {**base, "status": "DERIVED"},
            "unknown without a note": {**base, "value": None, "status": "UNKNOWN"},
            "not available without a note": {**base, "value": None, "status": "NOT_AVAILABLE"},
            "unspecified without a cited hash": {**base, "value": None, "status": "UNSPECIFIED", "note": "x"},
            "estimated without a note": {**base, "status": "ESTIMATED"},
            "measured from an annotation": {**base, "status": "MEASURED"},
            "simulated from an annotation": {**base, "status": "SIMULATED"},
            "ai assumption from an annotation": {**base, "status": "AI_ASSUMPTION"},
        }
        annotations = json.loads((ITEM / "design" / "annotations.json").read_text())
        for label, bad in cases.items():
            broken = copy.deepcopy(annotations)
            broken["materials"]["steel_1045"]["density"] = bad
            with self.subTest(label), self.assertRaises(ValueError):
                validate(broken, "engineering-model/v1/design-annotations")
        validate(annotations, "engineering-model/v1/design-annotations")
        for status in NULL_STATUSES:
            accepted = copy.deepcopy(annotations)
            accepted["materials"]["steel_1045"]["density"] = null_quantity("kg/m^3", status)
            with self.subTest(accepted=status.value):
                validate(accepted, "engineering-model/v1/design-annotations")


class TestFormatDetection(unittest.TestCase):
    def _file(self, directory, name, content: bytes) -> Path:
        path = Path(directory) / name
        path.write_bytes(content)
        return path

    def test_detection_trusts_content_not_extension(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            disguised = self._file(directory, "part.txt", b"ISO-10303-21;\nHEADER;\n")
            self.assertEqual(detect_format(disguised), "step")
            fake = self._file(directory, "part.step", b"not a step file at all")
            with self.assertRaisesRegex(UnsupportedFormat, "matches no supported CAD format"):
                detect_format(fake)

    def test_recognised_formats_without_an_importer_are_refused_by_name(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            for name, content, fmt in (
                ("part.stl", b"solid part\nfacet normal 0 0 1\n", "stl"),
                ("part.glb", b"glTF\x02\x00\x00\x00", "gltf"),
            ):
                with self.subTest(fmt):
                    with self.assertRaisesRegex(UnsupportedFormat, f"recognised as {fmt}, but no {fmt} importer"):
                        importer_for(self._file(directory, name, content))

    def test_git_lfs_pointer_is_named_as_such(self):
        """.gitattributes routes *.step to LFS; a pointer must not read as a broken CAD file."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            pointer = self._file(
                directory, "part.step",
                b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 1\n",
            )
            with self.assertRaisesRegex(UnsupportedFormat, "Git LFS pointer"):
                detect_format(pointer)

    def test_oversized_input_is_refused_before_reading(self):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            path = self._file(directory, "big.step", b"ISO-10303-21;" + b" " * 100)
            with mock.patch.object(importer_base, "MAX_CAD_BYTES", 50):
                with self.assertRaisesRegex(UnsupportedFormat, "exceeds"):
                    detect_format(path)


class TestBuilder(unittest.TestCase):
    def test_mass_and_inertia_convert_millimetres_to_si(self):
        extraction, annotations = pendulum()
        model = build(extraction, annotations)
        bob = component(model, "bob")
        # 20 mm cube of 1000 kg/m^3: 8e-6 m^3 -> 0.008 kg; I = m(a^2+b^2)/12 = 0.008*(2*0.02^2)/12.
        self.assertAlmostEqual(bob["geometry"]["volume"]["value"], 8e-6, places=15)
        self.assertAlmostEqual(bob["physical"]["mass"]["value"], 0.008, places=12)
        expected_inertia = 0.008 * 2 * 0.02**2 / 12
        for axis in range(3):
            self.assertAlmostEqual(bob["physical"]["inertia_about_com"]["value"][axis][axis], expected_inertia, places=15)
        self.assertEqual(bob["physical"]["center_of_mass"]["value"], [0.13, 0.0, 0.05])
        self.assertEqual(bob["physical"]["mass"]["status"], "DERIVED")
        self.assertIn("components/bob/material/density", bob["physical"]["mass"]["derived_from"])

    def test_missing_material_makes_mass_unknown_not_defaulted(self):
        extraction, annotations = pendulum(bob_material="not_a_material")
        model = build(extraction, annotations)
        bob = component(model, "bob")
        self.assertEqual(bob["physical"]["mass"]["status"], "UNKNOWN")
        self.assertIsNone(bob["physical"]["mass"]["value"])
        paths = [entry["path"] for entry in model["unknowns"]]
        self.assertIn("components/bob/physical/mass", paths)
        self.assertIn("components/bob/material/density", paths)

    def test_every_null_density_makes_mass_unknown_and_is_indexed_with_its_status(self):
        for status in NULL_STATUSES:
            with self.subTest(status=status.value):
                extraction, annotations = pendulum()
                annotations["materials"]["water"]["density"] = null_quantity("kg/m^3", status)
                model = build(extraction, annotations)
                mass = component(model, "bob")["physical"]["mass"]
                self.assertEqual((mass["status"], mass["value"]), ("UNKNOWN", None))
                self.assertIn(status.value, mass["note"])
                index = {entry["path"]: entry["status"] for entry in model["unknowns"]}
                self.assertEqual(index["components/bob/material/density"], status.value)
                self.assertEqual(index["components/bob/physical/mass"], "UNKNOWN")

    def test_annotation_for_a_part_the_cad_lacks_is_an_error(self):
        extraction, annotations = pendulum()
        annotations["parts"]["ghost"] = {"component_id": "ghost", "kind": "structure", "material": "water"}
        with self.assertRaisesRegex(ValueError, "does not contain"):
            build(extraction, annotations)

    def test_joint_axis_comes_from_cad_geometry_through_the_placement(self):
        """A pin modelled along local Z and rotated -90 degrees about X gives a +Y axis."""
        extraction, annotations = pendulum()
        pin = box_part("bob", (20, 20, 20), (120, -10, 40))
        rotate = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]  # local +Z -> assembly +Y
        pin["rotation"] = rotate
        pin["cylindrical_faces"] = [
            {"axis_origin_local": [-90.0, 10.0, 10.0], "axis_direction_local": [0.0, 0.0, -1.0], "radius": 2.0}
        ]
        extraction["parts"][1] = pin
        axis = build(extraction, annotations)["joints"][0]["axis"]
        self.assertEqual(axis["value"], [0.0, 1.0, 0.0])  # canonical sign, residue-free
        self.assertEqual(axis["status"], "DERIVED")

    def test_ambiguous_axis_is_unknown_not_guessed(self):
        extraction, annotations = pendulum()
        faces = extraction["parts"][1]["cylindrical_faces"]
        for expected_note, extra in (
            ("not parallel", {"axis_origin_local": [-90.0, 10.0, 10.0], "axis_direction_local": [1.0, 0.0, 0.0], "radius": 1.0}),
            ("not coaxial", {"axis_origin_local": [-80.0, 10.0, 10.0], "axis_direction_local": [0.0, 1.0, 0.0], "radius": 1.0}),
        ):
            with self.subTest(expected_note):
                broken = copy.deepcopy(extraction)
                broken["parts"][1]["cylindrical_faces"] = [*faces, extra]
                joint = build(broken, annotations)["joints"][0]
                self.assertEqual(joint["axis"]["status"], "UNKNOWN")
                self.assertIn(expected_note, joint["axis"]["note"])
        extraction["parts"][1]["cylindrical_faces"] = []
        self.assertEqual(build(extraction, annotations)["joints"][0]["axis"]["status"], "UNKNOWN")

    def test_canonical_direction_is_independent_of_modelling_sign(self):
        self.assertEqual(canonical_direction([0.0, -2.0, 0.0]), [0.0, 1.0, 0.0])
        self.assertEqual(canonical_direction([0.0, 1.0, -6e-17]), [0.0, 1.0, 0.0])

    def test_unknowns_index_survives_a_key_sorted_json_round_trip(self):
        """Regression: the index followed dict insertion order, so a model re-read
        from key-sorted JSON re-indexed in a different order and V2 reported it stale."""
        model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        reordered = json.loads(json.dumps(model, sort_keys=True))
        facets = component(reordered, "actuator")["domains"]
        component(reordered, "actuator")["domains"] = dict(reversed(list(facets.items())))
        self.assertEqual(index_unknowns(reordered), model["unknowns"])
        self.assertEqual([entry["path"] for entry in model["unknowns"]],
                         sorted(entry["path"] for entry in model["unknowns"]))

    def test_resolve_refuses_paths_that_are_not_quantities(self):
        model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        self.assertEqual(resolve(model, "components/link/physical/mass")["unit"], "kg")
        # Design-level quantities resolve (gravity is an input of statics and dynamics);
        # a design field that is not a quantity, or an unsupported root, does not.
        self.assertEqual(resolve(model, "design/gravity")["unit"], "m/s^2")
        for bad in ("components/nope/physical/mass", "components/link/physical", "design/name", "materials/steel"):
            with self.subTest(bad), self.assertRaises(KeyError):
                resolve(model, bad)


class TestReferenceValues(unittest.TestCase):
    """Closed-form values, checked against arithmetic done here by hand."""

    def setUp(self):
        self.model = build(*pendulum())
        self.mass = 0.008  # kg, 20 mm cube at 1000 kg/m^3
        self.lever = 0.1  # m, cube centre to the axis

    def test_gravity_torque(self):
        value, used = reference_value(self.model, "gravity_torque_as_modelled")
        self.assertAlmostEqual(value, self.mass * STANDARD_GRAVITY * self.lever, places=12)
        self.assertIn("components/bob/physical/mass", used)

    def test_small_oscillation_period(self):
        inertia_axis = self.mass * 2 * 0.02**2 / 12 + self.mass * self.lever**2  # parallel-axis theorem
        expected = 2 * math.pi * math.sqrt(inertia_axis / (self.mass * STANDARD_GRAVITY * self.lever))
        self.assertAlmostEqual(reference_value(self.model, "small_oscillation_period")[0], expected, places=12)

    def test_moving_mass(self):
        self.assertAlmostEqual(reference_value(self.model, "moving_mass")[0], self.mass, places=15)

    def test_unknown_input_blocks_rather_than_guesses(self):
        model = build(*pendulum(bob_material="not_a_material"))
        with self.assertRaises(ReferenceBlocked) as caught:
            reference_value(model, "gravity_torque_as_modelled")
        self.assertIn({"path": "components/bob/physical/mass", "status": "UNKNOWN"}, caught.exception.paths)

    def test_any_null_axis_blocks_every_derivation_with_its_status(self):
        for status in NULL_STATUSES:
            with self.subTest(status=status.value):
                model = build(*pendulum())
                model["joints"][0]["axis"] = null_quantity("1", status)
                with self.assertRaises(ReferenceBlocked) as caught:
                    reference_value(model, "small_oscillation_period")
                self.assertIn({"path": "joints/j1/axis", "status": status.value}, caught.exception.paths)


class TestRequirementCompilation(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        self.requirements = json.loads((ITEM / "requirements" / "requirements.json").read_text())

    def test_limits_compile_to_the_contract_case_format(self):
        golden, corners, blocked = compile_mechanical(self.model, self.requirements)
        validate(golden, "hardware-validation/v1/validation-cases")
        validate(corners, "hardware-validation/v1/validation-cases")
        limits = {case["id"]: case["metric_limits"] for case in corners["cases"]}
        self.assertEqual(limits["REQ-MECH-001"], {"static_torque_max_abs_nm": {"maximum": 2.5}})
        self.assertEqual(limits["REQ-MECH-005"], {"rom_min_clearance_m": {"minimum": 0.005}})
        self.assertTrue(all(case["requirement_ids"] == ["POLICY:V4-CORNER"] for case in corners["cases"]))

    def test_a_limit_resting_on_an_unknown_is_blocked_with_its_path(self):
        _golden, corners, blocked = compile_mechanical(self.model, self.requirements)
        self.assertNotIn("REQ-XD-001", [case["id"] for case in corners["cases"]])
        entry = next(item for item in blocked if item["id"] == "REQ-XD-001")
        self.assertEqual(entry["missing_inputs"],
                         [{"path": "components/actuator/domains/mechanical/continuous_output_torque", "status": "UNKNOWN"}])

    def test_a_limit_with_any_null_status_is_blocked_with_its_status(self):
        for status in NULL_STATUSES:
            with self.subTest(status=status.value):
                model = copy.deepcopy(self.model)
                torque = component(model, "actuator")["domains"]["mechanical"]
                torque["continuous_output_torque"] = null_quantity("N*m", status)
                _golden, corners, blocked = compile_mechanical(model, self.requirements)
                self.assertNotIn("REQ-XD-001", [case["id"] for case in corners["cases"]])
                entry = next(item for item in blocked if item["id"] == "REQ-XD-001")
                self.assertEqual(entry["missing_inputs"],
                                 [{"path": "components/actuator/domains/mechanical/continuous_output_torque",
                                   "status": status.value}])

    def test_tolerance_moves_each_bound_by_exactly_its_value(self):
        """<= gets maximum = limit + tolerance, >= gets minimum = limit - tolerance;
        the contract's comparator then flips exactly at the moved bound."""
        import math

        from ecad_validation.cases import _compare_corner

        requirements = copy.deepcopy(self.requirements)
        entries = {r["requirement_id"]: r for r in requirements["requirements"]}
        entries["REQ-MECH-001"]["tolerance"] = 0.25   # static_torque_max_abs_nm <= 2.5
        entries["REQ-MECH-005"]["tolerance"] = 0.002  # rom_min_clearance_m >= 0.005
        validate(requirements, "engineering-model/v1/engineering-requirements")
        _golden, corners, _blocked = compile_mechanical(self.model, requirements)
        limits = {case["id"]: case["metric_limits"] for case in corners["cases"]}
        self.assertEqual(limits["REQ-MECH-001"], {"static_torque_max_abs_nm": {"maximum": 2.75}})
        self.assertEqual(limits["REQ-MECH-005"], {"rom_min_clearance_m": {"minimum": 0.003}})
        at_bound = {"static_torque_max_abs_nm": 2.75, "rom_min_clearance_m": 0.003}
        for case_id, metric, beyond in (("REQ-MECH-001", "static_torque_max_abs_nm", math.nextafter(2.75, 3)),
                                        ("REQ-MECH-005", "rom_min_clearance_m", math.nextafter(0.003, 0))):
            with self.subTest(case_id):
                self.assertEqual(_compare_corner(at_bound, limits[case_id])[0].value, "PASS")
                self.assertEqual(_compare_corner({metric: beyond}, limits[case_id])[0].value, "FAIL")
        entries["REQ-MECH-001"]["tolerance"] = -0.1
        with self.assertRaisesRegex(ValueError, "tolerance"):
            validate(requirements, "engineering-model/v1/engineering-requirements")

    def test_a_literal_limit_must_be_in_the_metric_s_unit(self):
        for field, value, message in (("unit", "mN*m", "unit mN\\*m != the unit of static_torque_max_abs_nm"),
                                      ("metric", "made_up_metric", "produces no metric 'made_up_metric'")):
            with self.subTest(field):
                requirements = copy.deepcopy(self.requirements)
                next(r for r in requirements["requirements"] if r["requirement_id"] == "REQ-MECH-001")[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    compile_mechanical(self.model, requirements)

    def test_scenarios_and_derivations_come_from_the_domain_vocabulary(self):
        MECHANICAL.check_requirements(self.requirements)
        for label, edit in (
                ("unknown scenario", lambda r: r["requirements"][0]["scenario"].update(name="thermal_soak")),
                ("unknown parameter", lambda r: r["requirements"][0]["scenario"].update(ambient_k=300.0)),
                ("unknown derivation", lambda r: r["reference_values"][0].update(derivation="made_up"))):
            requirements = copy.deepcopy(self.requirements)
            edit(requirements)
            with self.subTest(label):
                # The generic schema leaves the vocabulary open; the domain closes it.
                validate(requirements, "engineering-model/v1/engineering-requirements")
                with self.assertRaises(ValueError):
                    MECHANICAL.check_requirements(requirements)

    def test_a_known_quantity_limit_is_used_and_its_unit_checked(self):
        model = copy.deepcopy(self.model)
        torque = component(model, "actuator")["domains"]["mechanical"]["continuous_output_torque"]
        torque.update(quantity(6.0, "N*m", Status.SPECIFIED, source("datasheet", "fixture")))
        _golden, corners, blocked = compile_mechanical(model, self.requirements)
        case = next(case for case in corners["cases"] if case["id"] == "REQ-XD-001")
        self.assertEqual(case["metric_limits"], {"static_torque_max_abs_nm": {"maximum": 6.0}})
        torque["unit"] = "kN*m"
        with self.assertRaisesRegex(ValueError, "unit"):
            compile_mechanical(model, self.requirements)


class TestMechanicalModel(unittest.TestCase):
    def setUp(self):
        self.model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        self.xml = build_mjcf(self.model)

    def exclusions(self, xml):
        import re

        return {tuple(sorted(pair)) for pair in re.findall(r'<exclude body1="([^"]+)" body2="([^"]+)"/>', xml)}

    def test_bearing_exclusion_is_the_realizer_and_the_joint_parent(self):
        """Regression: the shaft runs in the pillar's bore, but the pair excluded was
        (shaft, base_plate). The phantom shaft/pillar contact then pushed on inverse
        dynamics, and the V3 golden caught a 1.479 vs 1.682 N*m torque mismatch."""
        pairs = self.exclusions(self.xml)
        self.assertIn(("pillar", "shaft"), pairs)
        self.assertNotIn(("base_plate", "shaft"), pairs)

    def test_the_joint_pair_itself_stays_checked(self):
        self.assertNotIn(("link", "pillar"), self.exclusions(self.xml))
        self.assertIn('filterparent="disable"', self.xml)

    def test_full_inertia_uses_mujoco_ordering(self):
        """MuJoCo reads fullinertia as Ixx Iyy Izz Ixy Ixz Iyz."""
        import re

        model = copy.deepcopy(self.model)
        tensor = [[1.0, 0.4, 0.5], [0.4, 2.0, 0.6], [0.5, 0.6, 3.0]]
        component(model, "payload")["physical"]["inertia_about_com"]["value"] = tensor
        xml = build_mjcf(model)
        block = xml[xml.index('<body name="payload">'):]
        values = [float(v) for v in re.search(r'fullinertia="([^"]+)"', block).group(1).split()]
        self.assertEqual(values, [1.0, 2.0, 3.0, 0.4, 0.5, 0.6])

    def test_unknown_mass_makes_the_mechanical_model_incomplete(self):
        model = copy.deepcopy(self.model)
        component(model, "payload")["physical"]["mass"] = unknown("kg", ANNOTATION, "fixture")
        with self.assertRaisesRegex(ModelIncomplete, r"components/payload/physical/mass \(UNKNOWN\)") as caught:
            build_mjcf(model)
        self.assertEqual(caught.exception.inputs, [{"path": "components/payload/physical/mass", "status": "UNKNOWN"}])

    def test_any_null_mass_makes_the_mechanical_model_incomplete(self):
        for status in NULL_STATUSES:
            with self.subTest(status=status.value):
                model = copy.deepcopy(self.model)
                component(model, "payload")["physical"]["mass"] = null_quantity("kg", status)
                with self.assertRaisesRegex(ModelIncomplete, rf"components/payload/physical/mass \({status.value}\)") as caught:
                    build_mjcf(model)
                self.assertEqual(caught.exception.inputs,
                                 [{"path": "components/payload/physical/mass", "status": status.value}])

    def test_every_missing_value_is_named_not_only_the_first(self):
        model = copy.deepcopy(self.model)
        component(model, "payload")["physical"]["mass"] = unknown("kg", ANNOTATION, "fixture")
        model["joints"][0]["limits"]["upper"] = unknown("rad", ANNOTATION, "fixture")
        with self.assertRaises(ModelIncomplete) as caught:
            build_mjcf(model)
        self.assertEqual(caught.exception.inputs, [
            {"path": f"joints/{model['joints'][0]['joint_id']}/limits/upper", "status": "UNKNOWN"},
            {"path": "components/payload/physical/mass", "status": "UNKNOWN"},
        ])

    def test_rotation_to_quaternion_round_trips(self):
        for angle in (0.0, 0.3, math.pi / 2, math.pi - 1e-3, math.pi):
            c, s = math.cos(angle), math.sin(angle)
            for rotation in ([[1, 0, 0], [0, c, -s], [0, s, c]], [[c, 0, s], [0, 1, 0], [-s, 0, c]],
                             [[c, -s, 0], [s, c, 0], [0, 0, 1]]):
                w, x, y, z = rotation_to_quaternion(rotation)
                rebuilt = [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
                ]
                for i in range(3):
                    for j in range(3):
                        self.assertAlmostEqual(rebuilt[i][j], rotation[i][j], places=12)


class TestComparisonAndSanity(unittest.TestCase):
    def test_numbers_compare_with_tolerance_and_everything_else_exactly(self):
        self.assertEqual(same_content({"a": [1.0, "x"]}, {"a": [1.0 + 1e-13, "x"]}), [])
        self.assertTrue(same_content({"a": 1.0}, {"a": 1.0001}))
        self.assertTrue(same_content({"a": "x"}, {"a": "y"}))
        self.assertTrue(same_content({"a": 1}, {"b": 1}))
        self.assertEqual(same_text('pos="1 2.5"', 'pos="1 2.5000000000001"', "t"), [])
        self.assertTrue(same_text('pos="1 2.5"', 'pos="1 2.6"', "t"))
        self.assertTrue(same_text('pos="1"', 'quat="1"', "t"))

    def test_physically_impossible_inertia_is_rejected(self):
        self.assertEqual(inertia_problems("ok", [[2, 0, 0], [0, 3, 0], [0, 0, 4]]), [])
        self.assertIn("not symmetric", inertia_problems("a", [[2, 1, 0], [0, 3, 0], [0, 0, 4]])[0])
        self.assertIn("positive definite", inertia_problems("b", [[1, 0, 0], [0, 1, 0], [0, 0, -1]])[0])
        self.assertIn("triangle inequality", inertia_problems("c", [[1, 0, 0], [0, 1, 0], [0, 0, 5]])[0])




def _rotation_z(degrees):
    c, s_ = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _apply(r, v):
    return [sum(r[i][k] * v[k] for k in range(3)) for i in range(3)]


def _yawed(degrees):
    """The pendulum with the whole assembly, and its annotated sense, turned about +Z."""
    extraction, annotations = pendulum()
    turn = _rotation_z(degrees)
    for part in extraction["parts"]:
        part["rotation"] = _matmul(turn, part["rotation"])
        part["translation"] = _apply(turn, part["translation"])
    annotations["joints"][0]["axis_sense"] = _apply(turn, annotations["joints"][0]["axis_sense"])
    return build(extraction, annotations)


class TestJointSense(unittest.TestCase):
    """Regression: the joint's sense came from a canonicalisation rule, so a rigid
    re-orientation of the whole design could mirror its range unseen."""

    DERIVATIONS = ("gravity_torque_as_modelled", "small_oscillation_period", "moving_mass", "equilibrium_angle")

    def test_physics_is_invariant_under_a_rigid_yaw_of_the_whole_design(self):
        reference = {name: reference_value(build(*pendulum()), name)[0] for name in self.DERIVATIONS}
        for degrees in (30.0, 90.0, 179.8, 180.2, 271.0):
            model = _yawed(degrees)
            for name in self.DERIVATIONS:
                with self.subTest(degrees=degrees, derivation=name):
                    self.assertAlmostEqual(reference_value(model, name)[0], reference[name], places=9)

    def test_the_annotated_sense_sets_the_direction_of_a_positive_angle(self):
        extraction, annotations = pendulum()
        forward = build(extraction, annotations)
        annotations["joints"][0]["axis_sense"] = [0.0, -1.0, 0.0]
        reverse = build(extraction, annotations)
        self.assertEqual(forward["joints"][0]["axis"]["value"], [0.0, 1.0, 0.0])
        self.assertEqual(reverse["joints"][0]["axis"]["value"], [0.0, -1.0, 0.0])
        self.assertAlmostEqual(reference_value(forward, "equilibrium_angle")[0], math.pi / 2, places=12)
        self.assertAlmostEqual(reference_value(reverse, "equilibrium_angle")[0], -math.pi / 2, places=12)

    def test_a_sense_far_from_the_cad_axis_is_unknown(self):
        extraction, annotations = pendulum()
        annotations["joints"][0]["axis_sense"] = [1.0, 0.5, 0.0]  # 63 degrees from +Y
        axis = build(extraction, annotations)["joints"][0]["axis"]
        self.assertEqual(axis["status"], "UNKNOWN")
        self.assertIn("60 degrees", axis["note"])


class TestGeometryConventions(unittest.TestCase):
    def test_inertia_rotates_as_r_i_r_transpose(self):
        """Regression for the reviewer's surviving mutant: R^T I R passed because the
        only rotated part was symmetric under a 90-degree turn."""
        extraction, annotations = pendulum()
        turn = _rotation_z(30.0)
        extraction["parts"][1]["rotation"] = turn  # a 20 x 20 x 20 bob is isotropic;
        a, b, c = 40.0, 20.0, 10.0  # so make it a 40 x 20 x 10 box
        box = box_part("bob", (a, b, c), (120, -10, 40), cylinders=extraction["parts"][1]["cylindrical_faces"])
        box["rotation"] = turn
        extraction["parts"][1] = box
        model = build(extraction, annotations)
        got = component(model, "bob")["physical"]["inertia_about_com"]["value"]
        mass = 1000.0 * a * b * c * 1e-9
        local = [mass * (b * b + c * c) / 12 * 1e-6, mass * (a * a + c * c) / 12 * 1e-6, mass * (a * a + b * b) / 12 * 1e-6]
        diagonal = [[local[0], 0, 0], [0, local[1], 0], [0, 0, local[2]]]
        transpose = [[turn[j][i] for j in range(3)] for i in range(3)]
        expected = _matmul(_matmul(turn, diagonal), transpose)
        wrong = _matmul(_matmul(transpose, diagonal), turn)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(got[i][j], expected[i][j], places=15)
        self.assertGreater(abs(expected[0][1] - wrong[0][1]), 1e-9, "fixture must tell the two apart")

    def test_coaxial_faces_at_different_axial_positions_share_one_axis(self):
        extraction, annotations = pendulum()
        faces = extraction["parts"][1]["cylindrical_faces"]
        extraction["parts"][1]["cylindrical_faces"] = [
            *faces, {"axis_origin_local": [-90.0, 55.0, 10.0], "axis_direction_local": [0.0, -1.0, 0.0], "radius": 3.0}]
        axis = build(extraction, annotations)["joints"][0]["axis"]
        self.assertEqual(axis["status"], "DERIVED")
        self.assertEqual(axis["value"], [0.0, 1.0, 0.0])

    def test_period_of_a_tilted_axis_uses_the_perpendicular_gravity(self):
        """An axis tilted 30 degrees out of the horizontal feels g cos(30)."""
        extraction, annotations = pendulum()
        tilt = math.radians(30.0)
        direction = [0.0, math.cos(tilt), math.sin(tilt)]
        extraction["parts"][1]["cylindrical_faces"][0]["axis_direction_local"] = direction
        annotations["joints"][0]["axis_sense"] = direction
        model = build(extraction, annotations)
        mass, lever = 0.008, 0.1
        inertia_axis = mass * 2 * 0.02**2 / 12 + mass * lever**2
        expected = 2 * math.pi * math.sqrt(inertia_axis / (mass * STANDARD_GRAVITY * math.cos(tilt) * lever))
        self.assertAlmostEqual(reference_value(model, "small_oscillation_period")[0], expected, places=12)


class TestMoveReferences(unittest.TestCase):
    """Closed forms for the rated move, checked against arithmetic done here."""

    SCENARIO = {"name": "rated_move", "start_rad": 0.0, "end_rad": -1.2, "duration_s": 0.5}

    def test_minimum_jerk_peaks(self):
        model = build(*pendulum())
        self.assertAlmostEqual(reference_value(model, "min_jerk_peak_speed", self.SCENARIO)[0], 1.875 * 1.2 / 0.5)
        self.assertAlmostEqual(reference_value(model, "min_jerk_peak_accel", self.SCENARIO)[0],
                               10 / math.sqrt(3) * 1.2 / 0.25)

    def test_rated_move_peak_torque_for_a_point_like_bob(self):
        """Bob at radius d about +Y: gravity torque m g d cos(q), inertia I_com + m d^2."""
        model = build(*pendulum())
        mass, lever = 0.008, 0.1
        inertia = mass * 2 * 0.02**2 / 12 + mass * lever**2
        peak = 0.0
        for step in range(501):
            s_ = step / 500
            q = -1.2 * (10 * s_**3 - 15 * s_**4 + 6 * s_**5)
            accel = -1.2 * (60 * s_ - 180 * s_**2 + 120 * s_**3) / 0.25
            peak = max(peak, abs(inertia * accel - mass * STANDARD_GRAVITY * lever * math.cos(q)))
        self.assertAlmostEqual(reference_value(model, "rated_move_peak_torque", self.SCENARIO)[0], peak, places=12)

    def test_the_payload_override_is_applied_to_every_reference(self):
        model = build(*pendulum())
        scenario = {"name": "static_sweep", "payload_component": "bob", "payload_mass_kg": 0.024}
        self.assertAlmostEqual(reference_value(model, "moving_mass", scenario)[0], 0.024, places=15)
        self.assertAlmostEqual(reference_value(model, "gravity_torque_as_modelled", scenario)[0],
                               0.024 * STANDARD_GRAVITY * 0.1, places=12)


def _three_part(realizer_side):
    """frame + arm, with a separate pin on either side of the joint."""
    frame = box_part("frame", (40, 40, 40), (-20, -20, -60))
    arm = box_part("arm", (100, 10, 10), (0, 30, -5))
    pin = box_part("pin", (6, 60, 6), (-3, -25, -3),
                   cylinders=[{"axis_origin_local": [3.0, 0.0, 3.0], "axis_direction_local": [0.0, 1.0, 0.0], "radius": 3.0}])
    extraction = {"source": {"path": "fixture.step", "sha256": "0" * 64, "format": "step"},
                  "length_unit": "mm", "parts": [frame, arm, pin]}
    water = {"name": "water", "density": quantity(1000.0, "kg/m^3", Status.SPECIFIED, ANNOTATION)}
    annotations = {
        "design_id": "three", "materials": {"water": water},
        "parts": {name: {"component_id": name, "kind": "structure", "material": "water"} for name in ("frame", "arm", "pin")},
        "joints": [{"joint_id": "j1", "type": "revolute", "parent": "frame", "child": "arm", "realized_by": "pin",
                    "axis_sense": [0.0, 1.0, 0.0],
                    "limits": {"lower": quantity(-1.0, "rad", Status.SPECIFIED, ANNOTATION),
                               "upper": quantity(1.0, "rad", Status.SPECIFIED, ANNOTATION)}}],
        "attachments": [{"component": "pin", "attached_to": realizer_side}],
        "components_without_cad": [], "relationships": [],
    }
    return build(extraction, annotations)


class TestBearingExclusion(unittest.TestCase):
    def exclusions(self, model):
        import re

        return {tuple(sorted(p)) for p in re.findall(r'<exclude body1="([^"]+)" body2="([^"]+)"/>', build_mjcf(model))}

    def test_a_shaft_on_the_moving_side_runs_in_the_parent(self):
        self.assertIn(("frame", "pin"), self.exclusions(_three_part("arm")))
        self.assertNotIn(("arm", "frame"), self.exclusions(_three_part("arm")))

    def test_a_fixed_pin_runs_in_the_child(self):
        """Regression: a fixed pin was never excluded, so clearance failed at every pose."""
        pairs = self.exclusions(_three_part("frame"))
        self.assertIn(("arm", "pin"), pairs)
        self.assertNotIn(("arm", "frame"), pairs)

    def test_a_joint_realised_by_its_own_child_excludes_the_joint_pair_openly(self):
        """The pair must be excluded -- its proxies overlap by construction -- and the
        clearance scenario then reports it unchecked rather than passing it."""
        self.assertIn(("bob", "frame"), self.exclusions(build(*pendulum())))


class TestRefusals(unittest.TestCase):
    """Every documented refusal, so none can be deleted unnoticed."""

    def test_builder_refuses_inconsistent_annotations(self):
        cases = {
            "joint names a missing component": lambda a: a["joints"][0].__setitem__("child", "ghost"),
            "attachment names a missing component": lambda a: a["attachments"].append({"component": "ghost", "attached_to": "bob"}),
            "relationship names a missing component": lambda a: a["relationships"].append({"relation": "drives", "from": "ghost", "to": "bob"}),
            "a component is declared twice": lambda a: a["components_without_cad"].append(
                {"component_id": "bob", "name": "again", "kind": "other", "domains": {}}),
        }
        for label, mutate in cases.items():
            extraction, annotations = pendulum()
            mutate(annotations)
            with self.subTest(label), self.assertRaises(ValueError):
                build(extraction, annotations)

    def test_mechanical_model_refuses_what_it_cannot_represent(self):
        model = build(*pendulum())
        two = copy.deepcopy(model)
        two["joints"].append(copy.deepcopy(two["joints"][0]))
        with self.assertRaisesRegex(ModelIncomplete, "exactly one joint"):
            build_mjcf(two)
        welded = copy.deepcopy(model)
        welded["relationships"].append({"relation": "attached_to", "from": "bob", "to": "frame", "source": ANNOTATION})
        with self.assertRaisesRegex(ModelIncomplete, "rigidly attached"):
            build_mjcf(welded)
        axis = copy.deepcopy(model)
        axis["joints"][0]["axis"] = unknown("1", ANNOTATION, "fixture")
        with self.assertRaisesRegex(ModelIncomplete, r"joints/\w+/axis \(UNKNOWN\)"):
            build_mjcf(axis)


class TestUnknownsIndexOrder(unittest.TestCase):
    def test_index_is_sorted_whatever_the_facet_order(self):
        """Decay-proof twin of the regression test: its own fixture, not the sample's gaps."""
        extraction, annotations = pendulum()
        annotations["components_without_cad"] = [{
            "component_id": "motor", "name": "motor", "kind": "motor",
            "domains": {"thermal": {"limit": unknown("degC", ANNOTATION, "x")},
                        "electrical": {"kt": unknown("N*m/A", ANNOTATION, "x")},
                        "mechanical": {"torque": unknown("N*m", ANNOTATION, "x")}},
        }]
        model = build(extraction, annotations)
        paths = [entry["path"] for entry in model["unknowns"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), 3)
        reversed_model = json.loads(json.dumps(model, sort_keys=True))
        facets = component(reversed_model, "motor")["domains"]
        component(reversed_model, "motor")["domains"] = dict(reversed(list(facets.items())))
        self.assertEqual(index_unknowns(reversed_model), model["unknowns"])


class TestTolerance(unittest.TestCase):
    """The documented reproducibility tolerance, pinned: 1e-9 relative, scaled per array."""

    def test_scalars(self):
        self.assertEqual(same_content(1.0, 1.0 + 5e-10), [])
        self.assertTrue(same_content(1.0, 1.0 + 2e-9))

    def test_arrays_scale_by_their_largest_element(self):
        """Regression: near-zero inertia products carry kernel noise that a per-element
        relative test called a difference, which would fail CI off macOS."""
        self.assertEqual(same_content([[1e10, 4.8e-7], [4.8e-7, 1e10]], [[1e10, -3e-7], [-3e-7, 1e10]]), [])
        self.assertTrue(same_content([[1e10, 0.0]], [[1e10, 30.0]]))  # 3e-9 of the scale

    def test_xml_identifiers_compare_exactly(self):
        self.assertTrue(same_text('<body name="joint_001"/>', '<body name="joint_1"/>', "m"))
        self.assertTrue(same_text('pos="1 2"', 'pos="1 2 3"', "m"))
        self.assertEqual(same_text('fullinertia="1e-3 0 4.8e-20"', 'fullinertia="1e-3 0 -3e-20"', "m"), [])

class TestInputPropagation(unittest.TestCase):
    """What a check's inputs make of its verdict (results.propagate), and how they are found."""

    def setUp(self):
        self.model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())

    def test_any_null_input_blocks_whatever_the_verdict_and_before_an_assumption(self):
        from ecad_model.results import propagate

        for status in NULL_STATUSES:
            for verdict, reason in (("PASS", "CORNER_LIMITS_PASSED"), ("FAIL", "CORNER_LIMITS_FAILED"),
                                    ("INCONCLUSIVE", "CORNER_METRICS_INCONCLUSIVE"), ("BLOCKED", "TOOL_NOT_INSTALLED")):
                with self.subTest(status=status.value, verdict=verdict):
                    inputs = [{"path": "x", "status": status.value}, {"path": "y", "status": "AI_ASSUMPTION"}]
                    self.assertEqual(propagate(inputs, [], verdict, reason),
                                     ("BLOCKED", "MISSING_REQUIRED_INPUT", [f"{status.value}: x"]))

    def test_an_unresolvable_input_is_inconclusive_unless_already_blocked(self):
        from ecad_model.results import propagate

        self.assertEqual(propagate([], ["components/ghost/physical/mass"], "PASS", "CORNER_LIMITS_PASSED"),
                         ("INCONCLUSIVE", "INPUT_NOT_RESOLVABLE",
                          ["input not resolvable in the model: components/ghost/physical/mass"]))
        self.assertIsNone(propagate([], ["components/ghost/physical/mass"], "BLOCKED", "TOOL_NOT_INSTALLED"))

    def test_only_a_comparator_verdict_is_withheld_for_an_ai_assumption(self):
        from ecad_model.results import propagate

        assumed = [{"path": "components/link/material/density", "status": "AI_ASSUMPTION"}]
        for verdict, reason in (("PASS", "CORNER_LIMITS_PASSED"), ("FAIL", "CORNER_LIMITS_FAILED")):
            with self.subTest(verdict):
                self.assertEqual(propagate(assumed, [], verdict, reason),
                                 ("INCONCLUSIVE", "INPUT_IS_AI_ASSUMPTION",
                                  ["AI_ASSUMPTION: components/link/material/density"]))
        # A crash or a missing tool is not a judgement on the design; it keeps its own reason.
        for verdict, reason in (("FAIL", "ADAPTER_EXECUTION_ERROR"), ("FAIL", "CASE_CONFIGURATION_INVALID"),
                                ("BLOCKED", "TOOL_NOT_INSTALLED")):
            with self.subTest(verdict=verdict, reason=reason):
                self.assertIsNone(propagate(assumed, [], verdict, reason))

    def test_an_assumption_that_names_a_parent_is_still_an_input(self):
        """An AI_ASSUMPTION is not walked past because its derived_from names
        another quantity, nor because it names itself."""
        from ecad_model.results import input_leaves

        for parents in (["components/pillar/material/density"], ["components/link/material/density"]):
            with self.subTest(parents=parents):
                model = copy.deepcopy(self.model)
                density = component(model, "link")["material"]["density"]
                density.update(status="AI_ASSUMPTION", source=source("ai", "fixture"), derived_from=parents)
                found, unresolved = input_leaves(model, ["components/link/physical/mass"])
                self.assertIn({"path": "components/link/material/density", "status": "AI_ASSUMPTION"}, found)
                self.assertEqual(unresolved, [])

    def test_a_derived_quantity_is_listed_through_its_inputs(self):
        from ecad_model.results import input_leaves

        found, _ = input_leaves(self.model, ["components/link/physical/mass"])
        self.assertEqual(found, [{"path": "components/link/geometry/volume", "status": "DERIVED"},
                                 {"path": "components/link/material/density", "status": "ESTIMATED"}])

    def test_an_unresolvable_path_is_reported_not_raised(self):
        from ecad_model.results import input_leaves

        model = copy.deepcopy(self.model)
        component(model, "link")["physical"]["mass"]["derived_from"].append("components/pilar/material/density")
        found, unresolved = input_leaves(model, ["components/link/physical/mass", "design/annotations.json"])
        self.assertEqual(unresolved, ["components/pilar/material/density", "design/annotations.json"])
        self.assertIn({"path": "components/link/material/density", "status": "ESTIMATED"}, found)

    def test_lineage_problems_name_a_dangling_parent_and_a_cycle(self):
        from ecad_model.results import lineage_problems

        self.assertEqual(lineage_problems(self.model), [])
        dangling = copy.deepcopy(self.model)
        component(dangling, "link")["physical"]["mass"]["derived_from"].append("components/pilar/material/density")
        self.assertEqual(lineage_problems(dangling), [
            "components/link/physical/mass: derived_from names components/pilar/material/density, "
            "which is not a quantity in the model"])
        cycle = copy.deepcopy(self.model)
        component(cycle, "link")["material"]["density"]["derived_from"] = ["components/link/physical/mass"]
        self.assertTrue(any("leads back to itself" in problem for problem in lineage_problems(cycle)))

    def test_an_annotated_value_with_a_dangling_parent_reaches_the_model_and_is_caught(self):
        """The builder copies an annotated quantity whole; lineage_problems is what the build refuses on."""
        from ecad_model.results import lineage_problems

        extraction, annotations = pendulum()
        annotations["materials"]["water"]["density"]["derived_from"] = ["components/frame/material/densty"]
        self.assertTrue(lineage_problems(build(extraction, annotations)))


class TestMechanicalDependencies(unittest.TestCase):
    """What the mechanical adapter says each metric and reference rests on."""

    def setUp(self):
        self.model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        self.moving = ["link", "payload", "shaft"]

    def test_a_holding_torque_rests_on_gravity_the_joint_range_and_every_moving_mass(self):
        paths = MECHANICAL.dependencies(self.model, "static_torque_max_abs_nm", {"name": "static_sweep"})
        for path in ("design/gravity", "joints/j1/axis", "joints/j1/origin",
                     "joints/j1/limits/lower", "joints/j1/limits/upper",
                     *(f"components/{cid}/physical/{name}" for cid in self.moving
                       for name in ("mass", "center_of_mass", "inertia_about_com"))):
            with self.subTest(path):
                self.assertIn(path, paths)
        self.assertFalse([p for p in paths if p.startswith(("components/pillar/", "components/base_plate/"))],
                         "a fixed body cannot change a holding torque")

    def test_clearance_rests_on_geometry_and_the_range_not_on_mass(self):
        paths = MECHANICAL.dependencies(self.model, "rom_min_clearance_m", {"name": "rom_sweep"})
        for path in ("joints/j1/limits/lower", "joints/j1/limits/upper",
                     "components/pillar/geometry/bounding_box_local/min",
                     "components/base_plate/geometry/bounding_box_local/max",
                     "components/link/geometry/bounding_box_local/min"):
            with self.subTest(path):
                self.assertIn(path, paths)
        self.assertFalse([p for p in paths if "/physical/" in p or p == "design/gravity"])

    def test_references_list_gravity_exactly_when_they_use_it(self):
        mass_inputs = MECHANICAL.reference_inputs(self.model, "moving_mass", {"name": "static_sweep"})
        self.assertIn("components/link/physical/mass", mass_inputs)
        self.assertNotIn("design/gravity", mass_inputs)
        for derivation, scenario in (("gravity_torque_as_modelled", {"name": "static_sweep"}),
                                     ("small_oscillation_period", {"name": "free_swing", "amplitude_rad": 0.01}),
                                     ("equilibrium_angle", {"name": "free_swing", "amplitude_rad": 0.01}),
                                     ("rated_move_peak_torque", {"name": "rated_move", "start_rad": 0.0,
                                                                 "end_rad": -1.0, "duration_s": 0.8})):
            with self.subTest(derivation):
                self.assertIn("design/gravity", MECHANICAL.reference_inputs(self.model, derivation, scenario))

    def test_gravity_with_no_value_blocks_and_no_gravity_at_all_does_not_apply(self):
        for status in NULL_STATUSES:
            with self.subTest(status=status.value):
                model = copy.deepcopy(self.model)
                model["design"]["gravity"] = null_quantity("m/s^2", status)
                with self.assertRaises(ReferenceBlocked) as caught:
                    reference_value(model, "gravity_torque_as_modelled", {"name": "static_sweep"})
                self.assertIn({"path": "design/gravity", "status": status.value}, caught.exception.paths)
        weightless = copy.deepcopy(self.model)
        del weightless["design"]["gravity"]
        with self.assertRaises(ReferenceBlocked) as caught:
            reference_value(weightless, "gravity_torque_as_modelled", {"name": "static_sweep"})
        self.assertEqual(caught.exception.paths, [])
        self.assertGreater(reference_value(weightless, "moving_mass", {"name": "static_sweep"})[0], 0)


class TestRequirementRefusals(unittest.TestCase):
    """What the compiler and the mechanical vocabulary refuse, each on its own."""

    def setUp(self):
        self.model = json.loads((ITEM / "derived" / "engineering_model.json").read_text())
        self.requirements = json.loads((ITEM / "requirements" / "requirements.json").read_text())

    def test_a_reference_unit_and_metric_are_checked_as_a_requirement_s_are(self):
        for field, value, message in (("unit", "mN*m", "unit mN\\*m != the unit of static_torque_at_zero_nm"),
                                      ("metric", "made_up_metric", "produces no metric 'made_up_metric'")):
            with self.subTest(field):
                requirements = copy.deepcopy(self.requirements)
                requirements["reference_values"][0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    compile_mechanical(self.model, requirements)

    def test_an_id_shared_by_a_reference_and_a_requirement_is_refused(self):
        requirements = copy.deepcopy(self.requirements)
        requirements["requirements"][0]["requirement_id"] = requirements["reference_values"][0]["reference_id"]
        with self.assertRaisesRegex(ValueError, "must be unique: REF-MECH-001 repeat"):
            compile_mechanical(self.model, requirements)

    def test_an_id_the_case_engine_uses_for_a_whole_gate_is_refused(self):
        for reserved in ("golden-cases", "golden-manifest", "corners-cases", "corners-manifest"):
            with self.subTest(reserved):
                requirements = copy.deepcopy(self.requirements)
                requirements["requirements"][0]["requirement_id"] = reserved
                with self.assertRaisesRegex(ValueError, f"{reserved}: reserved"):
                    compile_mechanical(self.model, requirements)

    def test_a_limit_quantity_that_is_not_one_number_is_refused(self):
        requirements = copy.deepcopy(self.requirements)
        clearance = next(r for r in requirements["requirements"] if r["requirement_id"] == "REQ-MECH-005")
        clearance["limit"] = {"quantity": "joints/j1/origin"}
        with self.assertRaisesRegex(ValueError, "REQ-MECH-005: the limit joints/j1/origin is not a single number"):
            compile_mechanical(self.model, requirements)

    def test_each_scenario_carries_what_its_case_reads(self):
        MECHANICAL.check_requirements(self.requirements)
        move = {"name": "rated_move", "start_rad": 0.0, "end_rad": -1.0, "duration_s": 0.8}
        for label, edit in (
                ("rated move without its end", lambda r: r["requirements"][2]["scenario"].pop("end_rad")),
                ("free swing without its amplitude", lambda r: r["reference_values"][1]["scenario"].pop("amplitude_rad")),
                ("a move derivation on a static sweep", lambda r: r["reference_values"][6].update(scenario={"name": "static_sweep"})),
                ("a reference scenario outside the vocabulary", lambda r: r["reference_values"][0]["scenario"].update(name="thermal_soak")),
                ("a move derivation on a free swing", lambda r: r["reference_values"][8].update(
                    scenario={"name": "free_swing", "amplitude_rad": 0.01}))):
            requirements = copy.deepcopy(self.requirements)
            self.assertEqual(requirements["requirements"][2]["scenario"], {**move, "end_rad": -1.5707963267948966})
            edit(requirements)
            with self.subTest(label), self.assertRaises(ValueError):
                MECHANICAL.check_requirements(requirements)


class TestNonFiniteNumbers(unittest.TestCase):
    """JSON has no Infinity or NaN; a comparison with one proves nothing."""

    def test_an_infinity_is_not_close_to_a_number(self):
        for committed, fresh in (({"m": math.inf}, {"m": 1.0}), ({"m": [math.inf, 0.0]}, {"m": [1.0, 0.0]}),
                                 ({"m": 1.0}, {"m": -math.inf}), ({"m": math.nan}, {"m": math.nan})):
            with self.subTest(committed=committed):
                self.assertTrue(same_content(committed, fresh))
        self.assertTrue(same_text('pos="inf 2"', 'pos="1 2"', "m"))
        self.assertEqual(same_content({"m": [1.0, 2.0]}, {"m": [1.0, 2.0]}), [])

    def test_untrusted_json_may_not_carry_them(self):
        from ecad_model.dataset import _json

        for text in ("[Infinity]", "{\"m\": -Infinity}", "[NaN]"):
            with self.subTest(text), self.assertRaisesRegex(ValueError, "not a JSON number"):
                _json(text)
        self.assertEqual(_json("[1.5]"), [1.5])


class TestContractSchemas(unittest.TestCase):
    """Rules the manifest and results schemas state, each shown refusing on its own."""

    def setUp(self):
        self.manifest = json.loads((ITEM / "dataset-item.json").read_text())

    def test_the_manifest_restates_the_licence_rules_of_the_provenance(self):
        validate(self.manifest, "cad-dataset/v1/dataset-item")
        cases = {}
        unverified = copy.deepcopy(self.manifest)
        unverified["source"]["license"]["license_verified"] = False  # training_use_permitted stays true
        cases["unverified but permitting training"] = (unverified, "training_use_permitted|redistribution_permitted")
        uncited = copy.deepcopy(self.manifest)
        del uncited["source"]["license"]["license_text"]
        cases["verified without the licence text"] = (uncited, "license_text")
        third = copy.deepcopy(self.manifest)
        third["source_url"] = "https://example.org/part.step"
        third["source"]["origin"] = {"kind": "third_party", "author": "someone", "url": "https://example.org/part.step",
                                     "modifications": "none"}
        cases["third party verified without a verifier"] = (third, "verified_by")
        unmodified = copy.deepcopy(third)
        unmodified["source"]["license"].update(verified_by="a named reviewer", verified_at="2026-09-26")
        validate(unmodified, "cad-dataset/v1/dataset-item")
        del unmodified["source"]["origin"]["modifications"]
        cases["third party without its modifications"] = (unmodified, "modifications")
        anonymous = copy.deepcopy(third)
        anonymous["source"]["license"].update(verified_by="a named reviewer", verified_at="2026-09-26")
        anonymous["source_url"] = None
        cases["third party with no source URL"] = (anonymous, "self_authored")
        undated = copy.deepcopy(third)
        undated["source"]["license"]["verified_by"] = "a named reviewer"
        cases["third party verified by someone, but not when"] = (undated, "verified_at")
        unread = copy.deepcopy(third)
        unread["source"]["license"].update(license_verified=False, redistribution_permitted=False,
                                           training_use_permitted=False)
        del unread["source"]["license"]["license_text"]
        cases["third party unverified, citing no licence text"] = (unread, "license_text")
        for label, (document, message) in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, message):
                validate(document, "cad-dataset/v1/dataset-item")

    def _results(self, **changes):
        requirement = json.loads((ITEM / "requirements" / "requirements.json").read_text())["requirements"][0]
        row = {
            "validation_id": "s:v4.R", "check_id": "v4.R", "domain": "mechanical", "kind": "requirement",
            "requirement": "R", "title": "t", "source": requirement["source"], "metric": "m", "component": "c",
            "cad_components": [], "illustrative": False, "status": "PASS", "reason_code": "CORNER_LIMITS_PASSED",
            "findings": [], "measured_value": 1.0, "measured_by": "v4.R", "expected_value": 2.0, "operator": "<=",
            "applied_bound": {"maximum": 2.0}, "unit": "N*m", "tolerance": 0.0, "simulator": "mujoco",
            "simulator_version": "3.14.0", "configuration": {"command": ["x"], "scenario": {"name": "s"}, "seed": 0},
            "model_version": "1.0.0", "model_sha256": "0" * 64, "model_fidelity": "EXACT_GEOMETRY",
            "inputs": [{"path": "components/c/material/density", "status": "ESTIMATED"}],
            "timestamp": "2026-09-26T00:00:00Z", "input_hash": "0" * 64, "source_dirty": False,
            "environment": {"os": "Darwin", "machine": "arm64", "python": "3.14.4", "constraints_sha256": None,
                            "tools": {}},
            "receipt_sha256": "0" * 64, "evidence": [],
        }
        row.update(changes)
        return {"$schema": "https://embeddedos.org/schemas/engineering-model/v1/validation-results.schema.json",
                "results_version": "1.0.0", "sample_id": "s", "receipt_sha256": "0" * 64, "results": [row]}

    def test_the_results_schema_refuses_what_the_result_contract_forbids(self):
        schema = "engineering-model/v1/validation-results"
        validate(self._results(), schema)
        assumed = [{"path": "components/c/material/density", "status": "AI_ASSUMPTION"}]
        refused = {
            "a PASS with no simulator version": dict(simulator_version=None),
            "a PASS with nothing measured": dict(measured_value=None),
            "an illustrative reference": dict(kind="reference", operator="within", illustrative=True, status="FAIL"),
            "a reference with a requirement's operator": dict(kind="reference", status="FAIL"),
            "an illustrative requirement not flagged": dict(kind="illustrative requirement", status="WARNING"),
            "a flagged requirement not called illustrative": dict(illustrative=True, status="WARNING"),
            "an illustrative limit that passed": dict(kind="illustrative requirement", illustrative=True),
            "a PASS resting on a null input": dict(inputs=[{"path": "x", "status": "UNKNOWN"}]),
            "a FAIL resting on a null input": dict(inputs=[{"path": "x", "status": "NOT_AVAILABLE"}], status="FAIL",
                                                   reason_code="CORNER_LIMITS_FAILED"),
            "a PASS resting on an assumption": dict(inputs=assumed),
            "a PASS by any reason resting on an assumption": dict(inputs=assumed, reason_code="FIXTURE_PASSED"),
            "a comparator FAIL resting on an assumption": dict(inputs=assumed, status="FAIL",
                                                               reason_code="CORNER_LIMITS_FAILED"),
            "a WARNING resting on an assumption": dict(inputs=assumed, kind="illustrative requirement",
                                                       illustrative=True, status="WARNING",
                                                       reason_code="WITHIN_ILLUSTRATIVE_LIMIT"),
        }
        for label, changes in refused.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate(self._results(**changes), schema)
        accepted = {
            "a crash resting on an assumption": dict(inputs=assumed, status="FAIL", reason_code="ADAPTER_EXECUTION_ERROR"),
            "a null input, BLOCKED": dict(inputs=[{"path": "x", "status": "UNKNOWN"}], status="BLOCKED",
                                          reason_code="MISSING_REQUIRED_INPUT", simulator_version=None,
                                          measured_value=None),
            "a reference and the tolerance its comparator applies": dict(
                kind="reference", operator="within", component=None, reason_code="GOLDEN_COMPARISON_PASSED",
                applied_bound={"value": 1.0, "absolute_tolerance": 1e-6}),
        }
        for label, changes in accepted.items():
            with self.subTest(accepted=label):
                validate(self._results(**changes), schema)

    def test_base_types_refuse_what_the_pipeline_cannot_honour(self):
        from ecad_model.domains import DerivedFile, Metric

        with self.assertRaisesRegex(ValueError, "unknown comparator"):
            DerivedFile(path="p", data=b"", role="domain_model", media_type="text/plain", producer="x",
                        version="1", derived_from=(), comparator="roughly")
        with self.assertRaisesRegex(ValueError, "unknown model fidelity"):
            Metric("1", "GOOD_ENOUGH")


class TestDocumentationExamples(unittest.TestCase):
    """QUALITY.md: every public function's example must be one that was actually run."""

    def test_examples_in_modules_that_need_no_cad_kernel(self):
        import doctest
        import importlib

        for name in ("quantity", "schemas", "importers.base", "importers", "builder", "mjcf", "requirements",
                     "domains", "domains.mechanical", "results", "spice", "domains.electrical", "verilog",
                     "domains.digital"):
            with self.subTest(name):
                module = importlib.import_module(f"ecad_model.{name}")
                result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
                self.assertGreater(result.attempted, 0, f"{name} has no runnable examples")
                self.assertEqual(result.failed, 0)

    def test_every_public_function_of_the_electrical_modules_has_an_example(self):
        # attempted > 0 holds while most of a module's functions have none, and
        # it did for the electrical adapter's methods. These two modules came
        # with the electrical domain, so every public function and method in
        # them is held to QUALITY.md; the older modules, some of whose
        # functions still have none, are not held here.
        import doctest
        import importlib
        import inspect

        for name, known in (("spice", "parse_netlist"), ("domains.electrical", "ElectricalAdapter.extract")):
            module = importlib.import_module(f"ecad_model.{name}")
            examples = {test.name: len(test.examples) for test in doctest.DocTestFinder().find(module)}
            defined = {f"{module.__name__}.{attr}": value for attr, value in vars(module).items()
                       if not attr.startswith("_") and getattr(value, "__module__", None) == module.__name__}
            public = [qualified for qualified, value in defined.items() if inspect.isfunction(value)]
            public += [f"{qualified}.{attr}" for qualified, value in defined.items() if inspect.isclass(value)
                       for attr, method in vars(value).items() if not attr.startswith("_") and inspect.isfunction(method)]
            with self.subTest(name):
                self.assertIn(f"{module.__name__}.{known}", public)  # the walk finds functions and methods
                self.assertEqual([qualified for qualified in public if not examples.get(qualified)], [])

if __name__ == "__main__":
    unittest.main()
