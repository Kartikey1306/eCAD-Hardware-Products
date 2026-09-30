"""The mechanical domain: STEP assemblies, a MuJoCo model, closed-form references.

Everything the dataset runner must not know about the mechanical domain lives
here: which artefacts it reads (STEP, through the isolated OpenCASCADE
importer), how the engineering model is built from them, the MJCF domain
model, how its cases run (the case script under MuJoCo), the closed-form
reference values the goldens compare against, and the physical-sanity and
invariant checks of V1 and V2.

Reference values are computed by closed-form physics from the engineering
model, on a code path independent of the MJCF writer and the simulator, so a
frame, unit or inertia-ordering error in the conversion shows up as a golden
mismatch rather than a silently wrong answer.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..builder import VERSION as BUILDER_VERSION, build_engineering_model, resolve
from ..importers import importer_for
from ..mjcf import build_mjcf, rigid_groups
from ..quantity import is_null
from ..requirements import ReferenceBlocked
from ..schemas import validate as validate_schema
from .base import CaseTarget, DerivedFile, Extraction, Metric, SourceArtifact

VERSION = "1.0.0"  # of this adapter's derived outputs: the MJCF writer and the case target
EXTRACTION = "derived/cad_extraction.json"
SIMULATION_SCRIPT = "simulation/joint_dynamics.py"

# Every metric the case script produces. Dynamics use exact CAD mass
# properties; the range-of-motion clearance runs on each part's bounding box,
# a conservative proxy, so it is SIMPLIFIED.
METRICS = {
    "static_torque_max_abs_nm": Metric("N*m", "EXACT_GEOMETRY", "peak holding torque over the joint range"),
    "static_torque_at_zero_nm": Metric("N*m", "EXACT_GEOMETRY", "holding torque at q = 0"),
    "moving_mass_kg": Metric("kg", "EXACT_GEOMETRY", "mass of the moving rigid group"),
    "small_oscillation_period_s": Metric("s", "EXACT_GEOMETRY", "free-swing period"),
    "equilibrium_angle_rad": Metric("rad", "EXACT_GEOMETRY", "free-swing resting angle"),
    "move_peak_speed_rad_s": Metric("rad/s", "EXACT_GEOMETRY", "peak speed of the minimum-jerk move"),
    "move_peak_accel_rad_s2": Metric("rad/s^2", "EXACT_GEOMETRY", "peak acceleration of the minimum-jerk move"),
    "move_peak_torque_abs_nm": Metric("N*m", "EXACT_GEOMETRY", "peak required torque of the minimum-jerk move"),
    "rom_min_clearance_m": Metric("m", "SIMPLIFIED", "least clearance over the range, bounding-box proxies"),
    "rom_colliding_poses": Metric("1", "SIMPLIFIED", "poses with proxy contact"),
    "rom_checked_pairs": Metric("1", "SIMPLIFIED", "part pairs checked for clearance"),
    "rom_joint_pair_unchecked": Metric("1", "SIMPLIFIED", "1 when the joint's own pair could not be checked"),
}


def _cross(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _known(model: Dict[str, Any], path: str, missing: List[Dict[str, str]]) -> Any:
    item = resolve(model, path)
    if is_null(item["status"]):
        missing.append({"path": path, "status": item["status"]})
        return None
    return item["value"]


def _moving(model: Dict[str, Any]) -> List[str]:
    joint = model["joints"][0]
    roots = rigid_groups(model)
    return [
        c["component_id"]
        for c in model["components"]
        if c["cad_ref"] is not None and roots[c["component_id"]] == roots[joint["child"]]
    ]


MOVE_STEP_S = 1e-3  # the rated_move scenario samples its profile at this step

# The derivations that read a scenario's parameters, and the scenario that has them.
DERIVATION_SCENARIO = {"min_jerk_peak_speed": "rated_move", "min_jerk_peak_accel": "rated_move",
                       "rated_move_peak_torque": "rated_move"}


def _rotate(vector: Sequence[float], axis: Sequence[float], angle: float) -> List[float]:
    """Rodrigues: rotate a vector right-handedly about a unit axis."""
    c, s = math.cos(angle), math.sin(angle)
    k = _cross(axis, vector)
    along = _dot(axis, vector)
    return [v * c + ki * s + a * along * (1 - c) for v, ki, a in zip(vector, k, axis)]


def _bodies(model: Dict[str, Any], scenario: Dict[str, Any], used: List[str],
            missing: List[Dict[str, str]]) -> List[List[Any]]:
    """(mass, centre of mass, inertia) of every moving body, with any payload override applied."""
    bodies = []
    for cid in _moving(model):
        paths = [f"components/{cid}/physical/{name}" for name in ("mass", "center_of_mass", "inertia_about_com")]
        used += paths
        mass, com, inertia = (_known(model, path, missing) for path in paths)
        if mass is not None and scenario.get("payload_component") == cid:
            # Same shape at a different uniform density: the centre of mass
            # stays put and the inertia scales with the mass, exactly as the
            # scenario script applies the override.
            ratio = scenario["payload_mass_kg"] / mass
            mass, inertia = scenario["payload_mass_kg"], [[ratio * item for item in row] for row in inertia]
        bodies.append([mass, com, inertia])
    return bodies


def reference_value(
    model: Dict[str, Any], derivation: str, scenario: Optional[Dict[str, Any]] = None
) -> Tuple[float, List[str]]:
    """Compute one closed-form reference value from the engineering model.

    For a single revolute joint every one of these is exact: the moment of
    inertia about a fixed axis does not depend on the angle, and the
    velocity-dependent terms of the equation of motion vanish. None of them
    runs the simulator or reads the MJCF.

    Args:
        model: An engineering model with one joint.
        derivation: One of "moving_mass", "gravity_torque_as_modelled",
            "small_oscillation_period", "equilibrium_angle",
            "min_jerk_peak_speed", "min_jerk_peak_accel",
            "rated_move_peak_torque".
        scenario: The case's scenario. Its payload override is applied, and
            the move derivations read start_rad, end_rad and duration_s.

    Returns:
        (value in SI units, model paths the value was computed from).

    Raises:
        ReferenceBlocked: An input has a null status (its paths and statuses
            are attached), or the design records no gravity, which every
            derivation but the minimum-jerk ones needs (nothing is attached:
            the derivation does not apply).
        ValueError: The derivation name is not recognised.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[3] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> round(reference_value(model, "moving_mass")[0], 6)
        0.934914
        >>> round(reference_value(model, "min_jerk_peak_speed",
        ...                       {"name": "rated_move", "start_rad": 0.0, "end_rad": 1.0, "duration_s": 1.0})[0], 6)
        1.875
    """
    scenario = scenario or {}
    if derivation in ("min_jerk_peak_speed", "min_jerk_peak_accel"):
        delta = abs(scenario["end_rad"] - scenario["start_rad"])
        duration = scenario["duration_s"]
        # Peaks of 30s^2 - 60s^3 + 30s^4 (at s = 1/2) and of
        # 60s - 180s^2 + 120s^3 (at s = 1/2 - sqrt(3)/6).
        if derivation == "min_jerk_peak_speed":
            return 1.875 * delta / duration, []
        return (10 / math.sqrt(3)) * delta / duration**2, []

    joint = model["joints"][0]
    jid = joint["joint_id"]
    used: List[str] = [f"joints/{jid}/axis", f"joints/{jid}/origin"]
    missing: List[Dict[str, str]] = []
    axis = _known(model, f"joints/{jid}/axis", missing)
    origin = _known(model, f"joints/{jid}/origin", missing)
    bodies = _bodies(model, scenario, used, missing)
    if derivation == "moving_mass":
        if missing:
            raise ReferenceBlocked(f"{derivation} needs quantities that have no value", missing)
        return sum(mass for mass, _, _ in bodies), used
    if "gravity" not in model["design"]:
        raise ReferenceBlocked(f"{derivation} needs gravity, which this design does not record", [])
    used.append("design/gravity")
    gravity = _known(model, "design/gravity", missing)
    if missing:
        raise ReferenceBlocked(f"{derivation} needs quantities that have no value", missing)
    arms = [[c - o for c, o in zip(com, origin)] for _, com, _ in bodies]

    def gravity_torque(angle: float) -> float:
        """Torque gravity exerts about the axis with the moving group turned by angle."""
        return sum(
            _dot(_cross(_rotate(arm, axis, angle), [mass * g for g in gravity]), axis)
            for (mass, _, _), arm in zip(bodies, arms)
        )

    inertia_axis = 0.0
    for (mass, _, inertia), arm in zip(bodies, arms):
        perpendicular = [ri - _dot(arm, axis) * ai for ri, ai in zip(arm, axis)]
        inertia_axis += _dot(axis, [_dot(row, axis) for row in inertia]) + mass * _dot(perpendicular, perpendicular)

    if derivation == "gravity_torque_as_modelled":
        return abs(gravity_torque(0.0)), used

    total = sum(mass for mass, _, _ in bodies)
    combined = [sum(mass * arm[i] for (mass, _, _), arm in zip(bodies, arms)) / total for i in range(3)]
    radial = [ci - _dot(combined, axis) * ai for ci, ai in zip(combined, axis)]
    g_perp = [g - _dot(gravity, axis) * a for g, a in zip(gravity, axis)]
    if _dot(radial, radial) == 0 or _dot(g_perp, g_perp) == 0:
        raise ReferenceBlocked("the moving group's centre of mass lies on the joint axis, or the axis is vertical", [])

    if derivation == "equilibrium_angle":
        # The rotation, right-handed about the axis, that carries the centre
        # of mass directly "below" the axis along the perpendicular gravity.
        return math.atan2(_dot(_cross(radial, g_perp), axis), _dot(radial, g_perp)), used

    if derivation == "small_oscillation_period":
        # Linearised pendulum about the stable equilibrium:
        #   I_axis * theta'' = -M * |g_perp| * d * theta
        restoring = total * math.sqrt(_dot(g_perp, g_perp)) * math.sqrt(_dot(radial, radial))
        return 2 * math.pi * math.sqrt(inertia_axis / restoring), used

    if derivation == "rated_move_peak_torque":
        start, end, duration = scenario["start_rad"], scenario["end_rad"], scenario["duration_s"]
        delta, peak = end - start, 0.0
        for step in range(int(round(duration / MOVE_STEP_S)) + 1):
            s = min(1.0, step * MOVE_STEP_S / duration)
            angle = start + delta * (10 * s**3 - 15 * s**4 + 6 * s**5)
            accel = delta * (60 * s - 180 * s**2 + 120 * s**3) / duration**2
            # Required joint torque: inertia times acceleration, minus the
            # torque gravity already supplies.
            peak = max(peak, abs(inertia_axis * accel - gravity_torque(angle)))
        return peak, used

    raise ValueError(f"unknown derivation {derivation!r}")


def inertia_problems(label: str, inertia: Sequence[Sequence[float]]) -> List[str]:
    """Why an inertia tensor is physically impossible, if it is.

    A physical inertia tensor is symmetric, positive definite, and no
    principal moment exceeds the sum of the other two.

    Args:
        label: Name used in messages.
        inertia: A 3x3 matrix.

    Returns:
        One message for the first property violated; empty when possible.

    Example:
        >>> inertia_problems("box", [[2, 0, 0], [0, 3, 0], [0, 0, 4]])
        []
        >>> inertia_problems("rod", [[1, 0, 0], [0, 1, 0], [0, 0, 5]])[0].split(":")[0]
        'rod'
    """
    import numpy as np

    matrix = np.array(inertia, dtype=float)
    scale = max(float(np.abs(matrix).max()), 1e-300)
    if not np.allclose(matrix, matrix.T, rtol=0, atol=1e-9 * scale):
        return [f"{label}: inertia tensor is not symmetric"]
    moments = sorted(float(value) for value in np.linalg.eigvalsh(matrix))
    if moments[0] <= 0:
        return [f"{label}: inertia tensor is not positive definite (principal moments {moments})"]
    if moments[2] > moments[0] + moments[1] + 1e-9 * scale:
        return [f"{label}: principal moments {moments} violate the triangle inequality"]
    return []


class MechanicalAdapter:
    """One revolute joint in a STEP assembly, simulated with MuJoCo."""

    domain = "mechanical"
    formats = frozenset({"step"})
    description = ("joint statics, rated-move dynamics, free oscillation and range-of-motion clearance, "
                   "simulated with MuJoCo and compared with closed-form references")

    def _cad(self, root: Path, sources: Sequence[SourceArtifact]) -> Path:
        steps = [source for source in sources if source.format == "step"]
        if len(steps) != 1:
            raise ValueError(f"the mechanical domain reads exactly one STEP source, found {len(steps)}")
        return root / steps[0].path

    def extract(self, root: Path, sources: Sequence[SourceArtifact], annotations: Dict[str, Any],
                refs: Dict[str, str]) -> Extraction:
        """Extract the STEP assembly in isolation and build the engineering model from it.

        Raises:
            ExtractionError: The kernel refused, crashed, timed out or is absent.
            ValueError: The extraction or the model violates its schema, or
                the annotations are inconsistent with the CAD.
        """
        from ..schemas import REPOSITORY_ROOT

        cad = self._cad(root, sources)
        extraction = importer_for(cad).extract(cad, REPOSITORY_ROOT)
        validate_schema(extraction, "cad-dataset/v1/cad-extraction")
        model = build_engineering_model(
            extraction, annotations,
            design_name=annotations["design_id"].replace("_", " "), revision="1.0",
            extraction_ref=f"{refs['sample']}/{EXTRACTION}", annotations_ref=refs["annotations"],
            annotations_sha256=refs["annotations_sha256"],
        )
        kernel = extraction["importer"]
        return Extraction(
            model=model,
            producer=("ecad_model.builder", BUILDER_VERSION),
            files=[DerivedFile(
                path=EXTRACTION, data=json_bytes(extraction), role="extraction", media_type="application/json",
                producer="ecad_model.importers.step_ocp", version=f"{kernel['version']} ({kernel['kernel_version']})",
                derived_from=(cad.relative_to(root).as_posix(),))],
            tools=[{
                "tool_id": "opencascade", "name": "OpenCASCADE via cadquery-ocp",
                "version": kernel["kernel_version"],
                "invocation": ["python3", "-m", "ecad_model.importers.step_ocp", cad.relative_to(root).as_posix()],
                "settings": {"document_length_unit": "mm", "timeout_seconds": 120,
                             "address_space_limit_bytes": 2 * 1024 * 1024 * 1024,
                             "isolation": "run_process workspace copy"},
            }],
        )

    def mjcf_path(self, sample_id: str) -> str:
        return f"derived/mechanical/{sample_id}.mjcf.xml"

    def write_models(self, model: Dict[str, Any], sample_id: str) -> List[DerivedFile]:
        return [DerivedFile(
            path=self.mjcf_path(sample_id), data=build_mjcf(model).encode("utf-8"), role="domain_model",
            media_type="application/xml", producer="ecad_model.mjcf", version=VERSION,
            derived_from=("derived/engineering_model.json",), comparator="numeric_attributes")]

    def case_target(self, sample_id: str) -> CaseTarget:
        mjcf = self.mjcf_path(sample_id)
        return CaseTarget(
            adapter="mujoco", inputs=(SIMULATION_SCRIPT, mjcf),
            arguments=lambda scenario: ["--model", mjcf, "--scenario",
                                        json.dumps(scenario, sort_keys=True, separators=(",", ":"))])

    def reference_value(self, model: Dict[str, Any], derivation: str,
                        scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
        return reference_value(model, derivation, scenario)

    def metrics(self) -> Dict[str, Metric]:
        return dict(METRICS)

    def check_requirements(self, requirements: Dict[str, Any]) -> None:
        """Every scenario and derivation must be one this domain implements,
        and every derivation must be given the scenario it reads.

        Raises:
            ValueError: A scenario or derivation is not in the mechanical
                vocabulary (schemas/engineering-model/v1/mechanical-vocabulary),
                or a move derivation is paired with a scenario other than the
                rated move, whose start, end and duration it computes from.
        """
        validate_schema({
            "scenarios": [entry["scenario"] for entry in (*requirements["reference_values"], *requirements["requirements"])],
            "derivations": [entry["derivation"] for entry in requirements["reference_values"]],
        }, "engineering-model/v1/mechanical-vocabulary")
        for reference in requirements["reference_values"]:
            needed = DERIVATION_SCENARIO.get(reference["derivation"])
            if needed and reference["scenario"]["name"] != needed:
                raise ValueError(f"{reference['reference_id']}: {reference['derivation']} is computed from the "
                                 f"{needed} scenario, not {reference['scenario']['name']}")

    def dependencies(self, model: Dict[str, Any], metric: str, scenario: Dict[str, Any]) -> List[str]:
        """The model quantities a simulated metric depends on.

        Coarse on purpose, and a superset of what any one metric reads: the
        joint's axis, origin and range -- the range is in the MJCF every case
        runs on, the static sweep samples it, and the rated move is refused
        outside it -- and, for dynamics, every moving body's mass properties
        and placement and gravity; for clearance, every body on both sides
        and their bounding boxes.
        """
        joint = model["joints"][0]
        jid = joint["joint_id"]
        roots = rigid_groups(model)
        geometric = [c["component_id"] for c in model["components"] if c["cad_ref"] is not None]
        clearance = metric.startswith("rom_")
        bodies = geometric if clearance else [cid for cid in geometric if roots[cid] == roots[joint["child"]]]
        paths = [f"joints/{jid}/axis", f"joints/{jid}/origin", f"joints/{jid}/limits/lower", f"joints/{jid}/limits/upper"]
        if not clearance:
            paths.append("design/gravity")
        for cid in sorted(bodies):
            paths += [f"components/{cid}/placement/translation", f"components/{cid}/placement/rotation"]
            if clearance:
                paths += [f"components/{cid}/geometry/bounding_box_local/min",
                          f"components/{cid}/geometry/bounding_box_local/max"]
            else:
                paths += [f"components/{cid}/physical/{name}" for name in ("mass", "center_of_mass", "inertia_about_com")]
        return paths

    def reference_inputs(self, model: Dict[str, Any], derivation: str, scenario: Dict[str, Any]) -> List[str]:
        """The model paths a reference derivation reads (those it lacks, when it cannot run)."""
        try:
            return reference_value(model, derivation, scenario)[1]
        except ReferenceBlocked as exc:
            return [missing["path"] for missing in exc.paths]

    def document_schemas(self) -> Dict[str, str]:
        return {EXTRACTION: "cad-dataset/v1/cad-extraction"}

    def components_for(self, model: Dict[str, Any], metric: str) -> List[str]:
        """The CAD occurrences a metric depends on: the moving parts, and for a
        clearance metric the fixed parts it is measured against as well."""
        joint = model["joints"][0] if model["joints"] else None
        if joint is None:
            return []
        roots = rigid_groups(model)
        moving: List[str] = []
        fixed: List[str] = []
        for c in model["components"]:
            if c["cad_ref"] is None:
                continue
            label = f"{c['component_id']} ({c['cad_ref']['occurrence']})"
            (moving if roots[c["component_id"]] == roots[joint["child"]] else fixed).append(label)
        return sorted(moving + fixed) if metric.startswith("rom_") else sorted(moving)

    def simulation_files(self, root: Path) -> List[str]:
        return sorted(path.relative_to(root).as_posix() for path in (root / "simulation").glob("*.py"))

    def sanity_problems(self, model: Dict[str, Any]) -> List[str]:
        """Why the model's mass properties, axis or limits are physically impossible, if they are."""
        problems = []
        for component in model["components"]:
            cid = component["component_id"]
            if component["geometry"] is not None and component["geometry"]["volume"]["value"] <= 0:
                problems.append(f"{cid}: CAD volume is not positive")
            physical = component["physical"]
            if physical is None:
                continue
            if not is_null(physical["mass"]["status"]) and physical["mass"]["value"] <= 0:
                problems.append(f"{cid}: mass is not positive")
            if not is_null(physical["inertia_about_com"]["status"]):
                problems += inertia_problems(cid, physical["inertia_about_com"]["value"])
        for joint in model["joints"]:
            if not is_null(joint["axis"]["status"]):
                length = math.sqrt(sum(item * item for item in joint["axis"]["value"]))
                if abs(length - 1.0) > 1e-9:
                    problems.append(f"{joint['joint_id']}: axis is not a unit vector (length {length})")
            lower, upper = joint["limits"]["lower"], joint["limits"]["upper"]
            if not is_null(lower["status"]) and not is_null(upper["status"]) and not lower["value"] < upper["value"]:
                problems.append(f"{joint['joint_id']}: lower limit is not below the upper limit")
        return problems

    def invariant_problems(self, model: Dict[str, Any], extraction_files: Dict[str, Any],
                           domain_models: Dict[str, bytes]) -> List[str]:
        """Every cad_ref resolves to a CAD occurrence; MJCF bodies are exactly the CAD components."""
        problems = []
        extraction = extraction_files[EXTRACTION]
        parts = {part["name"]: part["occurrence"] for part in extraction["parts"]}
        for component in model["components"]:
            ref = component["cad_ref"]
            if ref is not None and parts.get(ref["part"]) != ref["occurrence"]:
                problems.append(f"{component['component_id']}: cad_ref {ref} does not resolve to a CAD occurrence")
        mjcf_text = next(iter(domain_models.values())).decode("utf-8")
        bodies = set(re.findall(r'<body name="([^"]+)"', mjcf_text))
        geometric = {c["component_id"] for c in model["components"] if c["cad_ref"] is not None}
        if bodies != geometric:
            problems.append(f"MJCF bodies {sorted(bodies)} != CAD components {sorted(geometric)}")
        return problems


def json_bytes(value: Any) -> bytes:
    """Reviewable, deterministic JSON: sorted keys, two-space indent, one final LF."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
