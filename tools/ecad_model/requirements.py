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
from typing import Any, Dict, List, Sequence, Tuple

from .builder import resolve
from .mjcf import rigid_groups
from .quantity import Status

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
    def __init__(self, message: str, paths: Sequence[str]):
        super().__init__(message)
        self.paths = list(paths)


def _cross(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _known(model: Dict[str, Any], path: str, missing: List[str]) -> Any:
    item = resolve(model, path)
    if item["status"] == Status.UNKNOWN.value:
        missing.append(path)
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


def reference_value(model: Dict[str, Any], derivation: str) -> Tuple[float, List[str]]:
    """Compute one closed-form reference value from the engineering model.

    Args:
        model: An engineering model with one joint.
        derivation: "gravity_torque_as_modelled", "small_oscillation_period"
            or "moving_mass".

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
    """
    joint = model["joints"][0]
    jid = joint["joint_id"]
    used: List[str] = []
    missing: List[str] = []
    axis = _known(model, f"joints/{jid}/axis", missing)
    origin = _known(model, f"joints/{jid}/origin", missing)
    used += [f"joints/{jid}/axis", f"joints/{jid}/origin"]
    gravity = model["design"]["gravity"]["value"]
    bodies = []
    for cid in _moving(model):
        paths = [f"components/{cid}/physical/{name}" for name in ("mass", "center_of_mass", "inertia_about_com")]
        used += paths
        values = [_known(model, path, missing) for path in paths]
        bodies.append(values)
    if missing:
        raise ReferenceBlocked(f"{derivation} needs quantities that are UNKNOWN", missing)

    if derivation == "moving_mass":
        return sum(mass for mass, _, _ in bodies), used

    # Gravity torque about the joint axis in the as-modelled pose (q = 0).
    torque = sum(_dot(_cross([c - o for c, o in zip(com, origin)], [mass * g for g in gravity]), axis)
                 for mass, com, _ in bodies)
    if derivation == "gravity_torque_as_modelled":
        return abs(torque), used

    if derivation == "small_oscillation_period":
        # Linearised pendulum about the stable equilibrium:
        #   I_axis * theta'' = -M * |g_perp| * d * theta
        # with I_axis by the parallel-axis theorem and d the perpendicular
        # distance from the axis to the moving group's centre of mass.
        total = sum(mass for mass, _, _ in bodies)
        combined = [sum(mass * com[i] for mass, com, _ in bodies) / total for i in range(3)]
        inertia_axis = 0.0
        for mass, com, inertia in bodies:
            r = [c - o for c, o in zip(com, origin)]
            r_perp = [ri - _dot(r, axis) * ai for ri, ai in zip(r, axis)]
            about_com = _dot(axis, [_dot(row, axis) for row in inertia])
            inertia_axis += about_com + mass * _dot(r_perp, r_perp)
        r = [c - o for c, o in zip(combined, origin)]
        distance = math.sqrt(max(0.0, _dot(r, r) - _dot(r, axis) ** 2))
        g_perp = [g - _dot(gravity, axis) * a for g, a in zip(gravity, axis)]
        restoring = total * math.sqrt(_dot(g_perp, g_perp)) * distance
        if restoring <= 0:
            raise ReferenceBlocked("the moving group's centre of mass lies on the joint axis", [])
        return 2 * math.pi * math.sqrt(inertia_axis / restoring), used

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
        requirement and the UNKNOWN model paths it rests on.

    Raises:
        ValueError: A quantity limit's unit differs from its requirement's.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> requirements = json.loads((item / "requirements/requirements.json").read_text())
        >>> golden, corners, blocked = compile_cases(model, requirements, "m.xml")
        >>> len(golden["cases"]), len(corners["cases"]), [entry["id"] for entry in blocked]
        (3, 5, ['REQ-XD-001'])
    """
    blocked: List[Dict[str, Any]] = []
    golden = []
    for reference in requirements["reference_values"]:
        try:
            value, _used = reference_value(model, reference["derivation"])
        except ReferenceBlocked as exc:
            blocked.append(
                {"id": reference["reference_id"], "gate": "V3", "reason": str(exc), "unknown_paths": exc.paths}
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
            if item["status"] == Status.UNKNOWN.value:
                blocked.append(
                    {
                        "id": requirement["requirement_id"],
                        "gate": "V4",
                        "reason": f"the limit is the model quantity {limit['quantity']}, which is UNKNOWN",
                        "unknown_paths": [limit["quantity"]],
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
