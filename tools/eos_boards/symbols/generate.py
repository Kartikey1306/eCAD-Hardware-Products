"""Write the symbols KiCad's own libraries do not have.

EoS_Connectors.kicad_sym: KiCad's generic double-row connectors stop at 2x40, and the Raspberry Pi
Compute Module 5 needs two 100-pin (2x50) connectors. The symbol follows KiCad's
Conn_02xNN_Odd_Even layout exactly: odd pins on the left, even pins on the right, 2.54 mm apart,
passive.

EoS_Parts.kicad_sym: a flow-through TPD4EUSB30 (see its docstring).

EoS_Sensors.kicad_sym: the Analog Devices ADT7410 temperature sensor (SOIC-8), which KiCad doesn't ship.

EoS_MCU.kicad_sym: the TI TM4C123GH6PM (LQFP-64). KiCad ships only the TM4C1230/1231, which lack USB;
the pins follow TI SPMS376E Table 23-2 and agree pin for pin with KiCad's TM4C1231H6PM.
It also holds the NXP LPC55S69JBD100 (HLQFP-100, exposed pad as pin 101), pins from the LPC55S6x data
sheet Rev. 2.5, Table 3, which KiCad doesn't ship.
And the Renesas R7FA2E1A92DFM (RA2E1, LQFP-64), pins from the RA2E1 data sheet R01DS0386EJ0170
Rev. 1.70, Table 1.15; KiCad has no RA-family symbol.

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


def tm4c123gh6pm() -> list:
    """TI TM4C123GH6PM, 64-pin LQFP (PM). Pins as TI SPMS376E, Table 23-2 (Signals by Pin Number),
    names with each pin's fixed function from Table 10-2: GPIOs on the right by port (A to D) and
    on the left (E, F), with reset, both oscillators and the hibernation pins; supplies on top
    (VDD 11/26/42/54, VDDA 2, VDDC 25/56), grounds below (GND 12/27/39/55, GNDA 3, GNDX 35)."""
    name = "TM4C123GH6PM"
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -17.78, 45.72], [Sym("end"), 17.78, -45.72],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]
    io = "bidirectional"
    # (number, name, type); None leaves a gap of one row
    left = [("38", "~{RST}", "input"), None,
            ("40", "OSC0", "passive"), ("41", "OSC1", "passive"), None,
            ("34", "XOSC0", "passive"), ("36", "XOSC1", "passive"), None,
            ("32", "~{WAKE}", "input"), ("33", "~{HIB}", "output"), ("37", "VBAT", "power_in"), None,
            ("9", "PE0/AIN3", io), ("8", "PE1/AIN2", io), ("7", "PE2/AIN1", io), ("6", "PE3/AIN0", io),
            ("59", "PE4/AIN9", io), ("60", "PE5/AIN8", io), None,
            ("28", "PF0/NMI", io), ("29", "PF1", io), ("30", "PF2", io), ("31", "PF3", io), ("5", "PF4", io)]
    right = [("17", "PA0/U0RX", io), ("18", "PA1/U0TX", io), ("19", "PA2", io), ("20", "PA3", io),
             ("21", "PA4", io), ("22", "PA5", io), ("23", "PA6", io), ("24", "PA7", io), None,
             ("45", "PB0/USB0ID", io), ("46", "PB1/USB0VBUS", io), ("47", "PB2", io), ("48", "PB3", io),
             ("58", "PB4/AIN10", io), ("57", "PB5/AIN11", io), ("1", "PB6", io), ("4", "PB7", io), None,
             ("52", "PC0/TCK/SWCLK", io), ("51", "PC1/TMS/SWDIO", io), ("50", "PC2/TDI", io),
             ("49", "PC3/TDO/SWO", io), ("16", "PC4", io), ("15", "PC5", io), ("14", "PC6", io), ("13", "PC7", io), None,
             ("61", "PD0/AIN7", io), ("62", "PD1/AIN6", io), ("63", "PD2/AIN5", io), ("64", "PD3/AIN4", io),
             ("43", "PD4/USB0DM", io), ("44", "PD5/USB0DP", io), ("53", "PD6", io), ("10", "PD7/NMI", io)]
    top = [("11", "VDD"), ("26", "VDD"), ("42", "VDD"), ("54", "VDD"), ("2", "VDDA"), ("25", "VDDC"), ("56", "VDDC")]
    bottom = [("12", "GND"), ("27", "GND"), ("39", "GND"), ("55", "GND"), ("3", "GNDA"), ("35", "GNDX")]

    def pin(number, label, kind, x, y, angle):
        return [Sym("pin"), Sym(kind), Sym("line"), [Sym("at"), x, y, angle], [Sym("length"), 2.54],
                [Sym("name"), label, _font()], [Sym("number"), number, _font()]]

    for column, x, angle in ((left, -20.32, 0), (right, 20.32, 180)):
        for row, entry in enumerate(column):
            if entry is not None:
                body.append(pin(*entry, x, round(43.18 - 2.54 * row, 2), angle))
    for k, (number, label) in enumerate(top):
        body.append(pin(number, label, "power_in", round(-7.62 + 2.54 * k, 2), 48.26, 270))
    for k, (number, label) in enumerate(bottom):
        body.append(pin(number, label, "power_in", round(-6.35 + 2.54 * k, 2), -48.26, 90))
    return [Sym("symbol"), name, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "U", 0, 50.8), _prop("Value", name, 0, -50.8),
            _prop("Footprint", "Package_QFP:LQFP-64_10x10mm_P0.5mm", 0, 0, True),
            _prop("Datasheet", "https://www.ti.com/lit/ds/symlink/tm4c123gh6pm.pdf", 0, 0, True),
            _prop("Description", "Tiva C Arm Cortex-M4F MCU, 80 MHz, 256 kB flash, 32 kB SRAM, 2 kB EEPROM, USB 2.0 "
                                 "full speed, hibernation module, LQFP-64 (TI SPMS376E)", 0, 0, True),
            body]


# --- pin table: (number, name, KiCad electrical type), NXP LPC55S6x data sheet Rev. 2.5 Table 3 ---
LPC55_PIO0 = {0: 54, 1: 7, 2: 81, 3: 83, 4: 86, 5: 88, 6: 89, 7: 6, 8: 26, 9: 55, 10: 21, 11: 13, 12: 12, 13: 71,
        14: 72, 15: 22, 16: 14, 17: 8, 18: 56, 19: 90, 20: 74, 21: 76, 22: 78, 23: 20, 24: 70, 25: 79, 26: 60,
        27: 27, 28: 66, 29: 92, 30: 94, 31: 23}
LPC55_PIO1 = {0: 11, 1: 59, 2: 61, 3: 62, 4: 1, 5: 31, 6: 5, 7: 9, 8: 24, 9: 10, 10: 40, 11: 93, 12: 67, 13: 2,
        14: 57, 15: 82, 16: 87, 17: 43, 18: 64, 19: 58, 20: 4, 21: 30, 22: 41, 23: 42, 24: 3, 25: 77, 26: 68,
        27: 85, 28: 73, 29: 80, 30: 65, 31: 91}
LPC55_TOP = [  # supplies, drawn along the top edge
    ("15", "VDD"), ("25", "VDD"), ("44", "VDD"), ("63", "VDD"), ("69", "VDD"), ("75", "VDD"), ("84", "VDD"),
    ("95", "VDD"), ("100", "VDD"), ("16", "VDDA"), ("17", "VREFP"), ("49", "VBAT_DCDC"), ("50", "VBAT_DCDC"),
    ("51", "VBAT_PMU"), ("96", "USB0_3V3"), ("38", "USB1_3V3"), ("39", "VDD_PMU"), ("45", "FB"),
]
LPC55_BOTTOM = [  # DC-DC switch node, reset, oscillators, USB, then every ground
    ("48", "LX"), ("32", "RESETN"), ("29", "XTAL32M_P"), ("28", "XTAL32M_N"), ("52", "XTAL32K_P"),
    ("53", "XTAL32K_N"), ("97", "USB0_DP"), ("98", "USB0_DM"), ("34", "USB1_DP"), ("35", "USB1_DM"),
    ("36", "USB1_VBUS"), ("101", "VSS"), ("19", "VSSA"), ("18", "VREFN"), ("46", "VSS_DCDC"), ("47", "VSS_DCDC"),
    ("99", "USB0_VSS"), ("33", "USB1_VSS"), ("37", "USB1_VSS"),
]
LPC55_ETYPE = {"FB": "input", "LX": "power_out", "RESETN": "input", "XTAL32M_P": "input", "XTAL32M_N": "output",
         "XTAL32K_P": "input", "XTAL32K_N": "output", "USB0_DP": "bidirectional", "USB0_DM": "bidirectional",
         "USB1_DP": "bidirectional", "USB1_DM": "bidirectional", "USB1_VBUS": "input"}

LPC55_FOOTPRINT = "EoS_Packages:HLQFP-100-1EP_14x14mm_P0.5mm_EP3.21x3.21mm"
LPC55_DATASHEET = "https://www.nxp.com/docs/en/data-sheet/LPC55S6x.pdf"


def lpc55s69jbd100() -> list:
    """NXP LPC55S69JBD100, HLQFP-100 (SOT1570-3) with exposed pad (pin 101, VSS). Pins as the
    LPC55S6x data sheet Rev. 2.5, Table 3 (100-pin HLQFP column): PIO0_0-31 on the left, PIO1_0-31
    on the right, supplies along the top, and the DC-DC node, reset, oscillators, USB and grounds
    along the bottom."""
    name = "LPC55S69JBD100"
    left = [(str(LPC55_PIO0[i]), f"PIO0_{i}") for i in range(32)]
    right = [(str(LPC55_PIO1[i]), f"PIO1_{i}") for i in range(32)]
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -27.94, 43.18], [Sym("end"), 27.94, -45.72],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]

    def pin(kind, x, y, angle, label, number):
        return [Sym("pin"), Sym(kind), Sym("line"), [Sym("at"), x, y, angle], [Sym("length"), 2.54],
                [Sym("name"), label, _font()], [Sym("number"), number, _font()]]

    for k, (number, label) in enumerate(left):
        body.append(pin("bidirectional", -30.48, round(38.1 - 2.54 * k, 2), 0, label, number))
    for k, (number, label) in enumerate(right):
        body.append(pin("bidirectional", 30.48, round(38.1 - 2.54 * k, 2), 180, label, number))
    for k, (number, label) in enumerate(LPC55_TOP):
        body.append(pin(LPC55_ETYPE.get(label, "power_in"), round(-22.86 + 2.54 * k, 2), 45.72, 270, label, number))
    for k, (number, label) in enumerate(LPC55_BOTTOM):
        body.append(pin(LPC55_ETYPE.get(label, "power_in"), round(-22.86 + 2.54 * k, 2), -48.26, 90, label, number))
    return [Sym("symbol"), name, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "U", 0, 46.99), _prop("Value", name, 0, -52.07),
            _prop("Footprint", LPC55_FOOTPRINT, 0, 0, True),
            _prop("Datasheet", LPC55_DATASHEET, 0, 0, True),
            _prop("Description", "Dual Arm Cortex-M33 MCU, 150 MHz, 640 KB flash, 320 KB SRAM, USB FS + HS, "
                                 "HLQFP-100 with exposed pad (VSS)", 0, 0, True),
            body]


def _check_lpc55s69() -> None:
    """Every HLQFP-100 pin 1-100, plus the pad (101), exactly once."""
    numbers = [str(n) for n in LPC55_PIO0.values()] + [str(n) for n in LPC55_PIO1.values()] + [n for n, _ in LPC55_TOP + LPC55_BOTTOM]
    assert len(numbers) == 101, len(numbers)
    assert sorted(numbers, key=int) == [str(n) for n in range(1, 102)], sorted(set(range(1, 102)) - {int(n) for n in numbers})

# --- pin table: (number, name, KiCad electrical type), Renesas R01DS0386EJ0170 Table 1.15, LQFP 64 ---
_IO = "bidirectional"
RA2E1_LEFT = [  # system pins and oscillators, then port 0 (the ADC pins), port 4, port 5; None leaves a row free
    ("25", "~{RES}", "input"), ("26", "P201/MD", _IO), ("27", "P200/NMI", "input"), None,
    ("10", "P212/EXTAL", _IO), ("9", "P213/XTAL", _IO), None,
    ("6", "P215/XCIN", "passive"), ("7", "P214/XCOUT", "passive"), None,
    ("64", "P000", _IO), ("63", "P001", _IO), ("62", "P002", _IO), ("61", "P003", _IO), ("60", "P004", _IO),
    ("59", "P010/VREFH0", "passive"), ("58", "P011/VREFL0", "passive"), ("55", "P012", _IO), ("54", "P013", _IO),
    ("53", "P014", _IO), ("52", "P015", _IO), None,
    ("1", "P400", _IO), ("2", "P401", _IO), ("3", "P402", _IO), ("4", "P403", _IO), ("16", "P407", _IO),
    ("15", "P408", _IO), ("14", "P409", _IO), ("13", "P410", _IO), ("12", "P411", _IO), None,
    ("49", "P500", _IO), ("50", "P501", _IO), ("51", "P502", _IO),
]
RA2E1_RIGHT = [  # port 1 (with SWDIO), port 2, port 3 (with SWCLK), port 9
    ("48", "P100", _IO), ("47", "P101", _IO), ("46", "P102", _IO), ("45", "P103", _IO), ("44", "P104", _IO),
    ("43", "P105", _IO), ("42", "P106", _IO), ("41", "P107", _IO), ("33", "P108/SWDIO", _IO), ("34", "P109", _IO),
    ("35", "P110", _IO), ("36", "P111", _IO), ("37", "P112", _IO), ("38", "P113", _IO), None,
    ("24", "P204", _IO), ("23", "P205", _IO), ("22", "P206", _IO), ("21", "P207", _IO), ("20", "P208", _IO), None,
    ("32", "P300/SWCLK", _IO), ("31", "P301", _IO), ("30", "P302", _IO), ("29", "P303", _IO), ("28", "P304", _IO), None,
    ("19", "P913", _IO), ("18", "P914", _IO), ("17", "P915", _IO),
]
RA2E1_TOP = [("11", "VCC", "power_in"), ("39", "VCC", "power_in"), ("56", "AVCC0", "power_in"), ("5", "VCL", "power_out")]
RA2E1_BOTTOM = [("8", "VSS", "power_in"), ("40", "VSS", "power_in"), ("57", "AVSS0", "power_in")]

RA2E1_FOOTPRINT = "Package_QFP:LQFP-64_10x10mm_P0.5mm"
RA2E1_DATASHEET = "https://www.renesas.com/en/document/dst/ra2e1-group-datasheet"


def r7fa2e1a92dfm() -> list:
    """Renesas R7FA2E1A92DFM, RA2E1 Group, 64-pin LQFP 10 x 10 mm, 0.5 mm pitch (PLQP0064KB-C or
    PLQP0064KL-A). Pins as R01DS0386EJ0170 Rev.1.70, Table 1.15 (LQFP/QFN 64-pin column), names as
    Figure 1.3: reset, mode, NMI, both oscillators and ports 0, 4 and 5 on the left; ports 1, 2, 3 and
    9 on the right; VCC (11, 39), AVCC0 (56) and VCL (5) on top; VSS (8, 40) and AVSS0 (57) below."""
    name = "R7FA2E1A92DFM"
    body = [Sym("symbol"), f"{name}_1_1",
            [Sym("rectangle"), [Sym("start"), -17.78, 45.72], [Sym("end"), 17.78, -45.72],
             [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]], [Sym("fill"), [Sym("type"), Sym("background")]]]]

    def pin(number, label, kind, x, y, angle):
        return [Sym("pin"), Sym(kind), Sym("line"), [Sym("at"), x, y, angle], [Sym("length"), 2.54],
                [Sym("name"), label, _font()], [Sym("number"), number, _font()]]

    for column, x, angle in ((RA2E1_LEFT, -20.32, 0), (RA2E1_RIGHT, 20.32, 180)):
        for row, entry in enumerate(column):
            if entry is not None:
                body.append(pin(*entry, x, round(43.18 - 2.54 * row, 2), angle))
    for k, (number, label, kind) in enumerate(RA2E1_TOP):
        body.append(pin(number, label, kind, round(-3.81 + 2.54 * k, 2), 48.26, 270))
    for k, (number, label, kind) in enumerate(RA2E1_BOTTOM):
        body.append(pin(number, label, kind, round(-2.54 + 2.54 * k, 2), -48.26, 90))
    return [Sym("symbol"), name, [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            _prop("Reference", "U", 0, 50.8), _prop("Value", name, 0, -50.8),
            _prop("Footprint", RA2E1_FOOTPRINT, 0, 0, True),
            _prop("Datasheet", RA2E1_DATASHEET, 0, 0, True),
            _prop("Description", "Renesas RA2E1 Arm Cortex-M23 MCU, 48 MHz, 128 KB code flash, 4 KB data flash, "
                                 "16 KB SRAM, 1.6-5.5 V, -40 to +85 C, LQFP-64 10 x 10 mm (R01DS0386)", 0, 0, True),
            body]


def _check_ra2e1() -> None:
    """Every LQFP-64 pin 1-64 exactly once."""
    entries = [e for e in RA2E1_LEFT + RA2E1_RIGHT if e is not None] + RA2E1_TOP + RA2E1_BOTTOM
    numbers = [e[0] for e in entries]
    assert len(numbers) == 64, len(numbers)
    assert sorted(numbers, key=int) == [str(n) for n in range(1, 65)], sorted(set(range(1, 65)) - {int(n) for n in numbers})


def main() -> int:
    _check_lpc55s69()
    _check_ra2e1()
    for file, symbols in (("EoS_Connectors", [double_row(50)]), ("EoS_Parts", [tpd4eusb30_flow_through()]),
                          ("EoS_Sensors", [adt7410()]), ("EoS_MCU", [tm4c123gh6pm(), lpc55s69jbd100(), r7fa2e1a92dfm()])):
        lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20231120], [Sym("generator"), "eos_boards"], *symbols]
        out = HERE / f"{file}.kicad_sym"
        out.write_text(dumps(lib) + "\n")
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
