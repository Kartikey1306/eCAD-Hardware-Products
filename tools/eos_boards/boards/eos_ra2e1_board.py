"""EoS RA2E1 Board: a Renesas RA2E1 development board that fits Uno R3 shields and Pmod modules, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-ra2e1-board/LICENSE.txt.

A 68.58 x 53.34 mm two-layer board for the Renesas R7FA2E1A92DFM (RA2E1, Arm Cortex-M23,
48 MHz, 128 KB flash, LQFP-64 10 x 10 mm) at 3.3 V, with Arduino Uno R3 shield headers, two
Digilent Pmod 12-pin host ports (Type 2A SPI and Type 6A I2C), a USB-C port with a CP2102N
USB-UART bridge on SCI9 (the SCI boot-mode port), a 3.3 V LDO with a controlled soft start, an
Arm 10-pin SWD header in place of a vendor debug probe, an MD jumper for SCI boot mode, reset and
user buttons, three user LEDs, a power LED and a 32.768 kHz sub-clock crystal. It does the job of
Renesas' EK-RA2E1; none of that kit's design files (schematic, layout, CAD, Gerbers, BOM) was
opened. The circuit comes from the chip makers' data sheets and application notes; the header
positions come from published Uno R3 and Pmod mechanical facts.

Sources, by short name:
  DS   = Renesas RA2E1 Group Datasheet R01DS0386EJ0170 Rev.1.70 (31 Oct 2025)
  UM   = Renesas RA2E1 Group User's Manual: Hardware R01UH0852EJ0170 Rev.1.70 (31 Oct 2025)
  QDG  = Renesas RA2 Quick Design Guide R01AN6060EU0104 Rev.1.04 (9 Jun 2026)
  E2   = Renesas E2 Emulator, E2 Emulator Lite Additional Document for User's Manual (Notes on
         Connection of RA Devices) R20UT4686EJ0360 Rev.3.60 (20 Apr 2026)
  CLK  = Renesas RX and RA families Design Guide for Main Clock Circuits and Sub Clock Circuits
         R01AN7202EJ0102 Rev.1.02 (23 Dec 2025)
  PMOD = Digilent Pmod Interface Specification, revised 29 September 2020 (file 1_3_0; the Wayback
         Machine copy of digilent.com's PDF, since digilent.com refuses scripted downloads)
All other part data sheets are named in each part's Description.

* Supplies (DS section 2.1, caution under Table 2.1; UM Table 38.1): VCC (pins 11, 39) to 3.3 V,
  0.1 uF at each VCC/VSS pair (11/8, 39/40); VCL (pin 5), the internal regulator's output, to VSS
  through 4.7 uF; AVCC0 must equal VCC and rise with or after it (DS Table 2.2 notes 1 and 2), so
  it comes from 3.3 V through a ferrite bead (Bourns MH1608-221Y: 220 ohm at 100 MHz, 100 mohm max,
  2 A), with 0.1 uF at the pin (DS 2.1) and 10 uF + 0.01 uF at the supply (UM Figure 29.33, "*1",
  reference values). There is no outside reference: VREFH0 (P010) is tied to AVCC0, the top of its
  1.6 V-AVCC0 range (DS Table 2.2), and VREFL0 (P011) to AVSS0, the connections DS Table 1.14 and UM
  Table 17.4 give these pins, so the ADC's high reference is AVCC0 whichever reference firmware
  selects; 0.1 uF from VREFH0 to VREFL0 (DS 2.1). AVSS0 to ground (UM 29.8.11).
* Supply ramp: DS Table 2.14 asks for a VCC rise of 0.02-2 ms/V at power-on (2 ms/V the limit in
  SCI boot mode, with voltage monitor 0 off). A plain LDO's start-up is only typical (Diodes'
  AP7361C: 150 us typical, no limits), so the 3.3 V LDO is TI's TPS7A91 (SBVS282A), whose ramp is
  set by its NR/SS capacitor and a charging current with limits: tSS = VREF x CNR/SS / INR/SS
  (Equation 6), VREF = 0.8 V, INR/SS = 4.0-9.0 uA with SS_CTRL to GND (section 5.5). CNR/SS = 10 nF
  +-10 % gives 0.80-2.2 ms to 3.283 V, 0.24-0.67 ms/V, inside DS Table 2.14's window. Output
  3.283 V from R1 = 3.57 kohm, R2 = 1.15 kohm (Table 7-1); 10 uF at IN and OUT (pin table: "10 uF or
  greater"); EN tied to IN (pin table: "EN must connect to IN if the enable function is not
  used"); PG unused ("can be left floating"). Thermal (SBVS282A 5.4, 7.1.4, 7.1.5): the 62.5 C/W RthJA
  is TI's JEDEC board, with the plated vias in the thermal pad that 7.1.4 asks for; this pad (1.2 x 2.0
  mm) has none, so this board's RthJA is higher and not known. With psiJB = 30.7 C/W, TJ = TB + 30.7 x
  PD, TB the board 1 mm from the package. Budget 300 mA from USB in all: VIN at most 5.25 V less D1's
  drop, about 4.9 V, so PD <= (4.9 - 3.283) V x 0.3 A = 0.49 W and TJ = TB + 15 C; keep TB under
  110 C (TJ 125 C max, 5.3). D1 at 0.3 A drops <= 0.48 V (0.14 W) and at 330 K/W (standard
  footprint) runs 48 C over ambient. Neither board temperature has been measured.
  The ramp sum assumes +5V itself rises faster than about 0.5 V/ms: EN is tied to IN, so a slower
  5 V (a bench supply on the shield's 5V pin) is followed by VOUT and can break DS Table 2.14's
  2 ms/V. With OFS1.LVDAS = 0 (voltage monitor 0 reset on at start-up) Table 2.14 sets no upper
  limit outside SCI boot mode.
* Clocks (QDG 5.6, DS Table 2.21): the HOCO runs at 48 MHz within 47.52-48.48 MHz (+-1 %) over
  -40 to 105 C and 1.6-5.5 V, which serves the SCIs, SPI and IIC; the RA2E1 has no USB, so nothing on
  the board needs the main oscillator's accuracy, and it is left out: P212/EXTAL and P213/XTAL serve
  as SCI1 (UM Table 17.4: MOSCCR.MOSTP = 1 makes them general ports; the main oscillator is stopped
  after reset, QDG 5.1). The sub-clock is fitted: the RTC counts the sub-clock or the LOCO (UM 22.1),
  and the LOCO is only 27.85-37.68 kHz (DS Table 2.21), useless for timekeeping. Crystal Abracon
  ABS07-32.768KHZ-9-T (CL 9 pF, ESR 70 kohm max at -40 to 85 C, 0.5 uW max); load capacitors from
  CLK Table 4.2.7 (Group 7, which includes the RA2E1): Standard CL drive (SOMCR.SODRV = 00, normal
  mode), CL 9 pF, Rd 0, CL1 = 15 pF on XCIN, CL2 = 18 pF on XCOUT, recommended ESR at most
  120 kohm. No feedback resistor (CLK section 2: built in).
* Reset, mode, NMI (QDG 3 and 6, E2 2.5, UM Table 17.4, Appendix 1): RES pulled up through 10 kohm
  (E2 Figure 2.7: 4.7-10 kohm) and no capacitor ("do not place a capacitor on the reset pin", QDG
  6.2); a reset button to ground; RES also goes to the SWD header and the Uno RESET pin. MD (P201)
  has an internal pull-up that is on during reset (UM Appendix 1, Table A1.1; QDG 3: "may replace
  the external pull-up"), and E2 Figure 2.9 puts 1.5 kohm and a switch from MD to ground: jumper JP1
  fitted at reset is SCI boot mode (UM Table 3.1). With the jumper on, MD sits at most
  3.3 V x 1.5 / (10 + 1.5) = 0.43 V for the 10-100 kohm pull-up (DS Table 2.10), under
  VIL = 0.2 VCC = 0.66 V (DS Table 2.5). P200/NMI is pulled up through 10 kohm (UM Table 17.4: "Connect
  to VCC through a resistor"; the value as RES).
* SWD (QDG 2.1 Figure 1, E2 2.4.1): Arm 10-pin 1.27 mm header, SWDIO P108, SWCLK P300, nRESET, VTref
  3.3 V. Both SWD pins have internal pull-ups on by default (UM Appendix 1; QDG 2: "no external
  resistors are required"). The chip has no SWO: DS Table 1.14 lists SWDIO and SWCLK as its only
  on-chip debug pins, so pins 6 and 8 are open.
  It replaces the vendor kit's J-Link OB probe, whose firmware is SEGGER's.
* USB-UART: Silicon Labs CP2102N-A02-GQFN24 (data sheet Rev. 1.5) on SCI9, P109 TXD9 / P110 RXD9:
  UM Table 35.18 makes these the only pins of SCI boot mode (serial programming), so the same port
  is the console and the programming port. It runs from the board's 3.3 V with its own regulator
  unused (Figure 2.3: VREGIN tied to VDD; VIO tied to VDD), so it is never unpowered while the RA2E1
  is. 4.7 uF + 0.1 uF at VREGIN/VDD and at VIO (section 2.1); 1 kohm RSTb pull-up (section 2.1). VBUS
  sense through 22.1 kohm / 47.5 kohm (Figure 2.5): 5 V reads 3.41 V, over VIH = VIO - 0.6 V = 2.7 V
  (Table 3.7), so the bridge connects, and turns on its D+ pull-up, only with a host present. Unused
  modem pins and GPIO are open (section 4.3.1: weak pull-ups by default).
* VBUS bleed, R7 = 1.5 kohm from VBUS to ground. Fed from the shield 5V pin with no host, the
  Schottky D1 is reverse-biased by about 5 V and leaks into VBUS. The CP2102N reads its VBUS pin as
  low only at or below VIL = 0.6 V (Table 3.7); the divider puts 47.5/69.6 of VBUS on it, so VBUS may
  reach 0.88 V. With the bleed the node is 1.47 kohm: 599 uA of leakage is needed to fake a host.
  D1 (Nexperia PMEG6010CEH, Table 7 and Fig. 2) leaks 0.8 uA typical at 5 V and 25 C, but about
  100 uA typical at 5 V and 85 C; no maximum is given at 5 V, and at 25 C the 60 V maximum is 4.5
  times the typical (50/11 uA), which at 85 C would be about 450 uA, still under 599 uA. A host pays
  3.4 mA (R7 dissipates 18 mW at 5.25 V).
* USB-C as a 5 V sink: 5.1 kohm Rd on CC1 and CC2 (TI SLVSFJ9 section 10.3.14.2). ESD protection
  Littelfuse SP0503BAHTG on D+, D- and VBUS, diodes to ground only, as the CP2102N data sheet shows
  (Figure 2.5); a USBLC6-style part, whose data-line diodes run to its VBUS pin, could let the live
  D+ pull-up hold VBUS near 2 V after an unplug. Fuse Littelfuse 1206L050YR (0.50 A hold, 1.00 A
  trip, 6 V, R1max 0.70 ohm), then the PMEG6010CEH Schottky (60 V, 1 A, VF <= 530 mV at 500 mA) to
  the 5 V rail, so 5 V fed into the shield 5V pin cannot reach the host.
* I2C (IIC0 on P204 SCL0_B / P407 SDA0_B) is shared by the Uno SDA/SCL pins and the Type 6A Pmod.
  PMOD section 2: "it is suggested to include jumpered pull-ups on system boards": 2.2 kohm to
  3.3 V through solder jumper JP2 (bridged as delivered; cut it when a shield or module brings its
  own). 2.2 kohm is above TI SLVA689A's RP(min) = (3.3 - 0.4) V / 3 mA = 0.97 kohm, and fast mode's
  300 ns rise (DS Table 2.35) holds up to 161 pF.
* Pmod ports (PMOD sections 3-5): 3.3 V only (the specification's reduced subset), both VCC pins
  and both GND pins joined; the host's 2x6 right-angle female socket at the board edge, the 7-12 row
  10.16 mm and the 1-6 row 12.70 mm from the edge, pin 1 as in Figure 5; two ports side by side
  0.9 in (22.86 mm) apart. J7, Type 2A (expanded SPI): 1 CS = P104 (SSLA1), 2 MOSI = P101 (MOSIA),
  3 MISO = P100 (MISOA), 4 SCK = P102 (RSPCKA), 7 INT = P105 (IRQ0), 8 RESET = P107, 9 CS2 = P106
  (SSLA3), 10 CS3 = P500. J8, Type 6A (expanded I2C): 1 INT = P205 (IRQ1), 2 RESET = P112, 3 SCL,
  4 SDA, 7-10 GPIO = P111, P113, P303, P304. Each interrupt line has an IRQ channel of its own
  (DS Table 1.15): IRQ0 J7 INT, IRQ1 J8 INT, IRQ4 user button, IRQ5 D3, IRQ6 D2.
  The KiCad socket footprint numbers its pads odd/even;
  the Pmod pin each pad carries is listed in the part's Description.
* LEDs at about 2 mA, the current Kingbright specifies them at: power LED APTD1608LCGCK (green,
  VF 1.9 V typ at 2 mA, DSAO7432) through 680 ohm from 3.3 V; user LEDs on P400 (red APTD1608LSURCK,
  VF 1.75 V, DSAO7433, 750 ohm), P401 (green, 680 ohm) and P403 (yellow APTD1608LSYCK, VF 1.85 V,
  DSAO7434, 680 ohm). P400 and P401 are GPT9 outputs (GTIOC9A/B), so two LEDs can be dimmed. All
  ports are high-impedance after reset (UM Appendix 1), so the LEDs start off.
* Buttons: C&K KMR2. User button on P402 (IRQ4) with a 10 kohm pull-up (internal pull-ups are off at
  reset, UM 17.2.5; the value as RES).
* The capacitive-touch button is left out (see the README): CTSU pins are used as GPIO here and
  TSCAP (P112) carries no 10 nF capacitor.

Mechanical facts (origin top-left, y down; the sources use mils from the lower-left corner, y up):
* Uno R3 outline 2700 x 2100 mil and the shield header positions (digital 10-pin from 1640 mil
  (D8) and 8-pin from 2500 mil (D0) on the 2000-mil row; power 8-pin from 1100 mil and analog 6-pin
  from 2000 mil on the 100-mil row): Matthew Beckler's "Arduino Uno R3" dimension drawing v1.05, as
  EoS KL25 Board and EoS LPC55S69 Board use them. Mounting holes, 3.20 mm, at (600, 2000),
  (550, 100), (2600, 1400) and (2600, 300) mil: Arduino UNO R3 product reference manual (A000066),
  section 5.4. The 10-pin socket's SCL end lies within the top-left hole's screw-head courtyard, so
  H1 is placed from the back, as on EoS KL25 Board.
* Pmod host ports on the left edge, where the Uno has its USB and power jacks and shields keep
  clear; the USB-C on the right edge below the Uno ICSP header's position, so a shield's ICSP socket
  does not land on it.

Uno pin map (DS Table 1.15 functions; D2, D3 on IRQ pins; PWM on D3, D5, D6 (AGT compare outputs),
D9, D10, D11 (GPT); the RA2E1 has one SPI, shared by D10-D13 and Pmod J7):
  D0 P212 RXD1   D1 P213 TXD1   D2 P409 IRQ6   D3 P410 IRQ5, AGTOB1   D4 P411
  D5 P914 AGTOA1 D6 P208 AGTOB0 D7 P207 D8 P206 D9 P302 GTIOC7A
  D10 P103 SSLA0, GTIOC5A  D11 P101 MOSIA, GTIOC8A  D12 P100 MISOA  D13 P102 RSPCKA
  SDA P407 SDA0  SCL P204 SCL0  A0 P012 AN007  A1-A5 P004-P000 AN004-AN000
IOREF and 3V3 are 3.3 V: most RA2E1 pins take at most VCC + 0.3 V (DS Table 2.1), so shields must
use 3.3 V logic. IOREF and 3V3 are outputs: fed with 3.3 V while 5 V is absent, they would put the
TPS7A91's OUT above IN + 0.3 V, its absolute maximum (SBVS282A 5.1). AREF and VIN are not connected
(see the README). Pins not used (P301, P408, P501, P502, P913, P915, P013-P015) are left open;
firmware sets them as outputs (UM Table 17.4).

Two layers, ground poured on both sides. Layout (see PRIORITY below): the 32.768 kHz lines run pin ->
crystal pad -> load capacitor on the top layer with no via, 4.9 mm (XCOUT) and 5.8 mm (XCIN) to the
crystal, 0.35 mm apart (CLK 6.1.1 (3), (4)), with VSS pin 8 running to C1 between D1 and XCOUT; no
other net's copper is laid on either layer in the crystal area by the pre-routes, D0/D1 leave pins
10/9 through vias just inside the chip outline and run north-east on the bottom layer, TXD9 enters
the chip outline at its corner between pins 1 and 64 and RXD9 crosses under the chip on the bottom
layer, both south of the LEDs.
"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
HOLE = "MountingHole:MountingHole_3.2mm_M3_ISO14580"
KMR2 = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
LED0603 = "LED_SMD:LED_0603_1608Metric"

DS = "Renesas R01DS0386 Rev.1.70"
UM = "Renesas R01UH0852 Rev.1.70"
QDG = "Renesas R01AN6060 Rev.1.04"
E2 = "Renesas R20UT4686 Rev.3.60"
CLK = "Renesas R01AN7202 Rev.1.02"
CP = "Silicon Labs CP2102N DS Rev. 1.5"
TPS = "TI SBVS282A"
PMOD = "Digilent Pmod Interface Specification (2020-09-29)"


def res(ref, value, a, b, sch, desc, rot=0, mfr=None, mpn=None):
    fields = {"Description": desc}
    if mpn:
        fields.update({"Manufacturer": mfr, "MPN": mpn})
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def cap(ref, value, a, b, sch, desc, fp=C0402, rot=0, mfr=None, mpn=None):
    fields = {"Description": desc}
    if mpn:
        fields.update({"Manufacturer": mfr, "MPN": mpn})
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def led(ref, value, anode, sch, mpn, desc):
    return Part(ref, "Device:LED_Small", value, LED0603, sch, {"A": anode, "K": "GND"},
                fields={"Manufacturer": "Kingbright", "MPN": mpn, "Description": desc})


def socket(ref, n, value, pins, sch, desc):
    """A female header for shields: pin 1 is the first signal named in ``pins``."""
    return Part(ref, f"Connector:Conn_01x{n:02d}_Socket", value,
                f"Connector_PinSocket_2.54mm:PinSocket_1x{n:02d}_P2.54mm_Vertical", sch,
                {str(i + 1): net for i, net in enumerate(pins)},
                fields={"Manufacturer": "Samtec", "MPN": f"SSW-1{n:02d}-01-T-S", "Description": desc})


# Pmod host port. PMOD Figure 5 (a host port on a right-hand edge, top view): the 1-6 row inboard,
# the 7-12 row 10.16 mm from the edge, pin 1 at the top. These ports are on the left edge, so the
# figure turns 180 degrees: pin 1 at the bottom. KiCad's right-angle 2x06 socket (opening to -x at
# rotation 0) puts its odd pads 2.54 mm further from the opening than its even pads, top to bottom.
# So odd pads 1, 3, ..., 11 carry Pmod pins 6, 5, ..., 1 and even pads 2, ..., 12 carry 12, ..., 7.
PMOD_PAD = {6: "1", 12: "2", 5: "3", 11: "4", 4: "5", 10: "6", 3: "7", 9: "8", 2: "9", 8: "10", 1: "11", 7: "12"}


def pmod(ref, value, signals, sch, what):
    """A Pmod 12-pin host port; ``signals`` maps Pmod pins 1-4 and 7-10 to nets."""
    pins = {5: "GND", 11: "GND", 6: "+3V3", 12: "+3V3", **signals}
    mapping = ", ".join(f"pad {PMOD_PAD[p]} = Pmod {p}" for p in sorted(PMOD_PAD, key=lambda q: int(PMOD_PAD[q])))
    return Part(ref, "Connector_Generic:Conn_02x06_Odd_Even", value,
                "Connector_PinSocket_2.54mm:PinSocket_2x06_P2.54mm_Horizontal", sch,
                {PMOD_PAD[p]: net for p, net in pins.items()},
                fields={"Manufacturer": "Sullins", "MPN": "PPPC062LJBN-RC",
                        "Description": f"Pmod host port, 2x6 right-angle female 2.54 mm, {what}, 3.3 V "
                                       f"({PMOD} sections 3-5, Figure 5); {mapping}"})


W, H = 68.58, 53.34          # 2700 x 2100 mil
MIL = 0.0254


def uno(x_mil, y_mil):
    """A position from the Uno R3 drawings (mils from the lower-left corner, y up) in board mm."""
    return round(x_mil * MIL, 4), round(H - y_mil * MIL, 4)


D0_PIN = uno(2500, 2000)      # D0 .. D7 run right to left, 100 mil apart
D8_PIN = uno(1640, 2000)      # D8 .. D13, GND, AREF, SDA, SCL run right to left
POWER_PIN = uno(1100, 100)    # NC, IOREF, RESET, 3V3, 5V, GND, GND, VIN run left to right
A0_PIN = uno(2000, 100)       # A0 .. A5 run left to right
HOLES = [uno(600, 2000), uno(550, 100), uno(2600, 1400), uno(2600, 300)]

# R7FA2E1A92DFM pins by name (DS Table 1.15, LQFP-64; names as DS Figure 1.3).
MCU_NETS = {
    "P212/EXTAL": "D0", "P213/XTAL": "D1", "P409": "D2", "P410": "D3", "P411": "D4", "P914": "D5",
    "P208": "D6", "P207": "D7", "P206": "D8", "P302": "D9", "P103": "D10", "P101": "SPI_MOSI",
    "P100": "SPI_MISO", "P102": "SPI_SCK", "P407": "SDA", "P204": "SCL",
    "P012": "A0", "P004": "A1", "P003": "A2", "P002": "A3", "P001": "A4", "P000": "A5",
    "P104": "PMODA_CS", "P105": "PMODA_INT", "P107": "PMODA_RST", "P106": "PMODA_CS2", "P500": "PMODA_CS3",
    "P205": "PMODB_INT", "P112": "PMODB_RST", "P111": "PMODB_IO7", "P113": "PMODB_IO8", "P303": "PMODB_IO9",
    "P304": "PMODB_IO10",
    "P109": "TXD9", "P110": "RXD9", "P108/SWDIO": "SWDIO", "P300/SWCLK": "SWCLK",
    "~{RES}": "RES", "P201/MD": "MD", "P200/NMI": "NMI",
    "P400": "LED1", "P401": "LED2", "P403": "LED3", "P402": "USER_BTN",
    "P215/XCIN": "XCIN", "P214/XCOUT": "XCOUT",
    "VCC": "+3V3", "VSS": "GND", "VCL": "VCL", "AVCC0": "AVCC0", "AVSS0": "GND",
    "P010/VREFH0": "AVCC0", "P011/VREFL0": "GND",
    **{p: NC for p in ("P301", "P408", "P501", "P502", "P913", "P915", "P013", "P014", "P015")},
}

PARTS = [
    # ---- USB-C (J1), ESD, CC, fuse, Schottky, VBUS bleed -------------------------------------------------------
    Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (40, 105), {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_DP", "D-": "USB_DM",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12",
                 "Description": "USB-C 2.0 receptacle, 16 pins: CP2102N USB-UART and board power"}),
    res("R1", "5.1k", "CC1", "GND", (75, 88), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC1, TI SLVSFJ9 section 10.3.14.2)"),
    res("R2", "5.1k", "CC2", "GND", (90, 88), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC2, TI SLVSFJ9 section 10.3.14.2)"),
    # three diodes to GND (pin 1 the common anode), none between the lines; D- on pad 2 and D+ on pad 3,
    # so that the pair reaches the CP2102N (D- above D+) uncrossed
    Part("U2", "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", (115, 105),
         {"1": "GND", "2": "USB_DM", "3": "USB_DP", "4": "VBUS"},
         fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                 "Description": f"USB ESD protection, three diodes to GND on D+, D- and VBUS, no path between them ({CP} Figure 2.5)"}),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (145, 88), {"1": "VBUS", "2": "VBUS_F"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                 "Description": "PTC resettable fuse 0.50 A hold, 1.00 A trip, 6 V, R1max 0.70 ohm, 1206 (Littelfuse 1206L data sheet)"}),
    Part("D1", "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F", (170, 105), {"A": "VBUS_F", "K": "+5V"},
         fields={"Manufacturer": "Nexperia", "MPN": "PMEG6010CEH",
                 "Description": "Schottky 60 V 1 A, VF <= 530 mV at 500 mA, IR 0.8 uA typ at 5 V, <= 50 uA at 25 C "
                                "(Nexperia PMEG6010CEH): the shield 5V pin cannot feed the USB host"}),
    res("R7", "1.5k", "VBUS", "GND", (75, 130), f"Resistor 1.5 kohm 1% 0402 (VBUS bleed: with the divider 1.47 kohm, so 599 uA of D1 "
        f"leakage keeps the CP2102N VBUS pin under VIL 0.6 V, {CP} Table 3.7; D1 leaks about 100 uA typ at 5 V, 85 C, "
        f"PMEG6010CEH Fig. 2)", rot=90),

    # ---- 3.3 V LDO with controlled soft start, power LED -----------------------------------------------------------
    Part("U4", "Regulator_Linear:TPS7A91", "TPS7A91", "Package_DFN_QFN:Texas_S-PDSO-N10_EP1.2x2mm", (235, 108),
         {"IN": "+5V", "EN": "+5V", "SS_CTRL": "GND", "NR/SS": "LDO_NR", "FB": "LDO_FB", "OUT": "+3V3",
          "PG": NC, "GND": "GND"},
         fields={"Manufacturer": "Texas Instruments", "MPN": "TPS7A9101DSKR",
                 "Description": f"LDO 1 A, adjustable, NR/SS soft start: 3.283 V, ramp 0.80-2.2 ms ({TPS}; {DS} Table 2.14)"}),
    cap("C13", "10u", "+5V", "GND", (205, 88), f"Capacitor 10 uF 16 V X5R 0805 (TPS7A91 IN, 10 uF or greater after 50 % derating, "
        f"{TPS} pin table and 7.1.3; 16 V at 5 V keeps more of it than a 10 V part)", C0805,
        mfr="Murata", mpn="GRM21BR61C106KE15L"),
    cap("C14", "10u", "+3V3", "GND", (270, 88), f"Capacitor 10 uF 10 V X5R 0603 (TPS7A91 OUT, 10 uF or greater, {TPS} pin table)", C0603,
        mfr="Murata", mpn="GRM188R61A106KE69D"),
    cap("C15", "10n", "LDO_NR", "GND", (215, 132), f"Capacitor 10 nF 50 V X7R 0402 +-10% (TPS7A91 NR/SS: tSS = 0.8 V x 9-11 nF / "
        f"9.0-4.0 uA = 0.80-2.2 ms, {TPS} Eq. 6 and 5.5; {DS} Table 2.14 asks 0.02-2 ms/V)"),
    res("R8", "3.57k", "+3V3", "LDO_FB", (265, 122), f"Resistor 3.57 kohm 0.1% 0402 (TPS7A91 R1, 3.283 V, {TPS} Table 7-1)", rot=90,
        mfr="Panasonic", mpn="ERA-2AEB3571X"),
    res("R9", "1.15k", "LDO_FB", "GND", (265, 142), f"Resistor 1.15 kohm 0.1% 0402 (TPS7A91 R2, 3.283 V, {TPS} Table 7-1)", rot=90,
        mfr="Panasonic", mpn="ERA-2AEB1151X"),
    res("R10", "680", "LED_PWR_A", "+3V3", (295, 105), "Resistor 680 ohm 1% 0402 (power LED: (3.3 V - 1.9 V) / 680 ohm = 2.1 mA, Kingbright DSAO7432)"),
    led("D2", "PWR", "LED_PWR_A", (310, 105), "APTD1608LCGCK", "LED green 0603, VF 1.9 V typ at 2 mA (Kingbright DSAO7432): power (3.3 V)"),

    # ---- USB-UART: CP2102N on the board's 3.3 V, VBUS sensed -------------------------------------------------------
    Part("U3", "Interface_USB:CP2102N-Axx-xQFN24", "CP2102N-A02-GQFN24", "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
         (150, 255), {"GND": "GND", "D+": "USB_DP", "D-": "USB_DM", "VIO": "+3V3", "VDD": "+3V3", "VREGIN": "+3V3",
                      "VBUS": "CP_VBUS", "~{RST}": "CP_RST", "RXD": "TXD9", "TXD": "RXD9",
                      **{p: NC for p in ("NC", "~{RI}/CLK", "~{WAKEUP}/GPIO.3", "RS485/GPIO.2", "~{RXT}/GPIO.1",
                                         "~{TXT}/GPIO.0", "~{SUSPEND}", "SUSPEND", "~{CTS}", "~{RTS}", "~{DSR}",
                                         "~{DTR}", "~{DCD}")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN24R",
                 "Description": f"USB-UART bridge on SCI9 (the SCI boot port, {UM} Table 35.18), from the board's 3.3 V, "
                                f"own regulator unused ({CP} Figure 2.3)"}),
    cap("C16", "4.7u", "+3V3", "GND", (195, 230), f"Capacitor 4.7 uF 10 V X5R 0603 (CP2102N VREGIN/VDD, {CP} Figure 2.3)", C0603),
    cap("C17", "100n", "+3V3", "GND", (210, 230), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VREGIN/VDD, {CP} Figure 2.3)"),
    cap("C18", "4.7u", "+3V3", "GND", (225, 230), f"Capacitor 4.7 uF 10 V X5R 0603 (CP2102N VIO, {CP} section 2.1)", C0603),
    cap("C19", "100n", "+3V3", "GND", (240, 230), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VIO, {CP} section 2.1)"),
    res("R11", "1k", "CP_RST", "+3V3", (195, 280), f"Resistor 1 kohm 1% 0402 (CP2102N RSTb pull-up, {CP} section 2.1)"),
    res("R5", "22.1k", "VBUS", "CP_VBUS", (100, 240), f"Resistor 22.1 kohm 1% 0402 (CP2102N VBUS divider: 5 V reads 3.41 V, {CP} Figure 2.5)", rot=90),
    res("R6", "47.5k", "CP_VBUS", "GND", (100, 262), f"Resistor 47.5 kohm 1% 0402 (CP2102N VBUS divider, {CP} Figure 2.5)", rot=90),

    # ---- RA2E1 and its supplies -------------------------------------------------------------------------------------
    Part("U1", "EoS_MCU:R7FA2E1A92DFM", "R7FA2E1A92DFM", "Package_QFP:LQFP-64_10x10mm_P0.5mm", (420, 235), MCU_NETS,
         fields={"Manufacturer": "Renesas", "MPN": "R7FA2E1A92DFM#AA0",
                 "Description": f"RA2E1 Cortex-M23 48 MHz, 128 KB flash, 16 KB SRAM, LQFP-64 10 x 10 mm "
                                f"(PLQP0064KB-C / PLQP0064KL-A, {DS} Table 1.12, Appendix 2)"}),
    cap("C1", "100n", "+3V3", "GND", (330, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC pin 11 / VSS pin 8, about 0.1 uF, {DS} 2.1)"),
    cap("C2", "100n", "+3V3", "GND", (345, 140), f"Capacitor 100 nF 16 V X7R 0402 (VCC pin 39 / VSS pin 40, about 0.1 uF, {DS} 2.1)"),
    cap("C3", "4.7u", "VCL", "GND", (360, 140), f"Capacitor 4.7 uF 10 V X7R 0603 (VCL pin 5, 4.7 uF multilayer ceramic, {UM} Table 38.1)", C0603,
        mfr="Murata", mpn="GRM188Z71A475KE15D"),
    Part("FB1", "Device:FerriteBead_Small", "220R", "Inductor_SMD:L_0603_1608Metric", (380, 140), {"1": "+3V3", "2": "AVCC0"},
         fields={"Manufacturer": "Bourns", "MPN": "MH1608-221Y",
                 "Description": "Ferrite bead 220 ohm at 100 MHz, 100 mohm, 2 A, 0603: AVCC0 filter (Bourns MH1608)"}),
    cap("C6", "100n", "AVCC0", "GND", (395, 140), f"Capacitor 100 nF 16 V X7R 0402 (AVCC0 pin 56 / AVSS0 pin 57, about 0.1 uF, {DS} 2.1)"),
    cap("C7", "100n", "AVCC0", "GND", (410, 140), f"Capacitor 100 nF 16 V X7R 0402 (VREFH0 pin 59 / VREFL0 pin 58, about 0.1 uF, {DS} 2.1)"),
    cap("C8", "10u", "AVCC0", "GND", (425, 140), f"Capacitor 10 uF 10 V X5R 0603 (AVCC0 supply, reference value, {UM} Figure 29.33)", C0603),
    cap("C9", "10n", "AVCC0", "GND", (440, 140), f"Capacitor 10 nF 50 V X7R 0402 (AVCC0 supply, reference value 0.01 uF, {UM} Figure 29.33)"),
    # 32.768 kHz sub-clock crystal (CLK Table 4.2.7, Group 7: CL 9 pF, CL1 15 pF, CL2 18 pF, Rd 0)
    Part("Y1", "Device:Crystal", "32.768kHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", (500, 205), {"1": "XCOUT", "2": "XCIN"},
         fields={"Manufacturer": "Abracon", "MPN": "ABS07-32.768KHZ-9-T",
                 "Description": f"Crystal 32.768 kHz, CL 9 pF, ESR 70 kohm max, 3.2 x 1.5 mm (Abracon ABS07); ESR under "
                                f"the 120 kohm {CLK} Table 4.2.7 recommends for Standard CL drive"}),
    cap("C4", "18p", "XCOUT", "GND", (515, 225), f"Capacitor 18 pF 50 V C0G 0402 (XCOUT load CL2 for a 9 pF crystal, {CLK} Table 4.2.7)",
        mfr="Murata", mpn="GRM1555C1H180JA01D"),
    cap("C5", "15p", "XCIN", "GND", (485, 225), f"Capacitor 15 pF 50 V C0G 0402 (XCIN load CL1 for a 9 pF crystal, {CLK} Table 4.2.7)",
        mfr="Murata", mpn="GRM1555C1H150JA01D"),

    # ---- Reset, mode, NMI, SWD, buttons ----------------------------------------------------------------------------
    res("R12", "10k", "RES", "+3V3", (455, 305), f"Resistor 10 kohm 1% 0402 (RES pull-up 4.7-10 kohm, {E2} Figure 2.7; no capacitor, {QDG} 6.2)", rot=90),
    res("R13", "10k", "NMI", "+3V3", (440, 305), f"Resistor 10 kohm 1% 0402 (P200/NMI pull-up, {UM} Table 17.4; value as RES)", rot=90),
    Part("SW1", "Switch:SW_Push", "RESET", KMR2, (470, 335), {"1": "RES", "2": "GND"},
         fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, reset (RES)"}),
    Part("JP1", "Jumper:Jumper_2_Open", "MD", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", (500, 350),
         {"A": "MD", "B": "MD_JP"},
         fields={"Description": f"Pin header 1x2 2.54 mm with a 2.54 mm shunt: fitted at reset = SCI boot mode ({UM} Table 3.1; {E2} Figure 2.9)"}),
    res("R14", "1.5k", "MD_JP", "GND", (520, 365), f"Resistor 1.5 kohm 1% 0402 (MD to GND through JP1, {E2} Figure 2.9: MD <= 0.43 V < VIL 0.66 V)", rot=90),
    Part("J2", "Connector:Conn_ARM_JTAG_SWD_10", "SWD", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
         (505, 305), {"VTref": "+3V3", "SWDIO/TMS": "SWDIO", "GND": "GND", "SWCLK/TCK": "SWCLK", "SWO/TDO": NC,
                      "KEY": NC, "NC/TDI": NC, "GNDDetect": "GND", "~{RESET}": "RES"},
         fields={"Manufacturer": "Samtec", "MPN": "FTSH-105-01-L-DV-K",
                 "Description": f"Arm Cortex Debug 10-pin, 1.27 mm: SWDIO P108, SWCLK P300, RES ({QDG} Figure 1); replaces the J-Link OB"}),
    Part("SW2", "Switch:SW_Push", "USER", KMR2, (330, 330), {"1": "USER_BTN", "2": "GND"},
         fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, user (P402, IRQ4)"}),
    res("R15", "10k", "USER_BTN", "+3V3", (315, 315), "Resistor 10 kohm 1% 0402 (user button pull-up; value as RES; internal pull-ups off at reset)", rot=90),

    # ---- User LEDs --------------------------------------------------------------------------------------------------
    res("R16", "750", "LED1_A", "LED1", (360, 360), "Resistor 750 ohm 1% 0402 (LED1: (3.3 V - 1.75 V) / 750 ohm = 2.1 mA, Kingbright DSAO7433)"),
    led("D3", "LED1", "LED1_A", (375, 360), "APTD1608LSURCK", "LED red 0603, VF 1.75 V typ at 2 mA (Kingbright DSAO7433): user LED1 (P400, GTIOC9A)"),
    res("R17", "680", "LED2_A", "LED2", (360, 375), "Resistor 680 ohm 1% 0402 (LED2: (3.3 V - 1.9 V) / 680 ohm = 2.1 mA, Kingbright DSAO7432)"),
    led("D4", "LED2", "LED2_A", (375, 375), "APTD1608LCGCK", "LED green 0603, VF 1.9 V typ at 2 mA (Kingbright DSAO7432): user LED2 (P401, GTIOC9B)"),
    res("R18", "680", "LED3_A", "LED3", (360, 390), "Resistor 680 ohm 1% 0402 (LED3: (3.3 V - 1.85 V) / 680 ohm = 2.1 mA, Kingbright DSAO7434)"),
    led("D5", "LED3", "LED3_A", (375, 390), "APTD1608LSYCK", "LED yellow 0603, VF 1.85 V typ at 2 mA (Kingbright DSAO7434): user LED3 (P403)"),

    # ---- I2C pull-ups (jumpered), Pmod ports, shield headers ----------------------------------------------------------
    res("R3", "2.2k", "I2C_PU", "SCL", (480, 395), "Resistor 2.2 kohm 1% 0402 (SCL pull-up: RP(min) 0.97 kohm, fast mode to 161 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    res("R4", "2.2k", "I2C_PU", "SDA", (495, 395), "Resistor 2.2 kohm 1% 0402 (SDA pull-up: RP(min) 0.97 kohm, fast mode to 161 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    Part("JP2", "Jumper:SolderJumper_2_Bridged", "I2C PU", "Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm", (510, 420),
         {"A": "I2C_PU", "B": "+3V3"},
         fields={"Description": f"I2C pull-ups to 3.3 V, bridged as delivered; cut to remove them ({PMOD} section 2: jumpered pull-ups)"}),
    pmod("J7", "PMOD A", {1: "PMODA_CS", 2: "SPI_MOSI", 3: "SPI_MISO", 4: "SPI_SCK", 7: "PMODA_INT", 8: "PMODA_RST",
                          9: "PMODA_CS2", 10: "PMODA_CS3"}, (560, 225), "Type 2A expanded SPI"),
    pmod("J8", "PMOD B", {1: "PMODB_INT", 2: "PMODB_RST", 3: "SCL", 4: "SDA", 7: "PMODB_IO7", 8: "PMODB_IO8",
                          9: "PMODB_IO9", 10: "PMODB_IO10"}, (560, 290), "Type 6A expanded I2C"),
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
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole", "M3", HOLE, (60 + 20 * i, 400), {},
                      side="B" if i == 0 else "F",
                      fields={"Description": f"Mounting hole 3.2 mm, unplated, Uno R3 position ({label}), Arduino A000066 section 5.4"}))

# Board placement: (x, y, rotation) in mm, origin top-left. The RA2E1 sits left of centre, turned
# 180 degrees: its port 0 (the ADC pins) faces the analog header below, its port 1 (SPI, SCI9, SWDIO)
# faces the Pmod ports on the left edge, its ports 2 and 3 face the digital header above, and its
# oscillator, VCL and port 4 side faces the USB-UART and power on the right. Decoupling sits 1 mm
# beyond the chip's courtyard, in line with each supply pin, except C1, which sits right in front of
# VCC pin 11 and VSS pin 8 so that D0/D1 between them leave through vias inside the chip outline.
MX, MY = 31.0, 24.0
PLACEMENT = {
    "U1": (MX, MY, 180),
    "J3": (D8_PIN[0], D8_PIN[1], 270), "J4": (D0_PIN[0], D0_PIN[1], 270),
    "J5": (POWER_PIN[0], POWER_PIN[1], 90), "J6": (A0_PIN[0], A0_PIN[1], 90),
    **{f"H{i + 1}": (x, y, 0) for i, (x, y) in enumerate(HOLES)},
    # Pmod host ports on the left edge, 22.86 mm apart: the even (7-12) row 10.16 mm from the edge
    "J8": (12.70, 8.00, 0), "J7": (12.70, 30.86, 0),
    # supply pins: VCC 11 (right) and 39 (left), VCL 5, AVCC0 56 and VREFH0 59 (below)
    "C1": (38.25, 23.23, 270), "C2": (22.84, 23.73, 270), "C3": (39.40, 26.90, 270),
    "C6": (30.75, 32.61, 270), "C7": (32.25, 32.61, 270),
    "FB1": (24.60, 35.20, 0), "C8": (27.80, 35.20, 0), "C9": (30.40, 35.20, 0),
    # sub-clock crystal beside XCIN/XCOUT (pins 6 and 7), its load capacitors beyond it
    "Y1": (41.80, 25.75, 90), "C4": (44.30, 24.50, 0), "C5": (44.30, 27.00, 0),
    # SWD header above the chip's SWDIO/SWCLK corner; RES and NMI pull-ups above their pins
    "J2": (20.00, 11.50, 0), "R12": (30.75, 15.40, 90), "R13": (29.50, 15.40, 90),
    # I2C pull-ups and their jumper under the SDA/SCL header pins
    "R3": (18.80, 5.90, 90), "R4": (21.34, 5.90, 90), "JP2": (25.00, 6.00, 0),
    # reset button and MD jumper bottom left, between the SPI Pmod and the power header
    "SW1": (21.50, 45.60, 0), "JP1": (17.40, 36.00, 0), "R14": (20.40, 38.54, 0),
    # user LEDs and the power LED below the oscillator, the user button below them
    "R16": (40.00, 31.20, 90), "D3": (40.00, 33.90, 90),
    "R17": (42.20, 31.20, 90), "D4": (42.20, 33.90, 90),
    "R18": (44.40, 31.20, 90), "D5": (44.40, 33.90, 90),
    "R10": (46.60, 31.20, 90), "D2": (46.60, 33.90, 90),
    "SW2": (39.00, 37.60, 0), "R15": (44.00, 37.60, 90),
    # USB-C on the right edge, below the Uno ICSP position; ESD, CC resistors, CP2102N
    "J1": (W - USB_C_EDGE, 36.00, 90), "U2": (57.40, 36.00, 270), "U3": (52.20, 36.00, 180),
    "R1": (58.90, 39.90, 90), "R2": (58.90, 32.10, 90),
    # above the CP2102N: VREGIN/VDD capacitors at its top-right corner (pins 6, 7), the RSTb pull-up
    # over pin 9, the VIO pair beside it, and the VBUS divider and bleed above them
    "C17": (54.40, 32.20, 90), "C16": (56.20, 31.90, 90), "R11": (52.45, 32.00, 90),
    "C19": (50.60, 32.20, 90), "C18": (48.60, 31.60, 90),
    "R5": (54.00, 29.90, 0), "R6": (54.00, 28.70, 0), "R7": (57.60, 29.00, 0),
    # power: fuse, Schottky, LDO with its capacitors and divider, in a row above the analog lines
    "F1": (58.00, 43.00, 0), "D1": (53.20, 43.00, 0),
    # (the LDO block as on EoS LPC55S69 Board: IN and NR/SS capacitors right, OUT capacitor and divider left)
    "U4": (45.80, 42.60, 0), "C13": (47.60, 39.30, 90), "C15": (48.90, 42.35, 0),
    "C14": (42.70, 40.50, 90), "R8": (41.90, 42.60, 0), "R9": (42.41, 44.10, 270),
}
# Laid before the autorouter, in this order, and locked (pcb_build.py priority_routes):
# * The USB pair, connector to ESD part to CP2102N, on the top layer with no via and the ESD pads
#   inline: D+ from A6 and D- from A7. The CP2102N numbers D+ (3) before D- (4) counter-clockwise, so
#   a pair reaching it from the receptacle has D+ on its left; only the receptacle's middle contacts
#   (A7 D-, A6 D+) give that order. B6 then joins A6 behind A7, under the shell; B7 can reach A7 only
#   by crossing D+ or that link, so its join, the one connection that must change layer, goes through
#   the bottom layer (two vias, in the signal path only with the plug the other way up).
# * The 32.768 kHz lines, pin -> crystal pad -> load capacitor, on the top layer with no via (CLK
#   6.1.1). VSS pin 8 runs to C1 between D1 and XCOUT, and VCC pin 11 to C1, before anything else
#   can take that gap.
# * D0 and D1 from the shield header to the chip: C1 closes their outward escape, so each drops
#   through a via just inside its pin and runs on the bottom layer straight north-east, away from
#   the crystal (CLK 6.1.4 (3): route the adjacent pins' wires through the bottom of the MCU and
#   bring them out away from the oscillator pins). Laid from the header end, so their straight
#   stretch lies under the header, not beside XCOUT.
# * The LED resistor-to-anode links, then TXD9 and RXD9: kept south of the LEDs and out of the
#   crystal area; TXD9 enters the chip outline at its corner between pins 1 and 64, RXD9 crosses
#   under the chip on the bottom layer.
# * The CP2102N's ground pin 2 to its exposed pad, whose four vias the generator adds.
# * The LDO's FB line, and EN to +5V at D1's cathode (not round NR/SS pin 8 through a via).
PRIORITY = [(("J1", "A6"), ("U2", "3")), (("U2", "3"), ("U3", "3")),
            (("J1", "A7"), ("U2", "2")), (("U2", "2"), ("U3", "4")),
            (("J1", "B6"), ("J1", "A6"), "join"), (("J1", "B7"), ("J1", "A7"), "join"),
            (("U1", "7"), ("Y1", "1")), (("Y1", "1"), ("C4", "1")),
            (("U1", "6"), ("Y1", "2")), (("Y1", "2"), ("C5", "1")),
            (("U1", "8"), ("C1", "2")), (("U1", "11"), ("C1", "1")),
            (("J4", "1"), ("U1", "10")), (("J4", "2"), ("U1", "9")),
            (("R16", "1"), ("D3", "2")), (("R17", "1"), ("D4", "2")), (("R18", "1"), ("D5", "2")),
            (("R10", "1"), ("D2", "2")),
            (("U3", "20"), ("U1", "34")), (("U3", "21"), ("U1", "35")),
            (("U3", "2"), ("U3", "25")),
            (("U4", "3"), ("R8", "2")), (("U4", "7"), ("D1", "1"))]

_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS RA2E1 Board  rev A", "x": 31.0, "y": 39.5, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 31.0, "y": 41.5, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 31.0, "y": 42.9, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    # front, 1.0 mm text: what each control and connector is, and Pmod pin 1 beside pad 11 of each socket
    # (PMOD Figure 5 turned for the left edge; the footprint's own pin-1 mark is on its pad 1, Pmod pin 6)
    {"text": "BOOT", "x": 17.8, "y": 33.6, "size": 1.0}, {"text": "RESET", "x": 21.5, "y": 48.0, "size": 1.0},
    {"text": "USER", "x": 39.0, "y": 39.9, "size": 1.0}, {"text": "SWD", "x": 20.0, "y": 7.45, "size": 0.8},
    {"text": "PMOD A SPI", "x": 15.2, "y": 37.2, "size": 1.0, "angle": 90},
    {"text": "PMOD B I2C", "x": 15.2, "y": 14.35, "size": 1.0, "angle": 90},
    {"text": "1", "x": 14.3, "y": 43.56, "size": 1.0}, {"text": "1", "x": 14.3, "y": 20.70, "size": 1.0},
]

BOARD = Board(
    name="eos-ra2e1-board",
    title="EoS RA2E1 Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["Uno R3 outline (2700 x 2100 mil) and shield header positions: Matthew Beckler, \"Arduino Uno R3\" dimension "
             "drawing v1.05, Wayne and Layne, public domain (wayneandlayne.com/files/common/arduino_uno_drawing.svg); "
             "facts only, no file copied",
             "Uno R3 mounting holes (4 x 3.20 mm at 15.24 / 2.54 / 66.04 / 17.78 / 45.72 / 50.80 mm) and pin order: "
             "Arduino UNO R3 product reference manual (SKU A000066), sections 5 and 5.4 "
             "(docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf); facts only",
             "Pmod host port pin numbering, row offsets (10.16 / 12.70 mm from the edge) and 0.9 in port spacing: "
             "Digilent Pmod Interface Specification, revised 29 September 2020, sections 4-5 and Figure 5 "
             "(digilent.com/reference/_media/reference/pmod/pmod-interface-specification-1_3_0.pdf); facts only"],
    width=W,
    height=H,
    corner_radius=1.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    priority_routes=PRIORITY,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "VBUS", "VBUS_F", "+5V", "AVCC0"],
    headings=[((30, 70), "USB-C, ESD, fuse, Schottky, VBUS bleed"), ((190, 70), "3.3 V LDO with soft start (DS Table 2.14), power LED"),
              ((90, 210), "USB-UART: CP2102N on SCI9 (SCI boot port)"), ((320, 122), "RA2E1 supplies, VCL, AVCC0 filter"),
              ((385, 185), "R7FA2E1A92DFM"), ((470, 185), "32.768 kHz sub-clock (R01AN7202 Table 4.2.7)"),
              ((475, 290), "Reset, MD jumper, NMI, SWD"), ((300, 300), "User button, user LEDs"),
              ((465, 375), "I2C pull-ups (jumpered)"), ((540, 70), "Uno R3 shield headers"), ((540, 205), "Pmod host ports"),
              ((40, 385), "Mounting holes"), ((35, 300), "Power nets")],
    power_block=(40.64, 315.0),
    notes=[((260, 440), "EoS RA2E1 Board, rev A. Designed by Kartikeydheer Srivastava. Fits Uno R3 shields (3.3 V logic) and Pmod modules (3.3 V).\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Values from Renesas R01DS0386 and R01UH0852 (RA2E1), R01AN6060, R20UT4686, R01AN7202, TI SBVS282A (TPS7A91),\n"
                       "Silicon Labs CP2102N Rev. 1.5, Digilent's Pmod Interface Specification, and the part data sheets named in each part.\n"
                       "JP1 fitted at reset: SCI boot mode over the CP2102N (SCI9). Firmware: stop the main oscillator (MOSCCR.MOSTP = 1),\n"
                       "so P212/P213 serve as SCI1 on D0/D1; sub-clock drive Standard CL (SOMCR.SODRV = 00).")],
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}, "Ground": {"track": 0.25, "clearance": 0.15}},
    # GND tracks are 0.25 mm: the CP2102N's pin 2 to its exposed pad and VSS pin 8 between D1 and XCOUT
    # (0.30 mm from XCOUT, CLK 6.1.2 (2)), and still narrow enough for the 0.25 mm pads at 0.5 mm pitch
    # +5V and +3V3 are 0.3 mm: they enter the TPS7A91's 0.25 mm pads and the LQFP-64's and QFN-24's
    # 0.3 mm and 0.25 mm pads at 0.5 mm pitch, which a 0.4 mm track cannot
    net_to_class={"VBUS": "Power", "VBUS_F": "Power", "+5V": "Supply", "+3V3": "Supply", "AVCC0": "Supply",
                  "VCL": "Supply", "USB_DP": "USB", "USB_DM": "USB", "GND": "Ground"},
)
