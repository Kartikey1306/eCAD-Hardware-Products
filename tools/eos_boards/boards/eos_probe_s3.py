"""EoS Probe S3: an ESP32-S3 debug probe, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-probe-s3/LICENSE.txt.

A USB-C probe for Arm SWD/JTAG targets and their UART. It speaks to the target at the target's
own I/O voltage (1.65-5.5 V, read from VTref), through one SN74LVC1T45 per line. Every value
follows the part's datasheet:

* ESP32-S3-WROOM-1 (Espressif datasheet, section 9 "Peripheral Schematics"): 22 uF and 0.1 uF
  on 3V3. EN gets the recommended RC delay of R = 10 kohm and C = 1 uF, plus a reset button.
  The boot button pulls IO0 (a strapping pin with a weak internal pull-up) to GND. USB D-/D+ go
  to IO19/IO20 through the 0 ohm positions Espressif shows. The supply must deliver at least
  0.5 A at 3.0-3.6 V. The strapping pins IO3, IO45 and IO46 are left unconnected so they keep
  their defaults. IO26-IO32 (the module's flash and PSRAM) are not used, nor IO33-IO37, which
  octal-PSRAM variants of the module take.
* AP7361C-33 LDO, 1 A (Diodes Inc.): input 2.2-6.0 V, so 5 V USB is in range; 4.7 uF on input
  and output, as its typical application shows (at least 1 uF and 2.2 uF are required).
* SN74LVC1T45 (TI SCES515): VCCA = 3.3 V on the ESP32-S3 side, VCCB = VTref on the target side.
  DIR high sends A to B; DIR is referenced to VCCA. If either supply is off, both ports go
  high-impedance, so an unpowered target is never driven. TI notes the data inputs are always
  active, so every input that could float gets a 100 kohm pull: on the target side when nothing
  is plugged in, and on the ESP32-S3 side while it boots. 0.1 uF on each VCC.
* SWDIO is the one bidirectional line: IO10 sets its direction, and it defaults to "read"
  (pulled low) so the probe never drives the target at power-up.
* nRESET is open-drain, through a 2N7002 that is held off at power-up.
* VTref is halved by 100 kohm / 100 kohm into IO1 (ADC1_CH0), so the probe can read the target
  voltage: 5.5 V reads as 2.75 V.

USB: USB-C as a 5 V sink (5.1 kohm on CC1 and CC2), USBLC6-2SC6 ESD protection, and a 500 mA
polyfuse. Target connector: the Arm 10-pin Cortex Debug header (1.27 mm). Target UART: 1x4,
2.54 mm (VTref, TX, RX, GND).
"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LVC = "Logic_LevelTranslator:SN74LVC1T45DBV"


def res(ref, value, a, b, sch, desc=None):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b},
                fields={"Description": desc or f"Resistor {value} 1% 0402"})


def cap(ref, value, a, b, sch, desc, fp=C0402):
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields={"Description": desc})


def shifter(ref, a, b, direction, sch, what):
    """One SN74LVC1T45: A on the ESP32-S3 side (3.3 V), B on the target side (VTref)."""
    return Part(ref, LVC, "SN74LVC1T45", "Package_TO_SOT_SMD:SOT-23-6", sch,
                {"VCCA": "+3V3", "VCCB": "VTREF", "GND": "GND", "A": a, "B": b, "DIR": direction},
                fields={"Manufacturer": "Texas Instruments", "MPN": "SN74LVC1T45DBVR",
                        "Description": f"Level translator, {what}"})


W, H = 62.0, 30.0

PARTS = [
    # ---- USB-C, protection, 3.3 V --------------------------------------------------------------
    Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (50, 110), {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_D+", "D-": "USB_D-",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12", "Description": "USB-C 2.0 receptacle, 16 pins"}),
    res("R1", "5.1k", "CC1", "GND", (90, 95), "Resistor 5.1 kohm 1% 0402 (USB-C sink, CC1)"),
    res("R2", "5.1k", "CC2", "GND", (105, 95), "Resistor 5.1 kohm 1% 0402 (USB-C sink, CC2)"),
    Part("U1", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6", (140, 110),
         {"I/O1": "USB_D+", "I/O2": "USB_D-", "GND": "GND", "VBUS": "VBUS"},
         fields={"Manufacturer": "STMicroelectronics", "MPN": "USBLC6-2SC6", "Description": "USB ESD protection"}),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (175, 95), {"1": "VBUS", "2": "+5V"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR", "Description": "PTC resettable fuse 500 mA hold, 1206"}),
    Part("U2", "Regulator_Linear:AP7361C-33E", "AP7361C-33", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (205, 110),
         {"VI": "+5V", "VO": "+3V3", "GND": "GND"},
         fields={"Manufacturer": "Diodes Incorporated", "MPN": "AP7361C-33E-13", "Description": "LDO 3.3 V 1 A, SOT-223"}),
    cap("C1", "4.7u", "+5V", "GND", (230, 105), "Capacitor 4.7 uF 10 V X5R 0805 (LDO input)", C0805),
    cap("C2", "4.7u", "+3V3", "GND", (245, 105), "Capacitor 4.7 uF 10 V X5R 0805 (LDO output)", C0805),
    res("R3", "1k", "+3V3", "LED_PWR_A", (265, 105), "Resistor 1 kohm 1% 0402 (power LED)"),
    Part("D1", "Device:LED_Small", "PWR", "LED_SMD:LED_0603_1608Metric", (280, 105), {"A": "LED_PWR_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LSURCK", "Description": "LED red 0603, power"}),

    # ---- ESP32-S3 ----------------------------------------------------------------------------------
    Part("U3", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N8R2", "RF_Module:ESP32-S3-WROOM-1", (150, 230),
         {"GND": "GND", "3V3": "+3V3", "EN": "EN", "IO0": "BOOT", "USB_D-": "ESP_D-", "USB_D+": "ESP_D+",
          "IO1": "VTREF_SENSE", "IO9": "SWO_A", "IO10": "SWDIO_DIR", "IO11": "SWDIO_A", "IO12": "SWCLK_A",
          "IO13": "TDI_A", "IO14": "NRESET_G", "IO15": "LED_STAT", "IO16": "LED_ACT", "IO17": "UART_TX_A",
          "IO18": "UART_RX_A", **{p: NC for p in ("IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "IO8", "IO21", "IO35",
                                                   "IO36", "IO37", "IO38", "IO39", "IO40", "IO41", "IO42", "IO45",
                                                   "IO46", "IO47", "IO48", "RXD0", "TXD0")}},
         fields={"Manufacturer": "Espressif", "MPN": "ESP32-S3-WROOM-1-N8R2",
                 "Description": "ESP32-S3 module, 8 MB flash, 2 MB PSRAM, PCB antenna"}),
    cap("C3", "22u", "+3V3", "GND", (205, 200), "Capacitor 22 uF 10 V X5R 0805 (module 3V3, Espressif C1)", C0805),
    cap("C4", "100n", "+3V3", "GND", (220, 200), "Capacitor 100 nF X7R 0402 (module 3V3, Espressif C3)"),
    res("R4", "10k", "EN", "+3V3", (205, 240), "Resistor 10 kohm 1% 0402 (EN RC delay, Espressif)"),
    cap("C5", "1u", "EN", "GND", (220, 240), "Capacitor 1 uF X7R 0402 (EN RC delay, Espressif)"),
    Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", (240, 250),
         {"1": "EN", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, reset (EN)"}),
    Part("SW2", "Switch:SW_Push", "BOOT", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", (240, 280),
         {"1": "BOOT", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, boot (IO0)"}),
    res("R5", "0", "USB_D-", "ESP_D-", (100, 200), "Resistor 0 ohm 0402 (USB D-, Espressif R6 position)"),
    res("R6", "0", "USB_D+", "ESP_D+", (100, 215), "Resistor 0 ohm 0402 (USB D+, Espressif R4 position)"),
    res("R7", "470", "LED_STAT", "LED_STAT_A", (205, 300), "Resistor 470 ohm 1% 0402 (status LED)"),
    Part("D2", "Device:LED_Small", "STAT", "LED_SMD:LED_0603_1608Metric", (220, 300), {"A": "LED_STAT_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LSYCK", "Description": "LED yellow 0603, status (IO15)"}),
    res("R8", "470", "LED_ACT", "LED_ACT_A", (205, 320), "Resistor 470 ohm 1% 0402 (activity LED)"),
    Part("D3", "Device:LED_Small", "ACT", "LED_SMD:LED_0603_1608Metric", (220, 320), {"A": "LED_ACT_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LSURCK", "Description": "LED red 0603, activity (IO16)"}),

    # ---- Level translators, one per line -------------------------------------------------------------
    shifter("U4", "SWCLK_A", "T_SWCLK", "+3V3", (330, 110), "SWCLK/TCK, probe to target"),
    shifter("U5", "SWDIO_A", "T_SWDIO", "SWDIO_DIR", (330, 160), "SWDIO/TMS, both ways (IO10 sets the direction)"),
    shifter("U6", "SWO_A", "T_SWO", "GND", (330, 210), "SWO/TDO, target to probe"),
    shifter("U7", "TDI_A", "T_TDI", "+3V3", (330, 260), "TDI, probe to target"),
    shifter("U8", "UART_TX_A", "T_UART_TX", "+3V3", (330, 310), "UART, probe TX to target RX"),
    shifter("U9", "UART_RX_A", "T_UART_RX", "GND", (330, 360), "UART, target TX to probe RX"),
    *[cap(f"C{6 + i}", "100n", "+3V3", "GND", (370, 105 + 50 * i), f"Capacitor 100 nF X7R 0402 (U{4 + i} VCCA)") for i in range(6)],
    *[cap(f"C{12 + i}", "100n", "VTREF", "GND", (385, 105 + 50 * i), f"Capacitor 100 nF X7R 0402 (U{4 + i} VCCB)") for i in range(6)],
    # inputs that could float: ESP32-S3 side while it boots, target side with nothing plugged in
    res("R9", "100k", "SWCLK_A", "GND", (300, 100), "Resistor 100 kohm 1% 0402 (SWCLK idles low)"),
    res("R10", "100k", "SWDIO_DIR", "GND", (300, 150), "Resistor 100 kohm 1% 0402 (SWDIO reads by default)"),
    res("R11", "100k", "SWDIO_A", "+3V3", (300, 170), "Resistor 100 kohm 1% 0402 (SWDIO idles high)"),
    res("R12", "100k", "TDI_A", "+3V3", (300, 250), "Resistor 100 kohm 1% 0402 (TDI idles high)"),
    res("R13", "100k", "UART_TX_A", "+3V3", (300, 300), "Resistor 100 kohm 1% 0402 (UART idles high)"),
    res("R14", "100k", "T_SWDIO", "VTREF", (410, 160), "Resistor 100 kohm 1% 0402 (target SWDIO idles high)"),
    res("R15", "100k", "T_SWO", "VTREF", (410, 210), "Resistor 100 kohm 1% 0402 (target SWO idles high)"),
    res("R16", "100k", "T_UART_RX", "VTREF", (410, 360), "Resistor 100 kohm 1% 0402 (target UART idles high)"),

    # ---- Target reset, VTref sense -------------------------------------------------------------------
    Part("Q1", "Transistor_FET:2N7002", "2N7002", "Package_TO_SOT_SMD:SOT-23", (450, 110),
         {"G": "NRESET_G", "S": "GND", "D": "T_NRESET"},
         fields={"Manufacturer": "Nexperia", "MPN": "2N7002,215", "Description": "N-MOSFET, target nRESET (open drain)"}),
    res("R17", "100k", "NRESET_G", "GND", (430, 120), "Resistor 100 kohm 1% 0402 (nRESET switch off at power-up)"),
    res("R18", "100k", "VTREF", "VTREF_SENSE", (450, 170), "Resistor 100 kohm 1% 0402 (VTref divider)"),
    res("R19", "100k", "VTREF_SENSE", "GND", (465, 170), "Resistor 100 kohm 1% 0402 (VTref divider)"),
    cap("C18", "100n", "VTREF_SENSE", "GND", (480, 170), "Capacitor 100 nF X7R 0402 (VTref sense filter)"),

    # ---- Target connectors ----------------------------------------------------------------------------
    Part("J2", "Connector:Conn_ARM_JTAG_SWD_10", "Cortex Debug", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
         (500, 230), {"VTref": "VTREF", "SWDIO/TMS": "T_SWDIO", "GND": "GND", "SWCLK/TCK": "T_SWCLK",
                      "SWO/TDO": "T_SWO", "KEY": NC, "NC/TDI": "T_TDI", "GNDDetect": "GND", "~{RESET}": "T_NRESET"},
         fields={"Manufacturer": "Samtec", "MPN": "FTSH-105-01-L-DV", "Description": "Arm Cortex Debug 10-pin, 1.27 mm"}),
    Part("J3", "Connector:Conn_01x04_Pin", "Target UART", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
         (500, 320), {"1": "VTREF", "2": "T_UART_TX", "3": "T_UART_RX", "4": "GND"},
         fields={"Description": "Target UART: 1 VTref, 2 TX (probe out), 3 RX (probe in), 4 GND"}),
]
for i in range(2):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M2", "MountingHole:MountingHole_2.2mm_M2_Pad_Via",
                      (60 + 20 * i, 360), {"1": "GND"}, fields={"Description": "Mounting hole M2, grounded"}))

# Board placement: (x, y, rotation) in mm, origin top-left. The module sits on the right edge with
# its antenna past the board edge, so Espressif's antenna keep-out lies off the board. USB-C on
# the left edge, the two target connectors on the top edge, buttons and LEDs along the bottom.
MODULE = (W - 6.75, H / 2)       # module origin: its antenna starts 6.75 mm out, at the board edge
PLACEMENT = {
    "U3": (MODULE[0], MODULE[1], 270),
    # USB-C, ESD and the 3.3 V supply on the left; the LDO and its capacitors bottom left
    "J1": (USB_C_EDGE, 16.0, 270), "U1": (11.8, 16.0, 90), "R1": (9.5, 10.0, 0), "R2": (9.5, 22.0, 0),
    "F1": (15.0, 8.0, 90), "U2": (16.4, 24.0, 0), "C1": (9.8, 27.8, 0), "C2": (24.2, 27.8, 0),
    "R3": (28.0, 27.8, 0), "D1": (31.0, 27.8, 180),
    # beside the module's 3V3 and EN pins (top right): decoupling, EN delay, reset button
    "C3": (56.5, 3.0, 0), "C4": (59.5, 3.0, 0), "R4": (53.5, 3.0, 0), "C5": (51.5, 3.0, 0),
    "SW1": (47.0, 2.8, 0), "SW2": (40.5, 27.5, 0),
    "R5": (40.2, 9.0, 0), "R6": (40.2, 10.6, 0),
    "R7": (33.5, 22.6, 0), "D2": (36.5, 22.6, 180), "R8": (33.5, 24.3, 0), "D3": (36.5, 24.3, 180),
    # target connectors on the top edge, reset switch and VTref sense beside them
    "J2": (32.0, 4.5, 0), "J3": (16.0, 2.6, 90),
    "Q1": (38.5, 4.0, 0), "R17": (38.5, 6.6, 0), "R18": (23.6, 8.6, 90), "R19": (25.0, 8.6, 90), "C18": (26.4, 8.6, 90),
    "H1": (4.0, 4.0, 0), "H2": (4.0, 26.5, 0),
}
# the six translators in two columns of three, each with its two capacitors beside it
for i, ref in enumerate(["U4", "U5", "U6", "U7", "U8", "U9"]):
    x, y = (23.0 if i < 3 else 33.0), 12.0 + 3.6 * (i % 3)
    PLACEMENT[ref] = (x, y, 0)
    PLACEMENT[f"C{6 + i}"] = (x - 2.6, y - 0.8, 90)
    PLACEMENT[f"C{12 + i}"] = (x + 2.6, y - 0.8, 90)
for ref, x, y in (("R9", 17.5, 12.8), ("R10", 17.5, 16.4), ("R11", 17.5, 17.6), ("R12", 38.5, 12.8),
                  ("R13", 38.5, 16.4), ("R14", 28.0, 15.6), ("R15", 28.0, 19.2), ("R16", 38.5, 19.4)):
    PLACEMENT[ref] = (x, y, 0)
_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS Probe S3  rev A", "x": 20.0, "y": 15.0, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 20.0, "y": 17.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 20.0, "y": 18.4, "size": 0.8, "layer": "B_SilkS", "mirror": True},
]

BOARD = Board(
    name="eos-probe-s3",
    title="EoS Probe S3",
    revision="A",
    date="2026-10-11",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    width=W,
    height=H,
    corner_radius=1.5,
    rules={"min_drill": 0.2},     # the ESP32-S3-WROOM-1 footprint's thermal vias under the module are 0.2 mm
    thickness=1.6,
    layers=2,
    parts=PARTS,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "VBUS": "power:VBUS"},
    flagged_nets=["GND", "VBUS", "+5V", "VTREF"],
    headings=[((35, 75), "USB-C, ESD, fuse"), ((190, 75), "3.3 V LDO (1 A)"), ((250, 75), "Power LED"),
              ((95, 175), "ESP32-S3-WROOM-1"), ((195, 180), "3V3 decoupling and EN delay (Espressif)"),
              ((290, 75), "Level translators: A = 3.3 V, B = target VTref"), ((420, 75), "Target reset, VTref sense"),
              ((480, 200), "Target connectors"), ((40, 345), "Mounting holes"), ((35, 300), "Power nets")],
    power_block=(40.64, 315.0),
    notes=[((260, 385), "EoS Probe S3, rev A. Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Values from Espressif's ESP32-S3-WROOM-1 datasheet (section 9), TI SCES515 (SN74LVC1T45),\n"
                       "and Diodes Inc. AP7361C. The target sets the I/O voltage through VTref (1.65-5.5 V).")],
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS": "Power", "+5V": "Power", "+3V3": "Power", "USB_D+": "USB", "USB_D-": "USB",
                  "ESP_D+": "USB", "ESP_D-": "USB"},
)
