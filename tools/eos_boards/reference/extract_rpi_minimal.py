"""Take the RP2350A core layout from Raspberry Pi's minimal design, for reuse on our boards.

Raspberry Pi's hardware design guide asks designers to copy its regulator layout rather than
redesign it, and publishes the whole minimal design under the MIT licence:

    RP2350A Minimal Design R4 (RPI-RP2350A-MINIMAL_R4-S1), (c) 2026 Raspberry Pi Ltd, MIT
    https://datasheets.raspberrypi.com/rp2350/Minimal-KiCAD.zip

This script reads that design's ``.kicad_pcb`` and writes two things:

* ``footprints/EoS_RPi_Reference.pretty``: the footprints of the parts around the chip, as
  library footprints (no nets, no UUIDs). Raspberry Pi's own 3D models travel inside them as
  KiCad embedded files; the inductor's model is swapped for KiCad's stock 2016 inductor,
  because Raspberry Pi's copy may come from the part's maker.
* ``reference/rp2350a_minimal_r4_core.json``: where those parts sit and the copper drawn
  between them (tracks, vias and the small zones under and beside the chip), relative to the
  chip's centre, with Raspberry Pi's net names translated to ours.

Only the chip's surroundings are taken: the regulator, the decoupling, the crystal, the USB
series resistors and the QSPI flash's data and clock lines. Each GPIO, SWD and RUN line's escape
through the decoupling ring is kept apart, as ``escapes``, cut where it leaves the ring: a board
uses one only for a line it routes itself (``priority_routes``), since where the line goes next
is the board's own. Connector and flash chip-select routing are each board's own (Raspberry
Pi's chip-select goes through 0 ohm options).

usage: python3 tools/eos_boards/reference/extract_rpi_minimal.py RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from eos_boards.sexpr import Sym, dumps, find, find_all, loads  # noqa: E402

SOURCE = ("Raspberry Pi RP2350A Minimal Design R4 (RPI-RP2350A-MINIMAL_R4-S1), "
          "MIT licence, (c) 2026 Raspberry Pi Ltd")
URL = "https://datasheets.raspberrypi.com/rp2350/Minimal-KiCAD.zip"
LIBRARY = "EoS_RPi_Reference"

# Raspberry Pi reference -> our reference designator, for every part reused around the chip.
PARTS = {
    "U1": "U1", "X1": "Y1", "L1": "L1", "C6": "C6", "C7": "C7", "C9": "C9", "R3": "R6",
    "R7": "R3", "R8": "R4", "R2": "R10", "C3": "C3", "C4": "C4",
    "C8": "C18", "C10": "C19", "C11": "C20",                          # DVDD decoupling
    "C12": "C16", "C13": "C10", "C14": "C14", "C15": "C11", "C16": "C13", "C17": "C15", "C18": "C12",
    "U3": "U4",                                                       # QSPI flash
}
# The areas taken, relative to the chip's centre (mm): x0, y0, x1, y1.
REGIONS = {
    "core": (-8.2, -8.2, 8.2, 14.8),        # the chip, its regulator, decoupling and crystal
    "flash": (-12.6, -15.5, 0.0, -3.0),     # from the QSPI pins to the flash
    "escape": (-8.2, -8.2, 8.2, 8.2),       # signal escapes through the decoupling ring, cut at its edge
}
# Raspberry Pi net -> (our net, the area its copper is taken from). Copper on other nets is not taken.
NETS = {
    "+3V3": ("+3V3", "core"), "+1V1": ("+1V1", "core"), "GND": ("GND", "core"),
    "/VREG_LX": ("/VREG_LX", "core"), "/VREG_AVDD": ("/VREG_AVDD", "core"),
    "Net-(U1-USB_DP)": ("/RP_USB_DP", "core"), "Net-(U1-USB_DM)": ("/RP_USB_DM", "core"),
    "/XIN": ("/XIN", "core"), "/XOUT": ("/XOUT", "core"), "Net-(C4-Pad1)": ("/XTAL_OUT", "core"),
    **{f"/QSPI_{n}": (f"/QSPI_{n}", "flash") for n in ("SD0", "SD1", "SD2", "SD3", "SCLK")},
    **{f"/GPIO{i}": (f"/GPIO{i}", "escape") for i in range(26)},
    **{f"/GPIO{i}_ADC{i - 26}": (f"/GPIO{i}_ADC{i - 26}", "escape") for i in range(26, 30)},
    "/SWCLK": ("/SWCLK", "escape"), "/SWD": ("/SWDIO", "escape"), "/RUN": ("/RUN", "escape"),
}
STOCK_MODELS = {"abracon_aota-b201610s3r3-101-t": "${KICAD10_3DMODEL_DIR}/Inductor_SMD.3dshapes/L_Cenker_CKCS201610.step"}
DROP = {"uuid", "path", "sheetname", "sheetfile", "locked", "tstamp"}


def _ref(fp: List[Any]) -> str:
    return next(str(p[2]) for p in find_all(fp, "property") if str(p[1]) == "Reference")


def _strip(node: Any) -> Any:
    """``node`` without UUIDs, nets or sheet links."""
    if not isinstance(node, list):
        return node
    out = [node[0]]
    for item in node[1:]:
        if isinstance(item, list) and item and isinstance(item[0], Sym) and str(item[0]) in DROP | {"net"}:
            continue
        out.append(_strip(item))
    return out


def _unrotate(node: List[Any], angle: float) -> None:
    """Pads and texts store the footprint's rotation in their own angle; take it back out."""
    if not angle:
        return
    for item in node:
        if isinstance(item, list) and item and str(item[0]) in ("pad", "property", "fp_text"):
            at = find(item, "at")
            if at is not None:
                a = ((float(at[3]) if len(at) > 3 else 0.0) - angle + 180) % 360 - 180
                del at[3:]
                if abs(a) > 1e-6:
                    at.append(round(a, 6))


def footprint(fp: List[Any], embedded: Dict[str, List[Any]]) -> Tuple[str, str]:
    """(name, .kicad_mod text) for the library version of a placed footprint."""
    name = str(fp[1]).split(":", 1)[-1]
    at = find(fp, "at")
    angle = float(at[3]) if len(at) > 3 else 0.0
    body = [x for x in _strip(copy.deepcopy(fp))[2:] if not (isinstance(x, list) and str(x[0]) == "at")]
    node: List[Any] = [Sym("footprint"), name, [Sym("version"), 20241229], [Sym("generator"), "eos_boards"], *body]
    _unrotate(node, angle)
    # A library footprint keeps KiCad's four standard fields. The rest are Raspberry Pi's part
    # database entries for the one part that was placed (its value, stock code, and so on),
    # which would be wrong on any other part using the same footprint.
    node[:] = [x for x in node if not (isinstance(x, list) and str(x[0]) == "property"
                                       and str(x[1]) not in ("Reference", "Value", "Datasheet", "Description"))]
    fields = {"Reference": "REF**", "Value": name, "Datasheet": "~",
              "Description": "From Raspberry Pi's RP2350A Minimal Design R4 (MIT licence)"}
    for prop in find_all(node, "property"):
        prop[2] = fields[str(prop[1])]
    model = find(node, "model")
    if model is not None:
        target = str(model[1])
        if name in STOCK_MODELS:
            model[1] = STOCK_MODELS[name]
        elif target.startswith("kicad-embed://"):
            entry = embedded[target[len("kicad-embed://"):]]
            node.insert(node.index(model), [Sym("embedded_files"), entry])
    return name, dumps(node) + "\n"


def _local(x: float, y: float, cx: float, cy: float) -> List[float]:
    return [round(x - cx, 6), round(y - cy, 6)]


def _inside(p: List[float], net: str) -> bool:
    x0, y0, x1, y1 = REGIONS[NETS[net][1]]
    return x0 <= p[0] <= x1 and y0 <= p[1] <= y1


def _clip(a: List[float], b: List[float], net: str) -> List[float]:
    """Where the segment from ``a`` (inside the net's area) to ``b`` (outside) leaves the area."""
    x0, y0, x1, y1 = REGIONS[NETS[net][1]]
    t = 1.0
    for i, (lo, hi) in enumerate(((x0, x1), (y0, y1))):
        d = b[i] - a[i]
        if b[i] > hi:
            t = min(t, (hi - a[i]) / d)
        elif b[i] < lo:
            t = min(t, (lo - a[i]) / d)
    return [round(a[0] + (b[0] - a[0]) * t, 6), round(a[1] + (b[1] - a[1]) * t, 6)]


def copper(board: List[Any], cx: float, cy: float, placed: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"source": SOURCE, "url": URL, "source_sha256": None,
                           "note": "mm relative to the RP2350A's centre, chip unrotated (regulator pins on its top edge). "
                                   "Written by extract_rpi_minimal.py; do not edit by hand.",
                           "footprints": placed, "tracks": [], "vias": [], "zones": [], "escapes": []}
    for seg in find_all(board, "segment"):
        net = str(find(seg, "net")[-1])
        a = _local(float(find(seg, "start")[1]), float(find(seg, "start")[2]), cx, cy)
        b = _local(float(find(seg, "end")[1]), float(find(seg, "end")[2]), cx, cy)
        escape = net in NETS and NETS[net][1] == "escape"
        if escape and _inside(a, net) != _inside(b, net):
            a, b = (a, _clip(a, b, net)) if _inside(a, net) else (_clip(b, a, net), b)
        if net in NETS and _inside(a, net) and _inside(b, net):
            out["escapes" if escape else "tracks"].append({"net": NETS[net][0], "layer": str(find(seg, "layer")[1]),
                                                           "w": float(find(seg, "width")[1]), "a": a, "b": b})
    for via in find_all(board, "via"):
        net = str(find(via, "net")[-1])
        p = _local(float(find(via, "at")[1]), float(find(via, "at")[2]), cx, cy)
        if net in NETS and NETS[net][1] != "escape" and _inside(p, net):
            out["vias"].append({"net": NETS[net][0], "x": p[0], "y": p[1], "d": float(find(via, "size")[1]),
                                "drill": float(find(via, "drill")[1])})
    for z in find_all(board, "zone"):
        net = str(find(z, "net_name")[1]) if find(z, "net_name") else str(find(z, "net")[-1])
        pts = [_local(float(p[1]), float(p[2]), cx, cy) for p in find_all(find(find(z, "polygon"), "pts"), "xy")]
        if net not in NETS or NETS[net][1] == "escape" or not all(_inside(p, net) for p in pts):
            continue
        cp = find(z, "connect_pads")
        mode = {"yes": "full", "no": "none"}.get(str(cp[1]) if len(cp) > 1 and isinstance(cp[1], Sym) else "", "thermal")
        clearance = find(cp, "clearance")
        out["zones"].append({"net": NETS[net][0], "layer": str(find(z, "layer")[1]),
                             "priority": int(find(z, "priority")[1]) if find(z, "priority") else 0,
                             "clearance": float(clearance[1]) if clearance else None,
                             "min_width": float(find(z, "min_thickness")[1]), "connection": mode, "outline": pts})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pcb", type=Path, help="RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb from Raspberry Pi's zip")
    ap.add_argument("--footprints", type=Path, default=HERE.parent / "footprints" / f"{LIBRARY}.pretty")
    ap.add_argument("--out", type=Path, default=HERE / "rp2350a_minimal_r4_core.json")
    args = ap.parse_args()

    board = loads(args.pcb.read_text())
    embedded = {str(find(f, "name")[1]): f for f in find_all(find(board, "embedded_files"), "file")}
    fps = {_ref(fp): fp for fp in find_all(board, "footprint")}
    chip = find(fps["U1"], "at")
    cx, cy = float(chip[1]), float(chip[2])
    if len(chip) > 3 and float(chip[3]):
        raise SystemExit("the reference chip is rotated; offsets assume it is not")

    args.footprints.mkdir(parents=True, exist_ok=True)
    placed: Dict[str, Dict[str, Any]] = {}
    written = set()
    for theirs, ours in PARTS.items():
        fp = fps[theirs]
        at = find(fp, "at")
        name, text = footprint(fp, embedded)
        if name not in written:
            (args.footprints / f"{name}.kicad_mod").write_text(text)
            written.add(name)
        rot = float(at[3]) if len(at) > 3 else 0.0
        placed[ours] = {"footprint": f"{LIBRARY}:{name}", "x": round(float(at[1]) - cx, 6),
                        "y": round(float(at[2]) - cy, 6), "rot": rot % 360,
                        # the pads the copper reaches: on any other pad, the copper keeps its clearance
                        "pads": {str(p[1]): NETS[str(find(p, "net")[-1])][0]
                                 for p in find_all(fp, "pad") if find(p, "net") is not None and str(find(p, "net")[-1]) in NETS
                                 and NETS[str(find(p, "net")[-1])][1] != "escape"}}
    data = copper(board, cx, cy, placed)
    data["source_sha256"] = hashlib.sha256(args.pcb.read_bytes()).hexdigest()   # the exact file these facts came from
    args.out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"footprints: {sorted(written)}")
    print({k: len(v) for k, v in data.items() if isinstance(v, (list, dict))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
