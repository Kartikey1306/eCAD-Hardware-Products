"""Deterministic requirements: closed-form reference values and case compilation.

No model decides whether 4.8 N*m satisfies <= 5 N*m. Reference values are
computed here by closed-form physics from the engineering model, on a code
path independent of the MJCF writer and the simulator, so a frame, unit or
inertia-ordering error in the conversion shows up as a golden mismatch.
Requirements compile into the existing V3/V4 case format, where the contract's
own comparators decide. A limit that depends on an UNKNOWN quantity is not
compiled at all: it is reported BLOCKED with the exact missing paths.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .builder import resolve
from .mjcf import rigid_groups
from .quantity import is_null

CASES_SCHEMA = "https://embeddedos.org/schemas/hardware-validation/v1/validation-cases.schema.json"
SIMULATION_SCRIPT = "simulation/joint_dynamics.py"

# The v1 receipt contract classifies checks into six domains that predate the
# engineering domains of issue #27. This mapping is a documented decision, not
# an equivalence.
CONTRACT_DOMAIN = {
    "mechanical": "integrated_physics",
    "electrical": "eda_circuit",
    "digital": "eda_circuit",
    "pcb": "physical_design",
    "power_electronics": "device_modeling",
    "control": "system_design",
    "electromagnetic": "device_modeling",
    "thermal": "integrated_physics",
    "full_system": "integrated_physics",
}


class ReferenceBlocked(ValueError):
    """A reference cannot be computed. paths lists the inputs that have no
    value, each {"path", "status"}; it is empty when the derivation itself does
    not apply to this design."""

    def __init__(self, message: str, paths: Sequence[Dict[str, str]]):
        super().__init__(message)
        self.paths = list(paths)


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
        ReferenceBlocked: An input is UNKNOWN; its paths are attached.
        ValueError: The derivation name is not recognised.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
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
    gravity = model["design"]["gravity"]["value"]
    bodies = _bodies(model, scenario, used, missing)
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

    if derivation == "moving_mass":
        return sum(mass for mass, _, _ in bodies), used
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


def _case(case_id: str, domain: str, mjcf_path: str, scenario: Dict[str, Any], requirement_id: str) -> Dict[str, Any]:
    return {
        "id": case_id,
        "adapter": "mujoco",
        "domain": CONTRACT_DOMAIN[domain],
        "inputs": [SIMULATION_SCRIPT, mjcf_path],
        "arguments": ["--model", mjcf_path, "--scenario", json.dumps(scenario, sort_keys=True, separators=(",", ":"))],
        "timeout_seconds": 300,
        "seed": 0,
        "requirement_ids": [requirement_id],
    }


def compile_cases(
    model: Dict[str, Any], requirements: Dict[str, Any], mjcf_path: str
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Compile requirements into V3 golden and V4 corner case documents.

    Case requirement_ids cite the contract's gate policies, which the v1
    requirements catalog defines; the engineering requirement each case
    implements is its case id, and the runner records both in the receipt.

    Args:
        model: The engineering model the limits and references resolve in.
        requirements: An engineering-requirements document.
        mjcf_path: Item-relative path of the mechanical model the cases run.

    Returns:
        (golden cases, corner cases, blocked items). A blocked item names the
        requirement and the null-status model paths it rests on, each with
        its status; a reference whose derivation does not apply has none.

    Raises:
        ValueError: A quantity limit's unit differs from its requirement's.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> requirements = json.loads((item / "requirements/requirements.json").read_text())
        >>> golden, corners, blocked = compile_cases(model, requirements, "m.xml")
        >>> len(golden["cases"]) == len(requirements["reference_values"])
        True
        >>> unknown_limits = [r["requirement_id"] for r in requirements["requirements"]
        ...                   if "quantity" in r["limit"]
        ...                   and is_null(resolve(model, r["limit"]["quantity"])["status"])]
        >>> [entry["id"] for entry in blocked] == unknown_limits
        True
    """
    blocked: List[Dict[str, Any]] = []
    golden = []
    for reference in requirements["reference_values"]:
        try:
            value, _used = reference_value(model, reference["derivation"], reference["scenario"])
        except ReferenceBlocked as exc:
            blocked.append(
                {"id": reference["reference_id"], "gate": "V3", "reason": str(exc), "missing_inputs": exc.paths}
            )
            continue
        case = _case(reference["reference_id"], reference["domain"], mjcf_path, reference["scenario"], "POLICY:V3-GOLDEN")
        case["expected_metrics"] = {
            reference["metric"]: {"value": float(f"{value:.12g}"), "absolute_tolerance": reference["absolute_tolerance"]}
        }
        golden.append(case)

    corners = []
    for requirement in requirements["requirements"]:
        limit = requirement["limit"]
        if "quantity" in limit:
            item = resolve(model, limit["quantity"])
            if is_null(item["status"]):
                blocked.append(
                    {
                        "id": requirement["requirement_id"],
                        "gate": "V4",
                        "reason": f"the limit is the model quantity {limit['quantity']}, which is {item['status']}",
                        "missing_inputs": [{"path": limit["quantity"], "status": item["status"]}],
                    }
                )
                continue
            if item["unit"] != requirement["unit"]:
                raise ValueError(
                    f"{requirement['requirement_id']}: limit unit {item['unit']} != requirement unit {requirement['unit']}"
                )
            bound = item["value"]
        else:
            bound = limit["value"]
        case = _case(
            requirement["requirement_id"], requirement["domain"], mjcf_path, requirement["scenario"], "POLICY:V4-CORNER"
        )
        case["metric_limits"] = {
            requirement["metric"]: {"maximum" if requirement["operator"] == "<=" else "minimum": bound}
        }
        corners.append(case)

    def document(gate: str, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"$schema": CASES_SCHEMA, "contract_version": "1.0.0", "gate": gate, "cases": cases}

    return document("V3", golden), document("V4", corners), blocked
