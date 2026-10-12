"""Take the Raspberry Pi Compute Module 4's 200-pin signal list from its datasheet.

    Pinout: Raspberry Pi Compute Module 4 datasheet, section 4 (Pinout)
            https://datasheets.raspberrypi.com/cm4/cm4-datasheet.pdf

Only facts are taken: pin numbers and signal names. The CM4's connectors and mounting holes sit
where the CM5's do: Figure 4 of the two datasheets gives the same 55 x 40 mm outline, the same
3.5 mm hole inset, the same 3 mm connector offsets and the same wireless cut-out, and the CM5
datasheet (section 1.2) says CM5 fits existing CM4 carrier boards. So a CM4 carrier is tested
against ``cm5_carrier.json``'s pads and holes, and against this file's pin list.

Writes ``reference/cm4_pins.json``.

usage: python3 tools/eos_boards/reference/extract_cm4.py cm4-datasheet.txt cm4-datasheet.pdf
       (cm4-datasheet.txt: ``pdftotext -layout cm4-datasheet.pdf``)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from eos_boards.reference.extract_cm5 import pinout  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("datasheet_text", type=Path)
    ap.add_argument("datasheet_pdf", type=Path, help="the PDF the text came from, for its SHA-256")
    ap.add_argument("--out", type=Path, default=HERE / "cm4_pins.json")
    args = ap.parse_args()
    data = {"source": "Raspberry Pi Compute Module 4 datasheet, section 4 (Pinout); facts only (pin names)",
            "url": "https://datasheets.raspberrypi.com/cm4/cm4-datasheet.pdf",
            "source_sha256": hashlib.sha256(args.datasheet_pdf.read_bytes()).hexdigest(),
            "note": "written by extract_cm4.py, do not edit by hand",
            "pins": pinout(args.datasheet_text.read_text(), "4. Pinout")}
    args.out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(data['pins'])} pins -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
