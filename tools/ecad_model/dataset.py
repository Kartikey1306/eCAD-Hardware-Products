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
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import MODEL_VERSION
from .builder import build_engineering_model, index_unknowns, resolve
from .importers import importer_for
from .mjcf import build_mjcf, rigid_groups
from .requirements import CONTRACT_DOMAIN, compile_cases
from .schemas import REPOSITORY_ROOT, validate as validate_schema

ITEM_SCHEMA = "https://embeddedos.org/schemas/cad-dataset/v1/dataset-item.schema.json"
EXTRACTION = "derived/cad_extraction.json"
MODEL = "derived/engineering_model.json"
ANNOTATIONS = "design/annotations.json"
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
        self.cad = steps[0]
        self.mjcf = f"derived/mechanical/{self.item_id}.mjcf.xml"

    def path(self, relative: str) -> Path:
        return self.root / relative

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
        listed = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "ls-files", "-co", "--exclude-standard", "-z", "--",
             self.repo_relative(self.root)],
            check=True, capture_output=True, timeout=30,
        ).stdout.decode("utf-8")
        return sorted(REPOSITORY_ROOT / name for name in listed.split("\0") if name)


def _json_bytes(value: Any) -> bytes:
    """Reviewable, deterministic JSON: sorted keys, two-space indent, one final LF."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(item: Item, relative: str, data: Optional[bytes] = None) -> Dict[str, Any]:
    payload = item.path(relative).read_bytes() if data is None else data
    media = "application/json" if relative.endswith(".json") else (
        "application/xml" if relative.endswith(".xml") else (
            "application/step" if relative.endswith(".step") else "text/x-python"
        )
    )
    return {"path": relative, "sha256": _sha256(payload), "size_bytes": len(payload), "media_type": media}


def _derive(item: Item) -> Dict[str, bytes]:
    """Every derived file of an item, computed from its CAD and inputs alone."""
    annotations_bytes = item.path(ANNOTATIONS).read_bytes()
    annotations = json.loads(annotations_bytes)
    requirements = json.loads(item.path(REQUIREMENTS).read_bytes())
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


def _domain_status(model: Dict[str, Any]) -> List[Dict[str, str]]:
    blocked_by: Dict[str, List[str]] = {}
    for unknown in model["unknowns"]:
        for domain in unknown["needed_by"]:
            blocked_by.setdefault(domain, []).append(unknown["path"])
    statuses = []
    for domain in DOMAINS:
        if domain == "mechanical":
            reason = "joint statics, rated-move dynamics, free oscillation and range-of-motion clearance are simulated"
            if blocked_by.get(domain):
                reason += "; comparison with actuator capability is BLOCKED on " + ", ".join(sorted(blocked_by[domain]))
            statuses.append({"domain": domain, "status": "implemented", "reason": reason})
        elif blocked_by.get(domain):
            statuses.append(
                {"domain": domain, "status": "blocked", "reason": "UNKNOWN: " + ", ".join(sorted(blocked_by[domain]))}
            )
        else:
            statuses.append(
                {"domain": domain, "status": "not_started", "reason": "no domain model or validator exists for this item yet"}
            )
    return statuses


def _item_manifest(item: Item, derived: Dict[str, bytes]) -> Dict[str, Any]:
    model = json.loads(derived[MODEL])
    producers = {
        EXTRACTION: ("ecad_model.importers.step_ocp", json.loads(derived[EXTRACTION])["importer"]["kernel_version"]),
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
    generator = item.path("source/generate_step.py")
    origin: Dict[str, Any] = {"kind": "self_authored", "author": "eCAD-Hardware-Products contributors"}
    if generator.is_file():
        origin["generator"] = _artifact(item, "source/generate_step.py")
    return {
        "$schema": ITEM_SCHEMA,
        "dataset_item_version": "1.0.0",
        "item_id": item.item_id,
        "title": model["design"]["name"],
        "source": {
            "cad": _artifact(item, item.item_relative(item.cad)),
            "origin": origin,
            "license": {
                "spdx": "MIT",
                "attribution": "eCAD-Hardware-Products contributors",
                "redistribution_permitted": True,
                "training_use_permitted": True,
                "basis": "self-authored in this repository, which is MIT licensed (see LICENSE)",
            },
        },
        "inputs": {"annotations": _artifact(item, ANNOTATIONS), "requirements": _artifact(item, REQUIREMENTS)},
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
    derived = _derive(item)
    for relative, data in derived.items():
        target = item.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = _item_manifest(item, derived)
    validate_schema(manifest, "cad-dataset/v1/dataset-item")
    item.path("dataset-item.json").write_bytes(_json_bytes(manifest))
    return [*derived, "dataset-item.json"]


# --- comparison ------------------------------------------------------------

_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE)


def same_content(a: Any, b: Any, where: str = "") -> List[str]:
    """Differences between two JSON values; numbers compare with tolerance.

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
    """
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str):
        return [] if a == b else [f"{where or '<root>'}: {a!r} != {b!r}"]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return [] if _close(float(a), float(b)) else [f"{where}: {a!r} != {b!r}"]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{where}: length {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in same_content(x, y, f"{where}[{i}]")]
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [f"{where}: keys differ: {sorted(set(a) ^ set(b))}"]
        return [d for key in sorted(a) for d in same_content(a[key], b[key], f"{where}/{key}")]
    return [f"{where}: {type(a).__name__} != {type(b).__name__}"]


def same_text(a: str, b: str, where: str) -> List[str]:
    """Differences between two texts whose embedded numbers compare with tolerance.

    Args:
        a: The committed text.
        b: The freshly derived text.
        where: Name used in messages.

    Returns:
        One message per difference; empty when equivalent.

    Example:
        >>> same_text('pos="1 2.5"', 'pos="1 2.5000000000001"', "model.xml")
        []
    """
    tokens_a, tokens_b = _NUMBER.split(a), _NUMBER.split(b)
    numbers_a, numbers_b = _NUMBER.findall(a), _NUMBER.findall(b)
    if tokens_a != tokens_b or len(numbers_a) != len(numbers_b):
        return [f"{where}: text differs outside its numbers"]
    return [
        f"{where}: number {i}: {x} != {y}"
        for i, (x, y) in enumerate(zip(numbers_a, numbers_b))
        if not _close(float(x), float(y))
    ]


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
    manifest = json.loads(item.path("dataset-item.json").read_bytes())
    recorded = [manifest["source"]["cad"], manifest["inputs"]["annotations"], manifest["inputs"]["requirements"]]
    if "generator" in manifest["source"]["origin"]:
        recorded.append(manifest["source"]["origin"]["generator"])
    recorded += [entry["artifact"] for entry in manifest["derived"]]
    problems = []
    for artifact in recorded:
        path = item.path(artifact["path"])
        if not path.is_file():
            problems.append(f"{artifact['path']}: recorded in dataset-item.json but missing")
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
        committed = path.read_bytes()
        if relative.endswith(".json"):
            problems += same_content(json.loads(committed), json.loads(data), relative)
        else:
            problems += same_text(committed.decode("utf-8"), data.decode("utf-8"), relative)
    return problems


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
    return integrity(item) + reproducibility(item)


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
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    commit, dirty = repository_state(REPOSITORY_ROOT)
    input_digest_before = hash_tree(item.root, item.files())

    def evidence(*relatives: str) -> List[EvidenceReference]:
        refs = []
        for relative in relatives:
            path = item.path(relative)
            if path.is_file():
                data = path.read_bytes()
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
            validate_schema(json.loads(item.path(relative).read_bytes()), schema)
        except (OSError, ValueError) as exc:
            v0_problems.append(f"{relative}: {exc}")
    v0_problems += integrity(item)
    v0 = [result("v0.dataset-schemas-and-hashes", GateLevel.V0, Domain.DATA_MANAGEMENT, Layer.DESIGN, v0_problems,
                 inputs, "DATASET_SCHEMAS_VALID", "DATASET_SCHEMA_OR_HASH_INVALID",
                 "every dataset document conforms to its schema and every recorded hash matches")]

    # V1: the CAD re-extracts, and the physics it yields is physically possible.
    try:
        fresh = _derive(item)
        model = json.loads(fresh[MODEL])
        extraction = json.loads(fresh[EXTRACTION])
        v1_problems = _sanity_problems(model)
        v1_blocked: Optional[str] = None
    except (OSError, ValueError) as exc:
        fresh, model, extraction, v1_problems, v1_blocked = {}, {}, {}, [], str(exc)
    if v1_blocked is None:
        v1 = [result("v1.cad-extraction-and-physical-sanity", GateLevel.V1, Domain.PHYSICAL_DESIGN, Layer.MODEL,
                     v1_problems, [cad_rel, ANNOTATIONS], "PHYSICAL_SANITY_PASSED", "PHYSICAL_SANITY_FAILED",
                     "the CAD re-extracts and every mass, inertia, axis and limit is physically possible")]
    else:
        v1 = [CheckResult(check_id="v1.cad-extraction-and-physical-sanity", gate=GateLevel.V1,
                          domain=Domain.PHYSICAL_DESIGN, layer=Layer.MODEL,
                          execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
                          reason_code="CAD_EXTRACTION_UNAVAILABLE", summary="the CAD could not be extracted here",
                          findings=[v1_blocked], evidence=evidence(cad_rel))]

    # V2: the committed derivation reproduces from the CAD and every cross-reference resolves.
    if fresh:
        requirements = json.loads(item.path(REQUIREMENTS).read_bytes())
        v2_problems = reproducibility(item, fresh) + _invariant_problems(
            item, model, extraction, requirements, fresh[item.mjcf].decode("utf-8"))
        v2 = [result("v2.cad-model-invariants", GateLevel.V2, Domain.PHYSICAL_DESIGN, Layer.VALIDATION, v2_problems,
                     [cad_rel, ANNOTATIONS, REQUIREMENTS, EXTRACTION, MODEL, item.mjcf],
                     "DERIVATION_REPRODUCED", "DERIVATION_DIVERGED",
                     "committed derived files reproduce from the CAD and every reference resolves")]
    else:
        v2 = [CheckResult(check_id="v2.cad-model-invariants", gate=GateLevel.V2, domain=Domain.PHYSICAL_DESIGN,
                          layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE,
                          verdict=Verdict.BLOCKED, reason_code="CAD_EXTRACTION_UNAVAILABLE",
                          summary="invariants need a fresh extraction, which was unavailable",
                          findings=[v1_blocked or "extraction unavailable"], evidence=evidence(cad_rel))]

    # V3/V4: the existing case engine, then BLOCKED checks for what rests on an UNKNOWN.
    requirements = json.loads(item.path(REQUIREMENTS).read_bytes())
    committed_model = json.loads(item.path(MODEL).read_bytes())
    _golden, _corners, blocked = compile_cases(committed_model, requirements, item.mjcf)
    engineering_ids = {entry["reference_id"] for entry in requirements["reference_values"]} | {
        entry["requirement_id"] for entry in requirements["requirements"]}
    gates: Dict[Any, List[Any]] = {GateLevel.V0: v0, GateLevel.V1: v1, GateLevel.V2: v2}
    for level, directory_name in ((GateLevel.V3, "golden"), (GateLevel.V4, "corners")):
        checks = execute_cases(item.root, level, directory_name)
        for check_result in checks:
            case_id = check_result.check_id.split(".", 1)[1]
            if case_id in engineering_ids:
                check_result.requirement_ids = [*check_result.requirement_ids, case_id]
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
        "ecad-validator": {"tool_id": "ecad-validator", "name": "eCAD dataset validator", "version": MODEL_VERSION,
                           "invocation": ["python3", "tools/ecad_model/cli.py", "validate"], "settings": {}},
    }
    for gate in gate_results:
        for check_result in gate.checks:
            if check_result.tool_id != "ecad-validator" and check_result.tool_version:
                tools[check_result.tool_id] = {
                    "tool_id": check_result.tool_id, "name": check_result.tool_id,
                    "version": check_result.tool_version,
                    "invocation": check_result.tool_invocation or [check_result.tool_id],
                    "settings": check_result.tool_settings,
                }
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
    """Write receipt, content-addressed evidence, requirement trace and report."""
    evidence_dir = output / "evidence" / "sha256"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for gate in product.gates:
        for check_result in gate.checks:
            for position, reference in enumerate(check_result.evidence):
                data = check_result.generated_evidence.get(reference.path)
                if data is None:
                    data = item.path(reference.path).read_bytes()
                if _sha256(data) != reference.sha256:
                    raise ValueError(f"evidence changed during validation: {reference.path}")
                target = evidence_dir / reference.sha256
                if not target.exists():
                    target.write_bytes(data)
                index.append({
                    "check_id": check_result.check_id, "position": position, "source_path": reference.path,
                    "stored": target.relative_to(output).as_posix(), "sha256": reference.sha256,
                })
    (output / "receipt.json").write_bytes(_json_bytes(receipt))
    (output / "evidence-index.json").write_bytes(_json_bytes({"evidence": index}))
    trace = _requirement_trace(receipt, requirements, json.loads(item.path(MODEL).read_bytes()))
    (output / "trace.json").write_bytes(_json_bytes(trace))
    (output / "report.md").write_text(_report(receipt, trace), encoding="utf-8")


def _requirement_trace(receipt: Dict[str, Any], requirements: Dict[str, Any],
                      model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Requirement -> check -> measurement -> verdict -> CAD components, for every requirement."""
    checks = {c["check_id"]: c for g in receipt["gates"] for c in g["checks"]}
    moving = []
    joint = model["joints"][0] if model["joints"] else None
    if joint:
        roots = rigid_groups(model)
        moving = sorted(
            f"{c['component_id']} ({c['cad_ref']['occurrence']})"
            for c in model["components"]
            if c["cad_ref"] is not None and roots[c["component_id"]] == roots[joint["child"]]
        )
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
                "cad_components": moving,
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
    lines += ["", "## Requirements", "", "| Requirement | Metric | Measured | Verdict | Why |", "|---|---|---|---|---|"]
    for row in trace:
        measured = "—" if row["measured"] is None else f"{row['measured']:.6g} {row['unit']}"
        why = "; ".join(row["findings"]) or row["reason_code"] or ""
        lines.append(f"| {row['requirement_id']} | `{row['metric']}` | {measured} | {row['verdict']} | {why} |")
    lines += ["", "Every row traces to the CAD occurrences it depends on in `trace.json`."]
    return "\n".join(lines) + "\n"


__all__ = ["Item", "build", "check", "inertia_problems", "integrity", "reproducibility", "same_content", "same_text", "validate"]
