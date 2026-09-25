"""Convert the engineering model into a MuJoCo (MJCF) mechanical model.

Dynamics come only from the CAD-derived mass properties: every body carries an
explicit inertial and inertiafromgeom is off, so the proxies never contribute
mass. Contact forces are a separate path -- a proxy overlap would push on the
joint -- so every dynamics scenario runs with contact disabled, and the
proxies are used only by the clearance scenario.

Collision geometry is each part's local bounding box. A box contains its part,
so "no contact between proxies" soundly implies "no contact between parts";
the converse does not hold, so a reported contact may be a false alarm. That
trade is deliberate: a clearance check must never pass where the CAD would
collide.

MuJoCo filters parent-child contacts by default, and the link body is nested in
the base body, so a naive model can never report the link hitting the base.
filterparent is therefore disabled, and only pairs the relationship graph
justifies are excluded: parts rigidly attached to each other, and bearing
interfaces (a shaft running in a bore).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Set, Tuple
from xml.sax.saxutils import quoteattr

from .quantity import Status

Matrix = Sequence[Sequence[float]]


class ModelIncomplete(ValueError):
    """The engineering model cannot be represented as a mechanical model."""


class MissingInput(ModelIncomplete):
    """A value the mechanical model needs is UNKNOWN.

    That is a missing input, not a defect in the design: validation reports
    it BLOCKED with MISSING_REQUIRED_INPUT, never FAIL.
    """


def _num(value: float) -> str:
    text = f"{value:.12g}"
    return "0" if text in ("-0", "0") else text


def _vec(values: Sequence[float]) -> str:
    return " ".join(_num(item) for item in values)


def rotation_to_quaternion(r: Matrix) -> List[float]:
    """Unit quaternion (w, x, y, z) for a proper rotation matrix.

    Args:
        r: A 3x3 rotation matrix.

    Returns:
        [w, x, y, z] with w >= 0.

    Example:
        >>> rotation_to_quaternion([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        [1.0, 0.0, 0.0, 0.0]
    """
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w, x, y, z = 0.25 * s, (r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2
        w, x, y, z = (r[2][1] - r[1][2]) / s, 0.25 * s, (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2
        w, x, y, z = (r[0][2] - r[2][0]) / s, (r[0][1] + r[1][0]) / s, 0.25 * s, (r[1][2] + r[2][1]) / s
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2
        w, x, y, z = (r[1][0] - r[0][1]) / s, (r[0][2] + r[2][0]) / s, (r[1][2] + r[2][1]) / s, 0.25 * s
    if w < 0:
        w, x, y, z = -w, -x, -y, -z
    return [w, x, y, z]


def _known(item: Dict[str, Any], label: str) -> Any:
    if item["status"] == Status.UNKNOWN.value:
        raise MissingInput(f"{label} is UNKNOWN: {item.get('note', 'no value recorded')}")
    return item["value"]


def rigid_groups(model: Dict[str, Any]) -> Dict[str, str]:
    """Map each component to the component it ultimately moves with.

    Args:
        model: An engineering model.

    Returns:
        component_id -> root component_id, following attached_to relations.

    Raises:
        ValueError: The attachments form a cycle.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> groups = rigid_groups(json.loads((item / "derived/engineering_model.json").read_text()))
        >>> groups["shaft"], groups["pillar"]
        ('link', 'base_plate')
    """
    attached = {
        relation["from"]: relation["to"]
        for relation in model["relationships"]
        if relation["relation"] == "attached_to"
    }
    roots: Dict[str, str] = {}
    for component in model["components"]:
        node, seen = component["component_id"], set()
        while node in attached:
            if node in seen:
                raise ValueError(f"attachment cycle through {node!r}")
            seen.add(node)
            node = attached[node]
        roots[component["component_id"]] = node
    return roots


def build_mjcf(model: Dict[str, Any], *, timestep: float = 0.0005) -> str:
    """Return the MJCF document for a single-revolute-joint design.

    Args:
        model: An engineering model with exactly one revolute joint.
        timestep: Integration timestep in seconds, recorded in the model.

    Returns:
        The MJCF text. Deterministic for a given model.

    Raises:
        ModelIncomplete: A value the mechanical model needs is UNKNOWN, the
            design is not a single revolute joint, or a component is attached
            to neither side of it.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> xml = build_mjcf(json.loads((item / "derived/engineering_model.json").read_text()))
        >>> '<exclude body1="pillar" body2="shaft"/>' in xml
        True
    """
    if len(model["joints"]) != 1:
        raise ModelIncomplete(f"the mechanical MVP supports exactly one joint, found {len(model['joints'])}")
    joint = model["joints"][0]
    if joint["type"] != "revolute":
        raise ModelIncomplete(f"joint {joint['joint_id']} is {joint['type']}, not revolute")

    geometric = [c for c in model["components"] if c["cad_ref"] is not None]
    roots = rigid_groups(model)
    moving_root = roots[joint["child"]]
    fixed_root = roots[joint["parent"]]
    if moving_root == fixed_root:
        raise ModelIncomplete("the joint's parent and child are rigidly attached to each other")
    for component in geometric:
        if roots[component["component_id"]] not in (moving_root, fixed_root):
            raise ModelIncomplete(
                f"component {component['component_id']!r} is attached to neither side of the joint"
            )

    axis = _known(joint["axis"], f"joint {joint['joint_id']} axis")
    origin = _known(joint["origin"], f"joint {joint['joint_id']} origin")
    lower = _known(joint["limits"]["lower"], f"joint {joint['joint_id']} lower limit")
    upper = _known(joint["limits"]["upper"], f"joint {joint['joint_id']} upper limit")
    gravity = _known(model["design"]["gravity"], "gravity")

    def body(component: Dict[str, Any], indent: str) -> List[str]:
        cid = component["component_id"]
        physical = component["physical"]
        mass = _known(physical["mass"], f"{cid} mass")
        com = _known(physical["center_of_mass"], f"{cid} centre of mass")
        inertia = _known(physical["inertia_about_com"], f"{cid} inertia")
        box_min = _known(component["geometry"]["bounding_box_local"]["min"], f"{cid} bounding box")
        box_max = _known(component["geometry"]["bounding_box_local"]["max"], f"{cid} bounding box")
        rotation = _known(component["placement"]["rotation"], f"{cid} rotation")
        translation = _known(component["placement"]["translation"], f"{cid} translation")
        centre_local = [(a + b) / 2 for a, b in zip(box_min, box_max)]
        half = [(b - a) / 2 for a, b in zip(box_min, box_max)]
        centre = [
            sum(rotation[i][k] * centre_local[k] for k in range(3)) + translation[i] for i in range(3)
        ]
        # MuJoCo orders fullinertia as Ixx Iyy Izz Ixy Ixz Iyz.
        full = [inertia[0][0], inertia[1][1], inertia[2][2], inertia[0][1], inertia[0][2], inertia[1][2]]
        return [
            f"{indent}<body name={quoteattr(cid)}>",
            f"{indent}  <inertial pos=\"{_vec(com)}\" mass=\"{_num(mass)}\" fullinertia=\"{_vec(full)}\"/>",
            f"{indent}  <geom name={quoteattr(cid + '_proxy')} type=\"box\" pos=\"{_vec(centre)}\" "
            f"quat=\"{_vec(rotation_to_quaternion(rotation))}\" size=\"{_vec(half)}\" "
            f"contype=\"1\" conaffinity=\"1\" group=\"1\"/>",
        ]

    fixed = [c for c in geometric if roots[c["component_id"]] == fixed_root]
    moving = [c for c in geometric if roots[c["component_id"]] == moving_root]
    fixed_main = next(c for c in fixed if c["component_id"] == fixed_root)
    moving_main = next(c for c in moving if c["component_id"] == moving_root)

    lines = [
        '<mujoco model={}>'.format(quoteattr(model["design"]["design_id"])),
        "  <!-- Generated by tools/ecad_model/mjcf.py from the engineering model. Do not edit. -->",
        '  <compiler angle="radian" inertiafromgeom="false" autolimits="true"/>',
        f'  <option timestep="{_num(timestep)}" gravity="{_vec(gravity)}" integrator="RK4">',
        '    <flag filterparent="disable"/>',
        "  </option>",
        "  <worldbody>",
    ]
    lines += body(fixed_main, "    ")
    for component in fixed:
        if component is not fixed_main:
            lines += body(component, "      ") + ["      </body>"]
    lines += body(moving_main, "      ")
    lines.append(
        f'        <joint name={quoteattr(joint["joint_id"])} type="hinge" pos="{_vec(origin)}" '
        f'axis="{_vec(axis)}" range="{_num(lower)} {_num(upper)}"/>'
    )
    for component in moving:
        if component is not moving_main:
            lines += body(component, "        ") + ["        </body>"]
    lines += ["      </body>", "    </body>", "  </worldbody>"]

    exclusions: Set[Tuple[str, str]] = set()
    ids = [c["component_id"] for c in geometric]
    for i, first in enumerate(ids):
        for second in ids[i + 1:]:
            if roots[first] == roots[second]:
                exclusions.add((first, second))
    # The joint's realizing part runs in a bore of the other side: a designed
    # bearing interface whose box proxies overlap by construction. A shaft on
    # the moving side runs in the parent; a fixed pin runs in the child. When
    # the realizer is the parent or child itself, the bearing IS the joint
    # pair: it has to be excluded, and the clearance scenario then reports
    # that pair as unchecked rather than passing it vacuously.
    realizer, parent, child = joint["realized_by"], joint["parent"], joint["child"]
    if realizer in (parent, child):
        bearing = (parent, child)
    elif roots[realizer] == moving_root:
        bearing = (realizer, parent)
    else:
        bearing = (realizer, child)
    first, second = sorted(bearing)
    exclusions.add((first, second))
    lines.append("  <contact>")
    for first, second in sorted(tuple(sorted(pair)) for pair in exclusions):
        lines.append(f"    <exclude body1={quoteattr(first)} body2={quoteattr(second)}/>")
    lines += ["  </contact>", "</mujoco>", ""]
    return "\n".join(lines)
