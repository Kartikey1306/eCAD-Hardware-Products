"""Take the Raspberry Pi Compute Module 5's carrier-side facts: its 200-pin signal list and where
its connectors' pads and mounting holes sit.

    Pinout: Raspberry Pi Compute Module 5 datasheet, section 4.2, table 4
            https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf
    Geometry: the CM5 footprint in Raspberry Pi's CM5 IO Board KiCad files
            (CM5IO.pretty/Raspberry-Pi-5-Compute-Module.kicad_mod), which the CM5IO datasheet
            says can be used in your own designs.

Only facts are taken: pin numbers and names, and pad and hole coordinates. No Raspberry Pi file
is copied into this repository; the carrier draws its connectors with KiCad's own Hirose DF40
footprints and is tested against these coordinates.

Writes ``reference/cm5_carrier.json``: positions in integer nanometres, relative to mounting
hole MH1 of that footprint (module edge 3.5 mm beyond it), and every pin's signal name.

usage: python3 tools/eos_boards/reference/extract_cm5.py cm5-datasheet.txt Raspberry-Pi-5-Compute-Module.kicad_mod
       (cm5-datasheet.txt: ``pdftotext -layout cm5-datasheet.pdf``)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from eos_boards.sexpr import find, find_all, loads  # noqa: E402


def nm(value: float) -> int:
    return round(value * 1_000_000)


def pinout(text: str) -> dict:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "4.2. Pinout")   # the heading, not the contents line
    pins = {}
    for line in lines[start:start + 420]:
        m = re.match(r"^\s{0,3}(\d{1,3})\s+(\S+(?: \((?:Input|Output)\))?)\s{2,}", line)
        if m and 1 <= int(m.group(1)) <= 200 and int(m.group(1)) not in pins:
            pins[int(m.group(1))] = m.group(2).replace(" (Input)", "").replace(" (Output)", "")
    missing = [p for p in range(1, 201) if p not in pins]
    if missing:
        raise SystemExit(f"pins not found in the datasheet text: {missing}")
    return {str(k): pins[k] for k in sorted(pins)}


def geometry(footprint: list) -> dict:
    pads, holes = {}, []
    for p in find_all(footprint, "pad"):
        at = find(p, "at")
        if str(p[1]).isdigit():
            pads[str(p[1])] = [nm(float(at[1])), nm(float(at[2]))]
        elif str(p[2]) == "np_thru_hole":
            holes.append([nm(float(at[1])), nm(float(at[2])), nm(float(find(p, "drill")[1]))])
    if len(pads) != 200 or len(holes) != 4:
        raise SystemExit(f"expected 200 pads and 4 holes, found {len(pads)} and {len(holes)}")
    return {"pads": dict(sorted(pads.items(), key=lambda kv: int(kv[0]))), "holes": sorted(holes)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("datasheet_text", type=Path)
    ap.add_argument("footprint", type=Path)
    ap.add_argument("--out", type=Path, default=HERE / "cm5_carrier.json")
    args = ap.parse_args()
    data = {"source": "Raspberry Pi Compute Module 5 datasheet (table 4) and the CM5 footprint in the CM5 IO "
                      "Board KiCad files; facts only (pin names, coordinates)",
            "note": "nanometres from mounting hole MH1; written by extract_cm5.py, do not edit by hand",
            "footprint_sha256": hashlib.sha256(args.footprint.read_bytes()).hexdigest(),
            "pins": pinout(args.datasheet_text.read_text()), **geometry(loads(args.footprint.read_text()))}
    args.out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(data['pins'])} pins, {len(data['pads'])} pads, {len(data['holes'])} holes -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
