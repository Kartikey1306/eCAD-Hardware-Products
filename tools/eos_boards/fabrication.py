"""What a fab needs written into every board, as data: the layer stack-up (part of the MIT generator).

Pure Python, and Python 3.9 compatible: ``pcb_build.py`` imports this module under KiCad's own
Python, and the unit tests import it as ``eos_boards.fabrication``.

Stack-ups. Each board's ``.kicad_pcb`` carries its layer stack-up: copper weights, dielectric
thicknesses and materials, the dielectric constant of each, the surface finish and the solder-mask
and silkscreen colours. Fabs read it from the board file and from the Gerber job file that KiCad
writes beside the Gerbers. The numbers are JLCPCB's published standard stack-ups for a 1.6 mm board,
read on 24 October 2026:

* 4 layers, JLC04161H-7628 (https://jlcpcb.com/impedance, "JLC04161H-7628 Stackup"): copper
  0.035 mm, prepreg 7628 x 1 0.2104 mm, inner copper 0.0152 mm, core 1.065 mm ("1.1mm H/HOZ with
  copper"), inner copper 0.0152 mm, prepreg 7628 x 1 0.2104 mm, copper 0.035 mm. The same page gives
  the dielectric constants: prepreg 7628 4.4, core 4.6.
* 6 layers, JLC06161H-7628 (same page): copper 0.035, prepreg 7628 0.2104, inner copper 0.0152,
  core 0.4, inner copper 0.0152, prepreg 7628 0.2028, inner copper 0.0152, core 0.4, inner copper
  0.0152, prepreg 7628 0.2104, copper 0.035 mm.
* 2 layers: JLCPCB's capabilities page (https://jlcpcb.com/capabilities/pcb-capabilities) gives the
  FR-4 dielectric constant "4.5 (2-Layer PCB)", 1 oz finished outer copper (0.035 mm) by default and
  1.6 mm board thickness. It publishes no core thickness for two layers on these pages, so the core
  is derived: 1.51 mm makes the copper, core and both 0.01 mm masks add up to 1.6 mm (KiCad's own
  default for a 1.6 mm two-layer board does the same).
* Solder mask: 0.01 mm ("Solder mask ink thickness >= 10um", capabilities page), green; silkscreen
  white. Surface finish: ENIG by default (BENCH-READY A5 asks for it wherever a pitch is 0.5 mm or
  finer or a part is a QFN, which covers nearly every board here; JLCPCB offers no HASL on six-layer
  boards). The loss tangent is not published on these pages; KiCad writes its own default, 0.02.

JLCPCB's finished thickness tolerance is +-10 % for boards of 1.0 mm and over (capabilities page),
so a stack-up must add up to the board's thickness within that.

A design file can override any of it with ``Board.stackup``: ``{"finish": "HAL lead-free"}``, other
colours, or a whole ``"layers"`` list of copper and dielectric rows for another fab's stack-up.
"""

from __future__ import annotations

import copy

STACKUP_CHECKED = "2026-10-24"
JLCPCB_IMPEDANCE = "https://jlcpcb.com/impedance"
JLCPCB_CAPABILITIES = "https://jlcpcb.com/capabilities/pcb-capabilities"

OUTER_CU = 0.035        # 1 oz finished outer copper
INNER_CU = 0.0152       # 0.5 oz inner copper, as JLCPCB's tables give it
MASK = 0.01             # solder mask, each side
TOLERANCE = 0.10        # finished thickness +-10 %

# Copper finishes as KiCad names them in a stack-up (the board setup's finish list).
FINISHES = ("None", "HAL SnPb", "HAL lead-free", "ENIG", "ENEPIG", "Hard gold", "Immersion tin",
            "Immersion nickel", "Immersion silver", "OSP", "HT_OSP", "User defined")


def _cu(name, thickness):
    return {"type": "copper", "name": name, "thickness": thickness}


def _dielectric(kind, thickness, material, epsilon_r):
    return {"type": kind, "thickness": thickness, "material": material, "epsilon_r": epsilon_r}


def _prepreg_7628(thickness):
    return _dielectric("prepreg", thickness, "FR4 7628", 4.4)


def _core(thickness):
    return _dielectric("core", thickness, "FR4", 4.6)


STACKUPS = {
    2: {"source": f"JLCPCB 2-layer 1.6 mm: FR-4 er 4.5, 1 oz outer copper ({JLCPCB_CAPABILITIES}, read "
                  f"{STACKUP_CHECKED}); core 1.51 mm derived so the stack adds up to 1.6 mm",
        "layers": [_cu("F.Cu", OUTER_CU), _dielectric("core", 1.51, "FR4", 4.5), _cu("B.Cu", OUTER_CU)]},
    4: {"source": f"JLCPCB JLC04161H-7628 ({JLCPCB_IMPEDANCE}, read {STACKUP_CHECKED})",
        "layers": [_cu("F.Cu", OUTER_CU), _prepreg_7628(0.2104), _cu("In1.Cu", INNER_CU), _core(1.065),
                   _cu("In2.Cu", INNER_CU), _prepreg_7628(0.2104), _cu("B.Cu", OUTER_CU)]},
    6: {"source": f"JLCPCB JLC06161H-7628 ({JLCPCB_IMPEDANCE}, read {STACKUP_CHECKED})",
        "layers": [_cu("F.Cu", OUTER_CU), _prepreg_7628(0.2104), _cu("In1.Cu", INNER_CU), _core(0.4),
                   _cu("In2.Cu", INNER_CU), _prepreg_7628(0.2028), _cu("In3.Cu", INNER_CU), _core(0.4),
                   _cu("In4.Cu", INNER_CU), _prepreg_7628(0.2104), _cu("B.Cu", OUTER_CU)]},
}
DEFAULTS = {"finish": "ENIG", "mask_color": "Green", "silk_color": "White", "mask_thickness": MASK}


def copper_names(layers):
    """KiCad's copper layer names, top to bottom: F.Cu, In1.Cu ... B.Cu."""
    return ["F.Cu"] + [f"In{i}.Cu" for i in range(1, layers - 1)] + ["B.Cu"]


def stackup_for(layers, thickness, override=None):
    """The stack-up a board of ``layers`` copper layers and ``thickness`` mm gets: JLCPCB's standard
    one for 1.6 mm, with ``override`` (``Board.stackup``) on top. Raises ValueError when there is no
    published stack-up for the board, or when the result is not a valid stack for it.

    >>> [r["name"] for r in stackup_for(4, 1.6)["layers"] if r["type"] == "copper"]
    ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
    """
    override = dict(override or {})
    unknown = sorted(set(override) - {"layers", "source", *DEFAULTS})
    if unknown:
        raise ValueError(f"stack-up: unknown option(s) {unknown}")
    if "layers" in override:
        if not override.get("source"):
            raise ValueError("stack-up: a design's own layer list needs a source (the fab's published stack-up)")
        out = {"source": override["source"], "layers": copy.deepcopy(override["layers"])}
    elif layers in STACKUPS and abs(thickness - 1.6) < 1e-9:
        out = copy.deepcopy(STACKUPS[layers])
    else:
        raise ValueError(f"stack-up: no published standard stack-up for {layers} layers at {thickness} mm; "
                         "give one with the design's stackup option")
    for key, value in DEFAULTS.items():
        out[key] = override.get(key, value)
    if "source" in override and "layers" not in override:
        out["source"] = override["source"]
    check_stackup(out, layers, thickness)
    return out


def check_stackup(stackup, layers, thickness):
    """Refuse a stack-up whose copper is not this board's, top to bottom, with one dielectric between
    each pair of copper layers, or whose total misses the board's thickness by more than the fab's
    tolerance."""
    rows = stackup["layers"]
    copper = [r.get("name") for r in rows if r.get("type") == "copper"]
    if copper != copper_names(layers):
        raise ValueError(f"stack-up: copper layers {copper}, but the board has {copper_names(layers)}")
    kinds = ["copper" if r.get("type") == "copper" else "dielectric" for r in rows]
    if kinds != ["copper", "dielectric"] * (layers - 1) + ["copper"]:
        raise ValueError(f"stack-up: rows must alternate copper and dielectric, top and bottom copper: {kinds}")
    for r in rows:
        if r["type"] not in ("copper", "core", "prepreg"):
            raise ValueError(f"stack-up: row type {r['type']!r}; use copper, core or prepreg")
        if not r.get("thickness", 0) > 0:
            raise ValueError(f"stack-up: row {r} has no thickness")
        if r["type"] != "copper" and not (r.get("material") and r.get("epsilon_r", 0) > 1):
            raise ValueError(f"stack-up: dielectric row {r} needs a material and its epsilon_r")
    if stackup["finish"] not in FINISHES:
        raise ValueError(f"stack-up: finish {stackup['finish']!r} is not one of KiCad's: {FINISHES}")
    total = stackup_thickness(stackup)
    if abs(total - thickness) > TOLERANCE * thickness:
        raise ValueError(f"stack-up: adds up to {total:.4f} mm, outside {thickness} mm +-{TOLERANCE:.0%}")


def stackup_thickness(stackup):
    """Copper, dielectrics and both solder masks, in mm."""
    return sum(r["thickness"] for r in stackup["layers"]) + 2 * stackup["mask_thickness"]


def _num(value):
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _q(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def stackup_text(stackup):
    """The board setup's ``(stackup ...)`` node, as KiCad writes it (it reformats the node when it
    next saves the board)."""
    mask = _num(stackup["mask_thickness"])
    lines = ["(stackup",
             f'\t(layer "F.SilkS" (type "Top Silk Screen") (color {_q(stackup["silk_color"])}))',
             '\t(layer "F.Paste" (type "Top Solder Paste"))',
             f'\t(layer "F.Mask" (type "Top Solder Mask") (color {_q(stackup["mask_color"])}) (thickness {mask}))']
    n = 0
    for r in stackup["layers"]:
        if r["type"] == "copper":
            lines.append(f'\t(layer {_q(r["name"])} (type "copper") (thickness {_num(r["thickness"])}))')
        else:
            n += 1
            lines.append(f'\t(layer "dielectric {n}" (type {_q(r["type"])}) (thickness {_num(r["thickness"])}) '
                         f'(material {_q(r["material"])}) (epsilon_r {_num(r["epsilon_r"])}))')
    lines += [f'\t(layer "B.Mask" (type "Bottom Solder Mask") (color {_q(stackup["mask_color"])}) (thickness {mask}))',
              '\t(layer "B.Paste" (type "Bottom Solder Paste"))',
              f'\t(layer "B.SilkS" (type "Bottom Silk Screen") (color {_q(stackup["silk_color"])}))',
              f'\t(copper_finish {_q(stackup["finish"])})',
              "\t(dielectric_constraints no)",
              ")"]
    return "\n".join(lines)


def insert_stackup(board_text, stackup):
    """``board_text`` (a saved ``.kicad_pcb``) with ``stackup`` as the first item of its setup.
    KiCad 10's Python does not wrap the board's stack-up object (its BOARD_STACKUP comes back as an
    opaque pointer), so the generator writes the node into the saved file; KiCad keeps it through every
    later load and save."""
    if board_text.count("(setup\n") != 1 or "(stackup" in board_text:
        raise ValueError("expected one (setup and no (stackup in the saved board")
    head, tail = board_text.split("(setup\n", 1)
    indent = tail[:len(tail) - len(tail.lstrip("\t"))]
    block = "\n".join(indent + line for line in stackup_text(stackup).split("\n"))
    return head + "(setup\n" + block + "\n" + tail
