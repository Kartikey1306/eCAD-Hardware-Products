"""Build the engineering semantic model from a CAD extraction and design annotations.

The CAD supplies geometry, placement, volume and the shape of the mass
distribution. Annotations supply design intent the CAD cannot carry. Every
number the builder produces is DERIVED and names exactly what it came from, so
a validation result can be traced back to the CAD occurrence that caused it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import MODEL_VERSION
from .quantity import Status, is_null, quantity, rounded, source, unknown

SCHEMA_ID = "https://embeddedos.org/schemas/engineering-model/v1/engineering-model.schema.json"
VERSION = "1.0.0"  # of the engineering models this builder writes
LENGTH_TO_METRES = {"mm": 1e-3, "m": 1.0, "inch": 0.0254}
STANDARD_GRAVITY = 9.80665  # m/s^2, defined exactly by the 3rd CGPM (1901)
AXIS_SENSE_MIN_COSINE = 0.5  # an annotated sense must lie within 60 degrees of the CAD axis

Matrix = List[List[float]]
Vector = List[float]


def _matmul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _transpose(a: Matrix) -> Matrix:
    return [[a[j][i] for j in range(3)] for i in range(3)]


def _apply(rotation: Matrix, point: Sequence[float]) -> Vector:
    return [sum(rotation[i][k] * point[k] for k in range(3)) for i in range(3)]


def _norm(v: Sequence[float]) -> float:
    return sum(item * item for item in v) ** 0.5


UNIT_NOISE = 1e-12


def _clean_unit(values: Any) -> Any:
    """Zero the floating-point residue in dimensionless unit vectors and rotations.

    A 90-degree rotation stored as a matrix carries cos(pi/2) ~ 6e-17, which
    then shows up as a spurious axis component. Only O(1) dimensionless values
    are cleaned: a general near-zero snap would be scale-dependent and could
    erase a genuinely small inertia.

    Example:
        >>> _clean_unit([0.0, 1.0, 1.1e-16])
        [0.0, 1.0, 0.0]
    """
    if isinstance(values, list):
        return [_clean_unit(item) for item in values]
    return 0.0 if abs(values) < UNIT_NOISE else values


def canonical_direction(direction: Sequence[float]) -> Vector:
    """Unit vector whose largest-magnitude component is positive.

    A cylinder's axis direction depends on how it was modelled, not on the
    design. Canonicalising it makes the joint's sign convention a property of
    the geometry: rotation is right-handed about this direction.

    Args:
        direction: Any non-zero 3-vector.

    Returns:
        The canonical unit vector, with floating-point residue zeroed.

    Raises:
        ValueError: The vector has zero length.

    Example:
        >>> canonical_direction([0.0, -2.0, 0.0])
        [0.0, 1.0, 0.0]
    """
    length = _norm(direction)
    if length == 0:
        raise ValueError("axis direction has zero length")
    unit = _clean_unit([item / length for item in direction])
    largest = max(range(3), key=lambda index: abs(unit[index]))
    # 0.0 - x rather than -x: negating 0.0 gives IEEE -0.0, which would leak into the JSON.
    return [0.0 - item for item in unit] if unit[largest] < 0 else unit


def _coaxial_axis(
    part: Dict[str, Any], scale: float
) -> Tuple[Optional[Vector], Optional[Vector], str]:
    """Return (origin, direction) of the single axis a part's cylinders share.

    Origin is the point on the axis nearest the part's centre of mass, in the
    part's local frame and metres. Returns (None, None, reason) when the part
    has no cylindrical face or its cylinders are not coaxial -- the axis is then
    UNKNOWN, never guessed.
    """
    faces = part["cylindrical_faces"]
    if not faces:
        return None, None, "the part has no cylindrical face to define an axis"
    direction = canonical_direction(faces[0]["axis_direction_local"])
    anchor = [item * scale for item in faces[0]["axis_origin_local"]]
    for face in faces[1:]:
        other = canonical_direction(face["axis_direction_local"])
        if _norm([a - b for a, b in zip(other, direction)]) > 1e-9:
            return None, None, "the part's cylindrical faces are not parallel"
        offset = [item * scale - a for item, a in zip(face["axis_origin_local"], anchor)]
        along = sum(o * d for o, d in zip(offset, direction))
        perpendicular = [o - along * d for o, d in zip(offset, direction)]
        if _norm(perpendicular) > 1e-9:
            return None, None, "the part's cylindrical faces are not coaxial"
    com = [item * scale for item in part["center_of_mass_local"]]
    along = sum((c - a) * d for c, a, d in zip(com, anchor, direction))
    origin = [a + along * d for a, d in zip(anchor, direction)]
    return origin, direction, ""


def build_engineering_model(
    extraction: Dict[str, Any],
    annotations: Dict[str, Any],
    *,
    design_name: str,
    revision: str,
    extraction_ref: str,
    annotations_ref: str,
    annotations_sha256: str,
) -> Dict[str, Any]:
    """Build the engineering model from a CAD extraction and design annotations.

    Args:
        extraction: A cad-dataset/v1/cad-extraction document.
        annotations: An engineering-model/v1/design-annotations document.
        design_name: Human-readable design name.
        revision: Design revision label.
        extraction_ref: Repository path of the extraction, for provenance.
        annotations_ref: Repository path of the annotations, for provenance.
        annotations_sha256: Digest of the annotation bytes.

    Returns:
        An engineering-model/v1/engineering-model document, in SI units.

    Raises:
        ValueError: The annotations name a CAD part, joint component or
            relationship endpoint that does not exist, or declare a component
            twice.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = build_engineering_model(
        ...     json.loads((item / "derived/cad_extraction.json").read_text()),
        ...     json.loads((item / "design/annotations.json").read_text()),
        ...     design_name="joint", revision="1.0", extraction_ref="e.json",
        ...     annotations_ref="a.json", annotations_sha256="0" * 64)
        >>> model["joints"][0]["axis"]["value"], model["joints"][0]["axis"]["status"]
        ([0.0, 1.0, 0.0], 'DERIVED')
    """
    cad_path = extraction["source"]["path"]
    cad_sha256 = extraction["source"]["sha256"]
    unit = extraction["length_unit"]
    scale = LENGTH_TO_METRES[unit]
    cad_source = source("cad", cad_path, cad_sha256)
    annotation_source = source("design_annotation", annotations_ref, annotations_sha256)
    computation = source("computation", "tools/ecad_model/builder.py")

    parts_by_name = {part["name"]: part for part in extraction["parts"]}
    for name in annotations["parts"]:
        if name not in parts_by_name:
            raise ValueError(f"annotations describe CAD part {name!r}, which the CAD does not contain")

    components: List[Dict[str, Any]] = []
    part_frames: Dict[str, Tuple[Matrix, Vector, Dict[str, Any]]] = {}
    for part in extraction["parts"]:
        annotated = annotations["parts"].get(part["name"])
        component_id = annotated["component_id"] if annotated else f"unannotated_{part['name']}"
        base = f"components/{component_id}"
        cad_input = f"cad:{cad_path}#{part['occurrence']}"
        rotation = _clean_unit([[float(item) for item in row] for row in part["rotation"]])
        translation = [item * scale for item in part["translation"]]
        part_frames[component_id] = (rotation, translation, part)

        volume = part["volume"] * scale**3
        area = part["surface_area"] * scale**2
        com_world = [
            a + b for a, b in zip(_apply(rotation, [c * scale for c in part["center_of_mass_local"]]), translation)
        ]
        # Unit-density inertia scales with length^5 and rotates as a tensor.
        unit_inertia_world = _matmul(
            _matmul(rotation, [[item * scale**5 for item in row] for row in part["inertia_about_com_unit_density_local"]]),
            _transpose(rotation),
        )

        material_key = annotated["material"] if annotated else None
        material = annotations["materials"].get(material_key) if material_key else None
        if material is None:
            density = unknown(
                "kg/m^3",
                annotation_source,
                f"CAD part {part['name']!r} has no material in the design annotations",
            )
        else:
            density = dict(material["density"])
        density_path = f"{base}/material/density"
        volume_path = f"{base}/geometry/volume"

        if is_null(density["status"]):
            mass = unknown("kg", computation, f"mass = density x volume, and density is {density['status']}")
            inertia = unknown("kg*m^2", computation, f"inertia scales with density, which is {density['status']}")
        else:
            rho = density["value"]
            mass = quantity(
                rounded(rho * volume), "kg", Status.DERIVED, computation,
                derived_from=[volume_path, density_path],
            )
            inertia = quantity(
                rounded([[rho * item for item in row] for row in unit_inertia_world]),
                "kg*m^2", Status.DERIVED, computation,
                derived_from=[cad_input, density_path],
                note="about the component's centre of mass, assembly axes",
            )

        components.append(
            {
                "component_id": component_id,
                "name": part["name"],
                "kind": annotated["kind"] if annotated else "other",
                "cad_ref": {"part": part["name"], "occurrence": part["occurrence"]},
                "material": {
                    "name": material["name"] if material else "unassigned",
                    "density": density,
                },
                "geometry": {
                    "volume": quantity(rounded(volume), "m^3", Status.DERIVED, cad_source, derived_from=[cad_input]),
                    "surface_area": quantity(rounded(area), "m^2", Status.DERIVED, cad_source, derived_from=[cad_input]),
                    "bounding_box_local": {
                        "min": quantity(
                            rounded([item * scale for item in part["bounding_box_local"]["min"]]),
                            "m", Status.DERIVED, cad_source, derived_from=[cad_input],
                        ),
                        "max": quantity(
                            rounded([item * scale for item in part["bounding_box_local"]["max"]]),
                            "m", Status.DERIVED, cad_source, derived_from=[cad_input],
                        ),
                    },
                },
                "physical": {
                    "mass": mass,
                    "center_of_mass": quantity(
                        rounded(com_world), "m", Status.DERIVED, cad_source,
                        derived_from=[cad_input], note="assembly frame",
                    ),
                    "inertia_about_com": inertia,
                },
                "placement": {
                    "translation": quantity(rounded(translation), "m", Status.DERIVED, cad_source, derived_from=[cad_input]),
                    "rotation": quantity(rounded(rotation), "1", Status.DERIVED, cad_source, derived_from=[cad_input]),
                },
                "domains": {},
            }
        )

    known_ids = {component["component_id"] for component in components}
    for extra in annotations["components_without_cad"]:
        if extra["component_id"] in known_ids:
            raise ValueError(f"component {extra['component_id']!r} is declared twice")
        known_ids.add(extra["component_id"])
        components.append(
            {
                "component_id": extra["component_id"],
                "name": extra["name"],
                "kind": extra["kind"],
                "cad_ref": None,
                "material": None,
                "geometry": None,
                "physical": None,
                "placement": None,
                "domains": {name: dict(facet) for name, facet in extra["domains"].items()},
            }
        )

    joints = []
    for joint in annotations["joints"]:
        for role in ("parent", "child", "realized_by"):
            if joint[role] not in known_ids:
                raise ValueError(f"joint {joint['joint_id']} {role} {joint[role]!r} is not a component")
        realizer = joint["realized_by"]
        rotation, translation, part = part_frames[realizer]
        origin_local, direction_local, reason = _coaxial_axis(part, LENGTH_TO_METRES[unit])
        cad_input = f"cad:{cad_path}#{part['occurrence']}"
        if origin_local is None or direction_local is None:
            axis = unknown("1", cad_source, f"joint axis from {realizer!r}: {reason}")
            origin = unknown("m", cad_source, f"joint origin from {realizer!r}: {reason}")
        else:
            line = canonical_direction(_apply(rotation, direction_local))
            sense_path = f"annotations:{annotations_ref}#joints/{joint['joint_id']}/axis_sense"
            sense = joint["axis_sense"]
            length = sum(item * item for item in sense) ** 0.5
            agreement = sum(a * b for a, b in zip(line, sense)) / length if length else 0.0
            # The CAD fixes the axis line; only design intent can fix which way
            # a positive angle turns. Without an explicit sense the sign would
            # follow a canonicalisation rule, and a rigid re-orientation of the
            # whole design could mirror the joint's range with nothing noticing.
            if abs(agreement) < AXIS_SENSE_MIN_COSINE:
                axis = unknown(
                    "1", annotation_source,
                    f"joint {joint['joint_id']}: axis_sense is more than 60 degrees from the CAD axis {rounded(line)}",
                )
            else:
                oriented = line if agreement > 0 else [0.0 - item for item in line]
                axis = quantity(
                    rounded(_clean_unit(oriented)), "1", Status.DERIVED, cad_source,
                    derived_from=[cad_input, sense_path],
                    note=(f"line from the cylindrical faces of {realizer!r}, direction from the annotated "
                          "axis_sense; a positive angle is right-handed about it"),
                )
            origin = quantity(
                rounded([a + b for a, b in zip(_apply(rotation, origin_local), translation)]), "m",
                Status.DERIVED, cad_source, derived_from=[cad_input],
                note="point on the axis nearest the realizing part's centre of mass",
            )
        joints.append(
            {
                "joint_id": joint["joint_id"],
                "type": joint["type"],
                "parent": joint["parent"],
                "child": joint["child"],
                "realized_by": realizer,
                "axis": axis,
                "origin": origin,
                "limits": {"lower": dict(joint["limits"]["lower"]), "upper": dict(joint["limits"]["upper"])},
            }
        )

    relationships = []
    design_id = annotations["design_id"]
    for component in components:
        if component["cad_ref"] is not None:
            relationships.append(
                {"relation": "contains", "from": design_id, "to": component["component_id"], "source": cad_source}
            )
    for attachment in annotations["attachments"]:
        for key in ("component", "attached_to"):
            if attachment[key] not in known_ids:
                raise ValueError(f"attachment names unknown component {attachment[key]!r}")
        relationships.append(
            {
                "relation": "attached_to",
                "from": attachment["component"],
                "to": attachment["attached_to"],
                "source": annotation_source,
            }
        )
    for joint in joints:
        relationships.append(
            {"relation": "constrained_by", "from": joint["child"], "to": joint["parent"], "source": annotation_source}
        )
    for relation in annotations["relationships"]:
        for key in ("from", "to"):
            if relation[key] not in known_ids:
                raise ValueError(f"relationship names unknown component {relation[key]!r}")
        relationships.append({**relation, "source": annotation_source})

    model = {
        "$schema": SCHEMA_ID,
        "model_version": MODEL_VERSION,
        "design": {
            "design_id": design_id,
            "name": design_name,
            "revision": revision,
            "sources": [{"path": cad_path, "format": "step", "sha256": cad_sha256, "length_unit": unit}],
            "gravity": quantity(
                [0.0, 0.0, -STANDARD_GRAVITY], "m/s^2", Status.SPECIFIED,
                source("handbook", "standard gravity, 3rd CGPM (1901)"),
                note="assembly +Z is up",
            ),
        },
        "components": components,
        "joints": joints,
        "relationships": relationships,
        "unknowns": [],
    }
    model["unknowns"] = index_unknowns(model)
    return model


def _needed_by(path: str) -> List[str]:
    parts = path.split("/")
    if "domains" in parts:
        return [parts[parts.index("domains") + 1]]
    if parts[0] == "joints":
        return ["mechanical", "control"]
    return ["mechanical", "thermal"]


def index_unknowns(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every quantity with a null status, by path, with its status and the domains that need it.

    Args:
        model: An engineering model.

    Returns:
        Entries sorted by path, so the index is identical however the model's
        dicts were ordered.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> index_unknowns(model)[0]["path"]
        'components/actuator/domains/electrical/torque_constant'
    """
    found: List[Dict[str, Any]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if {"value", "unit", "status", "source"} <= node.keys():
                if is_null(node["status"]):
                    entry = {"path": path, "status": node["status"], "needed_by": _needed_by(path)}
                    if node.get("note"):
                        entry["note"] = node["note"]
                    found.append(entry)
                return
            for key, value in node.items():
                walk(value, f"{path}/{key}" if path else key)
        elif isinstance(node, list):
            for item in node:
                key = item.get("component_id") or item.get("joint_id") if isinstance(item, dict) else None
                walk(item, f"{path}/{key}" if key else path)

    walk({"components": model["components"], "joints": model["joints"]}, "")
    # Sorted, so the index does not depend on dict insertion order: a model
    # re-read from key-sorted JSON must re-index to exactly the same list.
    return sorted(found, key=lambda entry: entry["path"])


def resolve(model: Dict[str, Any], path: str) -> Dict[str, Any]:
    """Resolve an id-based model path to the quantity it names.

    Args:
        model: An engineering model.
        path: e.g. "components/link/physical/mass" or "joints/j1/axis".

    Returns:
        The quantity dict at that path.

    Raises:
        KeyError: The path names no component or joint, does not exist, or
            does not end at a quantity.

    Example:
        >>> import json; from pathlib import Path
        >>> item = Path(__file__).resolve().parents[2] / "datasets/cad/robotic_joint_001"
        >>> model = json.loads((item / "derived/engineering_model.json").read_text())
        >>> resolve(model, "components/link/physical/mass")["status"]
        'DERIVED'
    """
    parts = path.split("/")
    if len(parts) < 2 or parts[0] not in ("components", "joints"):
        raise KeyError(f"unsupported model path: {path}")
    key = "component_id" if parts[0] == "components" else "joint_id"
    node: Any = next((item for item in model[parts[0]] if item[key] == parts[1]), None)
    if node is None:
        raise KeyError(f"no {parts[0][:-1]} {parts[1]!r} in the model")
    for part in parts[2:]:
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"model path does not exist: {path}")
        node = node[part]
    if not (isinstance(node, dict) and "status" in node):
        raise KeyError(f"model path is not a quantity: {path}")
    return node
