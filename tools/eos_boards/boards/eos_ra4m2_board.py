"""EoS RA4M2 Board: a Renesas RA4M2 development board that fits Uno R3 shields and Pmod modules, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-ra4m2-board/LICENSE.txt.

Original 80 x 170 mm, two-layer development board with the R7FA4M2AD3CFP,
Uno R3 shield sockets, SPI and I2C Pmod ports, USB full-speed device, USB-UART,
10-pin SWD, and an original 40-pin GPIO-access header. No vendor design file
was used. The outline dimensions alone come from Renesas EK-RA4M2 user manual
R20UT4815EG0100 section 3; connector and hole coordinates are original except
for the relative Uno R3 and Pmod geometry described below.

Sources and decisions:
* Renesas R01DS0367EJ0150 Rev.1.50 Table 1.17, LQFP100 column: all 100 MCU pins.
  R01UH0892EJ0150 Table 45.1: 100 nF at each VCC and 220 nF at VCL; Figure 37.34:
  AVCC0 filtering. R01AN5988 Rev.1.04 Table 1: USB supply bypass and unused VBATT
  tied to VCC. Every ground and reference pin has its own assigned connection.
* Renesas R01AN7202 Rev.1.02 Group 1, Tables 4.1.1 and 4.2.1: 16 MHz/8 pF
  crystal with 6 pF external loads, and 32.768 kHz/9 pF crystal with 15 pF loads.
  Select main oscillator drive for 8.1-16 MHz and standard CL sub-clock drive.
  These are starting values from the matching study, not measurements of this PCB.
* R01UH0892 Figure 26.3: USB device 27 ohm series resistors and 1 uF on VBUS sense.
  The published 15k/30k divider is changed to 18k/30k: at 5.5 V and 1% resistor
  extremes it produces at most 3.47 V, below the 3.6 V unpowered-input limit.
  At 4.4 V it produces at least 2.729 V, above 0.8 x 3.322 V = 2.658 V VIH.
* CP2102N data sheet Rev.1.5 Figures 2.3/2.6: bridge powered from the board's
  3.3 V, with VREGIN tied to VDD, bypass capacitors, 1k reset pull-up, 22.1k/47.5k
  VBUS sensing and an additional 5.1k bleed. The bridge cannot lose power while
  the MCU remains powered. Ground-only SP0503BAHTG ESD avoids holding VBUS up.
* TI SLVSFG1A: TPS2116 priority mux chooses the debug port first, with 27k/10k
  PR1 divider, 1 uF on each input and 100 uF polymer on output; reverse blocking protects
  the USB inputs. TI SBVS282A Table 7-1: TPS7A91 uses 3.57k/1.15k for 3.283 V.
  The 10 nF NR/SS capacitor gives 0.80-2.2 ms startup (Eq.6, tolerance included),
  within R01DS0367 Table 2.9. The input/output 22/10 uF values include TI's 50%
  capacitance derating allowance (SBVS282A section 7.1.3).
* Budget: reserve 120 mA for the board, including the MCU's 65 mA maximum core
  current, 10 mA USB maximum (DS Table 2.7), bridge, LEDs and pull-ups. All
  expansion 3V3, IOREF, Pmod and 5V loads share 150 mA; steady-state budget is 270 mA.
  C22 alone draws about 294 mA while charging at 5 V / 1.7 ms (353 mA at +20%
  capacitance; TPS2116 section 8.2.2). These are typical-ramp estimates, excluding
  C23 and downstream startup load; USB attach/inrush compliance is unverified.
  At 270 mA the 0.70 ohm fuse and 0.060 ohm mux lose 0.189 V and 0.016 V.
  If every expansion load is on 3.3 V, the LDO dissipates 0.60 W at 5.5 V input;
  JEDEC 62.5 C/W predicts 37.5 C rise, not a measured two-layer-board limit.
  Firmware must stay within the USB default-unit-load limit before enumeration,
  request enough bus power, and meet suspend current; no firmware is included.
* R20UT4686 Figures 2.7/2.9 and R01AN5988 sections 3/6: 10k reset pull-up,
  no reset capacitor, MD grounded through 1.5k when JP1 is fitted. MD's internal
  pull-up selects normal boot otherwise. P200/NMI has 10k pull-up. SCI9 boot
  pins P109/P110 also serve the USB-UART (R01UH0892 Table 44.27); SWO shares P109,
  so trace and the serial console are alternate functions, not simultaneous.
* TI SLVA689A: 2.2k I2C pulls support 400 kHz to 161 pF; JP2 removes both.
  Kingbright DSAO7432/7433/7434: 680/750 ohm LED resistors yield about 2 mA.
* Uno R3 relative socket coordinates: Matthew Beckler's public-domain dimension
  drawing v1.05. Mounting holes are at original locations. Pmod relative rows
  and 22.86 mm spacing: Digilent
  Pmod Interface Specification 1.3.0, sections 3-5 and Figure 5. The Renesas
  manual does not supply dimensioned mounting/header coordinates; they are
  not inferred from a photograph. This is not enclosure/mounting compatible.

3.3 V logic only; every power header is an output. AREF and VIN are open.
This original MCU pin assignment requires its own firmware configuration.
No board has been fabricated, powered or validated for USB, EMC or timing.
"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
HOLE = "MountingHole:MountingHole_3.2mm_M3_ISO14580"
USB_C = "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"
KMR2 = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
LED0603 = "LED_SMD:LED_0603_1608Metric"

DS = "Renesas R01DS0367 Rev.1.50"
UM = "Renesas R01UH0892 Rev.1.50"
QDG = "Renesas R01AN5988 Rev.1.04"
E2 = "Renesas R20UT4686 Rev.3.60"
CLK = "Renesas R01AN7202 Rev.1.02"
CP = "Silicon Labs CP2102N DS Rev. 1.5"
TPS = "TI SBVS282A"
MUX = "TI SLVSFG1A"
PMOD = "Digilent Pmod Interface Specification (2020-09-29)"
RD = "TI SLVSFJ9 section 10.3.14.2"

C100N = ("Samsung Electro-Mechanics", "CL05B104KO5NNNC")    # 100 nF 16 V X7R 0402
C4U7 = ("Murata", "GRM188R61A475KE15D")                     # 4.7 uF 10 V X5R 0603
C10U_0603 = ("Murata", "GRM188R61A106KE69D")                # 10 uF 10 V X5R 0603
C10U_0805 = ("Murata", "GRM21BR61C106KE15L")                # 10 uF 16 V X5R 0805
C22U = ("Murata", "GRM21BR61A226ME51L")                     # 22 uF 10 V X5R 0805


def res(ref, value, a, b, sch, desc, rot=0, mpn=None):
    if mpn is None:
        # no single vendor is required: any 1% 0402 thick-film part rated 62.5 mW or more will do; the
        # largest dissipation on the board is about 6 mW (R15 at 5.5 V)
        assert " 1% 0402 " in desc, ref
        desc = desc.replace(" 1% 0402 ", " 1% 0402 thick film, 62.5 mW or more ", 1)
    fields = {"Description": desc, **({"Manufacturer": mpn[0], "MPN": mpn[1]} if mpn else {})}
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def cap(ref, value, a, b, sch, desc, fp=C0402, rot=0, mpn=None):
    fields = {"Description": desc, **({"Manufacturer": mpn[0], "MPN": mpn[1]} if mpn else {})}
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def led(ref, value, anode, sch, mpn, desc):
    return Part(ref, "Device:LED_Small", value, LED0603, sch, {"A": anode, "K": "GND"},
                fields={"Manufacturer": "Kingbright", "MPN": mpn, "Description": desc})


def button(ref, value, net, sch, what):
    return Part(ref, "Switch:SW_Push", value, KMR2, sch, {"1": net, "2": "GND"},
                fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": f"Tactile switch, {what}"})


def socket(ref, n, value, pins, sch, desc):
    """A female header for shields: pin 1 is the first signal named in ``pins``."""
    return Part(ref, f"Connector:Conn_01x{n:02d}_Socket", value,
                f"Connector_PinSocket_2.54mm:PinSocket_1x{n:02d}_P2.54mm_Vertical", sch,
                {str(i + 1): net for i, net in enumerate(pins)},
                fields={"Manufacturer": "Samtec", "MPN": f"SSW-1{n:02d}-01-T-S", "Description": desc})


def usb_c(ref, prefix, sch, what):
    return Part(ref, "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", USB_C, sch,
                {"VBUS": f"VBUS_{prefix}", "GND": "GND", "CC1": f"{prefix}_CC1", "CC2": f"{prefix}_CC2",
                 "D+": f"{prefix}_C_DP", "D-": f"{prefix}_C_DM", "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
                fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12",
                        "Description": f"USB-C 2.0 receptacle, 16 pins: {what}"})


def esd(ref, prefix, sch, dp, dm):
    # pins 2, 3 and 4 are the same diode to the common anode (pin 1, Littelfuse SP05xxBA pinout), so a
    # port may put D+ and D- on either of pins 2 and 3
    return Part(ref, "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", sch,
                {"1": "GND", dp: f"{prefix}_C_DP", dm: f"{prefix}_C_DM", "4": f"VBUS_{prefix}"},
                fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                        "Description": "USB ESD protection, three diodes to GND on D+, D- and VBUS, no path between "
                                       f"them (Littelfuse SP05xxBA: pin 1 common; {CP} Figures 2.5 and 2.6)"})


def fuse(ref, a, b, sch, what):
    return Part(ref, "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", sch, {"1": a, "2": b},
                fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                        "Description": f"PTC fuse 0.50 A hold (0.42 A at 40 C), 1.00 A trip, 6 V, R1max 0.70 ohm, 1206, "
                                       f"{what} (Littelfuse 1206L)"})


# Pmod host port. PMOD Figure 5 (a host port on a right-hand edge, top view): the 1-6 row inboard,
# the 7-12 row 10.16 mm from the edge, pin 1 at the top. These ports are on the left edge, so the
# figure turns 180 degrees: pin 1 at the bottom. KiCad's right-angle 2x06 socket (opening to -x at
# rotation 0) puts its odd pads 2.54 mm further from the opening than its even pads, top to bottom.
# So odd pads 1, 3, ..., 11 carry Pmod pins 6, 5, ..., 1 and even pads 2, ..., 12 carry 12, ..., 7.
PMOD_PAD = {6: "1", 12: "2", 5: "3", 11: "4", 4: "5", 10: "6", 3: "7", 9: "8", 2: "9", 8: "10", 1: "11", 7: "12"}


def pmod(ref, value, signals, sch, what):
    """A Pmod 12-pin host port; ``signals`` maps Pmod pins 1-4 and 7-10 to nets (NC where left open)."""
    pins = {5: "GND", 11: "GND", 6: "+3V3", 12: "+3V3", **signals}
    mapping = ", ".join(f"pad {PMOD_PAD[p]} = Pmod {p}" for p in sorted(PMOD_PAD, key=lambda q: int(PMOD_PAD[q])))
    return Part(ref, "Connector_Generic:Conn_02x06_Odd_Even", value,
                "Connector_PinSocket_2.54mm:PinSocket_2x06_P2.54mm_Horizontal", sch,
                {PMOD_PAD[p]: net for p, net in pins.items()},
                fields={"Manufacturer": "Sullins", "MPN": "PPPC062LJBN-RC",
                        "Description": f"Pmod host port, 2x6 right-angle female 2.54 mm, {what}, 3.3 V "
                                       f"({PMOD} sections 3-5, Figure 5); {mapping}"})


W, H = 80.0, 170.0           # R20UT4815EG0100 section 3, published EK-RA4M2 dimensions
SHIELD_H = 53.34            # Uno R3 connector geometry, positioned independently on this board
MIL = 0.0254


def uno(x_mil, y_mil):
    """A position from the Uno R3 drawings (mils from the lower-left corner, y up) in board mm."""
    return round(x_mil * MIL, 4), round(SHIELD_H - y_mil * MIL, 4)


D0_PIN = uno(2500, 2000)      # D0 .. D7 run right to left, 100 mil apart
D8_PIN = uno(1640, 2000)      # D8 .. D13, GND, AREF, SDA, SCL run right to left
POWER_PIN = uno(1100, 100)    # NC, IOREF, RESET, 3V3, 5V, GND, GND, VIN run left to right
A0_PIN = uno(2000, 100)       # A0 .. A5 run left to right
HOLES = [(4.0, 58.0), (4.0, 166.0), (76.0, 58.0), (76.0, 166.0)]  # original mounting positions

# R7FA4M2AD3CFP pins by name (DS Table 1.17, LQFP100; names as DS Figure 1.3).
MCU_NETS = {
    "~{RES}": "RES", "P201/MD": "MD", "P200/NMI": "NMI",
    "P212/EXTAL": "EXTAL", "P213/XTAL": "XTAL", "XCIN": "XCIN", "XCOUT": "XCOUT",
    "USB_DP": "USB_DP", "USB_DM": "USB_DM", "P407": "USB_VBUS_S",
    "P005": "A0", "P004": "A1", "P003": "A2", "P002": "A3", "P001": "A4", "P000": "A5",
    "P400": "SCL", "P401": "SDA", "P402": "PMODB_RST", "P403": "PMODB_INT", "P404": "PMODB_IO7", "P405": "PMODB_IO8",
    "P505": "PMODB_IO9",
    "P408": "USER_BTN", "P409": "LED1", "P410": "LED2", "P411": "LED3",
    "P500": "PMODA_CS", "P501": "PMODA_INT", "P502": "PMODA_RST", "P503": "PMODA_CS2", "P504": "PMODA_CS3",
    "P100": "SPI_MISO", "P101": "SPI_MOSI", "P102": "SPI_SCK", "P103": "D10",
    "P602": "D9", "P603": "D8", "P610": "D7", "P115": "D6", "P608": "D5", "P609": "D4", "P114": "D3",
    "P111": "D2", "P112": "D1", "P113": "D0",
    "P108/TMS/SWDIO": "SWDIO", "P300/TCK/SWCLK": "SWCLK", "P109/TDO/SWO": "TXD9", "P110/TDI": "RXD9",
    "VCC": "+3V3", "VCC_USB": "+3V3", "VBATT": "+3V3", "VSS": "GND", "VSS_USB": "GND", "VCL": "VCL",
    "AVCC0": "AVCC0", "VREFH": "AVCC0", "VREFH0": "AVCC0", "AVSS0/VREFL": "GND", "VREFL0": "GND",
    **{p: NC for p in ("P006", "P007", "P008", "P013", "P014", "P015", "P406", "P412", "P413", "P414", "P415",
                       "P708", "P104", "P105", "P106", "P107", "P600", "P601", "P205", "P206", "P207", "P208",
                       "P209", "P210", "P211", "P214", "P301", "P302", "P303", "P304", "P305", "P306", "P307")},
}

PARTS = [
    # ---- RA4M2 and its supplies -----------------------------------------------------------------------
    Part("U1", "EoS_MCU:R7FA4M2AD3CFP", "R7FA4M2AD3CFP", "Package_QFP:LQFP-100_14x14mm_P0.5mm", (420, 240), MCU_NETS,
         fields={"Manufacturer": "Renesas", "MPN": "R7FA4M2AD3CFP#AA0",
                 "Description": f"RA4M2 Cortex-M33 100 MHz, 512 KB code flash, 128 KB SRAM, USB FS, LQFP-100 14 x 14 mm "
                                f"(PLQP0100KB-B, {DS} Table 1.14, Appendix 2)"}),
    # A 1206 body, so the main-crystal lines pass between its pads: its ground pad then sits on the
    # VSS pin 12 ground between the two oscillators (see PLACEMENT)
    cap("C1", "100n", "+3V3", "GND", (330, 140), f"Capacitor 100 nF 50 V X7R 10% 1206 (VCC pin 15 / VSS pin 12, 0.1 uF close to the pin, {UM} Table 45.1)",
        C1206, mpn=("Samsung Electro-Mechanics", "CL31B104KBCNNNC")),
    cap("C2", "100n", "+3V3", "GND", (345, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC pin 46 / VSS pin 45, {UM} Table 45.1)", mpn=C100N),
    cap("C3", "100n", "+3V3", "GND", (360, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC pin 62 / VSS pin 63, {UM} Table 45.1)", mpn=C100N),
    cap("C4", "100n", "+3V3", "GND", (375, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC pin 82 / VSS pin 83, {UM} Table 45.1)", mpn=C100N),
    cap("C5", "220n", "VCL", "GND", (390, 140), f"Capacitor 0.22 uF 50 V C0G 5% 1206 (VCL pin 9, stable nominal capacitance without X7R DC-bias loss, {UM} Table 45.1)", C1206,
        mpn=("Murata", "GRM31C5C1H224JE02L")),
    cap("C6", "100n", "+3V3", "GND", (405, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC_USB pin 29 to VSS_USB, close to VCC_USB, {QDG} Table 1)", mpn=C100N),
    Part("FB1", "Device:FerriteBead_Small", "220R", "Inductor_SMD:L_0603_1608Metric", (430, 140), {"1": "+3V3", "2": "AVCC0"},
         fields={"Manufacturer": "Bourns", "MPN": "MH1608-221Y",
                 "Description": "Ferrite bead 220 ohm at 100 MHz, 100 mohm, 2 A, 0603: AVCC0 filter (Bourns MH1608)"}),
    cap("C7", "100n", "AVCC0", "GND", (445, 140), f"Capacitor 100 nF 16 V X7R 0402 (AVCC0 pin 88 / AVSS0 pin 89, 0.1 uF, {UM} Figure 37.34)", mpn=C100N),
    cap("C8", "100n", "AVCC0", "GND", (460, 140), f"Capacitor 100 nF 16 V X7R 0402 (VREFH0 pin 91 / VREFL0 pin 90, 0.1 uF, {UM} Figure 37.34)", mpn=C100N),
    cap("C9", "10u", "AVCC0", "GND", (475, 140), f"Capacitor 10 uF 10 V X5R 0603 (AVCC0 supply, reference value, {UM} Figure 37.34)", C0603, mpn=C10U_0603),
    cap("C10", "10n", "AVCC0", "GND", (490, 140), f"Capacitor 10 nF 50 V X7R 0402 (AVCC0 supply, reference value 0.01 uF, {UM} Figure 37.34)",
        mpn=("Murata", "GRM155R71H103KA88D")),
    # 16 MHz main crystal (CLK Table 4.1.1, Group 1: 16 MHz, CL 8 pF, Rd 0, CL1 = CL2 = 6 pF)
    Part("Y1", "Device:Crystal_GND24", "16MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", (520, 200),
         {"1": "XTAL", "3": "EXTAL", "2": "GND", "4": "GND"},
         fields={"Manufacturer": "NDK", "MPN": "NX3225GA-16.000M-STD-CRG-2",
                 "Description": f"Crystal 16 MHz, CL 8 pF, ESR 80 ohm max, +-20 ppm, +-30 ppm over temperature, 3.2 x 2.5 mm "
                                f"(NDK NX3225GA); ESR under the 220 ohm {CLK} Table 4.1.1 recommends for 16 MHz"}),
    cap("C11", "6p", "XTAL", "GND", (505, 220), f"Capacitor 6 pF 50 V C0G 0402 (XTAL load CL2 for an 8 pF 16 MHz crystal, {CLK} Table 4.1.1)",
        mpn=("Murata", "GRM1555C1H6R0DA01D")),
    cap("C12", "6p", "EXTAL", "GND", (535, 220), f"Capacitor 6 pF 50 V C0G 0402 (EXTAL load CL1 for an 8 pF 16 MHz crystal, {CLK} Table 4.1.1)",
        mpn=("Murata", "GRM1555C1H6R0DA01D")),
    # 32.768 kHz sub-clock crystal (CLK Table 4.2.1, Group 1: Standard CL, CL 9 pF, CL1 = CL2 = 15 pF, Rd 0)
    Part("Y2", "Device:Crystal", "32.768kHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", (520, 260), {"1": "XCOUT", "2": "XCIN"},
         fields={"Manufacturer": "Abracon", "MPN": "ABS07-32.768KHZ-9-T",
                 "Description": f"Crystal 32.768 kHz, CL 9 pF, ESR 70 kohm max, 3.2 x 1.5 mm (Abracon ABS07); ESR under "
                                f"the 160 kohm {CLK} Table 4.2.1 recommends for Standard CL drive"}),
    cap("C13", "15p", "XCIN", "GND", (505, 280), f"Capacitor 15 pF 50 V C0G 0402 (XCIN load CL1 for a 9 pF crystal, {CLK} Table 4.2.1)",
        mpn=("Murata", "GRM1555C1H150JA01D")),
    cap("C14", "15p", "XCOUT", "GND", (535, 280), f"Capacitor 15 pF 50 V C0G 0402 (XCOUT load CL2 for a 9 pF crystal, {CLK} Table 4.2.1)",
        mpn=("Murata", "GRM1555C1H150JA01D")),

    # ---- Reset, mode, NMI, SWD, buttons, LEDs ----------------------------------------------------------
    res("R1", "10k", "RES", "+3V3", (455, 320), f"Resistor 10 kohm 1% 0402 (RES pull-up 4.7-10 kohm, {E2} Figure 2.7; no capacitor, {QDG} 6.1)", rot=90),
    res("R2", "10k", "NMI", "+3V3", (440, 320), f"Resistor 10 kohm 1% 0402 (P200/NMI pull-up, {UM} Table 19.3; value as RES)", rot=90),
    button("SW1", "RESET", "RES", (470, 350), "reset (RES)"),
    Part("JP1", "Jumper:Jumper_2_Open", "MD", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", (500, 365),
         {"A": "MD", "B": "MD_JP"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-102-07-G-S",
                 "Description": f"Pin header 1x2 2.54 mm, fitted with a Samtec SNT-100-BK-G 2.54 mm shunt at reset = SCI/USB boot "
                                f"mode ({UM} Table 3.1; {QDG} Figure 8)"}),
    res("R3", "1.5k", "MD_JP", "GND", (520, 380), f"Resistor 1.5 kohm 1% 0402 (MD to GND through JP1, {QDG} Figure 8, {E2} Figure 2.9)", rot=90),
    Part("J9", "Connector:Conn_ARM_JTAG_SWD_10", "SWD", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
         (505, 320), {"VTref": "+3V3", "SWDIO/TMS": "SWDIO", "GND": "GND", "SWCLK/TCK": "SWCLK", "SWO/TDO": "TXD9",
                      "KEY": NC, "NC/TDI": NC, "GNDDetect": "GND", "~{RESET}": "RES"},
         fields={"Manufacturer": "Samtec", "MPN": "FTSH-105-01-L-DV-K",
                 "Description": f"Arm Cortex Debug 10-pin, 1.27 mm: SWDIO P108, SWCLK P300, SWO P109, RES ({QDG} Figure 1, "
                                f"{UM} Table 44.32); replaces the J-Link OB"}),
    button("SW2", "USER", "USER_BTN", (330, 345), "user (P408, IRQ7)"),
    res("R22", "10k", "USER_BTN", "+3V3", (315, 330), "Resistor 10 kohm 1% 0402 (user button pull-up; value as RES; pull-ups off at reset)", rot=90),
    res("R24", "750", "LED1_A", "LED1", (360, 375), "Resistor 750 ohm 1% 0402 (LED1: (3.3 V - 1.75 V) / 750 ohm = 2.1 mA, Kingbright DSAO7433)"),
    led("D2", "LED1", "LED1_A", (375, 375), "APTD1608LSURCK", "LED red 0603, VF 1.75 V typ at 2 mA (Kingbright DSAO7433): user LED1 (P409)"),
    res("R25", "680", "LED2_A", "LED2", (360, 390), "Resistor 680 ohm 1% 0402 (LED2: (3.3 V - 1.9 V) / 680 ohm = 2.1 mA, Kingbright DSAO7432)"),
    led("D3", "LED2", "LED2_A", (375, 390), "APTD1608LCGCK", "LED green 0603, VF 1.9 V typ at 2 mA (Kingbright DSAO7432): user LED2 (P410)"),
    res("R26", "680", "LED3_A", "LED3", (360, 405), "Resistor 680 ohm 1% 0402 (LED3: (3.3 V - 1.85 V) / 680 ohm = 2.1 mA, Kingbright DSAO7434)"),
    led("D4", "LED3", "LED3_A", (375, 405), "APTD1608LSYCK", "LED yellow 0603, VF 1.85 V typ at 2 mA (Kingbright DSAO7434): user LED3 (P411)"),

    # ---- USB device port (J1): the RA4M2's USBFS ------------------------------------------------------
    usb_c("J1", "DEV", (40, 100), "USB, the RA4M2's own full-speed device port (USBFS)"),
    res("R4", "5.1k", "DEV_CC1", "GND", (75, 85), f"Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC1, {RD})"),
    res("R5", "5.1k", "DEV_CC2", "GND", (90, 85), f"Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC2, {RD})"),
    esd("U2", "DEV", (110, 100), dp="2", dm="3"),
    fuse("F1", "VBUS_DEV", "VBUS_DEV_F", (140, 85), "device port"),
    res("R6", "27", "DEV_C_DP", "USB_DP", (75, 125), f"Resistor 27 ohm 1% 0402 (USB_DP series, {UM} Figure 26.3; {DS} Table 2.34 ZDRV includes Rs = 27 ohm)"),
    res("R7", "27", "DEV_C_DM", "USB_DM", (90, 125), f"Resistor 27 ohm 1% 0402 (USB_DM series, {UM} Figure 26.3; {DS} Table 2.34 ZDRV includes Rs = 27 ohm)"),
    res("R8", "18k", "VBUS_DEV", "USB_VBUS_S", (120, 140), f"Resistor 18 kohm 1% 0402 (USB_VBUS divider, adapted from {UM} Figure 26.3: 5.5 V reads <=3.47 V with 1% tolerance, below 3.6 V unpowered limit)", rot=90),
    res("R9", "30k", "USB_VBUS_S", "GND", (120, 155), f"Resistor 30 kohm 1% 0402 (USB_VBUS divider, {UM} Figure 26.3)", rot=90),
    cap("C15", "1u", "USB_VBUS_S", "GND", (135, 155), f"Capacitor 1.0 uF 16 V X7R 0603 (USB_VBUS pin, {UM} Figure 26.3)", C0603,
        mpn=("Murata", "GRM188R71C105KA12D")),

    # ---- Debug port (J2): USB-C, ESD, CP2102N on SCI9 ----------------------------------------------------
    usb_c("J2", "DBG", (40, 200), "debug UART and serial programming (CP2102N on SCI9)"),
    res("R10", "5.1k", "DBG_CC1", "GND", (75, 185), f"Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC1, {RD})"),
    res("R11", "5.1k", "DBG_CC2", "GND", (90, 185), f"Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC2, {RD})"),
    esd("U3", "DBG", (110, 200), dp="3", dm="2"),
    fuse("F2", "VBUS_DBG", "VBUS_DBG_F", (140, 185), "debug port"),
    Part("U6", "Interface_USB:CP2102N-Axx-xQFN24", "CP2102N-A02-GQFN24", "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
         (150, 260), {"GND": "GND", "D+": "DBG_C_DP", "D-": "DBG_C_DM", "VIO": "+3V3", "VDD": "+3V3", "VREGIN": "+3V3",
                      "VBUS": "CP_VBUS", "~{RST}": "CP_RST", "RXD": "TXD9", "TXD": "RXD9",
                      **{p: NC for p in ("NC", "~{RI}/CLK", "~{WAKEUP}/GPIO.3", "RS485/GPIO.2", "~{RXT}/GPIO.1",
                                         "~{TXT}/GPIO.0", "~{SUSPEND}", "SUSPEND", "~{CTS}", "~{RTS}", "~{DSR}",
                                         "~{DTR}", "~{DCD}")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN24R",
                 "Description": f"USB-UART bridge on SCI9 (P109 TXD9, P110 RXD9: the boot-mode SCI, {UM} Table 44.27), from "
                                f"the board's 3.3 V, own regulator unused ({CP} Figure 2.3)"}),
    cap("C16", "100n", "+3V3", "GND", (195, 235), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VIO/VDD pins 5 and 6, beside the pins, {CP} Figure 2.3)", mpn=C100N),
    cap("C17", "100n", "+3V3", "GND", (210, 235), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VREGIN pin 7, beside the pin, {CP} Figure 2.3)", mpn=C100N),
    cap("C18", "4.7u", "+3V3", "GND", (225, 235), f"Capacitor 4.7 uF 10 V X5R 0603 (CP2102N VIO, {CP} section 2.1)", C0603, mpn=C4U7),
    cap("C19", "4.7u", "+3V3", "GND", (240, 235), f"Capacitor 4.7 uF 10 V X5R 0603 (CP2102N VREGIN/VDD, {CP} Figure 2.3)", C0603, mpn=C4U7),
    res("R12", "1k", "CP_RST", "+3V3", (195, 280), f"Resistor 1 kohm 1% 0402 (CP2102N RSTb pull-up, {CP} section 2.1)"),
    res("R13", "22.1k", "VBUS_DBG", "CP_VBUS", (100, 245), f"Resistor 22.1 kohm 1% 0402 (CP2102N VBUS divider: 5 V reads 3.41 V, {CP} Figure 2.6)", rot=90),
    res("R14", "47.5k", "CP_VBUS", "GND", (100, 265), f"Resistor 47.5 kohm 1% 0402 (CP2102N VBUS divider, {CP} Figure 2.6)", rot=90),
    res("R15", "5.1k", "VBUS_DBG", "GND", (75, 230), f"Resistor 5.1 kohm 1% 0402 (VBUS bleed: with the divider 4.75 kohm, so 185 uA of leakage keeps the "
        f"CP2102N VBUS pin under VIL 0.6 V, {CP} Table 3.7)", rot=90),

    # ---- Power mux (debug port first), 3.3 V LDO with soft start, power LED -------------------------------
    Part("U4", "Power_Management:TPS2116DRL", "TPS2116", "Package_TO_SOT_SMD:SOT-583-8", (200, 100),
         {"VIN1": "VBUS_DBG_F", "VIN2": "VBUS_DEV_F", "VOUT": "+5V", "GND": "GND", "PR1": "MUX_PR1",
          "MODE": "VBUS_DBG_F", "ST": NC},
         fields={"Manufacturer": "Texas Instruments", "MPN": "TPS2116DRLR",
                 "Description": f"Power mux 2.5 A, priority mode: VIN1 (debug port) first, VIN2 (USB device port) otherwise, reverse blocking ({MUX})"}),
    res("R16", "27k", "VBUS_DBG_F", "MUX_PR1", (170, 125), f"Resistor 27 kohm 1% 0402 (TPS2116 PR1 divider: VIN1 kept down to 3.7 x VREF = 3.40-4.00 V, {MUX} 7.6.1.1)", rot=90),
    res("R17", "10k", "MUX_PR1", "GND", (170, 140), f"Resistor 10 kohm 1% 0402 (TPS2116 PR1 divider, VREF 0.92-1.08 V, {MUX} Table 6.5)", rot=90),
    cap("C20", "1u", "VBUS_DBG_F", "GND", (175, 85), f"Capacitor 1 uF 16 V X7R 0603 (TPS2116 VIN1, {MUX} section 9)", C0603, mpn=("Murata", "GRM188R71C105KA12D")),
    cap("C21", "1u", "VBUS_DEV_F", "GND", (190, 85), f"Capacitor 1 uF 16 V X7R 0603 (TPS2116 VIN2, {MUX} section 9)", C0603, mpn=("Murata", "GRM188R71C105KA12D")),
    Part("C22", "Device:C_Polarized_Small", "100u", "Capacitor_SMD:CP_Elec_6.3x5.9", (230, 85),
         {"1": "+5V", "2": "GND"}, fields={"Manufacturer": "Panasonic", "MPN": "16SVPC100M",
         "Description": f"Polarized polymer capacitor 100 uF 16 V 20%, 24 mohm ESR, C6 case (Panasonic SVPC datasheet; TPS2116 VOUT, {MUX} 7.3.4 and 8.2.2); pad 1 positive"}),
    Part("U5", "Regulator_Linear:TPS7A91", "TPS7A91", "Package_DFN_QFN:Texas_S-PDSO-N10_EP1.2x2mm", (280, 105),
         {"IN": "+5V", "EN": "+5V", "SS_CTRL": "GND", "NR/SS": "LDO_NR", "FB": "LDO_FB", "OUT": "+3V3", "PG": NC, "GND": "GND"},
         fields={"Manufacturer": "Texas Instruments", "MPN": "TPS7A9101DSKR",
                 "Description": f"LDO 1 A, adjustable, NR/SS soft start: 3.283 V, ramp 0.80-2.2 ms ({TPS}; {DS} Table 2.9)"}),
    cap("C23", "22u", "+5V", "GND", (250, 85), f"Capacitor 22 uF 10 V X5R 0805 (TPS7A91 input, 10 uF or more, {TPS} 5.3 and 7.1.3)", C0805, mpn=C22U),
    cap("C24", "10u", "+3V3", "GND", (310, 85), f"Capacitor 10 uF 16 V X5R 0805 (TPS7A91 output, 10 uF or more, {TPS} 5.3 and 7.1.3)", C0805, mpn=C10U_0805),
    cap("C25", "10n", "LDO_NR", "GND", (255, 130), f"Capacitor 10 nF 50 V X7R 0402 +-10% (TPS7A91 NR/SS: tSS = 0.8 V x 9-11 nF / 9.0-4.0 uA = 0.80-2.2 ms, "
        f"{TPS} Eq. 6 and 5.5)", mpn=("Murata", "GRM155R71H103KA88D")),
    res("R18", "3.57k", "+3V3", "LDO_FB", (305, 120), f"Resistor 3.57 kohm 0.1% 0402 (TPS7A91 R1, 3.283 V, {TPS} Table 7-1)", rot=90,
        mpn=("Panasonic", "ERA-2AEB3571X")),
    res("R19", "1.15k", "LDO_FB", "GND", (305, 140), f"Resistor 1.15 kohm 0.1% 0402 (TPS7A91 R2, 3.283 V, {TPS} Table 7-1)", rot=90,
        mpn=("Panasonic", "ERA-2AEB1151X")),
    res("R23", "680", "LED_PWR_A", "+3V3", (335, 100), "Resistor 680 ohm 1% 0402 (power LED: (3.3 V - 1.9 V) / 680 ohm = 2.1 mA, Kingbright DSAO7432)"),
    led("D1", "PWR", "LED_PWR_A", (350, 100), "APTD1608LCGCK", "LED green 0603, VF 1.9 V typ at 2 mA (Kingbright DSAO7432): power (3.3 V)"),

    # ---- I2C pull-ups (jumpered), Pmod ports, shield headers -----------------------------------------------
    res("R20", "2.2k", "I2C_PU", "SCL", (480, 395), "Resistor 2.2 kohm 1% 0402 (SCL pull-up: RP(min) 0.97 kohm, fast mode to 161 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    res("R21", "2.2k", "I2C_PU", "SDA", (495, 395), "Resistor 2.2 kohm 1% 0402 (SDA pull-up: RP(min) 0.97 kohm, fast mode to 161 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    Part("JP2", "Jumper:SolderJumper_2_Bridged", "I2C PU", "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm", (510, 420),
         {"A": "I2C_PU", "B": "+3V3"},
         fields={"Description": f"I2C pull-ups to 3.3 V, bridged as delivered; cut to remove them ({PMOD} section 2: jumpered pull-ups)"}),
    pmod("J7", "PMOD A", {1: "PMODA_CS", 2: "SPI_MOSI", 3: "SPI_MISO", 4: "SPI_SCK", 7: "PMODA_INT", 8: "PMODA_RST",
                          9: "PMODA_CS2", 10: "PMODA_CS3"}, (560, 225), "Type 2A expanded SPI"),
    pmod("J8", "PMOD B", {1: "PMODB_INT", 2: "PMODB_RST", 3: "SCL", 4: "SDA", 7: "PMODB_IO7", 8: "PMODB_IO8",
                          9: "PMODB_IO9", 10: NC}, (560, 290), "Type 6A expanded I2C, pin 10 open"),
    socket("J3", 10, "D8-SCL", ["D8", "D9", "D10", "SPI_MOSI", "SPI_MISO", "SPI_SCK", "GND", NC, "SDA", "SCL"], (560, 90),
           "Socket 1x10 2.54 mm, Uno R3 digital D8-D13, GND, AREF (not connected), SDA, SCL (pin 1 = D8), 3.3 V logic"),
    socket("J4", 8, "D0-D7", ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7"], (560, 145),
           "Socket 1x8 2.54 mm, Uno R3 digital D0-D7 (pin 1 = D0), 3.3 V logic"),
    socket("J5", 8, "POWER", [NC, "+3V3", "RES", "+3V3", "+5V", "GND", "GND", NC], (520, 90),
           "Socket 1x8 2.54 mm, Uno R3 power: NC, IOREF (3.3 V), RESET, 3V3, 5V, GND, GND, VIN (not connected)"),
    socket("J6", 6, "A0-A5", ["A0", "A1", "A2", "A3", "A4", "A5"], (520, 145),
           "Socket 1x6 2.54 mm, Uno R3 analog A0-A5 (pin 1 = A0), 0-3.3 V"),
]
for i, label in enumerate(["top left", "bottom left", "right, upper", "right, lower"]):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole", "M3", HOLE, (60 + 20 * i, 470), {},
                      side="F",
                      fields={"Description": f"Mounting hole 3.2 mm, unplated, original position ({label}); not the EK-RA4M2 mounting pattern"}))

MX, MY = 32.5, 23.5
PLACEMENT = {
    "U1": (MX, MY, 90),
    "J3": (D8_PIN[0], D8_PIN[1], 270), "J4": (D0_PIN[0], D0_PIN[1], 270),
    "J5": (POWER_PIN[0], POWER_PIN[1], 90), "J6": (A0_PIN[0], A0_PIN[1], 90),
    **{f"H{i + 1}": (x, y, 0) for i, (x, y) in enumerate(HOLES)},
    "J7": (12.70, 7.50, 0), "J8": (12.70, 30.36, 0),
    # decoupling: each capacitor's supply pad faces its supply pin and its ground pad its VSS pin, so
    # the two pin-to-pad lines run side by side (C2, C4 and C7 turned for that)
    "C2": (42.1, 19.75, 270), "C3": (32.8, 13.6, 270), "C4": (22.4, 21.25, 270), "C6": (42.25, 27.05, 0),
    "C7": (22.4, 23.75, 270), "C8": (22.4, 26.1, 90), "FB1": (18.7, 22.6, 90), "C9": (20.25, 25.4, 90), "C10": (20.25, 22.2, 90),
    # Oscillators (R01AN7202 section 6.1). The bottom pin row runs VCL 9, XCIN 10, XCOUT 11, VSS 12,
    # XTAL 13, EXTAL 14, VCC 15. VSS 12 drops straight onto C5's ground pad and on to C1's: a ground
    # spine between the two oscillators. C5 (VCL) and C1 (VCC) are 1206 parts whose bodies straddle
    # the clock pairs, XCIN/XCOUT under C5 and XTAL/EXTAL under C1, so both capacitors' ground pads
    # sit on that spine and close their loops on the top layer. The 32.768 kHz crystal sits below C5
    # and left of the spine, the 16 MHz one below C1; each load capacitor's ground pad lies beyond its
    # crystal. The bottom layer under the whole area is a router keep-out, so its ground pour is solid.
    "C5": (30.525, 33.45, 0), "C1": (33.475, 35.8, 180),
    "Y2": (29.15, 36.2, 0), "C13": (27.9, 38.3, 270), "C14": (30.4, 38.3, 270),
    "Y1": (33.6, 38.75, 0), "C11": (32.5, 41.45, 270), "C12": (36.7, 37.9, 0),
    # SWD, reset, mode, NMI
    "J9": (57.0, 39.0, 0), "R2": (42.1, 22.6, 90), "R1": (42.1, 24.6, 90),
    "SW1": (50.0, 43.0, 0), "JP1": (55.0, 47.0, 90), "R3": (60.8, 43.0, 90),
    # LEDs, user button
    "R24": (41.9, 35.0, 90), "D2": (41.9, 37.7, 90), "R25": (43.7, 35.0, 90), "D3": (43.7, 37.7, 90),
    "R26": (45.5, 35.0, 90), "D4": (45.5, 37.7, 90),
    "SW2": (43.4, 43.0, 0), "R22": (47.4, 40.2, 90),
    # device port (J1)
    "J1": (W - USB_C_EDGE, 34.5, 90), "U2": (57.4, 34.5, 270), "R4": (59.6, 38.2, 90), "R5": (59.6, 31.0, 90),
    "F1": (61.3, 26.9, 270), "R6": (43.9, 28.6, 180), "R7": (43.9, 29.7, 180),
    "R8": (55.0, 37.6, 270), "R9": (45.6, 31.4, 0), "C15": (43.0, 31.4, 0),
    # debug port (J2) and the CP2102N
    "J2": (W - USB_C_EDGE, 9.70, 90), "U3": (57.4, 12.5, 270), "R10": (59.6, 9.6, 90), "R11": (58.9, 8.2, 0),
    "F2": (57.8, 15.9, 180), "U6": (52.2, 12.5, 180),
    "C16": (55.1, 8.9, 90), "C17": (53.6, 8.9, 90), "R13": (52.4, 8.9, 90), "R12": (51.2, 8.9, 90),
    "R14": (50.0, 8.9, 90), "R15": (48.8, 8.9, 90), "C18": (47.0, 11.0, 90), "C19": (47.0, 14.2, 90),
    # power mux and LDO
    "U4": (54.6, 18.9, 270), "C20": (54.0, 16.3, 0), "C21": (49.5, 21.8, 0), "R16": (52.4, 18.5, 90),
    "R17": (51.8, 20.5, 90), "C22": (58.1, 19.4, 90),
    "U5": (55.6, 25.4, 90), "C23": (52.1, 24.0, 180), "C24": (53.0, 27.6, 90), "C25": (55.6, 21.8, 90),
    "R18": (55.2, 28.6, 270), "R19": (56.4, 28.6, 90), "R23": (61.5, 20.2, 90), "D1": (61.5, 22.8, 90),
    # I2C pull-ups by the SDA/SCL header pins
    "R20": (18.8, 5.9, 90), "R21": (21.34, 5.9, 90), "JP2": (25.0, 6.0, 0),
}

# Keep the MCU USB pair on the right edge. The equivalent ESD channels let
# the main run stay on front copper; the connector escape crosses locally.
# The RES pull-up sits beside pin 38. The SWD header and the boot jumper sit right of the Uno shield
# outline (x > 68.58 mm), so a fitted shield covers neither; R3 stays by the jumper.
PLACEMENT["R1"] = (42.9, 23.5, 0)
PLACEMENT["R2"] = (50.0, 9.0, 90)
PLACEMENT["J9"] = (75.5, 46.6, 90)
PLACEMENT["JP1"] = (72.0, 52.9, 90)
PLACEMENT["R3"] = (77.6, 52.9, 0)

# Place the USB/power section beside the widened board edge; preserve all local
# clearances while giving the MCU USB routes another 11.4 mm of routing space.
_POWER_ZONE = {"U3", "R10", "R11", "F2", "U6", "C16", "C17", "R13", "R12", "R14", "R15", "C18", "C19",
               "U4", "C20", "C21", "R16", "R17", "C22", "U5", "C23", "C24", "C25", "R18", "R19", "R23", "D1",
               "U2", "R4", "R5", "F1", "R8"}
for _ref in _POWER_ZONE:
    _x, _y, _a = PLACEMENT[_ref]
    PLACEMENT[_ref] = (_x + 11.4, _y, _a)

# C22 uses Panasonic's C6 land pattern: 2.1 mm gap, 9.1 mm overall length,
# 1.6 mm width. Move the power indicator clear of the larger capacitor body.
PLACEMENT["C22"] = (72.7, 21.0, 0)
PLACEMENT["R23"] = (69.4, 41.0, 180)
PLACEMENT["D1"] = (72.2, 41.0, 180)

# CP2102N supply pins: VIO 5 and VDD 6 on the right side, VREGIN 7 at the top-right corner. C17 sits
# over pin 7 and C16 right of pins 5/6, each ground pad toward the chip, where its dog-bone via drops
# into a bottom-layer pour kept solid (a router keep-out) as far as the exposed pad's own vias. The
# 4.7 uF parts sit just beyond them (CP2102N Figure 2.3).
PLACEMENT["C17"] = (65.43, 9.1, 0)
PLACEMENT["C16"] = (67.25, 10.0, 180)
PLACEMENT["C18"] = (67.4, 6.9, 90)
PLACEMENT["C19"] = (65.7, 7.15, 90)
PLACEMENT["U3"] = (68.4, 12.5, 270)
# The top pins run CP_RST 9, CP_VBUS 8, +3V3 7. R12 (CP_RST pull-up) sits above pins 8/9 and joins
# the +3V3 capacitors on the top layer, so CP_VBUS, boxed in between, drops to the bottom layer in
# the gap under R12 and comes up at its divider (R14 over R13) left of the chip; the VBUS line then
# meets R13 and the bleed R15 from outside, and R14's ground end faces open pour. Builds 6-8 shut in
# R13's VBUS end, R12's 3.3 V end or R14's CP_VBUS end in turn.
PLACEMENT["R12"] = (63.3, 7.0, 0)
PLACEMENT["R13"] = (61.4, 8.9, 90)
PLACEMENT["R14"] = (61.4, 7.4, 180)

# The GPIO header is an original connector, not the vendor's pin-access layout.
_FREE_GPIO = ["P006", "P007", "P008", "P013", "P014", "P015", "P406", "P412", "P413", "P414", "P415",
              "P708", "P104", "P105", "P106", "P107", "P600", "P601", "P205", "P206", "P207", "P208",
              "P209", "P210", "P211", "P214", "P301", "P302", "P303", "P304", "P305", "P306", "P307"]
for _net in _FREE_GPIO:
    MCU_NETS[_net] = _net
PARTS.append(Part("J10", "Connector_Generic:Conn_02x20_Odd_Even", "GPIO ACCESS",
                  "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical", (565, 405),
                  {str(i + 1): net for i, net in enumerate(_FREE_GPIO + ["GND", "+3V3", "GND", "+3V3", "GND", "+3V3", "GND"])},
                  fields={"Manufacturer": "Samtec", "MPN": "TSW-120-07-G-D",
                          "Description": "Original 2x20 GPIO access header; pin map from Renesas R01DS0367 Table 1.17; 3.3 V logic, shared power budget"}))
PLACEMENT["J10"] = (35.0, 68.0, 0)

# Lay USB, local supply control, oscillator and bypass connections before fan-out.
PRIORITY = [
    (('J2', 'A6'), ('U3', '3')),
    (('J2', 'A7'), ('U3', '2')),
    (('U6', '3'), ('U3', '3')),
    (('U6', '4'), ('U3', '2')),
    (('J2', 'B6'), ('J2', 'A6'), 'join'),
    (('J2', 'B7'), ('J2', 'A7'), 'join'),
    # The debug pair's lines enclose R10 and R11, so each CC line needs vias to reach its Rd.
    # Lay both before the autorouter, which otherwise used their via sites (build 3: CC1 open).
    (('J2', 'A5'), ('R10', '1')),
    (('J2', 'B5'), ('R11', '1')),
    # The debug ESD part's common pin straight to the connector's ground contacts. The debug pair
    # leaves it no room for a dog-bone via, so this line takes its vias beside the two pads.
    (('U3', '1'), ('J2', 'B12')),
    # Device port: the trunk leaves J1's B row, where D+ (B6) lies above D- (B7) as at the MCU (pins
    # 28 over 27), so the pair never crosses itself. A7 then joins B7 round the free side of A6, and
    # A6 joins B6 round the other side of A7: both stay on the top layer, with no via.
    (('J1', 'B6'), ('U2', '2')),
    (('J1', 'B7'), ('U2', '3')),
    (('U1', '28'), ('R6', '2')),
    (('U1', '27'), ('R7', '2')),
    (('R6', '1'), ('U2', '2')),
    (('R7', '1'), ('U2', '3')),
    (('J1', 'A7'), ('J1', 'B7'), 'join'),
    (('J1', 'A6'), ('J1', 'B6'), 'join'),
    (('U5', '3'), ('R18', '2')),
    (('R18', '2'), ('R19', '1')),
    (('U4', '2'), ('U4', '7')),
    (('U4', '5'), ('R16', '1')),
    (('U4', '3'), ('C20', '1')),
    (('U4', '6'), ('C21', '1')),
    (('U4', '4'), ('R16', '2')),
    (('R16', '2'), ('R17', '1')),
    (('U5', '8'), ('C25', '1')),
    (('U5', '7'), ('U5', '9'), 'join'),
    (('U5', '9'), ('C23', '1')),
    (('U5', '1'), ('C24', '1')),
    # Oscillators: VCL, then the VSS 12 ground spine (pin 12 to C5's and C1's ground pads), then
    # each clock pair, the outer line of each pair first (XCOUT before XCIN under C5).
    (('U1', '9'), ('C5', '1')),
    (('U1', '12'), ('C5', '2')),
    (('C1', '2'), ('C5', '2')),
    (('U1', '11'), ('Y2', '1')),
    (('Y2', '1'), ('C14', '1')),
    (('U1', '10'), ('Y2', '2')),
    (('Y2', '2'), ('C13', '1')),
    (('U1', '13'), ('Y1', '1')),
    (('Y1', '1'), ('C11', '1')),
    (('U1', '14'), ('Y1', '3')),
    (('Y1', '3'), ('C12', '1')),
    (('U1', '15'), ('C1', '1')),
    # VSS 12 and the oscillator ground hanging off it join the board ground under the MCU, not
    # through the shield (R01AN7202 6.1.2(4)): a ground line from pin 12's inner end to VSS 63, and
    # from VSS 83, VSS 45 and VSS_USB 26 inward to it, each laid before those pins' own capacitor
    # lines. Build 9 left the whole oscillator ground on one 0.15 mm bottom-layer track.
    # A join stops at the first ground copper it meets; its far pad only steers the search, and the
    # maze lays the straight part of a path first. So 83 and 45 steer at each other (straight
    # across), and 26 steers at the opposite corner pin 75, a pure diagonal that keeps off the
    # inner ends of its neighbours, whose lines escape inward.
    (('U1', '12'), ('U1', '63')),
    (('U1', '83'), ('U1', '45'), 'join'),
    (('U1', '45'), ('U1', '83'), 'join'),
    (('U1', '26'), ('U1', '75'), 'join'),
    # Each MCU decoupling capacitor: supply pin to its supply pad, then VSS pin to its ground pad.
    (('U1', '46'), ('C2', '1')),
    (('U1', '45'), ('C2', '2')),
    (('U1', '62'), ('C3', '1')),
    (('U1', '63'), ('C3', '2')),
    (('U1', '82'), ('C4', '1')),
    (('U1', '83'), ('C4', '2')),
    (('U1', '29'), ('C6', '1')),
    # VSS_USB (26) lies below the USB pair and C6 above it: this ground line crosses under the pair
    (('U1', '26'), ('C6', '2')),
    (('U1', '88'), ('C7', '1')),
    (('U1', '89'), ('C7', '2')),
    (('U1', '91'), ('C8', '1')),
    (('U1', '90'), ('C8', '2')),
    (('U1', '87'), ('C7', '1'), 'join'),
    (('U6', '6'), ('C16', '1')),
    (('U6', '5'), ('C16', '1'), 'join'),
    (('U6', '7'), ('C17', '1')),
    (('C18', '1'), ('C16', '1'), 'join'),
    (('U6', '9'), ('R12', '1')),
    (('R12', '2'), ('C19', '1')),
    (('C19', '1'), ('C17', '1'), 'join'),
    (('U6', '8'), ('R14', '1')),
    (('R13', '2'), ('R14', '1'), 'join'),
    (('U6', '2'), ('U6', '25'), 'join'),
    # The CP2102N's 3.3 V straight from the regulator's output capacitor; build 9 joined it to the
    # rest of +3V3 by a 110 mm detour round the MCU.
    (('C24', '1'), ('C16', '1')),
    # Build 4 left these to the autorouter and they stayed open: the LDO output to the MCU's
    # supply (the 0.3 mm +3V3 class is the router's hardest net) and R17's ground end inside the
    # closed MUX_PR1 / VBUS route loop, whose only via site a bottom-layer track then covered.
    (('C6', '1'), ('C24', '1')),
    (('R17', '2'), ('C21', '2')),
]

_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS RA4M2 Board", "x": 40.0, "y": 58.0, "size": 1.4, "bold": True},
    {"text": "GPIO ACCESS  /  3.3V ONLY", "x": 40.0, "y": 62.0, "size": 1.0},
    {"text": "Expansion supply total: 150mA", "x": 40.0, "y": 121.0, "size": 1.0},
    {"text": "All power headers: outputs only", "x": 40.0, "y": 124.0, "size": 1.0},
    {"text": "EoS RA4M2 Board  rev A", "x": 34.0, "y": 40.0, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 34.0, "y": 42.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 34.0, "y": 43.4, "size": 0.8, "layer": "B_SilkS", "mirror": True},
]
# Pmod pin 1 is pad 11 of each socket (PMOD_PAD), not the footprint's square pad (Pmod pin 6, 3.3 V)
for _ref in ("J7", "J8"):
    TEXTS.append({"text": "1", "x": PLACEMENT[_ref][0] + 1.9, "y": PLACEMENT[_ref][1] + 12.7, "size": 1.0})

# Label the original GPIO connector by signal, on each side of its pad rows.
for _i, _label in enumerate(_FREE_GPIO + ["GND", "3V3", "GND", "3V3", "GND", "3V3", "GND"]):
    TEXTS.append({"text": f"{_i + 1}:{_label}", "x": 30.5 if _i % 2 == 0 else 42.1,
                  "y": 68.0 + (_i // 2) * 2.54, "size": 0.8})

BOARD = Board(
    name="eos-ra4m2-board",
    title="EoS RA4M2 Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["Overall 80 x 170 mm dimensions: Renesas EK-RA4M2 user manual R20UT4815EG0100 section 3; facts only.",
             "Uno R3 relative connector coordinates: Matthew Beckler Arduino Uno R3 dimension drawing v1.05, public domain; facts only.",
             "Pmod connector geometry and pin numbering: Digilent Pmod Interface Specification 1.3.0, Figure 5; facts only."],
    width=W,
    height=H,
    corner_radius=1.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    priority_routes=PRIORITY,
    # Bottom-layer keep-outs, so the ground pour there stays solid: under the clock lines from the
    # MCU pins down, and under both oscillators to beyond the load capacitors (R01AN7202 6.1.1 and
    # 6.1.3.1); and from the CP2102N decoupling capacitors' ground vias to its exposed pad's vias.
    # Beside the clock lines, the pins either side may still drop to the bottom layer below the row.
    # A top-layer keep-out left of the 32.768 kHz crystal keeps other lines out of its courtyard and
    # off its XCIN pad (build 7 ran P406 0.17 mm beside it).
    router_keepouts=[(29.6, 29.4, 34.6, 33.0, "B.Cu"), (27.0, 33.0, 38.4, 42.8, "B.Cu"),
                     (64.0, 8.75, 67.3, 12.4, "B.Cu"), (26.0, 33.3, 27.35, 40.4, "F.Cu")],
    # A via beside each ground pad of these parts, into the bottom pour: the MCU and CP2102N decoupling,
    # the crystals and their loads, the ESD parts' common pins and the regulator with its capacitors.
    ground_vias=["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14", "Y1",
                 "C16", "C17", "C18", "C19", "U2", "U3", "U5", "C23", "C24", "C25", "R19"],
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "VBUS_DEV", "VBUS_DEV_F", "VBUS_DBG", "VBUS_DBG_F", "AVCC0"],
    notes=[((260, 470), "EoS RA4M2 Board, rev A. Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "3.3 V logic; all header power pins are outputs. All expansion loads share 150 mA.\n"
                       "JP1 fitted at reset selects SCI/USB boot. SWO and UART TXD9 share P109.\n"
                       "80 x 170 mm outline from R20UT4815EG0100; original connector locations.")],
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS_DEV": "Power", "VBUS_DBG": "Power", "VBUS_DEV_F": "Supply", "VBUS_DBG_F": "Supply",
                  "+5V": "Supply", "+3V3": "Supply", "AVCC0": "Supply", "VCL": "Supply",
                  "DEV_C_DP": "USB", "DEV_C_DM": "USB", "USB_DP": "USB", "USB_DM": "USB", "DBG_C_DP": "USB", "DBG_C_DM": "USB"},
)
