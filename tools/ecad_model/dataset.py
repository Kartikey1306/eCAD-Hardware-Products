"""Build, check and validate one dataset item, whatever its domain.

A dataset item is a directory:

    source/provenance.json        origin, licence, primary domain, and the
                                  source artefacts, by path and format
    source/<artefacts>            the source of truth, e.g. a STEP assembly
    source/generate_*.py          how an artefact was authored (provenance only)
    design/annotations.json       design intent the artefacts cannot carry
    requirements/requirements.json
    simulation/                   domain simulation scripts run by case adapters
    derived/...                   everything derived from the inputs
    validation/{golden,corners}/cases.json
    dataset-item.json             licence, provenance, and a hash of every file

Nothing here knows a domain. The adapter registered for the sample's primary
domain (ecad_model.domains) reads its artefacts, builds the engineering model,
writes the domain model, says how cases run, and supplies the domain's V1 and
V2 checks.

Two properties are kept deliberately separate:

    integrity        every hash in dataset-item.json matches the committed bytes
                     exactly;
    reproducibility  rebuilding from the sources reproduces the committed derived
                     content to within a numeric tolerance. Kernel builds differ
                     in their last floating-point digits across platforms, so a
                     byte comparison here would fail on a CI runner for no
                     engineering reason.

validate() maps the item onto the existing V0-V4 receipt contract: V0 schemas
and hashes, V1 extraction and the domain's sanity checks, V2 reproduction and
the domain's invariants, V3/V4 the existing case engine plus BLOCKED checks
for anything that rests on a value with a null status (UNKNOWN, UNSPECIFIED
or NOT_AVAILABLE).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .builder import VERSION as BUILDER_VERSION, index_unknowns, resolve
from .domains import (
    DerivedFile, DomainAdapter, DomainNotImplemented, Extraction, SourceArtifact, adapter_for, domain_status,
)
from .domains.base import MEDIA_TYPES
from .importers import ExtractionError, UnsupportedFormat, regular_file
from .quantity import MissingInput, is_null
from .requirements import CONTRACT_DOMAIN, VERSION as COMPILER_VERSION, compile_cases
from .results import build_results, environment, input_leaves, lineage_problems, propagate, run_environment
from .schemas import REPOSITORY_ROOT, validate as validate_schema

ITEM_SCHEMA = "https://embeddedos.org/schemas/cad-dataset/v1/dataset-item.schema.json"
MODEL = "derived/engineering_model.json"
ANNOTATIONS = "design/annotations.json"
PROVENANCE = "source/provenance.json"
REQUIREMENTS = "requirements/requirements.json"
GOLDEN = "validation/golden/cases.json"
CORNERS = "validation/corners/cases.json"
MANIFEST = "dataset-item.json"
MANIFEST_VERSION = "1.0.0"
VALIDATOR_VERSION = "1.0.0"  # of this runner, as the receipt's ecad-validator tool
CASE_DOCUMENTS = ((GOLDEN, "V3", "golden"), (CORNERS, "V4", "corners"))
RELATIVE_TOLERANCE = 1e-9
ABSOLUTE_TOLERANCE = 1e-12


class Item:
    """Paths, identity and source artefacts of one dataset item directory.

    The sources are what the item's hand-written provenance declares, by path
    and format; nothing is found by globbing for an extension.

    Args:
        directory: The item directory.

    Raises:
        ValueError: The item directory is a symlink or lies outside the
            repository, the provenance is missing or invalid, or a declared
            source is not a regular file inside the item.

    Example:
        >>> item = Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")
        >>> item.item_id, item.domain, [s.format for s in item.sources]
        ('robotic_joint_001', 'mechanical', ['step'])
    """

    def __init__(self, directory: Path):
        # Before anything is read: a symlink could redirect a read past the
        # hashes, or a build's write to any file the user can modify -- the
        # item directory itself as much as anything inside it.
        if Path(directory).is_symlink():
            raise ValueError(f"{directory}: the item directory is a symlink; dataset items may not contain symlinks")
        self.root = Path(directory).resolve()
        self.item_id = self.root.name
        if not self.root.is_relative_to(REPOSITORY_ROOT):
            raise ValueError(f"{directory}: resolves outside the repository; it is not read")
        _refuse_symlinks(self)
        self.provenance = _provenance(self)
        self.domain: str = self.provenance["domain"]
        self.sources = [SourceArtifact(entry["path"], entry["format"]) for entry in self.provenance["artifacts"]]
        declared = [source.path for source in self.sources] + (
            [self.provenance["generator"]] if "generator" in self.provenance else [])
        for relative in declared:
            if not (self.root / relative).resolve().is_relative_to(self.root):
                raise ValueError(f"{self.item_id}: {relative} lies outside the item")
            if not os.path.lexists(self.root / relative):
                raise ValueError(f"{self.item_id}: the provenance declares {relative}, which does not exist")
            regular_file(self.root / relative)

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
            >>> all(item.path(source.path) in item.files() for source in item.sources)
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
        unlisted = [source.path for source in self.sources if self.path(source.path) not in files]
        if unlisted:
            raise ValueError(f"{relative}: git does not list the item's own sources {unlisted}; "
                             "refusing to skip their checks")
        return files


def _json_bytes(value: Any) -> bytes:
    """Reviewable, deterministic JSON: sorted keys, two-space indent, one final LF."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(item: Item, relative: str, data: Optional[bytes] = None, media_type: Optional[str] = None) -> Dict[str, Any]:
    payload = item.read(relative) if data is None else data
    media = media_type or MEDIA_TYPES.get(Path(relative).suffix, "application/octet-stream")
    return {"path": relative, "sha256": _sha256(payload), "size_bytes": len(payload), "media_type": media}


class Derivation:
    """Everything derived from an item's inputs, in the order it is written.

    Attributes:
        adapter: The domain adapter that derived it.
        extraction: What the adapter read: the model and its raw extraction.
        files: Every derived file by item-relative path, with the producer,
            lineage and comparator the manifest and check need.
        blocked: Requirements and references that rest on a null-status value.
    """

    def __init__(self, adapter: DomainAdapter, extraction: Extraction, files: Dict[str, DerivedFile],
                 blocked: List[Dict[str, Any]]):
        self.adapter = adapter
        self.extraction = extraction
        self.files = files
        self.blocked = blocked

    @property
    def model(self) -> Dict[str, Any]:
        return self.extraction.model

    def data(self) -> Dict[str, bytes]:
        return {path: derived.data for path, derived in self.files.items()}


def _derive(item: Item, registry: Optional[Dict[str, DomainAdapter]] = None) -> Derivation:
    """Everything derived from an item, computed from its sources and inputs alone.

    Raises:
        ExtractionError: The domain's importer refused, crashed, timed out or
            is not installed.
        MissingInput: The domain model needs a value that has a null status.
        ValueError: An input violates its schema, no adapter exists for the
            item's domain, or the inputs are inconsistent.
    """
    adapter = adapter_for(item.domain, registry)
    annotations_bytes = item.read(ANNOTATIONS)
    annotations = json.loads(annotations_bytes)
    requirements = json.loads(item.read(REQUIREMENTS))
    validate_schema(annotations, "engineering-model/v1/design-annotations")
    validate_schema(requirements, "engineering-model/v1/engineering-requirements")
    foreign = sorted({entry["domain"] for entry in (*requirements["reference_values"], *requirements["requirements"])}
                     - {adapter.domain})
    if foreign:
        # Each sample's requirements are compiled by its primary domain's adapter;
        # a requirement of another domain waits for cross-domain rules.
        raise ValueError(f"{item.item_id}: requirements for {', '.join(foreign)} cannot be compiled by the "
                         f"{adapter.domain} adapter")
    adapter.check_requirements(requirements)

    extraction = adapter.extract(item.root, item.sources, annotations, {
        "sample": item.repo_relative(item.root),
        "annotations": item.repo_relative(item.path(ANNOTATIONS)),
        "annotations_sha256": _sha256(annotations_bytes),
    })
    validate_schema(extraction.model, "engineering-model/v1/engineering-model")
    lineage = lineage_problems(extraction.model)
    if lineage:
        # An annotated value naming a parent that does not exist, or resting on
        # itself, would leave every result depending on it without inputs.
        raise ValueError(f"{item.item_id}: the model's lineage cannot be followed: " + "; ".join(lineage))
    files: Dict[str, DerivedFile] = {derived.path: derived for derived in extraction.files}
    files[MODEL] = DerivedFile(
        path=MODEL, data=_json_bytes(extraction.model), role="engineering_model", media_type="application/json",
        producer="ecad_model.builder", version=BUILDER_VERSION,
        # The model is derived from the extraction files, or, when an adapter
        # reads its artefacts directly, from the artefacts themselves.
        derived_from=(*([derived.path for derived in extraction.files]
                        or [source.path for source in item.sources if source.format in adapter.formats]),
                      ANNOTATIONS))
    try:
        domain_models = adapter.write_models(extraction.model, item.item_id)
    except MissingInput as exc:
        # Name what is actually missing: a mass with no value rests on a
        # density with no value, and it is the density, with its own status,
        # that someone has to supply.
        found, _ = input_leaves(extraction.model, [entry["path"] for entry in exc.inputs])
        null = {leaf["path"] for leaf in found if is_null(leaf["status"])}
        roots = [leaf for leaf in found if leaf["path"] in null and not null & set(
            resolve(extraction.model, leaf["path"]).get("derived_from", []))]
        raise MissingInput(str(exc), roots or exc.inputs) from exc
    for derived in domain_models:
        files[derived.path] = derived
    golden, corners, blocked = compile_cases(extraction.model, requirements, adapter.case_target(item.item_id),
                                             adapter.reference_value, adapter.metrics())
    for path, document, role in ((GOLDEN, golden, "golden_cases"), (CORNERS, corners, "corner_cases")):
        if not document["cases"]:
            continue  # the contract has no empty case document; a missing one is BLOCKED, as it should be
        files[path] = DerivedFile(
            path=path, data=_json_bytes(document), role=role, media_type="application/json",
            producer="ecad_model.requirements", version=COMPILER_VERSION, derived_from=(MODEL, REQUIREMENTS))
    return Derivation(adapter, extraction, files, blocked)


def _provenance(item: Item) -> Dict[str, Any]:
    """The sample's hand-authored provenance. Its absence stops everything: a
    licence the builder filled in would be a licence nobody checked, and the
    provenance is where the sample declares its domain and sources."""
    if not os.path.lexists(item.path(PROVENANCE)):
        raise ValueError(f"{item.item_id}: {PROVENANCE} is missing; licence and origin are never assumed")
    document = json.loads(item.read(PROVENANCE))
    validate_schema(document, "cad-dataset/v1/source-provenance")
    return document


def _simulation_digest(item: Item, simulation: List[str]) -> str:
    """One digest over the committed simulation scripts: the spec's simulation_version.

    It is the version of what this sample runs, never the simulator's own
    version, which belongs to a run and is recorded in its receipt.
    """
    lines = "".join(f"{path}\0{_sha256(item.read(path))}\n" for path in simulation)
    return f"sha256:{_sha256(lines.encode('utf-8'))}"


def _content_hash(item: Item) -> str:
    """The spec's sample hash: every file git lists for the item except the manifest itself."""
    from ecad_validation.hashing import hash_tree

    return f"sha256:{hash_tree(item.root, [path for path in item.files() if path != item.path(MANIFEST)])}"


def _item_manifest(item: Item, derivation: Derivation, registry: Optional[Dict[str, DomainAdapter]] = None) -> Dict[str, Any]:
    model = derivation.model
    provenance = item.provenance
    simulation = derivation.adapter.simulation_files(item.root)
    origin: Dict[str, Any] = dict(provenance["origin"])
    if "generator" in provenance:
        origin["generator"] = _artifact(item, provenance["generator"])
    return {
        "$schema": ITEM_SCHEMA,
        "dataset_item_version": MANIFEST_VERSION,
        "item_id": item.item_id,
        "domain": item.domain,
        "source_url": provenance["origin"].get("url"),
        "title": model["design"]["name"],
        "description": provenance["description"],
        "artifact_type": provenance["artifact_type"],
        "artifact_version": provenance["artifact_version"],
        "units": provenance["units"],
        "coordinate_system": provenance["coordinate_system"],
        "created_at": provenance["created_at"],
        "collected_at": provenance["collected_at"],
        "hash": _content_hash(item),
        "versions": {
            "extraction": ", ".join(f"{d.producer} {d.version}" for d in derivation.extraction.files) or "none",
            "engineering_model": BUILDER_VERSION,
            "domain_models": {derivation.adapter.domain: ", ".join(
                f"{d.producer} {d.version}" for d in derivation.files.values() if d.role == "domain_model") or "none"},
            "simulation": _simulation_digest(item, simulation),
            "validation_contract": "hardware-validation v1.0.0",
        },
        "source": {
            "artifacts": [{**_artifact(item, source.path), "format": source.format} for source in item.sources],
            "origin": origin,
            "license": dict(provenance["license"]),
        },
        "inputs": {
            "provenance": _artifact(item, PROVENANCE),
            "annotations": _artifact(item, ANNOTATIONS),
            "requirements": _artifact(item, REQUIREMENTS),
            "simulation": [_artifact(item, path) for path in simulation],
        },
        "derived": [
            {
                "role": derived.role,
                # Files the domain adapter produced name their domain; the
                # engineering model and the compiled cases are shared.
                **({"domain": derivation.adapter.domain} if derived.role in ("extraction", "domain_model") else {}),
                "artifact": _artifact(item, path, derived.data, derived.media_type),
                "producer": {"tool": derived.producer, "version": derived.version},
                "derived_from": list(derived.derived_from),
            }
            for path, derived in derivation.files.items()
        ],
        "domains": domain_status(item.domain, item.sources, model["unknowns"], registry),
    }


def build(directory: Path, registry: Optional[Dict[str, DomainAdapter]] = None) -> List[str]:
    """Write every derived file and dataset-item.json from the item's inputs.

    Args:
        directory: The dataset item directory.
        registry: Domain adapters to use in place of the platform's (tests only).

    Returns:
        The item-relative paths written.

    Raises:
        ValueError: An input violates its schema, extraction failed, or no
            adapter is registered for the item's domain.

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
    derivation = _derive(item, registry)
    for relative, data in derivation.data().items():
        _write_inside(item, relative, data)
    for relative, _gate, _name in CASE_DOCUMENTS:
        if relative not in derivation.files and os.path.lexists(item.path(relative)):
            # The requirements now compile to no case of this gate. A committed
            # document left behind would still be executed by validate.
            regular_file(item.path(relative))
            item.path(relative).unlink()
    manifest = _item_manifest(item, derivation, registry)
    validate_schema(manifest, "cad-dataset/v1/dataset-item")
    _write_inside(item, MANIFEST, _json_bytes(manifest))
    return [*derivation.files, MANIFEST]


def _refuse_symlinks(item: Item) -> None:
    """Refuse an item that contains any symlink, before anything is read or written.

    Git tracks symlinks. One inside an item can redirect a read to a file the
    hashes do not cover, or a build's write to any file the user can modify.
    """
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
    manifest = json.loads(item.read(MANIFEST))
    inputs = manifest["inputs"]
    recorded = [*manifest["source"]["artifacts"], inputs["provenance"], inputs["annotations"], inputs["requirements"],
                *inputs["simulation"]]
    if "generator" in manifest["source"]["origin"]:
        recorded.append(manifest["source"]["origin"]["generator"])
    recorded += [entry["artifact"] for entry in manifest["derived"]]
    problems = []
    committed = {item.item_relative(path) for path in item.files()} - {MANIFEST}
    unrecorded = sorted(committed - {artifact["path"] for artifact in recorded})
    if unrecorded:
        problems.append(f"files not recorded in {MANIFEST}: " + ", ".join(unrecorded))
    for artifact in recorded:
        relative = Path(artifact["path"])
        path = item.path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(item.root):
            # The manifest is untrusted input. Reading a path it names outside
            # the item would make check a hash oracle for any file on the host.
            problems.append(f"{artifact['path']}: recorded in {MANIFEST} outside the item; it is not read")
            continue
        if not path.is_file():
            problems.append(f"{artifact['path']}: recorded in {MANIFEST} but missing")
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


def reproducibility(item: Item, derived: Optional[Derivation] = None) -> List[str]:
    """Rebuilding from the sources must reproduce every committed derived file.

    Each file is compared the way its producer declared: JSON numbers within
    tolerance, an XML domain model exactly outside its numeric attributes, or
    the bytes exactly.

    Args:
        item: The dataset item.
        derived: A derivation already computed for this item, to avoid
            extracting the sources twice.

    Returns:
        One message per divergence beyond the numeric tolerance; empty when
        the committed derivation reproduces.

    Example:
        >>> reproducibility(Item(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"))
        []
    """
    problems = []
    derivation = _derive(item) if derived is None else derived
    for relative, _gate, _name in CASE_DOCUMENTS:
        if relative not in derivation.files and os.path.lexists(item.path(relative)):
            problems.append(f"{relative}: committed, but a fresh derivation compiles no such document")
    for relative, fresh in derivation.files.items():
        path = item.path(relative)
        if not path.is_file():
            problems.append(f"{relative}: derived file is not committed")
            continue
        committed = item.read(relative)
        try:
            if fresh.comparator == "json":
                problems += same_content(json.loads(committed), json.loads(fresh.data), relative)
            elif fresh.comparator == "numeric_attributes":
                problems += same_text(committed.decode("utf-8"), fresh.data.decode("utf-8"), relative)
            elif committed != fresh.data:
                problems.append(f"{relative}: bytes differ from a fresh derivation")
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
            problems.append(f"{relative}: the committed file cannot be read as its producer wrote it: {exc}")
    return problems


def _without_derived_hashes(manifest: Dict[str, Any]) -> Dict[str, Any]:
    stripped = json.loads(json.dumps(manifest))
    for entry in stripped["derived"]:
        entry["artifact"].pop("sha256")
        entry["artifact"].pop("size_bytes")
    return stripped


def manifest_problems(item: Item, derived: Optional[Derivation] = None,
                      registry: Optional[Dict[str, DomainAdapter]] = None) -> List[str]:
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
    fresh = _item_manifest(item, _derive(item, registry) if derived is None else derived, registry)
    try:
        committed = _without_derived_hashes(json.loads(item.read(MANIFEST)))
    except ValueError as exc:
        return [f"{MANIFEST}: not valid JSON: {exc}"]
    except (KeyError, TypeError, AttributeError) as exc:
        return [f"{MANIFEST}: does not have the shape build writes ({type(exc).__name__}: {exc})"]
    return same_content(committed, _without_derived_hashes(fresh), MANIFEST)


def cited_source_problems(item: Item) -> List[str]:
    """Every file an annotation cites by hash, and the licence text, must still have that hash.

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
    problems: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            origin = node.get("source") if {"value", "status", "source"} <= node.keys() else None
            if isinstance(origin, dict) and "sha256" in origin:
                problem = _citation_problem("cited source", origin["ref"], origin["sha256"])
                if problem:
                    problems.append(problem)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(item.read(ANNOTATIONS)))
    licence = item.provenance["license"].get("license_text")
    if licence:
        problem = _citation_problem("licence text", licence["path"], licence["sha256"])
        if problem:
            problems.append(problem)
    return sorted(set(problems))


def _citation_problem(what: str, ref: str, sha256: str) -> Optional[str]:
    """Why a file cited by hash does not hold: outside the repository (not
    read), missing, not a regular file, or changed since it was cited."""
    path = (REPOSITORY_ROOT / ref).resolve()
    if not path.is_relative_to(REPOSITORY_ROOT):
        return f"{what} {ref} lies outside the repository; it is not read"
    if not path.exists():
        return f"{what} {ref} does not exist"
    try:
        regular_file(path)
    except UnsupportedFormat as exc:
        return f"{what} {ref}: {exc}"
    if _sha256(path.read_bytes()) != sha256:
        return f"{what} {ref} has changed since it was cited"
    return None


def check(directory: Path, registry: Optional[Dict[str, DomainAdapter]] = None) -> List[str]:
    """All integrity and reproducibility problems of an item.

    Args:
        directory: The dataset item directory.
        registry: Domain adapters to use in place of the platform's (tests only).

    Returns:
        Problems as messages; empty when every hash matches and every derived
        file reproduces from the sources.

    Example:
        >>> check(REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")
        []
    """
    item = Item(directory)  # refuses a symlinked item before reading it
    # An item git cannot enumerate is refused before a native parser runs on it.
    item.files()
    derived = _derive(item, registry)
    return (integrity(item) + cited_source_problems(item) + reproducibility(item, derived)
            + manifest_problems(item, derived, registry))


def _reference_problems(item: Item, model: Dict[str, Any], requirements: Dict[str, Any]) -> List[str]:
    """Domain-neutral V2 invariants: every reference in the model and requirements resolves."""
    problems = []
    ids = {c["component_id"] for c in model["components"]} | {j["joint_id"] for j in model["joints"]}
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
    declared = {(artifact.path, artifact.format) for artifact in item.sources}
    for source in model["design"]["sources"]:
        path = REPOSITORY_ROOT / source["path"]
        if not path.is_relative_to(item.root) or source["sha256"] != _sha256(item.read(item.item_relative(path))):
            problems.append(f"the engineering model was derived from different bytes of {source['path']}")
        elif (item.item_relative(path), source["format"]) not in declared:
            problems.append(f"the engineering model names {source['path']} as {source['format']}, "
                            "which the provenance does not declare")
    if model["unknowns"] != index_unknowns(model):
        problems.append("the unknowns index is stale")
    return problems


# --- V0-V4 -------------------------------------------------------------------------

def validate(directory: Path, output: Path, registry: Optional[Dict[str, DomainAdapter]] = None) -> Dict[str, Any]:
    """Run V0-V4 on a dataset item and write a v1 receipt plus evidence.

    Nothing is PASS without hash-bound evidence, and anything that depends on
    a value with a null status is BLOCKED with the missing paths.

    Args:
        directory: The dataset item directory.
        output: A missing or empty directory for receipt.json, evidence/,
            evidence-index.json, results.json and report.md.
        registry: Domain adapters to use in place of the platform's (tests only).

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
    from ecad_validation.contract import validate_document
    from ecad_validation.engine import repository_state
    from ecad_validation.models import (
        CheckResult, Domain, EvidenceReference, ExecutionStatus, GateLevel, GateResult, Layer,
        ProductRunResult, Verdict,
    )

    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    from ecad_validation.hashing import hash_tree

    item = Item(directory)  # refuses a symlinked item before anything is read
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

    source_paths = [source.path for source in item.sources]
    inputs = [*source_paths, ANNOTATIONS, REQUIREMENTS, MANIFEST]
    try:
        adapter: Optional[DomainAdapter] = adapter_for(item.domain, registry)
    except DomainNotImplemented:
        adapter = None
    domain = item.domain

    # V0: every document conforms to its schema and every hash is exact.
    v0_problems = []
    for relative, schema in (
        (MANIFEST, "cad-dataset/v1/dataset-item"),
        (ANNOTATIONS, "engineering-model/v1/design-annotations"),
        (REQUIREMENTS, "engineering-model/v1/engineering-requirements"),
        *((adapter.document_schemas() if adapter else {}).items()),
        (MODEL, "engineering-model/v1/engineering-model"),
    ):
        try:
            validate_schema(json.loads(item.read(relative)), schema)
        except (OSError, ValueError) as exc:
            v0_problems.append(f"{relative}: {exc}")
    for problems_of in (integrity, cited_source_problems):
        try:
            v0_problems += problems_of(item)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            v0_problems.append(f"{problems_of.__name__}: {type(exc).__name__}: {exc}")
    v0 = [result("v0.dataset-schemas-and-hashes", GateLevel.V0, Domain.DATA_MANAGEMENT, Layer.DESIGN, v0_problems,
                 inputs, "DATASET_SCHEMAS_VALID", "DATASET_SCHEMA_OR_HASH_INVALID",
                 "every dataset document conforms to its schema and every recorded hash matches")]

    # V1: the sources re-extract, and what they yield passes the domain's sanity checks.
    v1_id = f"v1.{domain}.extraction-and-sanity"
    failure: Optional[Tuple[Any, Any, str, str]] = None
    fresh: Optional[Derivation] = None
    v1_problems: List[str] = []
    v1_findings: List[str] = []
    if adapter is None:
        # Nothing here can read this domain's artefacts. Decided before any
        # derivation runs, so no error raised while deriving can pose as it.
        failure = (ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED, "DOMAIN_NOT_IMPLEMENTED",
                   f"the {domain} domain is NOT_IMPLEMENTED in this platform")
        v1_findings = [f"no {domain} adapter is registered in this platform"]
    else:
        try:
            fresh = _derive(item, registry)
            v1_problems = adapter.sanity_problems(fresh.model)
        except ExtractionError as exc:
            failure = {
                "rejected": (ExecutionStatus.COMPLETED, Verdict.FAIL, "SOURCE_REJECTED", "the source was read and refused on its content"),
                "crashed": (ExecutionStatus.CRASHED, Verdict.INCONCLUSIVE, "EXTRACTION_CRASHED", "the parser died or produced no result"),
                "timed_out": (ExecutionStatus.TIMED_OUT, Verdict.INCONCLUSIVE, "EXTRACTION_TIMED_OUT", "the parser exceeded its time limit"),
                "unavailable": (ExecutionStatus.UNAVAILABLE, Verdict.BLOCKED, "EXTRACTOR_UNAVAILABLE", "the parser the domain needs is not installed here"),
            }[exc.kind]
            v1_findings = [str(exc)]
        except MissingInput as exc:
            # A value nobody has recorded is a missing input, not a design defect.
            failure = (ExecutionStatus.SKIPPED, Verdict.BLOCKED, "MISSING_REQUIRED_INPUT",
                       f"a value the {domain} model needs has no value")
            v1_findings = [f"{entry['status']}: {entry['path']}" for entry in exc.inputs] or [str(exc)]
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            # A schema-invalid input or an inconsistent annotation: the item is
            # wrong. The item is untrusted input, so an error it provokes in the
            # builder or the adapter is recorded here, never raised past the receipt.
            failure = (ExecutionStatus.COMPLETED, Verdict.FAIL, "DATASET_INPUT_INVALID", "the item's inputs cannot be built into a model")
            v1_findings = [str(exc) if isinstance(exc, (OSError, ValueError)) else f"{type(exc).__name__}: {exc}"]
    v1_blocked = "; ".join(v1_findings) if failure else None
    contract_domain = Domain(CONTRACT_DOMAIN[domain])
    if failure is None:
        v1 = [result(v1_id, GateLevel.V1, contract_domain, Layer.MODEL,
                     v1_problems, [*source_paths, ANNOTATIONS], "DOMAIN_SANITY_PASSED", "DOMAIN_SANITY_FAILED",
                     f"the sources re-extract and the {domain} model is physically possible")]
    else:
        status, verdict, reason, summary = failure
        refs, extra = generated(v1_id, {"failure": v1_blocked})
        v1 = [CheckResult(check_id=v1_id, gate=GateLevel.V1,
                          domain=contract_domain, layer=Layer.MODEL,
                          execution_status=status, verdict=verdict, reason_code=reason, summary=summary,
                          findings=v1_findings or [summary], evidence=[*evidence(*source_paths), *refs],
                          generated_evidence=extra)]

    # The requirements say what V3/V4 must contain. They are untrusted input
    # too: when they cannot be read, V0 has already said why, and V3/V4 each
    # record one BLOCKED check instead of the run stopping.
    requirements: Dict[str, Any] = {"reference_values": [], "requirements": []}
    requirements_problem: Optional[str] = None
    try:
        document = json.loads(item.read(REQUIREMENTS))
        validate_schema(document, "engineering-model/v1/engineering-requirements")
        requirements = document
    except (OSError, ValueError) as exc:
        requirements_problem = f"{REQUIREMENTS}: {exc}"

    # V2: the committed derivation reproduces and every reference resolves (any
    # domain), and the domain model is consistent with the engineering model.
    if fresh is not None and adapter is not None:
        derived_paths = list(fresh.files)
        v2 = [
            result("v2.dataset-reproduction", GateLevel.V2, Domain.DATA_MANAGEMENT, Layer.VALIDATION,
                   reproducibility(item, fresh) + manifest_problems(item, fresh, registry)
                   + _reference_problems(item, fresh.model, requirements),
                   [*source_paths, ANNOTATIONS, REQUIREMENTS, *derived_paths],
                   "DERIVATION_REPRODUCED", "DERIVATION_DIVERGED",
                   "committed derived files reproduce from the sources and every reference resolves"),
            result(f"v2.{domain}.model-invariants", GateLevel.V2, contract_domain, Layer.VALIDATION,
                   adapter.invariant_problems(
                       fresh.model, {d.path: json.loads(d.data) for d in fresh.extraction.files},
                       {path: d.data for path, d in fresh.files.items() if d.role == "domain_model"}),
                   [MODEL, *(path for path, d in fresh.files.items() if d.role in ("extraction", "domain_model"))],
                   "DOMAIN_MODEL_CONSISTENT", "DOMAIN_MODEL_INCONSISTENT",
                   f"the {domain} domain model is consistent with the engineering model"),
        ]
    else:
        v2 = [CheckResult(check_id=check_id, gate=GateLevel.V2, domain=check_domain,
                          layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE,
                          verdict=Verdict.BLOCKED, reason_code="DERIVATION_NOT_AVAILABLE",
                          summary="V2 needs a fresh derivation from the sources, which V1 could not produce",
                          findings=[v1_blocked or "derivation unavailable"], evidence=evidence(*source_paths))
              for check_id, check_domain in (("v2.dataset-reproduction", Domain.DATA_MANAGEMENT),
                                             (f"v2.{domain}.model-invariants", contract_domain))]

    gates: Dict[Any, List[Any]] = {GateLevel.V0: v0, GateLevel.V1: v1, GateLevel.V2: v2}
    entries = {GateLevel.V3: [(r["reference_id"], r) for r in requirements["reference_values"]],
               GateLevel.V4: [(r["requirement_id"], r) for r in requirements["requirements"]]}
    policy = {GateLevel.V3: "POLICY:V3-GOLDEN", GateLevel.V4: "POLICY:V4-CORNER"}
    all_ids = [entry_id for level in entries for entry_id, _ in entries[level]]

    def gate_check(level: Any, reason: str, summary: str, finding: str) -> Any:
        """The one BLOCKED check that stands in for a whole gate's cases."""
        name = "golden" if level is GateLevel.V3 else "corners"
        return CheckResult(
            check_id=f"{level.value.lower()}.{name}-cases", gate=level, domain=Domain.DATA_MANAGEMENT,
            layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
            reason_code=reason, summary=summary, requirement_ids=[policy[level]],
            findings=[finding], evidence=evidence(REQUIREMENTS))

    def not_evaluated(level: Any, reason: str, finding: str) -> List[Any]:
        """V3/V4 when nothing can be compiled: each requirement BLOCKED with the reason,
        or one gate-level check when there is none to name (or its ids collide)."""
        if entries[level] and requirements_problem is None and len(set(all_ids)) == len(all_ids):
            return [CheckResult(
                check_id=f"{level.value.lower()}.{entry_id}", gate=level, domain=Domain(CONTRACT_DOMAIN[entry["domain"]]),
                layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
                reason_code=reason, summary=f"{entry_id} was not evaluated: nothing was compiled for it",
                requirement_ids=[policy[level], entry_id], findings=[finding], evidence=evidence(REQUIREMENTS))
                for entry_id, entry in entries[level]]
        return [gate_check(level, reason, "no case of this gate was evaluated", finding)]

    if fresh is None or requirements_problem is not None:
        # Nothing was derived, so nothing committed can be trusted to implement
        # the requirements: running its cases would report a verdict on a model
        # V1 could not reproduce, for a domain V1 may call NOT_IMPLEMENTED.
        finding = requirements_problem or f"V1 did not derive a model: {v1_blocked}"
        for level in (GateLevel.V3, GateLevel.V4):
            gates[level] = not_evaluated(level, "DERIVATION_NOT_AVAILABLE", finding)
    else:
        assert adapter is not None
        committed_model, model_problem = _committed_model(item)
        if committed_model is None:
            # The committed cases were compiled from a model that is not there,
            # or not a valid model, to establish their inputs; V0 and V2 say why.
            for level in (GateLevel.V3, GateLevel.V4):
                gates[level] = not_evaluated(
                    level, "DERIVED_MODEL_NOT_COMMITTED" if not item.path(MODEL).is_file() else "COMMITTED_MODEL_INVALID",
                    model_problem or MODEL)
        else:
            for level in (GateLevel.V3, GateLevel.V4):
                gates[level] = _run_cases(item, level, fresh, adapter, committed_model, requirements,
                                          generated, evidence, gate_check)

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
    # Where the run happens is recorded here, bound into the receipt, so the
    # per-requirement results describe this run and not whoever regenerates them.
    constraints = REPOSITORY_ROOT / "tools" / "constraints-cad.txt"
    refs, extra = generated("v0.pinned-clean-source", {
        "commit": commit, "dirty": dirty,
        "environment": run_environment(constraints.read_bytes() if constraints.is_file() else None)})
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
            "tool_id": "ecad-validator", "name": "eCAD dataset validator", "version": VALIDATOR_VERSION,
            "invocation": ["python3", "tools/cad_dataset.py", "validate", item.repo_relative(item.root),
                           "--output", "<output directory>"],
            # The output path is host-specific; recording it would break portability.
            "settings": {"redacted_arguments": ["--output"]},
        },
    }
    if fresh is not None:
        for tool in fresh.extraction.tools:
            tools[tool["tool_id"]] = tool
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
    _write_run(item, output, product, receipt, None if requirements_problem else requirements, adapter)
    return receipt


def _committed_model(item: Item) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The committed engineering model, if it is there and valid.

    The committed cases ran on it, and the results read their inputs from
    it, so a model that does not parse or does not conform to its schema is
    used for neither.

    Returns:
        (model, None), or (None, why it cannot be used).
    """
    try:
        model = json.loads(item.read(MODEL))
        validate_schema(model, "engineering-model/v1/engineering-model")
    except (OSError, ValueError) as exc:
        return None, f"{MODEL}: {exc}"
    return model, None


def _run_cases(item: Item, level: Any, fresh: Derivation, adapter: DomainAdapter, committed_model: Dict[str, Any],
               requirements: Dict[str, Any], generated: Any, evidence: Any, gate_check: Any) -> List[Any]:
    """One gate's checks on a fresh derivation: exactly one per reference or
    requirement of the gate, plus any gate-level check the case engine reports.

    The committed case document is what runs -- its bytes are the evidence --
    but the fresh derivation says what it must contain. Where they disagree
    (inputs edited without a rebuild; V2 reports the divergence) the fresh
    derivation wins:

    - a document the fresh derivation no longer produces is not run at all;
    - a committed case for an entry the fresh derivation blocks is not
      counted, and the entry is BLOCKED as the fresh derivation says;
    - a committed case for an entry the fresh derivation does not compile is
      not counted;
    - an entry the fresh derivation compiles but the document lacks is
      BLOCKED with COMMITTED_CASE_MISSING.

    Then each executed check's inputs decide first (results.propagate), in
    V3 and V4 alike, and an illustrative limit met is a WARNING.
    """
    from ecad_validation.cases import execute_cases
    from ecad_validation.models import CheckResult, Domain, ExecutionStatus, GateLevel, Layer, Verdict

    relative, _gate, name = CASE_DOCUMENTS[0] if level is GateLevel.V3 else CASE_DOCUMENTS[1]
    policy = f"POLICY:{level.value}-{'GOLDEN' if level is GateLevel.V3 else 'CORNER'}"
    gate_level_ids = {f"{name}-cases", f"{name}-manifest"}
    compiled = ({case["id"] for case in json.loads(fresh.files[relative].data)["cases"]}
                if relative in fresh.files else set())
    blocked = {entry["id"]: entry for entry in fresh.blocked if entry["gate"] == level.value}
    try:
        committed_ids = {case["id"] for case in json.loads(item.read(relative))["cases"]
                         if isinstance(case, dict) and "id" in case} if os.path.lexists(item.path(relative)) else set()
    except (OSError, ValueError, KeyError, TypeError):
        committed_ids = set()
    # A committed case the fresh derivation blocks, or does not compile, is
    # stale: it is not counted, whether or not its document ran.
    stale = committed_ids & set(blocked)
    if relative in fresh.files:
        checks = [check for check in execute_cases(item.root, level, name)
                  if check.check_id.split(".", 1)[1] in compiled | gate_level_ids]
        for check in checks:
            if not check.evidence and check.verdict is not Verdict.BLOCKED:
                # The case engine reports a document it cannot parse as FAIL
                # without citing it, which the receipt contract forbids; the
                # document itself is the evidence.
                check.evidence = evidence(relative)
    else:
        checks = [gate_check(level, f"{name.upper()}_EVIDENCE_MISSING", f"no {name} case was compiled",
                             f"the requirements compile to no {name} case")]
    owners = {entry.get("requirement_id", entry.get("reference_id")): entry
              for entry in [*requirements["requirements"], *requirements["reference_values"]]}
    by_reference = {entry["reference_id"]: entry for entry in requirements["reference_values"]}
    by_requirement = {entry["requirement_id"]: entry for entry in requirements["requirements"]}
    illustrative_ids = {entry["requirement_id"] for entry in requirements["requirements"] if entry["illustrative"]}
    for check_result in checks:
        case_id = check_result.check_id.split(".", 1)[1]
        if case_id in owners:
            check_result.requirement_ids = [*check_result.requirement_ids, case_id]
        # The inputs decide first (results.propagate): a null-status input
        # blocks the check, one that does not resolve makes it INCONCLUSIVE,
        # and an AI_ASSUMPTION withholds the comparator's verdict on a
        # requirement (a reference's comparison is not a verdict on the design).
        try:
            if level is GateLevel.V4 and case_id in by_requirement:
                requirement = by_requirement[case_id]
                paths = adapter.dependencies(committed_model, requirement["metric"], requirement["scenario"]) + (
                    [requirement["limit"]["quantity"]] if "quantity" in requirement["limit"] else [])
            elif level is GateLevel.V3 and case_id in by_reference:
                reference = by_reference[case_id]
                paths = adapter.reference_inputs(committed_model, reference["derivation"], reference["scenario"])
            else:
                paths = None
            if paths is not None:
                found, unresolved = input_leaves(committed_model, paths)
                changed = propagate(found, unresolved, check_result.verdict.value, check_result.reason_code)
            else:
                changed = None
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            changed = propagate([], [f"{type(exc).__name__}: {exc}"], check_result.verdict.value,
                                check_result.reason_code)
        if changed:
            verdict, reason, findings = changed
            check_result.verdict, check_result.reason_code = Verdict(verdict), reason
            check_result.summary = f"{check_result.summary}; the inputs make it {verdict}"
            check_result.findings = [*findings, *check_result.findings]
        if case_id in illustrative_ids and check_result.verdict is Verdict.PASS:
            # Meeting a limit invented to exercise the pipeline qualifies
            # nothing. The contract's WARNING is advisory and cannot satisfy
            # a required check, so such a sample is never eligible for ebuild.
            check_result.verdict = Verdict.WARNING
            check_result.reason_code = "WITHIN_ILLUSTRATIVE_LIMIT"
            check_result.summary = "within an illustrative limit, which is not a qualification"
            check_result.findings = [*check_result.findings,
                                     f"{case_id} is illustrative: not a customer, safety or certification requirement"]
    executed = {check.check_id.split(".", 1)[1] for check in checks}
    for entry_id in sorted(compiled - executed):
        # The requirements compile to this case; the committed document does
        # not hold it, so nothing ran for it.
        checks.append(CheckResult(
            check_id=f"{level.value.lower()}.{entry_id}", gate=level,
            domain=Domain(CONTRACT_DOMAIN[owners[entry_id]["domain"]]), layer=Layer.VALIDATION,
            execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
            reason_code="COMMITTED_CASE_MISSING",
            summary=f"{relative} has no case for {entry_id}, which the requirements compile to",
            requirement_ids=[policy, entry_id],
            findings=[f"{relative} has no case {entry_id}; rebuild the item (V2 reports the divergence)"],
            evidence=evidence(REQUIREMENTS, relative)))
    for entry_id, entry in blocked.items():
        refs, extra = generated(f"{level.value.lower()}.{entry_id}", entry)
        findings = [f"{m['status']}: {m['path']}" for m in entry["missing_inputs"]] or [entry["reason"]]
        if entry_id in stale:
            findings.append(f"{relative} still holds a case {entry_id}, compiled before; it was not counted")
        checks.append(CheckResult(
            # A blocked check takes the contract domain of the requirement or
            # reference it implements.
            check_id=f"{level.value.lower()}.{entry_id}", gate=level,
            domain=Domain(CONTRACT_DOMAIN[owners[entry_id]["domain"]]),
            layer=Layer.VALIDATION, execution_status=ExecutionStatus.UNAVAILABLE, verdict=Verdict.BLOCKED,
            # spec: a missing required input is BLOCKED with MISSING_REQUIRED_INPUT; a
            # reference whose derivation does not apply to the design has no missing input.
            reason_code="MISSING_REQUIRED_INPUT" if entry["missing_inputs"] else "REFERENCE_NOT_APPLICABLE",
            summary=entry["reason"], requirement_ids=[policy, entry_id], findings=findings,
            evidence=[*evidence(REQUIREMENTS, MODEL), *refs], generated_evidence=extra,
        ))
    return checks


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
        >>> _tool_record("simulator", [a, b])["invocation"]
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
               requirements: Optional[Dict[str, Any]], adapter: Optional[DomainAdapter]) -> None:
    """Write content-addressed evidence, the receipt and its evidence index, then the results and the report.

    The receipt and evidence index are contract documents, so they follow the
    contract's serialisation rule exactly: canonical JSON (sorted keys,
    compact separators) plus one final LF, hashed as stored. They are written
    before the results are built from the stored evidence, so nothing the
    results do can cost the run its receipt. When no results can be built,
    the report says why.
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
    evidence_index = {
        "$schema": "https://embeddedos.org/schemas/hardware-validation/v1/evidence-index.schema.json",
        "contract_version": receipt["contract_version"],
        "product_id": receipt["product"]["id"],
        "receipt_sha256": _sha256(receipt_bytes),
        "generated_at": product.completed_at,
        "evidence": index,
    }
    validate_document(REPOSITORY_ROOT, "evidence-index.schema.json", evidence_index)
    (output / "receipt.json").write_bytes(receipt_bytes)
    (output / "evidence-index.json").write_bytes(canonical(evidence_index))
    document: Optional[Dict[str, Any]] = None
    why = _no_results_reason(item, adapter, requirements)
    if why is None:
        try:
            document = _results(item, adapter, receipt, receipt_bytes, requirements, output)
        except Exception as exc:
            # A defect in the results generator, not in the item: the receipt
            # stands, the report says what failed, and the error is raised.
            (output / "report.md").write_text(
                _report(receipt, None, f"generating them failed: {type(exc).__name__}: {exc}"), encoding="utf-8")
            raise
        (output / "results.json").write_bytes(canonical(document))
    (output / "report.md").write_text(_report(receipt, document["results"] if document else None, why or ""),
                                      encoding="utf-8")


def _no_results_reason(item: Item, adapter: Optional[DomainAdapter], requirements: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why a run can have no per-requirement results, or None when it can."""
    if adapter is None:
        return f"no {item.domain} adapter is registered, so no requirement could be evaluated"
    if requirements is None:
        return f"{REQUIREMENTS} could not be read"
    model, problem = _committed_model(item)
    if model is None:
        return f"the committed engineering model cannot be used ({problem})"
    return None


def _stored_evidence(output: Path, reference: Dict[str, Any]) -> bytes:
    """The bytes of one piece of a run's stored evidence, verified.

    A run directory may be handed over from elsewhere, so what its receipt
    says is not trusted to name a safe file: the path must be exactly the
    content address of the recorded digest, the file must be a regular file
    within the size limit, and its bytes must have that digest.

    Raises:
        ValueError: The path is not the content address, or the bytes differ.
        UnsupportedFormat: Not a regular file, or too large.
        OSError: The file does not exist.
    """
    expected = f"evidence/sha256/{reference['sha256']}"
    if reference["path"] != expected:
        raise ValueError(f"evidence {reference['evidence_id']}: {reference['path']!r} is not its content address {expected}")
    path = output / expected
    regular_file(path)
    data = path.read_bytes()
    if _sha256(data) != reference["sha256"]:
        raise ValueError(f"evidence {expected}: bytes do not match the digest the receipt records")
    return data


def _results(item: Item, adapter: DomainAdapter, receipt: Dict[str, Any], receipt_bytes: bytes,
             requirements: Dict[str, Any], output: Path) -> Dict[str, Any]:
    """The run's per-requirement results, from its receipt and stored evidence.

    The case documents, each check's execution record and the run's
    environment are read from the evidence store, verified by digest; the
    engineering model and requirements are the item's, which the caller
    ensures are the ones the run validated (validate() by running, and
    regenerate_results() by comparing the item's digest with the receipt's).
    """
    from .requirements import CASES_SCHEMA

    cases: Dict[Tuple[str, str], Dict[str, Any]] = {}
    executions: Dict[str, Dict[str, Any]] = {}
    recorded: Optional[Dict[str, Any]] = None
    for gate in receipt["gates"]:
        for check in gate["checks"]:
            for reference in check["evidence"]:
                data = _stored_evidence(output, reference)
                try:
                    record = json.loads(data)
                except ValueError:
                    continue  # not JSON: a source file or a domain model
                if not isinstance(record, dict):
                    continue
                if record.get("$schema") == CASES_SCHEMA and gate["gate"] in ("V3", "V4"):
                    # The case document this check ran, as it was run.
                    for case in record.get("cases", []):
                        if isinstance(case, dict) and "id" in case:
                            cases[(record.get("gate"), case["id"])] = case
                elif record.get("case_id") == check["check_id"].split(".", 1)[1] and "tool_version" in record:
                    executions[check["check_id"]] = record
                elif check["check_id"] == "v0.pinned-clean-source" and isinstance(record.get("environment"), dict):
                    recorded = record["environment"]
    if recorded is None:
        raise ValueError("the run recorded no environment (v0.pinned-clean-source evidence)")
    if not (all(isinstance(recorded.get(key), str) for key in ("os", "machine", "python"))
            and (recorded.get("constraints_sha256") is None or isinstance(recorded["constraints_sha256"], str))):
        raise ValueError("the run's environment record is malformed")
    model_bytes = item.read(MODEL)
    document = build_results(
        sample_id=item.item_id, receipt=receipt, receipt_sha256=_sha256(receipt_bytes), requirements=requirements,
        model=json.loads(model_bytes), model_sha256=_sha256(model_bytes), adapter=adapter, cases=cases,
        executions=executions, environment_record=environment(recorded, receipt["tools"]),
    )
    validate_schema(document, "engineering-model/v1/validation-results")
    return document


def regenerate_results(directory: Path, output: Path, registry: Optional[Dict[str, DomainAdapter]] = None) -> bytes:
    """Rebuild a finished run's results.json from its receipt and stored evidence.

    Refused unless the item is still exactly what the run validated: its
    input digest must equal the receipt's. Then the results carry no state of
    their own, and this returns the bytes the run wrote, on any machine.

    Args:
        directory: The dataset item the run validated.
        output: The run's output directory, which is untrusted: its receipt
            is schema-checked and every piece of evidence read is verified
            against the digest the receipt records.
        registry: Domain adapters to use in place of the platform's (tests only).

    Returns:
        The results document as canonical JSON bytes.

    Raises:
        ValueError: The item changed since the run, the receipt is invalid or
            for another item, a piece of evidence does not verify or is
            malformed, or the run wrote no results.
        OSError: A file the receipt names is missing.

    Example:
        >>> import tempfile
        >>> item = REPOSITORY_ROOT / "datasets/cad/robotic_joint_001"
        >>> with tempfile.TemporaryDirectory() as scratch:
        ...     _ = validate(item, Path(scratch) / "run")
        ...     regenerate_results(item, Path(scratch) / "run") == (Path(scratch) / "run" / "results.json").read_bytes()
        True
    """
    from ecad_validation.contract import validate_document
    from ecad_validation.hashing import canonical_json_bytes, hash_tree

    item = Item(directory)
    adapter = adapter_for(item.domain, registry)
    receipt_path = output / "receipt.json"
    regular_file(receipt_path)
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    validate_document(REPOSITORY_ROOT, "validation-receipt.schema.json", receipt)
    if receipt["product"]["id"] != f"datasets:{item.item_id}":
        raise ValueError(f"the receipt is for {receipt['product']['id']}, not datasets:{item.item_id}")
    if hash_tree(item.root, item.files()) != receipt["source"]["input_sha256"]:
        raise ValueError(f"{item.item_id} has changed since the run; its results cannot be regenerated from it")
    try:
        requirements: Optional[Dict[str, Any]] = json.loads(item.read(REQUIREMENTS))
        validate_schema(requirements, "engineering-model/v1/engineering-requirements")
    except (OSError, ValueError):
        requirements = None
    why = _no_results_reason(item, adapter, requirements)
    if why is not None:
        raise ValueError(f"the run wrote no results to regenerate: {why}")
    assert requirements is not None
    document = _results(item, adapter, receipt, receipt_bytes, requirements, output)
    return canonical_json_bytes(document) + b"\n"


def _report(receipt: Dict[str, Any], results: Optional[List[Dict[str, Any]]], why: str = "") -> str:
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
    if results is None:
        lines += ["", "## Requirements", "", f"No per-requirement results were written: {why}."]
        return "\n".join(lines) + "\n"
    lines += ["", "## Requirements", "",
              "| Requirement | Kind | Metric | Measured | Verdict | Why |", "|---|---|---|---|---|---|"]
    for row in results:
        measured = "—" if row["measured_value"] is None else f"{row['measured_value']:.6g} {row['unit']}"
        if row["measured_by"] not in (None, row["check_id"]):
            measured += f" (measured by {row['measured_by']})"
        why_row = "; ".join(row["findings"]) or row["reason_code"] or ""
        lines.append(f"| {row['requirement']} | {row['kind']} | `{row['metric']}` | {measured} | "
                     f"{row['status']} | {why_row} |")
    lines += ["", "An illustrative requirement is an example limit chosen to exercise the pipeline, "
              "not a customer, safety or certification requirement. Meeting one is reported WARNING "
              "(WITHIN_ILLUSTRATIVE_LIMIT), never PASS.",
              "Every row's inputs, simulator, evidence and CAD occurrences are in `results.json`."]
    return "\n".join(lines) + "\n"


__all__ = ["Item", "build", "check", "integrity", "regenerate_results", "reproducibility", "same_content", "same_text", "validate"]
