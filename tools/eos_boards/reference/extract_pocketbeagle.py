"""Take PocketBeagle's outline and P1/P2 header pin positions from BeagleBoard.org's board file.

    BeagleBoard.org PocketBeagle, CC BY 4.0, (c) 2017 Jason Kridner (Texas Instruments),
    Aron Phillips (GHI Electronics), Michael Welling (QWERTY Embedded)
    https://github.com/beagleboard/pocketbeagle (KiCAD/PocketBeagle.kicad_pcb)

Writes ``reference/pocketbeagle_headers.json``: every header pin's position in integer
nanometres, relative to the top-left corner of PocketBeagle's outline. A cape test reads it to
prove the cape's sockets meet PocketBeagle's pins exactly.

usage: python3 tools/eos_boards/reference/extract_pocketbeagle.py PocketBeagle.kicad_pcb
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from eos_boards.sexpr import find, find_all, loads  # noqa: E402


def nm(value: float) -> int:
    return round(value * 1_000_000)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pcb", type=Path, help="PocketBeagle.kicad_pcb from github.com/beagleboard/pocketbeagle")
    ap.add_argument("--out", type=Path, default=HERE / "pocketbeagle_headers.json")
    args = ap.parse_args()
    board = loads(args.pcb.read_text())
    edges = [g for g in find_all(board, "gr_line") + find_all(board, "gr_arc") if str(find(g, "layer")[1]) == "Edge.Cuts"]
    xs = [float(p[i]) for g in edges for p in (find(g, "start"), find(g, "end")) for i in (1,)]
    ys = [float(p[i]) for g in edges for p in (find(g, "start"), find(g, "end")) for i in (2,)]
    ox, oy = min(xs), min(ys)
    pins = {}
    for m in find_all(board, "module"):
        ref = next((str(t[2]) for t in find_all(m, "fp_text") if str(t[1]) == "reference"), "")
        if ref not in ("P1", "P2"):
            continue
        at = find(m, "at")
        if len(at) > 3 and float(at[3]):
            raise SystemExit(f"{ref} is rotated; this script expects it as drawn")
        for p in find_all(m, "pad"):
            pa = find(p, "at")
            pins[f"{ref}.{int(str(p[1]))}"] = [nm(float(at[1]) + float(pa[1]) - ox), nm(float(at[2]) + float(pa[2]) - oy)]
    data = {"source": "BeagleBoard.org PocketBeagle (KiCAD/PocketBeagle.kicad_pcb), CC BY 4.0",
            "url": "https://github.com/beagleboard/pocketbeagle",
            "source_sha256": hashlib.sha256(args.pcb.read_bytes()).hexdigest(),
            "note": "nanometres from the top-left corner of PocketBeagle's outline, seen from its top side. "
                    "Written by extract_pocketbeagle.py; do not edit by hand.",
            "outline_nm": [nm(max(xs) - ox), nm(max(ys) - oy)],
            "pins": dict(sorted(pins.items(), key=lambda kv: (kv[0].split(".")[0], int(kv[0].split(".")[1]))))}
    args.out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(pins)} pins, outline {data['outline_nm']} nm -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
