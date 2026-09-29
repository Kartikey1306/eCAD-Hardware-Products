"""Seed records for manufacturers that do not publish design files on GitHub (issue #28).

Issue #28 section 10 puts the official product page and official documentation above a
repository in the source hierarchy, but neither is machine-enumerable. raspberrypi.com
answers an automated client with a Cloudflare interstitial; st.com does not answer one at
all. Where a manufacturer's own documentation *source* is public the URLs can still be
recovered from it -- the Raspberry Pi entries in direct_sources.json were extracted from
raspberrypi/documentation, which cites official pip.raspberrypi.com document IDs.

This tool writes those URLs into records as candidates and nothing more. Availability is
still decided by verify.py from retrieved bytes, so a curated URL that has rotted becomes
'unknown' rather than a false claim. Absence is never asserted here: unlike a repository
tree, a curated list is not exhaustive, so a format missing from it means only that nobody
has looked.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
SOURCES = HERE.parent / "direct_sources.json"

sys.path.insert(0, str(HERE.parents[1]))

from devboard_cad.verify import derive_status, records_dir  # noqa: E402

REQUIRED_FORMATS = ("schematic", "pcb_source", "gerbers", "bom", "mechanical")


def _entry(url: Optional[str]) -> "OrderedDict[str, Any]":
    return OrderedDict([("available", None), ("url", url),
                        ("verified_revision", None), ("evidence", None)])


def build_record(board: Dict[str, Any]) -> "OrderedDict[str, Any]":
    files: "OrderedDict[str, Any]" = OrderedDict()
    for name in sorted(board["files"]):
        files[name] = _entry(board["files"][name])
    for name in REQUIRED_FORMATS:
        files.setdefault(name, _entry(None))

    note = (
        "Candidate URLs curated from the manufacturer's official documentation; "
        "availability is decided by verify.py from retrieved bytes. Unlike a repository "
        "tree this list is not exhaustive, so formats absent from it are recorded as "
        "unknown rather than absent."
    )
    if board.get("index_ref"):
        note += f" URLs extracted from {board['index_ref']}."

    record: "OrderedDict[str, Any]" = OrderedDict([
        ("$schema", "https://embeddedos.org/schemas/devboard-cad/v1/board-record.schema.json"),
        ("contract_version", "1.1.0"),
        ("board_id", board["board_id"]),
        ("manufacturer", board["manufacturer"]),
        ("family", board["family"]),
        ("board", board["board"]),
        ("part_number", board.get("part_number", "UNVERIFIED")),
        ("revision", board.get("revision", "unverified")),
        ("mcu_soc", board.get("mcu_soc", "UNVERIFIED")),
        ("hardware_revision", board.get("hardware_revision")),
        ("fpga", board.get("fpga")),
        ("cpu_architecture", board.get("cpu_architecture")),
        ("product_status", board.get("product_status", "unknown")),
        ("files", files),
        ("licenses", OrderedDict([
            ("hardware_license", board.get("hardware_license", "UNVERIFIED")),
            ("cad_license", None), ("schematic_license", None), ("pcb_license", None),
            ("mechanical_cad_license", None),
            ("redistribution_allowed", None), ("modification_allowed", None),
            ("commercial_use_allowed", None), ("attribution_required", None),
            ("license_url", None),
        ])),
        ("sources", OrderedDict([
            ("source_tier", board.get("source_tier", "manufacturer_official")),
            ("official_product_page", board["official_product_page"]),
            ("official_cad_repository", None),
            ("official_github_repository", None),
            ("official_documentation", board.get("official_documentation")),
            ("direct_cad_download", board["files"].get("step")),
            ("direct_schematic_download", board["files"].get("schematic")),
            ("direct_gerber_download", board["files"].get("gerbers")),
        ])),
        ("record_status", "incomplete"),
        ("notes", note),
    ])
    record["record_status"] = derive_status(record)
    return record


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--sources", default=str(SOURCES))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    boards = json.loads(Path(args.sources).read_text(encoding="utf-8"))["boards"]
    out_dir = records_dir(Path(args.root).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for board in boards:
        path = out_dir / (board["board_id"].replace(":", "__") + ".json")
        if path.exists() and not args.overwrite:
            skipped += 1
            continue
        record = build_record(board)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
        written += 1
        print(f"  {record['board_id']:34} {len(board['files'])} candidate(s)")
    print(f"\nwritten={written} skipped_existing={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
