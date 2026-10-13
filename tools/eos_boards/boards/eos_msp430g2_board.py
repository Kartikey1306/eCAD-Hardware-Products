"""EoS MSP430G2 Board: a BoosterPack-compatible (20-pin) MSP430G2553 board with a DIP-20 socket, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-msp430g2-board/LICENSE.txt.

A two-layer board for the TI MSP430G2553 in its 20-pin PDIP package, held in a socket so the
chip can be swapped or programmed elsewhere. Two 1x10 headers that follow TI's 20-pin
BoosterPack standard, a USB-C serial port (CP2102N), a Spy-Bi-Wire connector for a standard
MSP-FET, two user LEDs, a user button and a reset button. No vendor board file was used. Each
component value comes from the chip or part maker's document named next to it. The user-I/O
pins (red LED on P1.0, green LED on P1.6, button on P1.3) were chosen from the BoosterPack
standard's pin functions and common MSP430 practice, not from a datasheet: J1.2 (P1.0) is
"Analog In", J1.5 (P1.3) is "GPIO interrupt capable", and P1.6 is P1.6/TA0.1, a timer output.

* BoosterPack headers J1 and J2: TI's 20-pin standard (BoosterPack Standards and Design Guide,
  TI processors wiki, archived 2017-11-03): two 1x10 headers on a 0.1 in grid, 1.8 in
  (45.72 mm) apart, J1.1 and J2.20 level at the top. J1: 1 VCC, 2 P1.0, 3 P1.1 (UART RX),
  4 P1.2 (UART TX), 5 P1.3, 6 P1.4, 7 P1.5, 8 P2.0, 9 P2.1, 10 P2.2. J2, top to bottom: 20 GND,
  19 P2.6/XIN, 18 P2.7/XOUT, 17 TEST, 16 RST, 15 P1.7, 14 P1.6, 13 P2.5, 12 P2.4, 11 P2.3. These
  are the PDIP-20's two pin columns in order (TI SLAS735J, N20), so every line runs straight.
* MSP430G2553IN20 (TI SLAS735J), run at 3.3 V. SLAS735J gives no decoupling values; TI
  SLAU278AH Figure 2-2 (Spy-Bi-Wire, G2xx devices) shows 10 uF and 0.1 uF on DVCC.
* RST/NMI/SBWTDIO: 47 kohm pull-up and 1 nF to ground (SLAU278AH Figure 2-2: 47 kohm; the pin
  carries SBW data, so "the upper limit for C1 is 2.2 nF when using current TI tools", typical
  1.1 nF; SLAU144K Table 2-3 gives the same 2.2 nF limit). A button pulls it to ground. The pull-up
  sits below the pin, so the MCU supply reaches it from below, away from XOUT.
* TEST/SBWTCK: SLAS735J gives a 25-90 kohm internal pull-down. SLAU278AH Figure 2-2 note D allows
  a 500 ohm-1 kohm pull-down "for applications that are particularly concerned with excessive
  noise or ESD"; R14 (1 kohm) is that option, not fitted.
* 32.768 kHz crystal: Abracon ABS07-32.768KHZ-6-T (ABS07 datasheet, "REVISED: 08-10-22"):
  CL = 6 pF, ESR 70 kohm max. SLAA322D section 2.1 says to count every parasitic capacitance,
  traces and pins included, and Equation 3 gives CL1 = 2 x CLoad - Cparasitic. Per pin:
  2 pF of bond and package (SLAS735J, note 2 to the XT1 table, the part that makes up its
  XCAPx = 0 setting) plus an estimated 1-2 pF for the socket and the trace (7.2 mm of copper on
  XIN, 8.6 mm on XOUT: pin to crystal pad to load capacitor, then a 0.85 mm stub to the unfitted
  0 ohm link): 3-4 pF.
  CL1 = 12 - (3 to 4) = 8-9 pF, so 8.2 pF is fitted (load 5.6-6.1 pF). Firmware must set
  XCAPx = 00 (BCSCTL3 bits 3-2, SLAU144K Table 5-5). The reset value, 01 (about 6 pF), or code
  written for boards without load capacitors that sets XCAPx = 11 (12.5 pF), adds to C10/C11
  and runs ACLK slow (SLAA322D Figure 5). SLAS735J gives an oscillation allowance of 500 kohm
  at CL,eff = 6 pF, 7 times the ESR: "very safe" by SLAA322D Table 2. Measure ACLK on a built
  board (SLAS735J note 2).
* P2.6/P2.7 on J2.19/J2.18: these are the crystal pins, and SLAS735J XT1 note 1 says to keep
  other traces and crosstalk off XIN/XOUT. A BoosterPack trace there would load the crystal, so
  the header pins are joined only through two 0 ohm links (R11, R12), not fitted. To give a
  BoosterPack P2.6 (its "Timer Out" pin) and P2.7, remove Y1, C10 and C11 and fit the links.
* User I/O: red LED on P1.0 and green LED on P1.6 through jumper JP4, button on P1.3. SLAS735J
  gives every port pin a 20-50 kohm pull-up (RPull, enabled by P1REN), so P1.3 has no external
  one. LED resistors from the LED datasheets (Kingbright, at IF = 2 mA): red APTD1608LSURCK
  VF 1.75 V typ, green APTD1608LCGCK 1.9 V, yellow APTD1608LSYCK 1.85 V. 680 ohm from 3.3 V gives
  2.0-2.3 mA; with SLAS735J's worst-case VOH = VCC - 0.3 V, 1.6-1.8 mA.
* Programming: the MSP-FET 14-pin connector, wired as SLAU278AH Figure 2-2: pin 1 TDO/TDI to
  RST/NMI/SBWTDIO, pin 7 TCK to TEST/SBWTCK, pin 9 GND. Fuse blow is not supported, so (note C)
  TEST/VPP, pin 8, stays open and the 330 ohm R2 is not needed. This connector replaces TI's
  on-board eZ-FET, whose firmware is TI's.
* Power and the supply choice. One 1x3 header, JP1, feeds the board's 3.3 V rail (+3V3) from
  either the LDO (1-2, "USB") or the MSP-FET's VCC_TOOL, J4 pin 2 (2-3, "FET"). One shunt can
  make only one of those joins, so the LDO and the MSP-FET can never both drive the rail. That
  matters because the MSP-FET puts 3.3 V on pin 2 as soon as it powers up (TI SLAU647O Table 8).
  J4 pin 4, VCC_TARGET, is wired to the LDO output: it is an input in every state
  ("In, external VCC sense", Table 8), so with JP1 at 1-2 the MSP-FET senses the board's own
  supply (SLAU278AH Figure 2-2, J1). At 2-3 the rail meets pin 2 only. SLAU647O section 3.5:
  "Only pin 2 ... or pin 4 ... must be connected. Both connections are not supported at the
  same time." The MSP-FET supplies up to 100 mA, and SLAU647O asks for no more than 60 mA peak.
* MCU current: JP2 joins +3V3 to the MCU's own supply, VMCU (DVCC, its decoupling, the RST
  pull-up). Take it off and fit an ammeter to measure the MCU alone: the CP2102N, the power LED
  and the BoosterPack (J1.1) are on +3V3, outside the measurement. Every supply (LDO, MSP-FET, a
  BoosterPack on J1.1) feeds +3V3, and VMCU is fed only from +3V3 through JP2. So the CP2102N is
  powered whenever the MCU is, and P1.2 never drives an unpowered CP2102N, whose pins are rated
  VIO + 2.5 V while VIO < 3.3 V (CP2102N Rev. 1.5 Table 3.10). Only with JP2 open can the MCU be
  unpowered while the CP2102N runs. R10, 2.2 kohm in the CP2102N TXD line, then holds the current
  into P1.1's clamp to 3.6 V / 2.2 kohm = 1.6 mA, under SLAS735J's +/-2 mA absolute maximum
  "diode current at any device pin". At up to 1 Mbaud, 2.2 kohm into the pin's few pF delays
  edges by tens of ns, against a bit time of at least 1 us.
* USB-C: a 5 V sink (5.1 kohm on CC1 and CC2), the 500 mA polyfuse (Littelfuse 1206L050:
  0.50 A hold, 1.00 A trip, 6 V, R1max 0.70 ohm; 1206L series datasheet), then a PMEG6010CEH
  Schottky (Nexperia PMEG6010CEH v.4: VF <= 400 mV at 100 mA, <= 530 mV at 500 mA), then the
  AP7361C-33 LDO (Diodes DS37274 Rev. 5-2: input 2.2-6.0 V, at least 1 uF in and 2.2 uF out;
  4.7 uF on each, as its typical application shows). D4 stops the 3.3 V side reaching VBUS: when
  a BoosterPack feeds +3V3 with JP1 at 1-2 and USB unplugged, the LDO output lifts its input, and
  without D4 VBUS would rise to about 2.7 V, so a Type-C source waiting for vSafe0V might never
  turn on. R13, 5.1 kohm from VBUS to ground, sinks D4's leakage (<= 50 uA at 60 V, 0.8 uA typ at
  5 V, 25 C). With the CP2102N's divider in parallel that is 4.75 kohm, so up to 168 uA keeps VBUS
  under 0.8 V. A host pays 1.0 mA for it.
* USB serial: CP2102N-A02-GQFN20 (Silicon Labs CP2102N data sheet Rev. 1.5). Its regulator is not
  used (Figure 2.3): VREGIN and VDD share +3V3, so its UART levels match the MCU's. 4.7 uF and
  0.1 uF on each power pin, 1 kohm pull-up on RSTb (section 2.1). VBUS sense through the
  22.1 kohm / 47.5 kohm divider of Figure 2.5 (section 2.3: "a resistor divider ... on VBUS is
  required"): 3.41 V from 5 V, above VIH = VIO - 0.6 V, the level it uses "to detect when
  the device is connected to a bus" (section 2.3, Table 3.7). The CP2102N stays powered without a
  host, so R13 keeps that pin reading "no bus" until a cable is in. ESD protection is
  the SP0503BAHTG the data sheet shows in Figure 2.5: three diodes with a common anode to ground
  and their cathodes on D+, D- and VBUS. Nothing joins D+ or D- to VBUS, so a powered CP2102N's
  D+ pull-up cannot hold VBUS up after the host unplugs, as a steering-diode array's diodes to
  its VBUS pin could. Littelfuse's SP05xxBA data sheet gives the SP0503BAHT's figures: 5.5 V
  standoff, 1 nA typical and 100 nA maximum leakage at 5 V, 30 pF typical, pin 1 the common
  anode. TXD and RXD meet P1.1 (RXD) and P1.2 (TXD) through jumpers JP3.
  With JP1 at 2-3 and the MSP-FET not powering the rail, the CP2102N is unpowered while a USB
  host still drives VBUS onto its VBUS pin through R5/R6, above the VIO + 2.5 V of Table 3.10.
  Silicon Labs accepts that case (section 2.3: "the current limitation of the resistor divider
  prevents high VBUS pin leakage current, even though the VIO + 2.5 V specification is not
  strictly met while the device is not powered"); the README still says to unplug USB then.
* USB layout. The ESD array sits directly behind the receptacle (ST DS4260 Rev 7 section 2.3
  and TI SPMA059 section 4.1: protection as close as possible to the connector), turned so the
  data lines run straight in from the receptacle's A6 (D+) and A7 (D-) contacts and on to the
  CP2102N with D+ above D-, the CP2102N's own pin order. The receptacle duplicates each data
  contact (B6 = D+, B7 = D-) in the order D-, D+, D-, D+, so each B contact crosses the other
  line to reach its twin; both crossings are made behind the pad row, on the bottom layer
  through a via pair, none under the receptacle's shell, which a keep-out in front of the pads
  enforces. VBUS reaches the array's VBUS pin from the A9/B4 pair. All of it, and the crystal,
  the decoupling and the Spy-Bi-Wire clock, are laid first as priority routes, top layer, since
  the autorouter gives a different result on every run.
* 16 MHz at 3.3 V: SLAS735J allows 16 MHz only from VCC = 3.3 V up (12 MHz at 2.7 V, linear
  between; Recommended Operating Conditions and Figure 1). The AP7361C-33 is 3.3 V +-1 % at
  25 C and 100 mA, with up to 1 % more load regulation (DS37274), so at its low limit, 3.27 V,
  the safe ceiling is about 15.8 MHz. Run from the LDO at 12 MHz (CALBC1_12MHZ) for a full
  margin, or at 16 MHz with the MSP-FET supplying 3.4-3.6 V (JP1 at 2-3).
* Power budget, from USB: MCU about 5 mA at 16 MHz (SLAS735J active-mode figure), user LEDs
  4.6 mA, power LED 2.1 mA, CP2102N 13.7 mA at 3 Mbaud plus 0.23 mA of USB pull-up (Rev. 1.5
  Table 3.2): about 26 mA. A BoosterPack may draw up to 300 mA more. At 326 mA the LDO dissipates
  at most (5.25 V - 3.3 V) x 0.326 A = 0.64 W, counting no drop in the fuse or D4: 70 C above
  ambient at DS37274's 110 C/W (SOT-223, minimum pad), against its 150 C thermal shutdown. At
  4.75 V in, the fuse (0.70 ohm) and D4 (<= 0.53 V) leave 3.99 V, above the 3.44 V the LDO needs
  (140 mV dropout at 300 mA). The fuse holds 0.42 A at 40 C (1206L derating table). From the
  MSP-FET (JP1 at 2-3) the same board load is about 26 mA, which leaves about 34 mA for a
  BoosterPack within SLAU647O's 60 mA.
"""

from __future__ import annotations

from ..design import NC, USB_C_EDGE, Board, Part
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
HDR = "Connector_PinHeader_2.54mm:PinHeader_"
CP2102N = "Silicon Labs CP2102N data sheet Rev. 1.5"


def res(ref, value, a, b, sch, desc, dnp=False):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields={"Description": desc}, dnp=dnp)


def cap(ref, value, a, b, sch, desc, fp=C0402, mpn=None):
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b},
                fields={"Description": desc, **({"Manufacturer": "Murata", "MPN": mpn} if mpn else {})})


def led(ref, value, anode, sch, mpn, desc):
    return Part(ref, "Device:LED_Small", value, LED0603, sch, {"A": anode, "K": "GND"},
                fields={"Manufacturer": "Kingbright", "MPN": mpn, "Description": desc})


W, H = 56.0, 80.0
HDR_TOP = 10.0                     # y of J1 pin 1 and J2 pin 20
J1_X, J2_X = W / 2 - 22.86, W / 2 + 22.86   # 1.8 in apart, centred on the board

# The MSP430G2553's PDIP-20 pins (SLAS735J, N20), by number.
MCU = {"1": "VMCU", "2": "P1_0", "3": "P1_1", "4": "P1_2", "5": "P1_3", "6": "P1_4", "7": "P1_5",
       "8": "P2_0", "9": "P2_1", "10": "P2_2", "11": "P2_3", "12": "P2_4", "13": "P2_5", "14": "P1_6",
       "15": "P1_7", "16": "RST_NMI", "17": "TEST_SBWTCK", "18": "XOUT", "19": "XIN", "20": "GND"}
# BoosterPack J1 pins 1-10, top to bottom (TI 20-pin standard, header "A"). J1.1 is the board's
# 3.3 V rail, so a BoosterPack is outside the MCU current measurement.
J1_PINS = ["+3V3", "P1_0", "P1_1", "P1_2", "P1_3", "P1_4", "P1_5", "P2_0", "P2_1", "P2_2"]
# BoosterPack J2 pins 20 down to 11, top to bottom (header "B"). Footprint pin k is J2 pin 21 - k,
# so pin 1, the square pad, is J2.20 (GND) at the top, as in TI's figure.
J2_PINS = ["GND", "HDR_P2_6", "HDR_P2_7", "TEST_SBWTCK", "RST_NMI", "P1_7", "P1_6", "P2_5", "P2_4", "P2_3"]

PARTS = [
    # ---- USB-C, ESD, fuse, reverse block, 3.3 V --------------------------------------------------
    Part("J3", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (50, 120), {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_D+", "D-": "USB_D-",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12",
                 "Description": "USB-C 2.0 receptacle, 16 pins: power and the CP2102N serial port"}),
    res("R1", "5.1k", "CC1", "GND", (95, 100), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd, CC1; USB Type-C specification)"),
    res("R2", "5.1k", "CC2", "GND", (110, 100), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd, CC2; USB Type-C specification)"),
    res("R13", "5.1k", "VBUS", "GND", (125, 100), "Resistor 5.1 kohm 1% 0402 (VBUS bleed: with the CP2102N divider 4.75 kohm, "
        "so up to 168 uA of D4 leakage keeps VBUS under 0.8 V; PMEG6010CEH v.4 IR <= 50 uA at 25 C)"),
    Part("U3", "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", (140, 120),
         {"1": "GND", "2": "USB_D+", "3": "USB_D-", "4": "VBUS"},
         fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                 "Description": f"USB ESD protection, common-anode TVS array on D+, D-, VBUS: 5.5 V standoff, 30 pF "
                                f"(Littelfuse SP05xxBA; {CP2102N} Figure 2.5)"}),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (165, 100), {"1": "VBUS", "2": "VBUS_F"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                 "Description": "PTC resettable fuse 0.50 A hold, 1.00 A trip, 6 V, R1max 0.70 ohm, 1206 (Littelfuse 1206L series)"}),
    Part("D4", "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F", (185, 100), {"A": "VBUS_F", "K": "+5V"},
         fields={"Manufacturer": "Nexperia", "MPN": "PMEG6010CEH,115",
                 "Description": "Schottky 60 V 1 A, VF <= 400 mV at 100 mA (Nexperia PMEG6010CEH v.4): the 3.3 V side cannot lift VBUS"}),
    Part("U4", "Regulator_Linear:AP7361C-33E", "AP7361C-33", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (210, 120),
         {"VI": "+5V", "VO": "LDO_3V3", "GND": "GND"},
         fields={"Manufacturer": "Diodes Incorporated", "MPN": "AP7361C-33E-13",
                 "Description": "LDO 3.3 V 1 A, SOT-223; input 2.2-6.0 V (Diodes DS37274 Rev. 5-2)"}),
    cap("C1", "4.7u", "+5V", "GND", (230, 110), "Capacitor 4.7 uF 10 V X5R 0805 (LDO input: DS37274 requires >= 1 uF, "
        "typical application 4.7 uF)", C0805),
    cap("C2", "4.7u", "LDO_3V3", "GND", (245, 110), "Capacitor 4.7 uF 10 V X5R 0805 (LDO output: DS37274 requires >= 2.2 uF "
        "ceramic, typical application 4.7 uF)", C0805),
    Part("JP1", "Connector_Generic:Conn_01x03", "PWR", HDR + "1x03_P2.54mm_Vertical", (300, 115),
         {"1": "LDO_3V3", "2": "+3V3", "3": "FET_VCC_TOOL"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-103-07-G-S", "Description": "Supply jumper, one shunt: 1-2 USB (LDO powers +3V3, MSP-FET senses it on J4 pin 4), "
                                "2-3 FET (MSP-FET VCC_TOOL, J4 pin 2, powers +3V3)"}),
    res("R3", "680", "+3V3", "LED_PWR_A", (330, 110), "Resistor 680 ohm 1% 0402 (power LED: (3.3 - 1.85 V) / 680 = 2.1 mA, "
        "Kingbright APTD1608LSYCK VF at 2 mA)"),
    led("D3", "PWR", "LED_PWR_A", (345, 110), "APTD1608LSYCK", "LED yellow 0603, +3V3 present"),
    Part("JP2", "Connector_Generic:Conn_01x02", "IMCU", HDR + "1x02_P2.54mm_Vertical", (370, 115),
         {"1": "+3V3", "2": "VMCU"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-102-07-G-S", "Description": "Jumper: +3V3 to the MCU supply (VMCU). Remove and fit an ammeter to measure the MCU alone"}),

    # ---- CP2102N USB-UART ---------------------------------------------------------------------------
    Part("U2", "Interface_USB:CP2102N-Axx-xQFN20", "CP2102N-A02-GQFN20",
         "Package_DFN_QFN:SiliconLabs_QFN-20-1EP_3x3mm_P0.5mm_EP1.8x1.8mm", (90, 230),
         {"VDD": "+3V3", "VREGIN": "+3V3", "GND": "GND", "D+": "USB_D+", "D-": "USB_D-", "VBUS": "USB_SENSE",
          "~{RST}": "BR_RST", "TXD": "BR_TXD", "RXD": "BR_RXD",
          **{p: NC for p in ("RS485/GPIO.1", "CLK/GPIO.0", "NC", "~{SUSPEND}", "~{WAKEUP}", "SUSPEND", "~{CTS}",
                             "~{RTS}", "~{RXT}/GPIO.3", "~{TXT}/GPIO.2")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN20R",
                 "Description": f"USB to UART bridge, QFN-20; internal regulator unused ({CP2102N} Figure 2.3)"}),
    cap("C3", "4.7u", "+3V3", "GND", (140, 205), f"Capacitor 4.7 uF 10 V X5R 0805 (CP2102N VDD; {CP2102N} section 2.1: "
        "4.7 uF and 0.1 uF on each power pin)", C0805),
    cap("C4", "100n", "+3V3", "GND", (152, 205), f"Capacitor 100 nF X7R 0402 (CP2102N VDD; {CP2102N} section 2.1)"),
    cap("C5", "4.7u", "+3V3", "GND", (164, 205), f"Capacitor 4.7 uF 10 V X5R 0805 (CP2102N VREGIN; {CP2102N} section 2.1)", C0805),
    cap("C6", "100n", "+3V3", "GND", (176, 205), f"Capacitor 100 nF X7R 0402 (CP2102N VREGIN; {CP2102N} section 2.1)"),
    res("R4", "1k", "BR_RST", "+3V3", (140, 250), f"Resistor 1 kohm 1% 0402 (CP2102N RSTb pull-up to VDD; {CP2102N} section 2.1)"),
    res("R5", "22.1k", "VBUS", "USB_SENSE", (160, 250), f"Resistor 22.1 kohm 1% 0402 (CP2102N VBUS sense divider, {CP2102N} "
        "Figure 2.5)"),
    res("R6", "47.5k", "USB_SENSE", "GND", (175, 250), f"Resistor 47.5 kohm 1% 0402 (CP2102N VBUS sense divider: 3.41 V "
        f"from 5 V; {CP2102N} Figure 2.5, Tables 3.7 and 3.10)"),
    res("R10", "2.2k", "BR_TXD", "BR_TXD_R", (192, 250), "Resistor 2.2 kohm 1% 0402 (CP2102N TXD to P1.1: with JP2 open, "
        "3.6 V / 2.2 kohm = 1.6 mA into the unpowered MCU's clamp, under SLAS735J's +/-2 mA)"),
    Part("JP3", "Connector_Generic:Conn_02x02_Odd_Even", "UART", HDR + "2x02_P2.54mm_Vertical", (210, 235),
         {"1": "BR_TXD_R", "2": "P1_1", "3": "BR_RXD", "4": "P1_2"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-102-07-G-D", "Description": "Jumpers: 1-2 CP2102N TXD to P1.1 (UCA0RXD), 3-4 CP2102N RXD from P1.2 (UCA0TXD)"}),

    # ---- MSP430G2553 ------------------------------------------------------------------------------
    Part("U1", "MCU_Texas_MSP430:MSP430G2553IN20", "MSP430G2553IN20", "Package_DIP:DIP-20_W7.62mm_Socket", (300, 230),
         MCU, fields={"Manufacturer": "Texas Instruments", "MPN": "MSP430G2553IN20",
                      "Socket": "Mill-Max 110-43-320-41-001000 (20-pin, 0.3 in, machined, gold contacts)",
                      "Description": "MSP430G2553 16 kB flash, 512 B RAM, PDIP-20, fitted in a DIP-20 socket (TI SLAS735J)"}),
    cap("C7", "10u", "VMCU", "GND", (370, 195), "Capacitor 10 uF 10 V X5R 0805 (DVCC; TI SLAU278AH Figure 2-2, C2)", C0805),
    cap("C8", "100n", "VMCU", "GND", (385, 195), "Capacitor 100 nF X7R 0402 (DVCC; TI SLAU278AH Figure 2-2, C3)"),
    res("R7", "47k", "RST_NMI", "VMCU", (370, 240), "Resistor 47 kohm 1% 0402 (RST/NMI pull-up; TI SLAU278AH Figure 2-2, R1)"),
    cap("C9", "1n", "RST_NMI", "GND", (385, 250), "Capacitor 1 nF C0G 0402 (RST/NMI; SBW limit 2.2 nF, typical 1.1 nF: "
        "TI SLAU278AH Figure 2-2 note B, SLAU144K Table 2-3)", mpn="GRM1555C1H102JA01D"),
    res("R14", "1k", "TEST_SBWTCK", "GND", (395, 268), "Resistor 1 kohm 0402, not fitted: TEST pull-down for noise or ESD "
        "(TI SLAU278AH Figure 2-2 note D: 500 ohm-1 kohm)", dnp=True),
    Part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_THT:SW_PUSH_6mm", (410, 250), {"1": "RST_NMI", "2": "GND"},
         fields={"Manufacturer": "TE Connectivity", "MPN": "1825910-6", "Description": "Tactile switch 6 x 6 mm, reset (RST/NMI)"}),
    Part("Y1", "Device:Crystal_Small", "32.768kHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", (370, 290),
         {"1": "XIN", "2": "XOUT"},
         fields={"Manufacturer": "Abracon", "MPN": "ABS07-32.768KHZ-6-T",
                 "Description": "Crystal 32.768 kHz, CL 6 pF, ESR 70 kohm max, 3.2 x 1.5 mm (Abracon ABS07); "
                                "firmware sets XCAPx = 00"}),
    cap("C10", "8.2p", "XIN", "GND", (360, 305), "Capacitor 8.2 pF +/-0.25 pF C0G 50 V 0402 (XIN load: 2 x 6 pF - 3 to 4 pF, "
        "TI SLAA322D Eq. 3; 2 pF package (SLAS735J) + 1-2 pF socket and trace; XCAPx = 00)", mpn="GRM1555C1H8R2CA01D"),
    cap("C11", "8.2p", "XOUT", "GND", (380, 305), "Capacitor 8.2 pF +/-0.25 pF C0G 50 V 0402 (XOUT load: 2 x 6 pF - 3 to 4 pF, "
        "TI SLAA322D Eq. 3; 2 pF package (SLAS735J) + 1-2 pF socket and trace; XCAPx = 00)", mpn="GRM1555C1H8R2CA01D"),
    res("R11", "0", "XIN", "HDR_P2_6", (405, 285), "Resistor 0 ohm 0402, not fitted: P2.6 to BoosterPack J2.19 when Y1, C10, "
        "C11 are removed (SLAS735J XT1 note 1: no other traces on XIN)", dnp=True),
    res("R12", "0", "XOUT", "HDR_P2_7", (405, 300), "Resistor 0 ohm 0402, not fitted: P2.7 to BoosterPack J2.18 when Y1, C10, "
        "C11 are removed (SLAS735J XT1 note 1: no other traces on XOUT)", dnp=True),

    # ---- BoosterPack headers --------------------------------------------------------------------
    Part("J1", "Connector:Conn_01x10_Pin", "BoosterPack J1", HDR + "1x10_P2.54mm_Vertical", (465, 120),
         {str(i + 1): net for i, net in enumerate(J1_PINS)},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-110-07-G-S", "Description": "BoosterPack J1, pins 1-10 (TI 20-pin standard): VCC (+3V3), P1.0, P1.1 RX, P1.2 TX, "
                                "P1.3, P1.4, P1.5, P2.0, P2.1, P2.2"}),
    Part("J2", "Connector:Conn_01x10_Pin", "BoosterPack J2", HDR + "1x10_P2.54mm_Vertical", (465, 170),
         {str(i + 1): net for i, net in enumerate(J2_PINS)},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-110-07-G-S", "Description": "BoosterPack J2: footprint pin k is J2 pin 21-k; top to bottom J2.20 GND, J2.19 P2.6, "
                                "J2.18 P2.7, J2.17 TEST, J2.16 RST, J2.15 P1.7, J2.14 P1.6, J2.13 P2.5, J2.12 P2.4, J2.11 P2.3"}),

    # ---- Programming: MSP-FET 14-pin JTAG connector, wired for Spy-Bi-Wire -----------------------
    Part("J4", "Connector_Generic:Conn_02x07_Odd_Even", "MSP-FET", "Connector_IDC:IDC-Header_2x07_P2.54mm_Vertical",
         (300, 330), {"1": "RST_NMI", "2": "FET_VCC_TOOL", "3": NC, "4": "LDO_3V3", "5": NC, "6": NC,
                      "7": "TEST_SBWTCK", "8": NC, "9": "GND", "10": NC, "11": NC, "12": NC, "13": NC, "14": NC},
         fields={"Manufacturer": "Wurth Elektronik", "MPN": "61201421621",
                 "Description": "MSP-FET 14-pin JTAG connector, Spy-Bi-Wire (TI SLAU278AH Figure 2-2): 1 SBWTDIO, "
                                "2 VCC_TOOL (via JP1), 4 VCC_TARGET (LDO output), 7 SBWTCK, 9 GND; 8 TEST/VPP open"}),

    # ---- User LEDs and button ---------------------------------------------------------------------
    Part("JP4", "Connector_Generic:Conn_02x02_Odd_Even", "LEDS", HDR + "2x02_P2.54mm_Vertical", (430, 340),
         {"1": "P1_0", "2": "LED_R_J", "3": "P1_6", "4": "LED_G_J"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-102-07-G-D", "Description": "Jumpers: 1-2 red LED on P1.0, 3-4 green LED on P1.6 (remove 3-4 for I2C on P1.6/UCB0SCL)"}),
    res("R8", "680", "LED_R_J", "LED_R_A", (455, 335), "Resistor 680 ohm 1% 0402 (red LED: (3.3 - 1.75 V) / 680 = 2.3 mA, "
        "Kingbright APTD1608LSURCK VF at 2 mA)"),
    led("D1", "RED", "LED_R_A", (470, 335), "APTD1608LSURCK", "LED red 0603, user LED on P1.0"),
    res("R9", "680", "LED_G_J", "LED_G_A", (455, 355), "Resistor 680 ohm 1% 0402 (green LED: (3.3 - 1.9 V) / 680 = 2.1 mA, "
        "Kingbright APTD1608LCGCK VF at 2 mA)"),
    led("D2", "GREEN", "LED_G_A", (470, 355), "APTD1608LCGCK", "LED green 0603, user LED on P1.6"),
    Part("SW2", "Switch:SW_Push", "P1.3", "Button_Switch_THT:SW_PUSH_6mm", (500, 345), {"1": "P1_3", "2": "GND"},
         fields={"Manufacturer": "TE Connectivity", "MPN": "1825910-6",
                 "Description": "Tactile switch 6 x 6 mm, user button on P1.3 (internal pull-up, P1REN; SLAS735J RPull)"}),
]
for i in range(4):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
                      (60 + 20 * i, 385), {"1": "GND"}, fields={"Description": "Mounting hole M3, grounded"}))

# Board placement: (x, y, rotation) in mm, origin top-left. The BoosterPack area is the top: J1 and
# J2 1.8 in apart, the socket between them with each PDIP pin level with its header pin, so every
# line runs straight across. A BoosterPack reaches 0.35 in above pin 1 and 0.15 in below pin 10
# (TI's guide); the buttons sit just below that. Then the MSP-FET connector and jumpers, then
# USB-C, the CP2102N and the regulator along the bottom edge.
PIN1 = (W / 2 - 3.81, HDR_TOP)      # socket pin 1; pin 20 is level with it, 7.62 mm to the right
PLACEMENT = {
    "J1": (J1_X, HDR_TOP, 0), "J2": (J2_X, HDR_TOP, 0), "U1": (PIN1[0], PIN1[1], 0),
    # DVCC decoupling between pin 1 (DVCC) and pin 20 (DVSS), just above the socket
    "C8": (W / 2, 7.4, 0), "C7": (W / 2, 5.0, 0),
    # crystal beside pins 19 (XIN) and 18 (XOUT); its capacitors' ground ends face each other
    "Y1": (35.6, HDR_TOP + 3.81, 90), "C10": (38.0, HDR_TOP + 3.05, 270), "C11": (39.4, HDR_TOP + 4.57, 90),
    # the unfitted P2.6/P2.7 links right beside the load capacitors, so XIN/XOUT carry no long stub
    "R11": (39.42, HDR_TOP + 2.54, 0), "R12": (40.82, HDR_TOP + 5.08, 0),
    # RST/NMI network beside pin 16: the pull-up's VMCU end faces down, away from XOUT; TEST pull-down
    "R7": (35.4, HDR_TOP + 10.67, 270), "C9": (36.8, HDR_TOP + 9.65, 90), "R14": (39.6, HDR_TOP + 8.13, 270),
    # buttons and user LEDs just below the BoosterPack area
    "SW2": (3.0, 39.5, 0), "JP4": (15.5, 39.5, 0),
    "R8": (21.6, 39.5, 0), "D1": (24.6, 39.5, 180), "R9": (21.6, 42.04, 0), "D2": (24.6, 42.04, 180),
    "SW1": (44.5, 39.5, 0),
    # MSP-FET connector, supply jumper beside its pins 2 and 4, UART and current jumpers
    "J4": (24.0, 53.0, 270), "JP1": (32.0, 50.5, 0), "JP3": (36.5, 48.5, 0), "JP2": (44.0, 48.5, 0),
    "R10": (41.5, 54.3, 0),
    # CP2102N, its capacitors, reset pull-up and VBUS divider, 1 mm clear of its 0.5 mm-pitch pads
    "U2": (47.5, 57.0, 0), "C4": (45.6, 60.8, 0), "C6": (47.8, 60.8, 0), "C3": (45.2, 62.9, 0), "C5": (48.9, 62.9, 0),
    "R4": (51.2, 59.8, 90), "R5": (52.8, 59.8, 90), "R6": (54.4, 59.8, 90),
    # USB-C on the bottom edge (design.USB_C_EDGE: HRO's 5.79 mm from the pegs to the edge); the ESD
    # array directly behind its pad row, its D+ pin straight above A6 (D+) and its D- pin up and
    # to the right of A7 (D-); CC resistors, bleed, fuse, Schottky, LDO
    "J3": (34.0, H - USB_C_EDGE, 0), "U3": (34.75, 67.6, 0), "R1": (31.0, 69.6, 0), "R2": (36.45, 70.6, 0),
    "R13": (27.6, 67.6, 0), "F1": (26.6, 72.2, 90), "D4": (23.6, 72.2, 90),
    "U4": (14.5, 72.5, 180), "C1": (20.5, 75.0, 270), "C2": (20.5, 70.0, 90),
    "R3": (10.0, 63.5, 0), "D3": (13.0, 63.5, 180),
    "H1": (4.0, 4.0, 0), "H2": (W - 4.0, 4.0, 0), "H3": (4.0, H - 4.0, 0), "H4": (W - 4.0, H - 4.0, 0),
}
# Laid first, in this order, before the autorouter (see the docstring). USB: A6 (D+) straight up
# into the ESD array's D+ pin and A7 (D-) up into its D- pin; VBUS from A9/B4 round the array's
# east side into its VBUS pin; D- on to the CP2102N through the array's middle and out of its top,
# then D+ north-west of it, as the CP2102N's pins 4 and 5 lie; then each duplicated contact
# (B6 = D+, B7 = D-) to its line through a via pair behind the pad row. Then the crystal (pin,
# crystal pad, load capacitor, then the short stub to the unfitted link), the decoupling and
# SBWTCK, which leaves pin 17 downward, away from XOUT (pin 18).
PRIORITY = [(("J3", "A6"), ("U3", "2")), (("J3", "A7"), ("U3", "3")),
            (("J3", "A9"), ("U3", "4")),
            (("U3", "3"), ("U2", "5")), (("U3", "2"), ("U2", "4")),
            (("J3", "B6"), ("U3", "2"), "join"), (("J3", "B7"), ("U3", "3"), "join"),
            (("U1", "19"), ("Y1", "1")), (("Y1", "1"), ("C10", "1")), (("C10", "1"), ("R11", "1")),
            (("U1", "18"), ("Y1", "2")), (("Y1", "2"), ("C11", "1")), (("C11", "1"), ("R12", "1")),
            (("U1", "1"), ("C8", "1")), (("U2", "7"), ("C6", "1")), (("U2", "6"), ("C4", "1")),
            (("U1", "17"), ("J4", "7"))]
# Top-layer keep-outs: in front of the receptacle's data pads, so neither duplicated contact is
# joined under the shell; and the ESD array's east side beside its D- pin, so the data lines
# leave through its middle and VBUS comes in from the east.
KEEPOUTS = [(32.85, 73.55, 35.15, 75.5), (36.2, 66.9, 37.4, 69.4)]
_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]


def _label(text, x, y):
    return {"text": text, "x": x, "y": y, "size": 0.8}


TEXTS = [
    {"text": "EoS MSP430G2 Board  rev A", "x": 26.0, "y": 61.6, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 26.0, "y": 63.6, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 26.0, "y": 65.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    # front: BoosterPack header ends and their supply pins
    _label("1", 2.6, HDR_TOP), _label("VCC", 8.6, HDR_TOP), _label("10", 2.6, HDR_TOP + 22.86),
    _label("20", 53.9, HDR_TOP), _label("GND", 47.4, HDR_TOP), _label("11", 53.9, HDR_TOP + 22.86),
    # buttons and user LEDs
    _label("P1.3", 6.25, 37.3), _label("RESET", 47.75, 37.3),
    _label("JP4 LEDS", 16.77, 37.3), _label("P1.0", 28.4, 39.5), _label("P1.6", 28.4, 42.04),
    # jumpers: names, pin 1 ends and positions
    _label("UART", 37.77, 46.4), _label("RX", 41.6, 48.5), _label("TX", 41.6, 51.04),
    _label("3V3", 47.3, 48.5), _label("MCU", 47.3, 51.04), _label("IMCU", 51.3, 49.77),
    _label("USB", 32.0, 48.4), _label("FET", 32.0, 57.6),
    _label("PWR 1-2 USB 2-3 FET", 36.5, 60.6),
    _label("MSP-FET SBW", 16.4, 60.3), _label("PWR", 16.3, 63.5),
]

BOARD = Board(
    name="eos-msp430g2-board",
    title="EoS MSP430G2 Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["BoosterPack J1/J2 positions (1.8 in apart, 0.1 in grid, J1.1 and J2.20 level) and signal assignment from "
             "TI's 20-pin BoosterPack standard, BoosterPack Standards and Design Guide (processors.wiki.ti.com, "
             "archived 2017-11-03); used as facts only"],
    width=W,
    height=H,
    corner_radius=2.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "VBUS": "power:VBUS"},
    flagged_nets=["GND", "VBUS", "+5V", "+3V3", "VMCU"],
    headings=[((35, 80), "USB-C, ESD, bleed, fuse, Schottky"), ((195, 80), "3.3 V LDO"), ((280, 80), "Supply choice (one shunt)"),
              ((320, 80), "Power LED"), ((355, 80), "MCU current jumper"), ((60, 180), "CP2102N USB-UART (regulator unused)"),
              ((185, 210), "UART jumpers, TXD series resistor"), ((255, 180), "MSP430G2553 in a DIP-20 socket"),
              ((355, 180), "DVCC decoupling, RST/NMI (SLAU278 Fig. 2-2)"), ((350, 275), "32.768 kHz crystal, XCAPx = 00"),
              ((440, 85), "BoosterPack headers (TI 20-pin standard)"), ((270, 300), "MSP-FET Spy-Bi-Wire connector"),
              ((420, 320), "User LEDs and button"), ((40, 365), "Mounting holes"), ((35, 300), "Power nets")],
    power_block=(40.64, 315.0),
    notes=[((150, 360), "EoS MSP430G2 Board, rev A. BoosterPack-compatible (20-pin). Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Values from TI SLAS735J, SLAU144K, SLAU278AH, SLAU647O, SLAA322D; Silicon Labs CP2102N Rev. 1.5;\n"
                       "Diodes DS37274 (AP7361C); Nexperia PMEG6010CEH v.4; Littelfuse 1206L and SP05xxBA; Abracon ABS07;\n"
                       "Kingbright. 16 MHz only with VCC >= 3.3 V (SLAS735J); 12 MHz from the LDO for full margin.\n"
                       "JP1 (one shunt): 1-2 USB/LDO powers +3V3, 2-3 MSP-FET VCC_TOOL powers +3V3.\n"
                       "JP2 off = measure the MCU alone. Firmware: XCAPx = 00 for Y1 with C10/C11.")],
    priority_routes=PRIORITY,
    router_keepouts=KEEPOUTS,
    # a via costs as much as 5 mm of track in the priority routes: they stay on the top layer
    # unless, like the duplicated USB contacts, they cannot
    maze_via_cost_mm=5.0,
    # 3.3 V nets at 0.3 mm: they enter the CP2102N's 0.3 mm pads at 0.5 mm pitch, which a 0.3 mm
    # track can (TM4C123 board, same part); a 0.4 mm track could not
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS": "Power", "VBUS_F": "Power", "+5V": "Power", "+3V3": "Supply", "LDO_3V3": "Supply",
                  "VMCU": "Supply", "FET_VCC_TOOL": "Supply", "USB_D+": "USB", "USB_D-": "USB"},
)
