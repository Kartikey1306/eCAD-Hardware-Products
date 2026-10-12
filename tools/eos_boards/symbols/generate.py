"""Write the symbols KiCad's own libraries do not have.

EoS_Connectors.kicad_sym: KiCad's generic double-row connectors stop at 2x40, and the Raspberry Pi
Compute Module 5 needs two 100-pin (2x50) connectors. The symbol follows KiCad's
Conn_02xNN_Odd_Even layout exactly: odd pins on the left, even pins on the right, 2.54 mm apart,
passive.

EoS_Parts.kicad_sym: a flow-through TPD4EUSB30 (see its docstring).

EoS_Sensors.kicad_sym: the Analog Devices ADT7410 temperature sensor (SOIC-8), which KiCad doesn't ship.

usage: python3 tools/eos_boards/symbols/generate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from eos_boards.sexpr import Sym, dumps  # noqa: E402


def _font():
    return [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]


def _prop(key, value, x, y, hide=False):
    node = [Sym("property"), key, value, [Sym("at"), x, y, 0]]
    eff = _font()
    if hide:
        eff.append([Sym("hide"), Sym("yes")])
    node.append(eff)
    return node


def double_row(rows: int) -> list:
    name = f"Conn_02x{rows:02d}_Odd_Even"
    top = round(2.54 * (rows // 2 - 1), 2)
    bottom = round(top - 2.54 * (rows - 1), 2)
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -1.27, round(top + 1.27, 2)], [Sym("end"), 3.81, round(bottom - 1.27, 2)],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]
    for k in range(rows):
        y = round(top - 2.54 * k, 2)
        for number, x, angle in ((2 * k + 1, -5.08, 0), (2 * k + 2, 7.62, 180)):
            body.append([Sym("pin"), Sym("passive"), Sym("line"), [Sym("at"), x, y, angle], [Sym("length"), 3.81],
                         [Sym("name"), f"Pin_{number}", _font()], [Sym("number"), str(number), _font()]])
    return [Sym("symbol"), name, [Sym("pin_names"), [Sym("offset"), 1.016], [Sym("hide"), Sym("yes")]],
            [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "J", 1.27, round(top + 2.54, 2)), _prop("Value", name, 1.27, round(bottom - 2.54, 2)),
            _prop("Footprint", "", 0, 0, True), _prop("Datasheet", "", 0, 0, True),
            _prop("Description", f"Generic connector, double row, 02x{rows:02d}, odd/even pin numbering "
                                 "(row 1 odd numbers, row 2 even numbers), laid out as KiCad's own", 0, 0, True),
            body]


def tpd4eusb30_flow_through() -> list:
    """TI TPD4EUSB30 drawn for flow-through routing, as TI lays it out: each line enters one side
    of the package and leaves from the pad opposite (1/10, 2/9, 4/7, 5/6). KiCad's own symbol
    marks the far-side pads no-connect, so a line could not pass through."""
    name = "TPD4EUSB30_FlowThrough"
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -5.08, 7.62], [Sym("end"), 5.08, -7.62],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]
    rows = [("1", "D1+", "10"), ("2", "D1-", "9"), ("4", "D2+", "7"), ("5", "D2-", "6")]
    for k, (left, label, right) in enumerate(rows):
        y = round(5.08 - 2.54 * k - (2.54 if k >= 2 else 0), 2)
        body.append([Sym("pin"), Sym("passive"), Sym("line"), [Sym("at"), -7.62, y, 0], [Sym("length"), 2.54],
                     [Sym("name"), label, _font()], [Sym("number"), left, _font()]])
        body.append([Sym("pin"), Sym("passive"), Sym("line"), [Sym("at"), 7.62, y, 180], [Sym("length"), 2.54],
                     [Sym("name"), label, _font()], [Sym("number"), right, _font()]])
    for number, x in (("3", -1.27), ("8", 1.27)):
        body.append([Sym("pin"), Sym("power_in"), Sym("line"), [Sym("at"), x, -10.16, 90], [Sym("length"), 2.54],
                     [Sym("name"), "GND", _font()], [Sym("number"), number, _font()]])
    return [Sym("symbol"), name, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "U", 0, 8.89), _prop("Value", "TPD4EUSB30", 0, -12.7),
            _prop("Footprint", "Package_SON:USON-10_2.5x1.0mm_P0.5mm", 0, 0, True),
            _prop("Datasheet", "https://www.ti.com/lit/ds/symlink/tpd4eusb30.pdf", 0, 0, True),
            _prop("Description", "4-channel ESD protection, flow-through: each line enters one pad and leaves the pad "
                                 "opposite (1/10, 2/9, 4/7, 5/6)", 0, 0, True),
            body]


def adt7410() -> list:
    """Analog Devices ADT7410, SOIC-8: pins as its data sheet (Rev. C, Table 4): 1 SCL, 2 SDA,
    3 A0, 4 A1, 5 INT (open drain), 6 CT (open drain), 7 GND, 8 VDD."""
    name = "ADT7410"
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -7.62, 5.08], [Sym("end"), 7.62, -7.62],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]
    left = [("1", "SCL", "input", 2.54), ("2", "SDA", "bidirectional", 0.0),
            ("3", "A0", "input", -2.54), ("4", "A1", "input", -5.08)]
    right = [("5", "INT", "open_collector", 2.54), ("6", "CT", "open_collector", 0.0)]
    for number, label, kind, y in left:
        body.append([Sym("pin"), Sym(kind), Sym("line"), [Sym("at"), -10.16, y, 0], [Sym("length"), 2.54],
                     [Sym("name"), label, _font()], [Sym("number"), number, _font()]])
    for number, label, kind, y in right:
        body.append([Sym("pin"), Sym(kind), Sym("line"), [Sym("at"), 10.16, y, 180], [Sym("length"), 2.54],
                     [Sym("name"), label, _font()], [Sym("number"), number, _font()]])
    body.append([Sym("pin"), Sym("power_in"), Sym("line"), [Sym("at"), 0, 7.62, 270], [Sym("length"), 2.54],
                 [Sym("name"), "VDD", _font()], [Sym("number"), "8", _font()]])
    body.append([Sym("pin"), Sym("power_in"), Sym("line"), [Sym("at"), 0, -10.16, 90], [Sym("length"), 2.54],
                 [Sym("name"), "GND", _font()], [Sym("number"), "7", _font()]])
    return [Sym("symbol"), name, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "U", 0, 10.16), _prop("Value", name, 0, -12.7),
            _prop("Footprint", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 0, 0, True),
            _prop("Datasheet", "https://www.analog.com/media/en/technical-documentation/data-sheets/ADT7410.pdf", 0, 0, True),
            _prop("Description", "16-bit digital I2C temperature sensor, +-0.5 C, SOIC-8", 0, 0, True),
            body]


def main() -> int:
    for file, symbols in (("EoS_Connectors", [double_row(50)]), ("EoS_Parts", [tpd4eusb30_flow_through()]),
                          ("EoS_Sensors", [adt7410()])):
        lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20231120], [Sym("generator"), "eos_boards"], *symbols]
        out = HERE / f"{file}.kicad_sym"
        out.write_text(dumps(lib) + "\n")
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
