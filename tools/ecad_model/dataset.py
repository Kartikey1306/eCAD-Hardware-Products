"""Build, check and validate one CAD dataset item.

A dataset item is a directory:

    source/<item>.step            the CAD: source of truth for physical structure
    source/generate_step.py       how it was authored (provenance only)
    design/annotations.json       design intent the CAD cannot carry
    requirements/requirements.json
    simulation/                   domain simulation scripts run by case adapters
    derived/...                   everything derived from the three inputs
    validation/{golden,corners}/cases.json
    dataset-item.json             licence, provenance, and a hash of every file

Two properties are kept deliberately separate:

    integrity        every hash in dataset-item.json matches the committed bytes
                     exactly;
    reproducibility  rebuilding from the CAD reproduces the committed derived
                     content to within a numeric tolerance. Kernel builds differ
                     in their last floating-point digits across platforms, so a
                     byte comparison here would fail on a CI runner for no
                     engineering reason.

validate() maps the item onto the existing V0-V4 receipt contract: V0 schemas
and hashes, V1 physical sanity, V2 CAD/model/MJCF invariants, V3/V4 the
existing case engine plus BLOCKED checks for anything that rests on an UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import MODEL_VERSION
from .builder import build_engineering_model, index_unknowns, resolve
from .importers import ExtractionError, UnsupportedFormat, importer_for, regular_file
from .mjcf import MissingInput, build_mjcf, rigid_groups
from .requirements import CONTRACT_DOMAIN, compile_cases
from .schemas import REPOSITORY_ROOT, validate as validate_schema

ITEM_SCHEMA = "https://embeddedos.org/schemas/cad-dataset/v1/dataset-item.schema.json"
EXTRACTION = "derived/cad_extraction.json"
MODEL = "derived/engineering_model.json"
ANNOTATIONS = "design/annotations.json"
PROVENANCE = "source/provenance.json"
REQUIREMENTS = "requirements/requirements.json"
GOLDEN = "validation/golden/cases.json"
CORNERS = "validation/corners/cases.json"
DOMAINS = (
    "mechanical",
    "electrical",
    "digital",
    "pcb",
    "power_electronics",
    "control",
    "electromagnetic",
    "thermal",
    "full_system",
)
RELATIVE_TOLERANCE = 1e-9
ABSOLUTE_TOLERANCE = 1e-12


class Item:
    """Paths and identity of one dataset item directory.

    Args:
        directory: The item directory; it must hold exactly one source/*.step.

    Raises:
        ValueError: There is no STEP file, or more than one.

    Example:
        >>> item = Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")
        >>> item.item_id, item.cad.name
        ('robotic_joint_001', 'robotic_joint_001.step')
    """

    def __init__(self, directory: Path):
        self.root = directory.resolve()
        self.item_id = self.root.name
        steps = sorted((self.root / "source").glob("*.step"))
        if len(steps) != 1:
            raise ValueError(f"{self.root}: expected exactly one source/*.step, found {len(steps)}")
        regular_file(steps[0])
        self.cad = steps[0]
        self.mjcf = f"derived/mechanical/{self.item_id}.mjcf.xml"

    def path(self, relative: str) -> Path:
        return self.root / relative

    def read(self, relative: str) -> bytes:
        """The bytes of one of the item's files, if it is a regular file.

        Every read of an item's content goes through here. The item is
        untrusted input: a FIFO would block the read forever, a symlink could
        point outside the item, and an oversized file would be read whole
        before any other guard ran.

        Raises:
            UnsupportedFormat: Not a regular file, or too large.
            OSError: The file does not exist.
        """
        path = self.path(relative)
        regular_file(path)
        return path.read_bytes()

    def repo_relative(self, path: Path) -> str:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()

    def item_relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def files(self) -> List[Path]:
        """The item's files as git sees them: tracked plus untracked-not-ignored.

        Walking the directory would also pick up __pycache__ and other ignored
        output, so the input digest would change whenever Python cached bytecode.

        Returns:
            Absolute paths, sorted.

        Example:
            >>> item = Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")
            >>> item.cad in item.files()
            True
        """
        relative = self.repo_relative(self.root)
        ignored = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "check-ignore", "-q", "--no-index", "--", relative],
            capture_output=True, timeout=30,
        )
        if ignored.returncode == 0:
            raise ValueError(f"{relative}: the item lies under a git-ignored path, so its files cannot be enumerated")
        listed = subprocess.run(
            # :(literal) stops git reading the item's own path as a glob or pathspec magic.
            ["git", "-C", str(REPOSITORY_ROOT), "ls-files", "-co", "--exclude-standard", "-z", "--",
             f":(literal){relative}"],
            check=True, capture_output=True, timeout=30,
        ).stdout.decode("utf-8")
        files = sorted(REPOSITORY_ROOT / name for name in listed.split("\0") if name)
        if self.cad not in files:
            raise ValueError(f"{relative}: git does not list the item's own CAD file; refusing to skip its checks")
        return files


def _json_bytes(value: Any) -> bytes:
    """Reviewable, deterministic JSON: sorted keys, two-space indent, one final LF."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(item: Item, relative: str, data: Optional[bytes] = None) -> Dict[str, Any]:
    payload = item.read(relative) if data is None else data
    media = "application/json" if relative.endswith(".json") else (
        "application/xml" if relative.endswith(".xml") else (
            "application/step" if relative.endswith(".step") else "text/x-python"
        )
    )
    return {"path": relative, "sha256": _sha256(payload), "size_bytes": len(payload), "media_type": media}


def _derive(item: Item) -> Dict[str, bytes]:
    """Every derived file of an item, computed from its CAD and inputs alone."""
    annotations_bytes = item.read(ANNOTATIONS)
    annotations = json.loads(annotations_bytes)
    requirements = json.loads(item.read(REQUIREMENTS))
    validate_schema(annotations, "engineering-model/v1/design-annotations")
    validate_schema(requirements, "engineering-model/v1/engineering-requirements")

    extraction = importer_for(item.cad).extract(item.cad, REPOSITORY_ROOT)
    validate_schema(extraction, "cad-dataset/v1/cad-extraction")
    model = build_engineering_model(
        extraction,
        annotations,
        design_name=annotations["design_id"].replace("_", " "),
        revision="1.0",
        extraction_ref=item.repo_relative(item.path(EXTRACTION)),
        annotations_ref=item.repo_relative(item.path(ANNOTATIONS)),
        annotations_sha256=_sha256(annotations_bytes),
    )
    validate_schema(model, "engineering-model/v1/engineering-model")
    golden, corners, _blocked = compile_cases(model, requirements, item.mjcf)
    return {
        EXTRACTION: _json_bytes(extraction),
        MODEL: _json_bytes(model),
        item.mjcf: build_mjcf(model).encode("utf-8"),
        GOLDEN: _json_bytes(golden),
        CORNERS: _json_bytes(corners),
    }


# Domains this platform has a validator for. A domain is only ever reported
# "implemented" from here, never from a sample's data.
VALIDATED_DOMAINS = {
    "mechanical": "joint statics, rated-move dynamics, free oscillation and range-of-motion clearance, "
                  "simulated with MuJoCo and compared with closed-form references",
}


def _domain_status(model: Dict[str, Any]) -> List[Dict[str, str]]:
    missing: Dict[str, List[str]] = {}
    for entry in model["unknowns"]:
        for domain in entry["needed_by"]:
            missing.setdefault(domain, []).append(entry["path"])
    statuses = []
    for domain in DOMAINS:
        lacking = sorted(missing.get(domain, []))
        if domain in VALIDATED_DOMAINS:
            reason = VALIDATED_DOMAINS[domain]
            if lacking:
                reason += "; requirements resting on " + ", ".join(lacking) + " are BLOCKED"
            statuses.append({"domain": domain, "status": "implemented", "reason": reason})
        else:
            reason = f"no {domain} validator exists in this platform yet"
            if lacking:
                reason += "; this sample also lacks " + ", ".join(lacking)
            statuses.append({"domain": domain, "status": "not_implemented", "reason": reason})
    return statuses


def _provenance(item: Item) -> Dict[str, Any]:
    """The sample's hand-authored provenance. Its absence stops the build: a
    licence the builder filled in would be a licence nobody checked."""
    if not os.path.lexists(item.path(PROVENANCE)):
        raise ValueError(f"{item.item_id}: {PROVENANCE} is missing; licence and origin are never assumed")
    document = json.loads(item.read(PROVENANCE))
    validate_schema(document, "cad-dataset/v1/source-provenance")
    return document


def _simulation_files(item: Item) -> List[str]:
    return sorted(item.item_relative(path) for path in item.path("simulation").glob("*.py"))


def _item_manifest(item: Item, derived: Dict[str, bytes]) -> Dict[str, Any]:
    model = json.loads(derived[MODEL])
    provenance = _provenance(item)
    kernel = json.loads(derived[EXTRACTION])["importer"]
    producers = {
        EXTRACTION: ("ecad_model.importers.step_ocp", kernel["kernel_version"]),
        MODEL: ("ecad_model.builder", MODEL_VERSION),
        item.mjcf: ("ecad_model.mjcf", MODEL_VERSION),
        GOLDEN: ("ecad_model.requirements", MODEL_VERSION),
        CORNERS: ("ecad_model.requirements", MODEL_VERSION),
    }
    lineage = {
        EXTRACTION: [item.item_relative(item.cad)],
        MODEL: [EXTRACTION, ANNOTATIONS],
        item.mjcf: [MODEL],
        GOLDEN: [MODEL, REQUIREMENTS],
        CORNERS: [MODEL, REQUIREMENTS],
    }
    roles = {EXTRACTION: "cad_extraction", MODEL: "engineering_model", item.mjcf: "mechanical_model",
             GOLDEN: "golden_cases", CORNERS: "corner_cases"}
    origin: Dict[str, Any] = dict(provenance["origin"])
    if item.path("source/generate_step.py").is_file():
        origin["generator"] = _artifact(item, "source/generate_step.py")
    return {
        "$schema": ITEM_SCHEMA,
        "dataset_item_version": "1.0.0",
        "item_id": item.item_id,
        "title": model["design"]["name"],
        "description": provenance["description"],
        "artifact_type": provenance["artifact_type"],
        "artifact_version": provenance["artifact_version"],
        "units": provenance["units"],
        "coordinate_system": provenance["coordinate_system"],
        "created_at": provenance["created_at"],
        "collected_at": provenance["collected_at"],
        "versions": {
            "extraction": f"{kernel['name']} {kernel['version']} ({kernel['kernel_version']})",
            "engineering_model": MODEL_VERSION,
            "domain_models": {"mechanical": f"ecad_model.mjcf {MODEL_VERSION}"},
            "validation_contract": "hardware-validation v1.0.0",
        },
        "source": {
            "cad": _artifact(item, item.item_relative(item.cad)),
            "origin": origin,
            "license": dict(provenance["license"]),
        },
        "inputs": {
            "provenance": _artifact(item, PROVENANCE),
            "annotations": _artifact(item, ANNOTATIONS),
            "requirements": _artifact(item, REQUIREMENTS),
            "simulation": [_artifact(item, path) for path in _simulation_files(item)],
        },
        "derived": [
            {
                "role": roles[path],
                "artifact": _artifact(item, path, data),
                "producer": {"tool": producers[path][0], "version": producers[path][1]},
                "derived_from": lineage[path],
            }
            for path, data in derived.items()
        ],
        "domains": _domain_status(model),
    }


def build(directory: Path) -> List[str]:
    """Write every derived file and dataset-item.json from the item's inputs.

    Args:
        directory: The dataset item directory.

    Returns:
        The item-relative paths written.

    Raises:
        ValueError: An input violates its schema, or extraction failed.

    Example (on a copy, so the committed item is untouched):
        >>> import shutil, tempfile
        >>> with tempfile.TemporaryDirectory(dir=REPOSITORY_ROOT) as scratch:
        ...     copy = Path(scratch) / "robotic_joint_001"
        ...     _ = shutil.copytree(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001", copy)
        ...     written = build(copy)
        >>> written[-1]
        'dataset-item.json'
    """
    item = Item(directory)
    _refuse_symlinks(item)
    derived = _derive(item)
    for relative, data in derived.items():
        _write_inside(item, relative, data)
    manifest = _item_manifest(item, derived)
    validate_schema(manifest, "cad-dataset/v1/dataset-item")
    _write_inside(item, "dataset-item.json", _json_bytes(manifest))
    return [*derived, "dataset-item.json"]


def _refuse_symlinks(item: Item) -> None:
    """Refuse an item that contains any symlink, before anything is read or written.

    Git tracks symlinks. One inside an item can redirect a read to a file the
    hashes do not cover, or a build's write to any file the user can modify.
    """
    import os

    for directory, subdirectories, files in os.walk(item.root, followlinks=False):
        for name in [*subdirectories, *files]:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"{item.item_id}: {item.root.name}/{path.relative_to(item.root).as_posix()} "
                                 "is a symlink; dataset items may not contain symlinks")


def _write_inside(item: Item, relative: str, data: bytes) -> None:
    """Write a derived file, refusing any symlink on the way to it.

    A committed item can carry symlinks, and Path.write_bytes follows them:
    without this, building an untrusted item could overwrite any file the
    user can write.
    """
    target = item.root / relative
    current = item.root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{relative}: refusing to write through the symlink {item.item_relative(current.parent)}/{part}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.resolve().is_relative_to(item.root):
        raise ValueError(f"{relative}: resolves outside the item")
    target.write_bytes(data)


# --- comparison ------------------------------------------------------------

_QUOTED = re.compile(r'"([^"]*)"')


def _close(a: float, b: float, scale: float = 0.0) -> bool:
    """Equal within the relative tolerance of the larger of the values and scale."""
    tolerance = max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * max(abs(a), abs(b), scale))
    return abs(a - b) <= tolerance


def _flatten(value: Any) -> Optional[List[float]]:
    """The numbers of a (nested) all-number list, or None if it holds anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        flat: List[float] = []
        for item in value:
            inner = _flatten(item)
            if inner is None:
                return None
            flat += inner
        return flat
    return None


def _same_shape(a: Any, b: Any) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same_shape(x, y) for x, y in zip(a, b))
    return not isinstance(a, list) and not isinstance(b, list)


def _array_problems(a: List[float], b: List[float], where: str) -> List[str]:
    # One tolerance for the whole array, scaled by its largest magnitude: a
    # physically zero product of inertia beside a 1e10 moment is kernel noise
    # (Linux aarch64 against macOS arm64: up to 1e-8 mm^5), and a per-element
    # relative test would call two platforms' noise a difference.
    scale = max([abs(item) for item in a + b] or [0.0])
    return [
        f"{where}[{i}]: {x!r} != {y!r}"
        for i, (x, y) in enumerate(zip(a, b))
        if not _close(x, y, scale)
    ]


def same_content(a: Any, b: Any, where: str = "") -> List[str]:
    """Differences between two JSON values; numbers compare with tolerance.

    Scalars compare with a relative tolerance of 1e-9 (absolute floor 1e-12).
    An all-number array -- a vector or matrix -- uses one tolerance scaled by
    its largest element, so noise in a physically zero entry is not a
    difference.

    Args:
        a: The committed value.
        b: The freshly derived value.
        where: Path prefix for messages.

    Returns:
        One message per difference; empty when equivalent.

    Example:
        >>> same_content({"m": 1.0}, {"m": 1.0 + 1e-13})
        []
        >>> same_content({"m": 1.0}, {"m": 1.1})
        ['/m: 1.0 != 1.1']
        >>> same_content({"I": [[1e10, 4.8e-7]]}, {"I": [[1e10, -3e-7]]})
        []
    """
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str):
        return [] if a == b else [f"{where or '<root>'}: {a!r} != {b!r}"]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return [] if _close(float(a), float(b)) else [f"{where}: {a!r} != {b!r}"]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{where}: length {len(a)} != {len(b)}"]
        flat_a, flat_b = _flatten(a), _flatten(b)
        if flat_a is not None and flat_b is not None:
            if not _same_shape(a, b):
                return [f"{where}: array shapes differ"]
            return _array_problems(flat_a, flat_b, where)
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in same_content(x, y, f"{where}[{i}]")]
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [f"{where}: keys differ: {sorted(set(a) ^ set(b))}"]
        return [d for key in sorted(a) for d in same_content(a[key], b[key], f"{where}/{key}")]
    return [f"{where}: {type(a).__name__} != {type(b).__name__}"]


def _numbers(text: str) -> Optional[List[float]]:
    tokens = text.split()
    if not tokens:
        return None
    try:
        return [float(token) for token in tokens]
    except ValueError:
        return None


def same_text(a: str, b: str, where: str) -> List[str]:
    """Differences between two XML texts whose numeric attribute values compare with tolerance.

    Everything outside quoted attribute values must match exactly, and so must
    every non-numeric value. An attribute holding only numbers -- a position,
    an inertia list -- compares as one array with a tolerance scaled by its
    largest element.

    Args:
        a: The committed text.
        b: The freshly derived text.
        where: Name used in messages.

    Returns:
        One message per difference; empty when equivalent.

    Example:
        >>> same_text('pos="1 2.5"', 'pos="1 2.5000000000001"', "model.xml")
        []
        >>> same_text('<body name="joint_001"/>', '<body name="joint_1"/>', "model.xml")
        ["model.xml: value 0: 'joint_001' != 'joint_1'"]
    """
    parts_a, parts_b = _QUOTED.split(a), _QUOTED.split(b)
    if len(parts_a) != len(parts_b):
        return [f"{where}: the documents have different structure"]
    problems = []
    for index, (x, y) in enumerate(zip(parts_a, parts_b)):
        if index % 2 == 0:
            if x != y:
                problems.append(f"{where}: text differs outside attribute values")
            continue
        value = index // 2
        numbers_x, numbers_y = _numbers(x), _numbers(y)
        if numbers_x is None or numbers_y is None:
            if x != y:
                problems.append(f"{where}: value {value}: {x!r} != {y!r}")
        elif len(numbers_x) != len(numbers_y):
            problems.append(f"{where}: value {value}: {len(numbers_x)} numbers != {len(numbers_y)}")
        else:
            problems += _array_problems(numbers_x, numbers_y, f"{where}: value {value}")
    return problems


def integrity(item: Item) -> List[str]:
    """Every hash recorded in dataset-item.json must match the committed bytes exactly.

    Args:
        item: The dataset item.

    Returns:
        One message per missing file or mismatched hash; empty when intact.

    Example:
        >>> integrity(Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"))
        []
    """
    manifest = json.loads(item.read("dataset-item.json"))
    inputs = manifest["inputs"]
    recorded = [manifest["source"]["cad"], inputs["provenance"], inputs["annotations"], inputs["requirements"],
                *inputs["simulation"]]
    if "generator" in manifest["source"]["origin"]:
        recorded.append(manifest["source"]["origin"]["generator"])
    recorded += [entry["artifact"] for entry in manifest["derived"]]
    problems = []
    committed = {item.item_relative(path) for path in item.files()} - {"dataset-item.json"}
    unrecorded = sorted(committed - {artifact["path"] for artifact in recorded})
    if unrecorded:
        problems.append("files not recorded in dataset-item.json: " + ", ".join(unrecorded))
    for artifact in recorded:
        path = item.path(artifact["path"])
        if not path.is_file():
            problems.append(f"{artifact['path']}: recorded in dataset-item.json but missing")
            continue
        try:
            regular_file(path)
        except UnsupportedFormat as exc:
            problems.append(f"{artifact['path']}: {exc}")
            continue
        data = path.read_bytes()
        if _sha256(data) != artifact["sha256"] or len(data) != artifact["size_bytes"]:
            problems.append(f"{artifact['path']}: bytes do not match the recorded hash")
    return problems


def reproducibility(item: Item, derived: Optional[Dict[str, bytes]] = None) -> List[str]:
    """Rebuilding from the CAD must reproduce every committed derived file.

    Args:
        item: The dataset item.
        derived: A derivation already computed for this item, to avoid
            extracting the CAD twice.

    Returns:
        One message per divergence beyond the numeric tolerance; empty when
        the committed derivation reproduces.

    Example:
        >>> reproducibility(Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"))
        []
    """
    problems = []
    for relative, data in (_derive(item) if derived is None else derived).items():
        path = item.path(relative)
        if not path.is_file():
            problems.append(f"{relative}: derived file is not committed")
            continue
        committed = item.read(relative)
        if relative.endswith(".json"):
            problems += same_content(json.loads(committed), json.loads(data), relative)
        else:
            problems += same_text(committed.decode("utf-8"), data.decode("utf-8"), relative)
    return problems


def _without_derived_hashes(manifest: Dict[str, Any]) -> Dict[str, Any]:
    stripped = json.loads(json.dumps(manifest))
    for entry in stripped["derived"]:
        entry["artifact"].pop("sha256")
        entry["artifact"].pop("size_bytes")
    return stripped


def manifest_problems(item: Item, derived: Optional[Dict[str, bytes]] = None) -> List[str]:
    """dataset-item.json must be exactly what build would write now.

    It is generated, so a hand edit -- a licence flag, a domain claimed as
    implemented -- is a divergence from what the inputs imply. Derived-file
    hashes are left out: integrity() checks them against the committed bytes
    exactly, and reproducibility() checks their content within tolerance, so
    a last-digit difference between platforms does not fail here.

    Args:
        item: The dataset item.
        derived: A derivation already computed for this item.

    Returns:
        One message per divergence; empty when the manifest is current.

    Example:
        >>> manifest_problems(Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"))
        []
    """
    fresh = _item_manifest(item, _derive(item) if derived is None else derived)
    committed = json.loads(item.read("dataset-item.json"))
    return same_content(_without_derived_hashes(committed), _without_derived_hashes(fresh), "dataset-item.json")


def cited_source_problems(item: Item) -> List[str]:
    """Every file an annotation cites by hash must still have that hash.

    A citation is read only if it resolves to a regular file inside the
    repository: annotations are untrusted input, and an absolute or ../ ref
    would otherwise have the checker read any file on the host.

    Args:
        item: The dataset item.

    Returns:
        One message per cited file that is outside the repository, missing,
        not a regular file, or changed.

    Example:
        >>> cited_source_problems(Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"))
        []
    """
    problems = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            origin = node.get("source") if {"value", "status", "source"} <= node.keys() else None
            if isinstance(origin, dict) and "sha256" in origin:
                ref = origin["ref"]
                path = (REPOSITORY_ROOT / ref).resolve()
                if not path.is_relative_to(REPOSITORY_ROOT):
                    problems.append(f"cited source {ref} lies outside the repository; it is not read")
                elif not path.exists():
                    problems.append(f"cited source {ref} does not exist")
                else:
                    try:
                        regular_file(path)
                    except UnsupportedFormat as exc:
                        problems.append(f"cited source {ref}: {exc}")
                    else:
                        if _sha256(path.read_bytes()) != origin["sha256"]:
                            problems.append(f"cited source {ref} has changed since it was cited")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(item.read(ANNOTATIONS)))
    return sorted(set(problems))


def check(directory: Path) -> List[str]:
    """All integrity and reproducibility problems of an item.

    Args:
        directory: The dataset item directory.

    Returns:
        Problems as messages; empty when every hash matches and every derived
        file reproduces from the CAD.

    Example:
        >>> check(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")
        []
    """
    item = Item(directory)
    # Before anything is read or parsed: a symlink could redirect a read past
    # the hashes, and an item git cannot enumerate is refused before the
    # native STEP parser is run on it.
    _refuse_symlinks(item)
    item.files()
    derived = _derive(item)
    return (integrity(item) + cited_source_problems(item) + reproducibility(item, derived)
            + manifest_problems(item, derived))


# --- physical sanity -----------------------------------------------------------

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


def _sanity_problems(model: Dict[str, Any]) -> List[str]:
    problems = []
    for component in model["components"]:
        cid = component["component_id"]
        if component["geometry"] is not None and component["geometry"]["volume"]["value"] <= 0:
            problems.append(f"{cid}: CAD volume is not positive")
        physical = component["physical"]
        if physical is None:
            continue
        if physical["mass"]["status"] != "UNKNOWN" and physical["mass"]["value"] <= 0:
            problems.append(f"{cid}: mass is not positive")
        if physical["inertia_about_com"]["status"] != "UNKNOWN":
            problems += inertia_problems(cid, physical["inertia_about_com"]["value"])
    for joint in model["joints"]:
        if joint["axis"]["status"] != "UNKNOWN":
            length = math.sqrt(sum(item * item for item in joint["axis"]["value"]))
            if abs(length - 1.0) > 1e-9:
                problems.append(f"{joint['joint_id']}: axis is not a unit vector (length {length})")
        lower, upper = joint["limits"]["lower"], joint["limits"]["upper"]
        if lower["status"] != "UNKNOWN" and upper["status"] != "UNKNOWN" and not lower["value"] < upper["value"]:
            problems.append(f"{joint['joint_id']}: lower limit is not below the upper limit")
    return problems


def _invariant_problems(item: Item, model: Dict[str, Any], extraction: Dict[str, Any],
                       requirements: Dict[str, Any], mjcf_text: str) -> List[str]:
    problems = []
    parts = {part["name"]: part["occurrence"] for part in extraction["parts"]}
    ids = {c["component_id"] for c in model["components"]} | {j["joint_id"] for j in model["joints"]}
    for component in model["components"]:
        ref = component["cad_ref"]
        if ref is not None and parts.get(ref["part"]) != ref["occurrence"]:
            problems.append(f"{component['component_id']}: cad_ref {ref} does not resolve to a CAD occurrence")
    for relation in model["relationships"]:
        for end in ("from", "to"):
            if relation[end] not in ids and relation[end] != model["design"]["design_id"]:
                problems.append(f"relationship {relation['relation']} names unknown {relation[end]!r}")
    for requirement in requirements["requirements"]:
        if requirement["component"] not in ids:
            problems.append(f"{requirement['requirement_id']}: constrains unknown component {requirement['component']!r}")
        if "quantity" in requirement["limit"]:
            try:
                resolve(model, requirement["limit"]["quantity"])
            except KeyError as exc:
                problems.append(f"{requirement['requirement_id']}: {exc.args[0]}")
    bodies = set(re.findall(r'<body name="([^"]+)"', mjcf_text))
    geometric = {c["component_id"] for c in model["components"] if c["cad_ref"] is not None}
    if bodies != geometric:
        problems.append(f"MJCF bodies {sorted(bodies)} != CAD components {sorted(geometric)}")
    if model["design"]["source_cad"]["sha256"] != _sha256(item.cad.read_bytes()):
        problems.append("the engineering model was derived from different CAD bytes")
    if model["unknowns"] != index_unknowns(model):
        problems.append("the unknowns index is stale")
    return problems


# --- V0-V4 -------------------------------------------------------------------------

def validate(directory: Path, output: Path) -> Dict[str, Any]:
    """Run V0-V4 on a dataset item and write a v1 receipt plus evidence.

    Nothing is PASS without hash-bound evidence, and anything that depends on
    an UNKNOWN is BLOCKED with the missing paths.

    Args:
        directory: The dataset item directory.
        output: A missing or empty directory for receipt.json, evidence/,
            evidence-index.json, trace.json and report.md.

    Returns:
        The receipt, which conforms to validation-receipt.schema.json.

    Raises:
        ValueError: output is not empty, or a producer cross-reference check
            failed (an unknown tool or requirement, or a duplicate check id).

    Example:
        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as scratch:
        ...     receipt = validate(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001", Path(scratch) / "run")
        >>> [gate["verdict"] for gate in receipt["gates"]][1:4]
        ['PASS', 'PASS', 'PASS']
        >>> receipt["gates"][4]["verdict"]  # REQ-XD-001 rests on an UNKNOWN actuator torque
        'BLOCKED'
    """
    from ecad_validation.cases import execute_cases
    from ecad_validation.contract import validate_document
    from ecad_validation.engine import repository_state
    from ecad_validation.models import (
        CheckResult, Domain, EvidenceReference, ExecutionStatus, GateLevel, GateResult, Layer,
        ProductRunResult, Verdict,
    )

    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    from ecad_validation.hashing import hash_tree

    item = Item(directory)
    _refuse_symlinks(item)  # before the input digest or any other read
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    commit, dirty = repository_state(REPOSITORY_ROOT)
    input_digest_before = hash_tree(item.root, item.files())

    def evidence(*relatives: str) -> List[EvidenceReference]:
        refs = []
        for relative in relatives:
            if item.path(relative).is_file():
                data = item.read(relative)
                refs.append(EvidenceReference(path=relative, sha256=_sha256(data),
                                              media_type=_artifact(item, relative)["media_type"],
                                              size_bytes=len(data)))
        return refs

    def generated(check_id: str, payload: Dict[str, Any]) -> Tuple[List[EvidenceReference], Dict[str, bytes]]:
        data = _json_bytes({"check_id": check_id, **payload})
        digest = _sha256(data)
        path = f"generated/{digest}.json"
        return [EvidenceReference(path=path, sha256=digest, media_type="application/json", size_bytes=len(data))], {path: data}

    def result(check_id: str, gate: Any, domain: Any, layer: Any, problems: List[str], inputs: Sequence[str],
               pass_code: str, fail_code: str, summary: str) -> Any:
        refs, extra = generated(check_id, {"problems": problems})
        return CheckResult(
            check_id=check_id, gate=gate, domain=domain, layer=layer,
            execution_status=ExecutionStatus.COMPLETED,
            verdict=Verdict.FAIL if problems else Verdict.PASS,
            reason_code=fail_code if problems else pass_code,
            summary=summary, findings=problems,
            evidence=[*evidence(*inputs), *refs], generated_evidence=extra,
        )

    cad_rel = item.item_relative(item.cad)
    inputs = [cad_rel, ANNOTATIONS, REQUIREMENTS, "dataset-item.json"]

    # V0: every document conforms to its schema and every hash is exact.
    v0_problems = []
    for relative, schema in (
        ("dataset-item.json", "cad-dataset/v1/dataset-item"),
        (ANNOTATIONS, "engineering-model/v1/design-annotations"),
        (REQUIREMENTS, "engineering-model/v1/engineering-requirements"),
        (EXTRACTION, "cad-dataset/v1/cad-extraction"),
        (MODEL, "engineering-model/v1/engineering-model"),
    ):
        try:
            validate_schema(json.loads(item.read(relative)), schema)
        except (OSError, ValueError) as exc:
            v0_problems.append(f"{relative}: {exc}")
    v0_problems += integrity(item) + cited_source_problems(item)
    v0 = [result("v0.dataset-schemas-and-hashes", GateLevel.V0, Domain.DATA_MANAGEMENT, Layer.DESIGN, v0_problems,
                 inputs, "DATASET_SCHEMAS_VALID", "DATASET_SCHEMA_OR_HASH_INVALID",
                 "every dataset document conforms to its schema and every recorded hash matches")]

    # V1: the CAD re-extracts, and the physics it yields is physically possible.
    failure: Optional[Tuple[Any, Any, str, str]] = None
    try:
        fresh = _derive(item)
        model = json.loads(fresh[MODEL])
        extraction = json.loads(fresh[EXTRACTION])
        v1_problems = _sanity_problems(model)
    except ExtractionError as exc:
        fresh, model, extraction, v1_problems = {}, {}, {}, []
        failure = {
            "rejected": (ExecutionStatus.COMPLETED, Verdict.FAIL, "CAD_REJECTED", "the CAD was read and refused on its content"),
            "crashed": (ExecutionStatus.CRASHED, Verdict.INCONCLUSIVE, "CAD_EXTRACTION_CRASHED", "the CAD parser died or produced no result"),
            "timed_out": (ExecutionStatus.TIMED_OUT, Verdict.INCONCLUSIVE, "CAD_EXTRACTION_TIMED_OUT", "the CAD parser exceeded its time limit"),
            "unavailable": (ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED, "CAD_KERNEL_UNAVAILABLE", "the CAD kernel is not installed here"),
        }[exc.kind]
        v1_blocked: Optional[str] = str(exc)
    except MissingInput as exc:
        # A value nobody has recorded is a missing input, not a design defect.
        fresh, model, extraction, v1_problems = {}, {}, {}, []
        failure = (ExecutionStatus.SKIPPED, Verdict.BLOCKED, "MISSING_REQUIRED_INPUT",
                   "a value the mechanical model needs is UNKNOWN")
        v1_blocked = str(exc)
    except (OSError, ValueError) as exc:
        # A schema-invalid input or an inconsistent annotation: the item is wrong.
        fresh, model, extraction, v1_problems = {}, {}, {}, []
        failure = (ExecutionStatus.COMPLETED, Verdict.FAIL, "DATASET_INPUT_INVALID", "the item's inputs cannot be built into a model")
        v1_blocked = str(exc)
    else:
        v1_blocked = None
    if failure is None:
        v1 = [result("v1.cad-extraction-and-physical-sanity", GateLevel.V1, Domain.PHYSICAL_DESIGN, Layer.MODEL,
                     v1_problems, [cad_rel, ANNOTATIONS], "PHYSICAL_SANITY_PASSED", "PHYSICAL_SANITY_FAILED",
                     "the CAD re-extracts and every mass, inertia, axis and limit is physically possible")]
    else:
        status, verdict, reason, summary = failure
        refs, extra = generated("v1.cad-extraction-and-physical-sanity", {"failure": v1_blocked})
        v1 = [CheckResult(check_id="v1.cad-extraction-and-physical-sanity", gate=GateLevel.V1,
                          domain=Domain.PHYSICAL_DESIGN, layer=Layer.MODEL,
                          execution_status=status, verdict=verdict, reason_code=reason, summary=summary,
                          findings=[v1_blocked or summary], evidence=[*evidence(cad_rel), *refs],
                          generated_evidence=extra)]

    # V2: the committed derivation reproduces from the CAD and every cross-reference resolves.
    if fresh:
        requirements = json.loads(item.read(REQUIREMENTS))
        v2_problems = reproducibility(item, fresh) + manifest_problems(item, fresh) + _invariant_problems(
            item, model, extraction, requirements, fresh[item.mjcf].decode("utf-8"))
        v2 = [result("v2.cad-model-invariants", GateLevel.V2, Domain.PHYSICAL_DESIGN, Layer.VALIDATION, v2_problems,
                     [cad_rel, ANNOTATIONS, REQUIREMENTS, EXTRACTION, MODEL, item.mjcf],
                     "DERIVATION_REPRODUCED", "DERIVATION_DIVERGED",
                     "committed derived files reproduce from the CAD and every reference resolves")]
    else:
        v2 = [CheckResult(check_id="v2.cad-model-invariants", gate=GateLevel.V2, domain=Domain.PHYSICAL_DESIGN,
                          layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE,
                          verdict=Verdict.BLOCKED, reason_code="CAD_EXTRACTION_NOT_AVAILABLE",
                          summary="invariants need a fresh derivation from the CAD, which V1 could not produce",
                          findings=[v1_blocked or "extraction unavailable"], evidence=evidence(cad_rel))]

    # V3/V4: the existing case engine, then BLOCKED checks for what rests on an UNKNOWN.
    requirements = json.loads(item.read(REQUIREMENTS))
    committed_model = json.loads(item.read(MODEL))
    _golden, _corners, blocked = compile_cases(committed_model, requirements, item.mjcf)
    engineering_ids = {entry["reference_id"] for entry in requirements["reference_values"]} | {
        entry["requirement_id"] for entry in requirements["requirements"]}
    illustrative_ids = {entry["requirement_id"] for entry in requirements["requirements"] if entry["illustrative"]}
    gates: Dict[Any, List[Any]] = {GateLevel.V0: v0, GateLevel.V1: v1, GateLevel.V2: v2}
    for level, directory_name in ((GateLevel.V3, "golden"), (GateLevel.V4, "corners")):
        checks = execute_cases(item.root, level, directory_name)
        for check_result in checks:
            case_id = check_result.check_id.split(".", 1)[1]
            if case_id in engineering_ids:
                check_result.requirement_ids = [*check_result.requirement_ids, case_id]
            if case_id in illustrative_ids and check_result.verdict is Verdict.PASS:
                # Meeting a limit invented to exercise the pipeline qualifies
                # nothing. The contract's WARNING is advisory and cannot satisfy
                # a required check, so such a sample is never eligible for ebuild.
                check_result.verdict = Verdict.WARNING
                check_result.reason_code = "WITHIN_ILLUSTRATIVE_LIMIT"
                check_result.summary = "within an illustrative limit, which is not a qualification"
                check_result.findings = [*check_result.findings,
                                         f"{case_id} is illustrative: not a customer, safety or certification requirement"]
        for entry in blocked:
            if entry["gate"] != level.value:
                continue
            refs, extra = generated(f"{level.value.lower()}.{entry['id']}", entry)
            requirement = next((r for r in requirements["requirements"] if r["requirement_id"] == entry["id"]), None)
            domain = CONTRACT_DOMAIN[requirement["domain"]] if requirement else "integrated_physics"
            checks.append(CheckResult(
                check_id=f"{level.value.lower()}.{entry['id']}", gate=level, domain=Domain(domain),
                layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
                reason_code="REQUIREMENT_INPUT_UNKNOWN", summary=entry["reason"],
                requirement_ids=[f"POLICY:{level.value}-{'GOLDEN' if level is GateLevel.V3 else 'CORNER'}", entry["id"]],
                findings=[f"UNKNOWN: {path}" for path in entry["unknown_paths"]],
                evidence=[*evidence(REQUIREMENTS, MODEL), *refs], generated_evidence=extra,
            ))
        gates[level] = checks

    input_digest_after = hash_tree(item.root, item.files())
    refs, extra = generated("v0.dataset-input-immutability",
                            {"before": input_digest_before, "after": input_digest_after})
    unchanged = input_digest_before == input_digest_after
    gates[GateLevel.V0].append(CheckResult(
        check_id="v0.dataset-input-immutability", gate=GateLevel.V0, domain=Domain.DATA_MANAGEMENT,
        layer=Layer.VALIDATION, execution_status=ExecutionStatus.COMPLETED,
        verdict=Verdict.PASS if unchanged else Verdict.FAIL,
        reason_code="VALIDATION_INPUT_UNCHANGED" if unchanged else "SOURCE_MUTATED_DURING_VALIDATION",
        summary="the dataset item's files were identical before and after validation" if unchanged
        else "the dataset item's files changed while validation was running",
        evidence=refs, generated_evidence=extra,
    ))
    refs, extra = generated("v0.pinned-clean-source", {"commit": commit, "dirty": dirty})
    gates[GateLevel.V0].append(CheckResult(
        check_id="v0.pinned-clean-source", gate=GateLevel.V0, domain=Domain.DATA_MANAGEMENT,
        layer=Layer.VALIDATION, execution_status=ExecutionStatus.COMPLETED,
        verdict=Verdict.BLOCKED if dirty else Verdict.PASS,
        reason_code="SOURCE_TREE_DIRTY" if dirty else "SOURCE_REVISION_PINNED",
        summary="source tree contains changes not represented by the pinned commit" if dirty
        else "source tree is clean and bound to the recorded commit",
        evidence=refs, generated_evidence=extra,
    ))
    gate_results = [GateResult.from_checks(level, gates[level]) for level in GateLevel]
    tools: Dict[str, Dict[str, Any]] = {
        "ecad-validator": {
            "tool_id": "ecad-validator", "name": "eCAD dataset validator", "version": MODEL_VERSION,
            "invocation": ["python3", "tools/cad_dataset.py", "validate", item.repo_relative(item.root),
                           "--output", "<output directory>"],
            # The output path is host-specific; recording it would break portability.
            "settings": {"redacted_arguments": ["--output"]},
        },
    }
    if extraction:
        tools["opencascade"] = {
            "tool_id": "opencascade", "name": "OpenCASCADE via cadquery-ocp",
            "version": extraction["importer"]["kernel_version"],
            "invocation": ["python3", "-m", "ecad_model.importers.step_ocp", item.item_relative(item.cad)],
            "settings": {"document_length_unit": "mm", "timeout_seconds": 120,
                         "address_space_limit_bytes": 2 * 1024 * 1024 * 1024, "isolation": "run_process workspace copy"},
        }
    runs: Dict[str, List[Any]] = {}
    for gate in gate_results:
        for check_result in gate.checks:
            if check_result.tool_id != "ecad-validator" and check_result.tool_version:
                runs.setdefault(check_result.tool_id, []).append(check_result)
    for tool_id, tool_checks in runs.items():
        tools[tool_id] = _tool_record(tool_id, tool_checks)
    product = ProductRunResult(
        product_id=f"datasets:{item.item_id}", product_path=item.repo_relative(item.root),
        source_commit=commit, source_dirty=dirty,
        input_sha256=input_digest_after,
        started_at=started, completed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        gates=gate_results, tools=[tools[name] for name in sorted(tools)],
    )
    receipt = product.to_receipt()
    _check_references(receipt, requirements)
    validate_document(REPOSITORY_ROOT, "validation-receipt.schema.json", receipt)
    _write_run(item, output, product, receipt, requirements)
    return receipt


def _tool_record(tool_id: str, checks: Sequence[Any]) -> Dict[str, Any]:
    """One receipt record for a tool, stating only what all its checks share.

    Each check runs the tool with its own arguments, which its hash-bound
    execution record keeps. The receipt keeps one record per tool, so it
    holds the common part of the invocations and the settings every check
    agrees on -- never one check's arguments presented as the tool's.

    Raises:
        ValueError: The checks report different versions of one tool.

    Example:
        >>> from types import SimpleNamespace as C
        >>> a = C(tool_version="3.14.0", tool_invocation=["py", "s.py", "--scenario", "{a}"], tool_settings={"k": 1})
        >>> b = C(tool_version="3.14.0", tool_invocation=["py", "s.py", "--scenario", "{b}"], tool_settings={"k": 1})
        >>> _tool_record("mujoco", [a, b])["invocation"]
        ['py', 's.py']
    """
    versions = {check.tool_version for check in checks}
    if len(versions) != 1:
        raise ValueError(f"tool {tool_id} reported different versions in one run: {sorted(versions)}")
    invocations = [list(check.tool_invocation or [tool_id]) for check in checks]
    common: List[str] = []
    for parts in zip(*invocations):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    while len(common) > 1 and common[-1].startswith("-"):
        common.pop()  # an option whose value differs between checks
    settings = {key: value for key, value in checks[0].tool_settings.items()
                if all(check.tool_settings.get(key) == value for check in checks)}
    settings["per_check_invocation"] = "each check's execution record"
    return {"tool_id": tool_id, "name": tool_id, "version": versions.pop(),
            "invocation": common or [tool_id], "settings": settings}


def _check_references(receipt: Dict[str, Any], requirements: Dict[str, Any]) -> None:
    """Producer cross-reference checks: every cited tool and requirement exists."""
    catalog = json.loads((REPOSITORY_ROOT / "contracts/hardware-validation/v1/policy-requirements.json").read_bytes())
    known = {entry["requirement_id"] for entry in catalog["requirements"]}
    known |= {entry["reference_id"] for entry in requirements["reference_values"]}
    known |= {entry["requirement_id"] for entry in requirements["requirements"]}
    tools = {tool["tool_id"] for tool in receipt["tools"]}
    seen = set()
    for gate in receipt["gates"]:
        for check_result in gate["checks"]:
            if check_result["check_id"] in seen:
                raise ValueError(f"duplicate check ID {check_result['check_id']}")
            seen.add(check_result["check_id"])
            if check_result["tool_id"] not in tools:
                raise ValueError(f"check {check_result['check_id']} references unknown tool {check_result['tool_id']}")
            unknown = set(check_result["requirement_ids"]) - known
            if unknown:
                raise ValueError(f"check {check_result['check_id']} references unknown requirements {sorted(unknown)}")


def _write_run(item: Item, output: Path, product: Any, receipt: Dict[str, Any],
               requirements: Dict[str, Any]) -> None:
    """Write the receipt, content-addressed evidence and its index, the trace and the report.

    The receipt and evidence index are contract documents, so they follow the
    contract's serialisation rule exactly: canonical JSON (sorted keys,
    compact separators) plus one final LF, hashed as stored.
    """
    from ecad_validation.contract import validate_document
    from ecad_validation.hashing import canonical_json_bytes

    def canonical(value: Any) -> bytes:
        return canonical_json_bytes(value) + b"\n"

    evidence_dir = output / "evidence" / "sha256"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for gate_index, gate in enumerate(product.gates):
        for check_index, check_result in enumerate(gate.checks):
            receipt_check = receipt["gates"][gate_index]["checks"][check_index]
            for position, reference in enumerate(check_result.evidence):
                data = check_result.generated_evidence.get(reference.path)
                generated = data is not None
                if data is None:
                    data = item.read(reference.path)
                if _sha256(data) != reference.sha256:
                    raise ValueError(f"evidence changed during validation: {reference.path}")
                target = evidence_dir / reference.sha256
                if not target.exists():
                    target.write_bytes(data)
                stored = target.relative_to(output).as_posix()
                receipt_check["evidence"][position]["path"] = stored
                provenance = (
                    {"source_type": "generated", "generator_tool_id": check_result.tool_id,
                     "recorded_at": product.completed_at}
                    if generated else
                    {"source_type": "repository", "source_path": f"{item.repo_relative(item.root)}/{reference.path}",
                     "source_commit": product.source_commit, "recorded_at": product.completed_at}
                )
                index.append({
                    "evidence_id": receipt_check["evidence"][position]["evidence_id"],
                    "path": stored, "sha256": reference.sha256, "media_type": reference.media_type,
                    "size_bytes": reference.size_bytes, "check_id": check_result.check_id,
                    "requirement_ids": check_result.requirement_ids, "producer_tool_id": check_result.tool_id,
                    "captured_at": product.completed_at, "provenance": provenance,
                })
    validate_document(REPOSITORY_ROOT, "validation-receipt.schema.json", receipt)
    receipt_bytes = canonical(receipt)
    (output / "receipt.json").write_bytes(receipt_bytes)
    evidence_index = {
        "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/evidence-index.schema.json",
        "contract_version": receipt["contract_version"],
        "product_id": receipt["product"]["id"],
        "receipt_sha256": _sha256(receipt_bytes),
        "generated_at": product.completed_at,
        "evidence": index,
    }
    validate_document(REPOSITORY_ROOT, "evidence-index.schema.json", evidence_index)
    (output / "evidence-index.json").write_bytes(canonical(evidence_index))
    trace = _requirement_trace(receipt, requirements, json.loads(item.read(MODEL)))
    (output / "trace.json").write_bytes(_json_bytes(trace))
    (output / "report.md").write_text(_report(receipt, trace), encoding="utf-8")


def _requirement_trace(receipt: Dict[str, Any], requirements: Dict[str, Any],
                      model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Requirement -> check -> measurement -> verdict -> CAD components, for every requirement."""
    checks = {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}
    moving: List[str] = []
    fixed: List[str] = []
    joint = model["joints"][0] if model["joints"] else None
    if joint:
        roots = rigid_groups(model)
        for c in model["components"]:
            if c["cad_ref"] is None:
                continue
            label = f"{c['component_id']} ({c['cad_ref']['occurrence']})"
            (moving if roots[c["component_id"]] == roots[joint["child"]] else fixed).append(label)
        moving.sort()
        fixed.sort()
    rows = []
    for gate, entries, key in (("V3", requirements["reference_values"], "reference_id"),
                               ("V4", requirements["requirements"], "requirement_id")):
        for entry in entries:
            check_result = checks.get(f"{gate.lower()}.{entry[key]}")
            metric = entry["metric"]
            rows.append({
                "requirement_id": entry[key],
                "title": entry["title"],
                "gate": gate,
                "metric": metric,
                "unit": entry["unit"],
                "measured": (check_result or {}).get("metrics", {}).get(metric),
                "verdict": (check_result or {}).get("verdict", "NOT_RUN"),
                "reason_code": (check_result or {}).get("reason_code"),
                "check_id": (check_result or {}).get("check_id"),
                "findings": (check_result or {}).get("findings", []),
                "kind": "reference" if gate == "V3" else (
                    "illustrative requirement" if entry.get("illustrative") else "requirement"),
                "source": entry["source"],
                # Clearance is measured between the two sides; everything else
                # depends only on the parts that move.
                "cad_components": sorted(moving + fixed) if metric.startswith("rom_") else moving,
            })
    return rows


def _report(receipt: Dict[str, Any], trace: List[Dict[str, Any]]) -> str:
    lines = [
        f"# Validation report: {receipt['product']['id']}",
        "",
        f"- Source commit: `{receipt['source']['commit']}` (dirty: {receipt['source']['dirty']})",
        f"- Overall verdict: **{receipt['overall_verdict']}**",
        f"- Execution complete: {receipt['execution_complete']}",
        "",
        "| Gate | Verdict | Checks |",
        "|---|---|---|",
    ]
    for gate in receipt["gates"]:
        summary = ", ".join(f"{c['check_id']}={c['verdict']}" for c in gate["checks"])
        lines.append(f"| {gate['gate']} | {gate['verdict']} | {summary} |")
    lines += ["", "## Requirements", "",
              "| Requirement | Kind | Metric | Measured | Verdict | Why |", "|---|---|---|---|---|---|"]
    for row in trace:
        measured = "—" if row["measured"] is None else f"{row['measured']:.6g} {row['unit']}"
        why = "; ".join(row["findings"]) or row["reason_code"] or ""
        lines.append(f"| {row['requirement_id']} | {row['kind']} | `{row['metric']}` | {measured} | "
                     f"{row['verdict']} | {why} |")
    lines += ["", "An illustrative requirement is an example limit chosen to exercise the pipeline, "
              "not a customer, safety or certification requirement. Meeting one is reported WARNING "
              "(WITHIN_ILLUSTRATIVE_LIMIT), never PASS.",
              "Every row traces to the CAD occurrences it depends on in `trace.json`."]
    return "\n".join(lines) + "\n"


__all__ = ["Item", "build", "check", "inertia_problems", "integrity", "reproducibility", "same_content", "same_text", "validate"]
