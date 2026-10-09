"""Mirror the openly licensed development-board CAD files into the repository (issue #48).

The database (issue #28) records, for every board, where each design file lives and the
SHA-256 of the bytes that were verified. For the boards whose licence allows
redistribution, this tool keeps an unmodified copy of those exact bytes under
``boards/cad/<vendor>/<board>/`` so that the files survive a vendor moving them.

Three rules decide what is copied, and none of them is negotiable:

1. **Licence first.** Only records with ``licenses.redistribution_allowed`` set to
   ``true`` are mirrored. Unknown is not permission: those boards keep their link and
   digest and nothing else.
2. **The bytes must be the verified bytes.** A payload whose SHA-256 differs from the
   record's ``evidence.sha256`` is refused, so the mirror can never hold something other
   than what the database claims was checked.
3. **The bytes must be a CAD file.** Only files the verifier recorded as a CAD format are
   selected: Eagle, KiCad and Altium sources, Gerber and drill files, STEP, STL and DXF
   models, and archives of them. Schematic PDFs, drawings, BOMs and datasheets are not
   copied; their records keep the link and digest. Each payload is identified again from
   its content, and one that is not CAD, such as a web page or JSON, is refused.

The files are committed as regular files (``.gitattributes`` exempts them from the
repository's LFS rules and from line-ending conversion, so the bytes stay identical).
``check`` also accepts Git LFS pointer files, whose ``oid`` is the SHA-256 of the object,
so the mirror can move to LFS later without the check changing.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devboard_cad.verify import Fetcher, detect_format, is_binary_stl  # noqa: E402

TOOL_ID = "devboard-cad-mirror@0.1.0"
MIRROR_DIR = Path("boards") / "cad"
MANIFEST_PATH = Path("tools") / "devboard_cad" / "mirror-manifest.json"
ATTRIBUTION_NAME = "ATTRIBUTION.md"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"

CAD_FORMATS = frozenset({"eagle", "kicad", "gerber", "excellon", "step", "stl", "dxf"})
DOC_FORMATS = frozenset({"pdf", "csv"})
ALTIUM_SUFFIXES = (".schdoc", ".pcbdoc", ".prjpcb", ".schlib", ".pcblib")
OFFICE_SUFFIXES = (".xls", ".xlsx", ".doc", ".docx")
# Members that make an archive a design bundle rather than a document bundle: Gerber
# layers, Allegro photoplots and drill files, and native ECAD/MCAD sources.
CAD_MEMBER_SUFFIXES = (
    ".gbr", ".ger", ".gbl", ".gtl", ".gbo", ".gto", ".gbs", ".gts", ".gbp", ".gtp",
    ".gko", ".gm1", ".gml", ".g1", ".g2", ".g3", ".g4", ".pho", ".art", ".drl", ".xln",
    ".exc", ".brd", ".sch", ".lbr", ".kicad_pcb", ".kicad_sch", ".kicad_mod", ".step",
    ".stp", ".stl", ".dxf",
) + ALTIUM_SUFFIXES
EXTENSION_FOR_FORMAT = {
    "pdf": ".pdf", "zip": ".zip", "step": ".step", "stl": ".stl", "dxf": ".dxf",
    "gerber": ".gbr", "excellon": ".drl", "csv": ".csv", "eagle": ".xml",
}


# --------------------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------------------

@dataclass
class Source:
    """One verified file of one board, with every format claim it satisfies."""

    record: Dict[str, Any]
    url: str
    sha256: str
    size_bytes: Optional[int]
    captured_at: Optional[str]
    detected: Optional[str] = None
    formats: List[str] = field(default_factory=list)

    @property
    def board_id(self) -> str:
        return str(self.record["board_id"])


def redistributable(record: Dict[str, Any]) -> bool:
    return (record.get("licenses") or {}).get("redistribution_allowed") is True


def recorded_kind(detected: Optional[str], url: str) -> str:
    """``cad`` or ``docs`` from the format the verifier recorded, before any bytes are read.

    The verifier records STEP with its schema, e.g. ``step:AUTOMOTIVE_DESIGN { ... }``, so
    only the part before the colon names the format.
    """
    detected = (detected or "").split(":", 1)[0] or None
    if detected in CAD_FORMATS or detected == "zip":
        return "cad"
    if detected == "ole" and file_name(url, None).lower().endswith(ALTIUM_SUFFIXES):
        return "cad"
    return "docs"


def select(records: Iterable[Dict[str, Any]]) -> List[Source]:
    """Every verified CAD file of every redistributable board, one entry per URL per board."""
    out: List[Source] = []
    for record in records:
        if not redistributable(record):
            continue
        by_url: Dict[str, Source] = {}
        for name, entry in sorted((record.get("files") or {}).items()):
            if not isinstance(entry, dict) or entry.get("available") is not True:
                continue
            evidence = entry.get("evidence") or {}
            url, digest = entry.get("url"), evidence.get("sha256")
            if not url or not digest:
                continue
            if recorded_kind(evidence.get("detected_format"), url) != "cad":
                continue
            source = by_url.get(url)
            if source is None:
                source = Source(record, url, digest, evidence.get("size_bytes"),
                                evidence.get("captured_at"), evidence.get("detected_format"))
                by_url[url] = source
            source.formats.append(name)
        out.extend(by_url.values())
    out.sort(key=lambda s: (s.board_id, s.url))
    return out


# --------------------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------------------

def identify(payload: bytes) -> Optional[str]:
    """Name the payload's format from its bytes, or None when it is not recognised."""
    found = detect_format(payload[:8192])
    if found is None and is_binary_stl(payload):
        return "stl"
    return found


def _zip_members(payload: bytes) -> List[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
    except (zipfile.BadZipFile, OSError):
        return []
    return [n for n in names if not n.startswith("__MACOSX/") and not Path(n).name.startswith("._")]


def category(payload: bytes, filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(category, detected_format)``; category is ``cad``, ``docs`` or None."""
    found = identify(payload)
    lower = filename.lower()
    if found in CAD_FORMATS:
        return "cad", found
    if found in DOC_FORMATS:
        return "docs", found
    if found == "ole":
        if lower.endswith(ALTIUM_SUFFIXES):
            return "cad", "altium"
        if lower.endswith(OFFICE_SUFFIXES):
            return "docs", "office"
        return None, found
    if found == "zip":
        members = _zip_members(payload)
        if not members:
            return None, found
        if any(m.lower().endswith(CAD_MEMBER_SUFFIXES) for m in members):
            return "cad", "zip"
        return "docs", "zip"
    return None, found


# --------------------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._+-]+")


def safe_component(text: str) -> str:
    cleaned = _SAFE.sub("-", text).strip("-.")
    return cleaned or "file"


def board_dir(board_id: str) -> Path:
    vendor, _, board = board_id.partition(":")
    if not board:
        vendor, board = "unknown", board_id
    return MIRROR_DIR / safe_component(vendor.lower()) / safe_component(board.lower())


def file_name(url: str, detected: Optional[str]) -> str:
    """The URL's own file name, made filesystem-safe, with an extension when it has none."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    name = safe_component(Path(path).name) if Path(path).name else "file"
    if not Path(name).suffix and detected in EXTENSION_FOR_FORMAT:
        name += EXTENSION_FOR_FORMAT[detected]
    return name


def plan_paths(sources: Sequence[Source], kinds: Dict[str, Tuple[str, Optional[str]]]) -> Dict[str, Path]:
    """Assign each source a path, adding a digest prefix only when names collide."""
    paths: Dict[str, Path] = {}
    taken: Dict[Path, str] = {}
    for source in sources:
        kind, detected = kinds[source.url + "\0" + source.board_id]
        base = board_dir(source.board_id) / str(kind)
        candidate = base / file_name(source.url, detected)
        if candidate in taken and taken[candidate] != source.sha256:
            candidate = base / f"{source.sha256[:8]}-{candidate.name}"
        taken[candidate] = source.sha256
        paths[source.url + "\0" + source.board_id] = candidate
    return paths


# --------------------------------------------------------------------------------------
# manifest and attribution
# --------------------------------------------------------------------------------------

def manifest_entry(source: Source, path: Path, kind: str, detected: Optional[str], size: int) -> Dict[str, Any]:
    licences = source.record.get("licenses") or {}
    return {
        "board_id": source.board_id,
        "manufacturer": source.record.get("manufacturer"),
        "board": source.record.get("board"),
        "path": path.as_posix(),
        "category": kind,
        "detected_format": detected,
        "formats": sorted(source.formats),
        "url": source.url,
        "sha256": source.sha256,
        "size_bytes": size,
        "retrieved_at": source.captured_at,
        "licence": licences.get("cad_license") or licences.get("hardware_license"),
        "licence_url": licences.get("license_url"),
    }


def render_attribution(record: Dict[str, Any], entries: Sequence[Dict[str, Any]]) -> str:
    licences = record.get("licenses") or {}
    licence = licences.get("cad_license") or licences.get("hardware_license") or "see source"
    licence_url = licences.get("license_url")
    lines = [
        f"# {record.get('board')}",
        "",
        f"Design files published by **{record.get('manufacturer')}**, copied here without",
        "modification from the official sources listed below. Each file is byte-identical to",
        "the SHA-256 recorded for it in",
        "[`tools/devboard_cad/records/`](../../../../tools/devboard_cad/records/).",
        "",
        f"- Board ID: `{record.get('board_id')}`",
        f"- Part number: {record.get('part_number')}",
        f"- Licence: {licence}" + (f" ({licence_url})" if licence_url else ""),
        f"- Attribution: {record.get('manufacturer')}",
        "- Changes: none",
        "",
        "| File | Kind | Format | Source | SHA-256 | Retrieved |",
        "|---|---|---|---|---|---|",
    ]
    for entry in sorted(entries, key=lambda e: e["path"]):
        rel = Path(entry["path"]).relative_to(board_dir(record["board_id"])).as_posix()
        lines.append(
            f"| [`{rel}`]({rel}) | {entry['category']} | {', '.join(entry['formats'])} "
            f"| [source]({entry['url']}) | `{entry['sha256'][:16]}…` | {entry['retrieved_at'] or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def load_manifest(root: Path) -> Dict[str, Any]:
    path = root / MANIFEST_PATH
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"tool": TOOL_ID, "entries": []}


def write_manifest(root: Path, entries: Sequence[Dict[str, Any]]) -> None:
    path = root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "tool": TOOL_ID,
        "policy": ("CAD files only, and only from boards whose records set "
                   "licenses.redistribution_allowed to true."),
        "entries": sorted(entries, key=lambda e: (e["board_id"], e["path"])),
    }
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------

@dataclass
class Report:
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    refused: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refused


def build(root: Path, records: Sequence[Dict[str, Any]], fetcher: Any,
          vendors: Sequence[str] = ()) -> Report:
    """Write the selected boards' files, their attribution and the manifest."""
    report = Report()
    wanted = {v.lower() for v in vendors}
    sources = [s for s in select(records)
               if not wanted or s.board_id.partition(":")[0].lower() in wanted]
    payloads: Dict[str, bytes] = {}
    kinds: Dict[str, Tuple[str, Optional[str]]] = {}
    accepted: List[Source] = []
    existing = {(e["board_id"], e["url"]): root / e["path"] for e in load_manifest(root).get("entries", [])}
    for source in sources:
        payload = None
        held = existing.get((source.board_id, source.url))
        if held is not None and held.is_file():
            data = held.read_bytes()
            if hashlib.sha256(data).hexdigest() == source.sha256:
                payload = data
        if payload is None:
            result = fetcher.get(source.url)
            payload = result.payload
            if payload is None:
                report.refused.append(f"{source.board_id}: {source.url}: not retrieved ({result.error})")
                continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest != source.sha256:
            report.refused.append(
                f"{source.board_id}: {source.url}: sha256 {digest[:16]} != recorded {source.sha256[:16]}")
            continue
        kind, detected = category(payload, file_name(source.url, identify(payload)))
        if kind != "cad":
            report.refused.append(f"{source.board_id}: {source.url}: not a CAD file ({detected})")
            continue
        key = source.url + "\0" + source.board_id
        payloads[key] = payload
        kinds[key] = (kind, detected)
        accepted.append(source)

    paths = plan_paths(accepted, kinds)
    manifest = load_manifest(root)
    entries = [e for e in manifest.get("entries", [])
               if wanted and e["board_id"].partition(":")[0].lower() not in wanted]
    per_board: Dict[str, List[Dict[str, Any]]] = {}
    for source in accepted:
        key = source.url + "\0" + source.board_id
        path, payload = paths[key], payloads[key]
        kind, detected = kinds[key]
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == source.sha256:
            report.unchanged.append(path.as_posix())
        else:
            target.write_bytes(payload)
            report.written.append(path.as_posix())
        entry = manifest_entry(source, path, kind, detected, len(payload))
        entries.append(entry)
        per_board.setdefault(source.board_id, []).append(entry)

    for source in accepted:
        board_entries = per_board.pop(source.board_id, None)
        if board_entries is None:
            continue
        attribution = root / board_dir(source.board_id) / ATTRIBUTION_NAME
        attribution.write_text(render_attribution(source.record, board_entries), encoding="utf-8")
    write_manifest(root, entries)
    report.removed = prune(root, entries)
    return report


def prune(root: Path, entries: Sequence[Dict[str, Any]]) -> List[str]:
    """Delete whatever the manifest no longer names: stray files and boards left empty."""
    removed: List[str] = []
    base = root / MIRROR_DIR
    if not base.is_dir():
        return removed
    keep = {(root / e["path"]).resolve() for e in entries}
    boards = {board_dir(e["board_id"]) for e in entries}
    for path in sorted(base.rglob("*"), reverse=True):
        parts = path.relative_to(base).parts
        if path.is_file() and len(parts) < 3:
            path.unlink()
            removed.append(path.relative_to(root).as_posix())
            continue
        if len(parts) < 3:
            continue
        board = MIRROR_DIR / parts[0] / parts[1]
        if path.is_file() and (path.resolve() not in keep) and (board not in boards or len(parts) >= 4):
            path.unlink()
            removed.append(path.relative_to(root).as_posix())
    for path in sorted(base.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    return removed


# --------------------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------------------

def lfs_pointer_oid(data: bytes) -> Optional[str]:
    """Return the sha256 oid when ``data`` is a Git LFS pointer file, else None."""
    if not data.startswith(LFS_POINTER_PREFIX) or len(data) > 1024:
        return None
    match = re.search(rb"^oid sha256:([0-9a-f]{64})$", data, re.MULTILINE)
    return match.group(1).decode("ascii") if match else None


def check(root: Path, records: Sequence[Dict[str, Any]]) -> List[str]:
    """Problems with the mirror, or an empty list when it is complete and intact.

    Works on a checkout without LFS content: a pointer file's oid is the SHA-256 of the
    object it stands for, so integrity is provable from the pointer alone.
    """
    problems: List[str] = []
    manifest = load_manifest(root)
    entries = manifest.get("entries", [])
    by_key = {(e["board_id"], e["url"]): e for e in entries}
    allowed = {r["board_id"] for r in records if redistributable(r)}

    for source in select(records):
        if (source.board_id, source.url) not in by_key:
            problems.append(f"missing: {source.board_id} {source.url}")

    for entry in entries:
        label = f"{entry['board_id']} {entry['path']}"
        if entry["board_id"] not in allowed:
            problems.append(f"not redistributable: {label}")
        path = root / entry["path"]
        if not path.is_file():
            problems.append(f"file absent: {label}")
            continue
        data = path.read_bytes()
        oid = lfs_pointer_oid(data)
        digest = oid or hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            problems.append(f"digest mismatch: {label}")
        if oid is None and category(data, path.name)[0] != entry["category"]:
            problems.append(f"content is not {entry['category']}: {label}")
        attribution = root / board_dir(entry["board_id"]) / ATTRIBUTION_NAME
        if not attribution.is_file():
            problems.append(f"no {ATTRIBUTION_NAME}: {entry['board_id']}")

    mirrored = {(root / e["path"]).resolve() for e in entries}
    boards = {board_dir(e["board_id"]) for e in entries}
    base = root / MIRROR_DIR
    if base.is_dir():
        for path in base.rglob("*"):
            parts = path.relative_to(base).parts
            if not path.is_file():
                continue
            if len(parts) < 3:
                problems.append(f"stray file in mirror: {path.relative_to(root).as_posix()}")
                continue
            board = MIRROR_DIR / parts[0] / parts[1]
            if board not in boards:
                problems.append(f"board without CAD files in mirror: {path.relative_to(root).as_posix()}")
            elif len(parts) >= 4 and path.resolve() not in mirrored:
                problems.append(f"untracked file in mirror: {path.relative_to(root).as_posix()}")
    return sorted(set(problems))


# --------------------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_records(root: Path) -> List[Dict[str, Any]]:
    directory = root / "tools" / "devboard_cad" / "records"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]


def summarise(root: Path) -> str:
    entries = load_manifest(root).get("entries", [])
    boards = {e["board_id"] for e in entries}
    by_kind: Dict[str, int] = {}
    for entry in entries:
        by_kind[entry["category"]] = by_kind.get(entry["category"], 0) + 1
    size = sum(e["size_bytes"] for e in entries)
    kinds = ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items()))
    return f"{len(entries)} files for {len(boards)} boards ({kinds}), {size / 1e6:.1f} MB"


def cmd_build(args: argparse.Namespace) -> int:
    root = repo_root()
    fetcher = Fetcher(cache_dir=args.cache, offline=args.offline)
    report = build(root, load_records(root), fetcher, args.vendor)
    for line in report.refused:
        print(f"REFUSED {line}", file=sys.stderr)
    print(f"written {len(report.written)}, unchanged {len(report.unchanged)}, "
          f"removed {len(report.removed)}, refused {len(report.refused)}")
    print(summarise(root))
    return 0 if report.ok else 1


def cmd_check(args: argparse.Namespace) -> int:
    root = repo_root()
    problems = check(root, load_records(root))
    for line in problems:
        print(line, file=sys.stderr)
    print(f"{summarise(root)}; {len(problems)} problem(s)")
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="copy the verified CAD files of redistributable boards into boards/cad/")
    b.add_argument("--vendor", action="append", default=[],
                   help="only this vendor prefix of board_id (repeatable), e.g. --vendor sparkfun")
    b.add_argument("--offline", action="store_true", help="use only the verifier's local cache")
    b.add_argument("--cache", type=Path, default=None, help="cache directory (default: the verifier's)")
    b.set_defaults(func=cmd_build)
    c = sub.add_parser("check", help="fail unless the mirror is complete and every digest matches")
    c.set_defaults(func=cmd_check)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
