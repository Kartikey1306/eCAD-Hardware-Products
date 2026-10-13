"""EoS KE16Z Board: an NXP Kinetis KE16Z development board that fits Uno R3 shields, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-ke16z-board/LICENSE.txt.

A 68.58 x 53.34 mm two-layer board for the NXP MKE16Z64VLF4 (Kinetis KE1xZ, Cortex-M0+,
48 MHz, 64 KB flash, 8 KB SRAM, MSCAN, LQFP-48) at 3.3 V. It does the job of NXP's KE16Z
evaluation board: Arduino Uno R3 shield headers, a USB-C port with a CP2102N USB-UART bridge on
LPUART1, an 8 MHz crystal, an RGB LED, reset and two user buttons, a power LED, and an Arm 10-pin
SWD header in place of OpenSDA. No design file of NXP's (schematic, layout, Gerbers, BOM) was
opened. The circuit comes from the chip makers' data sheets; the header positions come from
published Uno R3 mechanical facts.

Mechanical facts (origin top-left, y down; the sources use mils from the lower-left corner, y up):

* Outline 2700 x 2100 mil = 68.58 x 53.34 mm, and the shield header positions: Matthew
  Beckler's "Arduino Uno R3" dimension drawing v1.05 (Wayne and Layne): digital 1x10 from
  1640 mil (D8) to 740 mil (SCL) and 1x8 from 2500 mil (D0) to 1800 mil (D7) on the 2000-mil
  row; power 1x8 from 1100 mil and analog 1x6 from 2000 mil on the 100-mil row. Checked against
  KiCad 10's Module:Arduino_UNO_R3_WithMountingHoles footprint, pad by pad (pad 1 = 1100 mil,
  pad 9 = 2000 mil, pad 15 = 2500 mil, pad 23 = 1640 mil, pad 32 = 740 mil; rows 1900 mil apart).
* Mounting holes, 3.2 mm, at (600, 2000), (550, 100), (2600, 1400) and (2600, 300) mil: Arduino
  UNO R3 product reference manual (A000066), section 5.4, the Beckler drawing, and the same
  KiCad footprint's four holes. Unplated. The 10-pin socket's SCL end lies within the top-left
  hole's screw-head courtyard, so H1 is placed from the back, where its standoff goes.
* The Uno R3 pin order (A000066 section 5): power header NC, IOREF, RESET, 3V3, 5V, GND, GND,
  VIN; digital D0-D13, GND, AREF, SDA, SCL.

Every value follows a data sheet or a chip maker's guide. Sources, by short name:
  DS     = NXP KE1xZP48M48SF0 data sheet, Rev. 3, 06/2020 (Wayback Machine copy of nxp.com's PDF)
  RM     = NXP KE1xZP48M48SF0RM reference manual, Rev. 3, 06/2020 (Wayback Machine copy)
  PKG    = NXP 98ASH00962A rev. H, LQFP-48 7 x 7 x 1.4 mm, 0.5 mm pitch (SOT313-3, JEDEC MS-026-BBC)
  CP     = Silicon Labs CP2102N data sheet Rev. 1.5
  AN3208 = NXP (Freescale) AN3208 "Crystal Oscillator Troubleshooting Guide", Rev. 0
  AN1706 = NXP (Freescale) AN1706 "Microcontroller Oscillator Circuit Design Considerations"
  AN2867 = ST AN2867 Rev 24 "Guidelines for oscillator design" (the gain-margin method)
  KLQRUG = NXP (Freescale) Kinetis L Peripheral Module Quick Reference, Rev 0, 09/2012: NXP's
           Kinetis hardware layout guidance (chapter 2; USB, 9.6.3). Written for Kinetis L; used
           here for its layout rules, which are not specific to one chip

* Chip and package. The symbol is KiCad's own MCU_NXP_Kinetis:MKE16Z64VLF4; its 48 pins match
  DS section 4.1 (LQFP-48 column) pin for pin, including pin 10 VSS/VREFL. The footprint is
  KiCad's Package_QFP:LQFP-48_7x7mm_P0.5mm (JEDEC MS-026 BBC), checked against PKG: 7 x 7 mm
  body, 9.0 mm across the leads, 0.5 mm pitch, leads 0.17-0.27 mm wide with a 0.5-0.7 mm foot;
  the pads are 0.30 x 1.475 mm centred 4.1625 mm out, so each covers its foot from 3.43 to
  4.90 mm (the foot runs 3.8 to 4.5 mm).
* Supply. DS Table 24: VDD and VDDA 2.7-5.5 V, VDDA within 0.1 V of VDD. The board runs at 3.3 V
  from an AP7361C-33 LDO (Diodes DS37274 Rev. 5-2: 2.2-6.0 V in, 1 A; "Bypass to ground through
  at least 1 uF" on IN and "at least 2.2 uF" on OUT; 4.7 uF on each, as its typical application
  circuit shows). VDDA is tied to the 3.3 V rail. Decoupling as DS Figure 8 and Table 26 show it:
  100 nF CDEC at VDD pin 7 (to VSS/VREFL pin 10), at VDDA pin 8 and at VDD pin 31 / VSS pin 30;
  100 nF CREF at VREFH pin 9 to VREFL, with the 1 nF C0G and 10 nF X7R in parallel that Table 26
  note 1 recommends "for improved ADC performance"; DS 6.1.2: "bulk capacitance, 10 uF or more,
  at the entrance of the power plane", so 10 uF where 3.3 V reaches the chip. DS Table 25 note 1
  limits the ramp to 500 V/ms; the LDO's start-up time is 150 us typical (DS37274, COUT 2.2 uF),
  about 22 V/ms.
* 3.3 V is chosen rather than 5 V (the chip allows both) because the CP2102N's I/O supply is at
  most 3.6 V (CP Table 3.1). IOREF is 3.3 V: the KE16Z's pins take at most VDD + 0.3 V (DS Table
  23), and "none of the I/O pins, including open-drain and pseudo open-drain pins, are allowed
  to go above VDD" (DS 2.2.13). Every pin is clamped to VDD by an ESD diode (DS Table 24 note 1),
  so a shield driving 5 V onto a pin pushes current into the 3.3 V rail, which the LDO cannot
  sink and which also feeds the CP2102N (VDD absolute maximum 4.2 V, CP Table 3.10): that can
  damage both chips. Nothing may feed the 3V3 or IOREF pins either: they are the LDO's output,
  whose absolute maximum is VIN + 0.3 V (DS37274).
* VREFH. DS Table 50: VREFH 2.5 V to VDDA + 0.1 V. JP1 takes VREFH from the 3.3 V rail (VDDA) as
  delivered, or from the AREF header pin (cut and re-bridge); AREF must then stay within
  2.5 V-VDDA.
* Clock. The chip boots from its 48 MHz FIRC (RM 14.4.1), which DS Table 42 gives as +-1 % over
  voltage and temperature, so no crystal is needed to run. The crystal is for MSCAN, the "6" in
  KE16: RM 42.5.5.2 says the CAN clock source must meet "the tight oscillator tolerance
  requirements (up to 0.4%) of the CAN protocol" and recommends the oscillator clock
  (SOSCDIV2_CLK, RM 42.1.2) rather than the bus clock. (DS Table 42's note calls the FIRC
  "compliant with CAN and LIN standards"; the crystal gives margin either way.) 8 MHz in the
  medium range (DS Table 41: 4-8 MHz), low-power mode (HGO = 0): DS Table 40 note 3, "RF is
  integrated and must not be attached externally", and RS = 0 (Table 40; DS 6.1.5, Figure 31,
  "Diagram 2"). Crystal: ECS-80-10-30B-CWN-TR (ECS ECX-53B: 8 MHz, CL 10 pF, ESR 100 ohm max,
  C0 5 pF max, drive level 100 uW max). Load capacitors from AN3208 section 5 (C1 = C2, their
  series value plus strays = CL): C = 2 x CL - Cstray = 20 - 9 = 11 pF, Cstray = 7 pF pin
  capacitance + 2 pF of board (AN1706 3.1.1, about 1 pF per cm of trace). DS Table 31 gives 7 pF
  for analog and digital pins but refers EXTAL/XTAL to the oscillator specifications, which list
  none, so the 7 pF is an assumption. The crystal's +-10 ppm / +-15 ppm option is far inside
  CAN's 0.4 %; any 8 MHz 10 pF ECX-53B code would serve, but this one is the one distributors
  stock (Digi-Key: active, 2026-10-13).
  Gain margin (AN2867 section 3.4: gm / gmcrit, at least 5): gmcrit = 4 x ESR x (2 pi f)^2 x
  (C0 + CL)^2 = 0.227 mA/V; DS Table 40 gives the medium-range gm as 2.2-9.7 mA/V, so the margin
  is at least 9.7. (The 18 pF crystal of the same family would give 4.1, under 5.) Drive level,
  AN3208 Eqn. 1, P = 2 R1 [pi f V (CL + C0)]^2, with V taken as the low-power mode's 1.0 V
  peak-to-peak (DS Table 40, Vpp; a conservative peak): 28 uW, under the crystal's 100 uW. In
  high-gain mode (3.3 V swing) it would be 310 uW, so firmware must use low-power mode.
* Reset (DS 6.1.4, Figure 27): "The resistor value must be in the range of 4.7 kohm to 10 kohm;
  the recommended capacitance value is 0.1 uF": 10 kohm and 100 nF, and a reset button to GND.
  The pin is pseudo open drain with an internal 10 kohm pull-up. NMI_b (PTD3, NMI by default,
  DS 4.1): 10 kohm pull-up and no capacitor (DS 6.1.4, Figure 29: "Do not add a pull-down
  resistor or capacitor on the NMI_b pin"). PTD3 is not on a header, so a shield cannot fire it.
* Debug: an Arm Cortex 10-pin (1.27 mm) SWD header, J2: SWD_DIO (PTA4), SWD_CLK (PTC4),
  RESET_b (PTA5), VTref = 3.3 V. DS Figure 30: 10 kohm pull-up on SWD_DIO, 10 kohm pull-down on
  SWD_CLK ("recommended for system robustness") and 0.1 uF at the header's VDD. The KE16Z has no
  SWO pin (DS 4.1). It replaces OpenSDA, whose firmware is NXP's. The chip boots only from its
  flash (DS 2.1.5); there is no ROM bootloader (RM Table 11-1: 0x1C00_0000, the ROM base, is
  reserved), so there is no ISP button.
* Power path. USB-C as a 5 V sink: 5.1 kohm Rd on CC1 and CC2 (USB Type-C specification, sink
  termination).
  ESD protection on D+, D- and VBUS: Littelfuse SP0503BAHTG (SP05xxBA data sheet: 5.5 V standoff,
  100 nA maximum leakage at 5 V, 30 pF; three diodes from each line to the common pin 1, none
  between the lines), the part CP Figure 2.5 shows. Pins 2, 3 and 4 are the same diode, so D+ is
  on pin 3 and D- on pin 2, the order that keeps the pair from crossing (see Layout). A USBLC6-2SC6 is not used: its data-line diodes run to its VBUS pin, so after
  a host unplugs, the CP2102N's D+ pull-up (live on the board's 3.3 V) could hold VBUS near 2 V,
  between the VBUS pin's VIL and VIH (CP Table 3.7), and the bridge might never see the unplug.
  VBUS through a Littelfuse 1206L050 PTC (1206L series: 0.50 A hold, 1.00 A trip, 6 V, R1max
  0.70 ohm), then a Nexperia PMEG6010CEH Schottky (product data sheet 1 July 2023, Table 7:
  VF 350 mV typ / 400 mV max at 100 mA, 530 mV max at 500 mA) to the 5 V rail, which feeds the
  LDO, the RGB LED and the shield 5V pin. The diode keeps 5 V fed into the 5V pin from reaching
  the USB host. The shield VIN pin is not connected: there is no 7-12 V input, and a voltage
  there must not reach the 5 V rail. The 5V pin is that rail, VBUS less F1 and D1: at 300 mA in
  all (250 mA for shields, from the 5V and 3V3 pins together, and 50 mA for the board) F1 drops
  at most 0.21 V (R1max 0.70 ohm; Rmin 0.15 ohm) and D1 at most 0.53 V (Table 7, 500 mA), so
  the pin gives 4.26 V or more from a 5.0 V port, 4.0 V or more from a 4.75 V one, about
  4.4-4.5 V typically. D1 then dissipates at most 0.16 W, a 53 C rise at Table 6's 330 K/W on its standard footprint, and F1's hold current
  derates to 0.35 A at 60 C (1206L table), still above 300 mA. At 450 mA (a 400 mA shield) D1
  would rise up to 79 C and F1 could trip on a warm day (0.42 A hold at 40 C), so shields are
  rated 250 mA in all, from the 5V and 3V3 pins together, and at most 200 mA of it from 3V3: with
  the board's 30 mA or so of 3.3 V load the LDO then dissipates at most (5.25 - 3.3) V x 0.23 A =
  0.45 W, a 49 C rise at 110 C/W (DS37274, SOT-223, minimum pad). Fed from a shield, the 5V pin
  has no fuse, reverse protection or TVS in front of the LDO (absolute maximum 6.5 V, DS37274):
  4.75-5.25 V only, the right way round. From a 4.75 V port at 300 mA the LDO still gets 4.75 - 0.21 - 0.53 = 4.01 V,
  above 3.3 V plus its 140 mV maximum dropout at 300 mA (DS37274). Inrush: C1 (4.7 uF) on 5 V and
  about 25 uF on 3.3 V charge at plug-in with no soft start, about 105 uC at nominal values,
  against the 50 uC the USB-IF inrush test is commonly quoted with (not re-read here); the
  CP2102N's two 4.7 uF, the 10 uF bulk DS 6.1.2 asks for and the LDO's 2.2 uF minimum alone are
  21.6 uF (71 uC at 3.3 V), so meeting it would need a load switch. Not measured.
* USB-UART: Silicon Labs CP2102N-A02-GQFN20 (CP Rev. 1.5) on LPUART1 (PTC7 TX, PTC6 RX, ALT2,
  DS 4.1), which are also the D1/D0 header pins, as on the Uno. It runs from the board's 3.3 V
  with its own regulator unused (CP Figure 2.3: VREGIN tied to VDD, 3.0-3.6 V in; QFN20: VIO =
  VDD), so it is powered whenever the KE16Z is and the KE16Z's TX never drives an unpowered
  bridge. "4.7 uF and 0.1 uF bypass capacitors required for each power pin": one pair at VREGIN
  and one at VDD. 1 kohm RSTb pull-up to VDD ("In all cases, a 1 kohm pull-up on the RSTb pin is
  recommended", CP 2.1). Its VBUS pin ("A 5 V signal on this pin indicates a USB network
  connection", CP Table 5.3) senses the connector's VBUS through the 22.1 k / 47.5 k divider CP
  2.3 requires (Figure 2.6, self-powered): 5 V reads 3.41 V, over VIH = VIO - 0.6 V = 2.7 V; 4.4 V
  reads 3.00 V. So the bridge connects to USB, and its D+ pull-up comes on, only when a host
  supplies VBUS. Bleed: with the board fed from the shield 5V pin and no host, D1 is reverse
  biased by about 5 V and its leakage flows into VBUS. The CP2102N reads its VBUS pin as low only
  at or below VIL = 0.6 V (CP Table 3.7), so VBUS must stay under 0.6 V x 69.6 / 47.5 = 0.88 V.
  R5 = 5.1 kohm in parallel with the divider is 4.75 kohm, which holds that for up to 185 uA of
  leakage. PMEG6010CEH Table 7: IR 0.8 uA typical at 5 V and 25 C, 50 uA maximum at 60 V and
  25 C; its Fig. 2 (typical) shows about 70 uA at 5 V and 85 C. A host pays 1.0 mA for the bleed.
  TXD and RXD meet D0/D1 through 1 kohm, so a shield driving D0 against the bridge's TXD fights at
  most 3.3 mA, within its 6.5 mA low-drive rating (CP Table 3.7). The KE16Z's VIH is 0.7 x VDD =
  2.31 V (DS Table 25), under the CP2102N's VOH of VIO - 0.7 V = 2.6 V; the CP2102N's VIH (2.7 V)
  is under the KE16Z's unloaded output high, since the bridge input draws only its leakage and
  weak pull-up current (DS Table 25 gives VDD - 0.8 V only at 2.8 mA). Unused bridge pins are
  open (CP 4.3.1: GPIO default to open drain with a weak pull-up).
* RGB LED: Wurth 150141M173100 (common anode; pin 1 anode, 2 blue, 3 red, 4 green). VF at 20 mA:
  red 2.0 V typ (2.4 max), green and blue 3.2 V typ (3.6 max), 30 mA continuous max. From a
  3.3 V pin the green and blue could not light reliably, so the anode is on the 5 V rail and each
  colour is switched by an AO3400A N-MOSFET (Alpha & Omega: VGS(th) 0.65-1.45 V, RDS(on) < 48
  mohm at VGS = 2.5 V). The 5 V rail is VBUS less the fuse and D1, about 4.65 V at the board's
  load (D1 Table 7: 270-350 mV typ between 10 and 100 mA): red (4.65 - 2.0) / 560 ohm = 4.7 mA,
  green and blue (4.65 - 3.2) / 300 ohm = 4.8 mA; from a 5.25 V shield supply 5.8 and 6.8 mA.
  Pins are analog or disabled after reset (RM 17.2.2), so 100 kohm holds each gate low and the
  LED off until firmware drives it. Red on PTD1 (FTM0_CH3); green on PTC2 and blue on PTC3,
  whose FTM0_CH2 / FTM0_CH3 alternates (DS 4.1) give PWM when firmware moves those channels off
  D9 or red. FTM0 and FTM1 have eight channels in all (DS Figure 1: 6 + 2): the six Uno PWM pins
  take six and red the seventh; the eighth, FTM1_CH0, is only on A1 (PTB2) and SWD_CLK (PTC4).
* Power LED: Kingbright APTD1608LCGCK (DSAO7432: VF 1.9 V typ at 2 mA) on 3.3 V through 680 ohm:
  2.1 mA.
* Buttons: C&K KMR2. User buttons on PTD5 and PTE3 with 10 kohm pull-ups to 3.3 V, the value DS
  Figure 29 uses for NMI_b: their ports' pulls are off at reset (DS Table 6).
* I2C (LPI2C0 on PTA2 SDA / PTA3 SCL, ALT3, DS 4.1; PTB6/PTB7, the other choice, are the crystal
  pins) on the Uno SDA/SCL pins, with 4.7 kohm pull-ups to 3.3 V. TI SLVA689A Eq. 1 with the
  KE16Z's own sink rating (DS Table 25: 2.4 mA at 0.8 V): Rp(min) = (3.3 - 0.8) V / 2.4 mA =
  1.04 kohm; Eq. 6: Rp(max) = tr / (0.8473 Cb), so 4.7 kohm meets fast mode's 300 ns up to 75 pF
  and standard mode's 1000 ns up to 251 pF. Pull-ups on a shield must go to 3.3 V (IOREF).

Arduino pin map (KE16Z pin, function, DS 4.1; PWM on D3, D5, D6, D9, D10, D11 as on the Uno; every
port pin can interrupt, DS 2.2.13):
  D0 PTC6 LPUART1_RX (bridge TXD via 1 k)   D1 PTC7 LPUART1_TX (bridge RXD via 1 k)
  D2 PTD2                                   D3 PTA1 FTM1_CH1
  D4 PTD4                                   D5 PTC1 FTM0_CH1
  D6 PTC0 FTM0_CH0                          D7 PTA0 (also ADC0_SE0)
  D8 PTE6                                   D9 PTD0 FTM0_CH2
  D10 PTB5 FTM0_CH5, LPSPI0_PCS1            D11 PTB4 FTM0_CH4, LPSPI0_SOUT
  D12 PTE1 LPSPI0_SIN                       D13 PTE0 LPSPI0_SCK
  SDA PTA2 LPI2C0_SDA                       SCL PTA3 LPI2C0_SCL
  A0 PTB3 ADC0_SE7   A1 PTB2 ADC0_SE6   A2 PTB1 ADC0_SE5   A3 PTB0 ADC0_SE4   A4 PTA7 ADC0_SE3
  A5 PTA6 ADC0_SE2
A4 and A5 are analog inputs only here, not SDA/SCL as on the Uno: the KE16Z's I2C pins carry no
ADC channel. J7 (2x6, 2.54 mm) brings out PTE4/PTE5 (CAN0_RX/TX, ALT5, for an external CAN
transceiver), PTD6/PTD7 (LPUART2), PTE10 (CLKOUT), PTC5 (RTC_CLKOUT), PTE8 (ACMP0_IN3), PTE11
(PWT_IN1, LPTMR0_ALT1) and PTE2, with 3.3 V and GND. All 42 port pins are used.

Layout (two layers; the autorouter, Freerouting, gives a different result on every run, so
everything below is laid by placement and `priority_routes`, before it runs):
* USB, NXP's Kinetis USB layout guidance (KLQRUG 9.6.3: "Route the USB D+ and D- signals
  as parallel 90 ohm differential pairs ... Minimize vias and corners ... Avoid signal stubs"):
  the pair runs on the top layer from the receptacle's A6/A7 contacts through the ESD part's pads
  (pins 3 and 2, inline, no stub) to the CP2102N's D+/D- pins, which are level with A6/A7. The
  receptacle's second contacts join behind: B7 (D-) to A7 under the shell on the top layer, and
  B6 (D+) to A6 through two vias, the one crossing a USB-C pair needs, kept in the stub.
* Crystal, NXP's Kinetis hardware guidance (KLQRUG 2.1.3.3.1: "The crystal or resonator
  must be located close to the MCU. No signals of any kind should be routed on the layer
  directly below the crystal. ... A ground pour must be placed around the crystal and its load
  components") and DS 6.1.5 (a guard ring may be added): Y1 sits below the VREFH capacitors, 1 mm
  from the MCU's courtyard, turned so its EXTAL pad (3) is on the far side, reached over the top,
  and its XTAL pad (1) on the near side, reached down the gap between Y1 and the MCU, so the two
  lines never run side by side or cross. Each load capacitor sits beside its own pad; pin ->
  crystal pad -> capacitor is laid on the top layer with no via, and Y1's ground pads and both
  capacitors' ground ends are one ground trace. VSS pin 10 lies above EXTAL (pin 11), so that
  trace meets VSS through the pours rather than a top-layer track across EXTAL. The extra I/O
  header, the RGB LED and the buttons, whose lines used to run under the crystal, are now below
  and left of the MCU, and the VREFH jumper beside its capacitors, so no line needs to pass it.
* Decoupling, DS 6.1.2 ("bypass capacitors ... as close as possible to each VDD/VSS pair,
  including VDDA/VSSA and VREFH/VREFL") and Table 26 note 2 ("as close as possible to the
  VREFH/VREFL pins"): VDD pins 7 and 8 are joined at their pads and run to C8, C7, JP1's 3.3 V
  side and C10, the 10 uF bulk where 3.3 V enters (DS 6.1.2); VREFH pin 9 runs through C13, C12
  and C11 to JP1's middle pad, with VSS pin 10 to their ground ends; JP1's AREF side leaves to
  the left. RESET_b's 10 kohm and 100 nF sit beside pin 47 (DS 6.1.4 Figure 27), the CP2102N's
  100 nF capacitors at its VDD and VREGIN pins with the 4.7 uF ones beside them (CP Figure 2.3), and
  the LDO's at its IN and OUT pins; each is joined by a short top-layer route laid first.

The touch-sense electrodes and the thermistor of the vendor board are left out (see the README).
Two layers, ground poured on both sides.
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

DS = "NXP KE1xZP48M48SF0 Rev. 3"
RM = "NXP KE1xZP48M48SF0RM Rev. 3"
CP = "Silicon Labs CP2102N Rev. 1.5"
LDO = "Diodes DS37274 Rev. 5-2"
WE = "Wurth 150141M173100"


# Capacitor part numbers by value, all Murata and all "In Production" on Murata's product pages (checked
# 2026-10-13); the 11 pF load capacitors are the high-Q C0G GJM series, as the GRM 11 pF 0402 is not for
# new designs.
MURATA = {"100n": "GRM155R71C104KA88D", "4.7u": "GRM21BR71A475KE51L", "4.7u 25V": "GRM219R61E475KA73D",
          "10u": "GRM21BR61C106KE15L", "10n": "GRM155R71H103KA88D", "1n": "GRM1555C1H102JA01D",
          "11p": "GJM1555C1H110JB01D"}


def yageo(value):
    """Yageo RC0402FR-07 (1 %, 0402) part number: 5.1k -> RC0402FR-075K1L, 680 -> RC0402FR-07680RL."""
    code = (value[:-1].replace(".", "K") if "." in value else value[:-1] + "K") if value.endswith("k") else value + "R"
    return f"RC0402FR-07{code}L"


def res(ref, value, a, b, sch, desc, rot=0):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b},
                fields={"Manufacturer": "Yageo", "MPN": yageo(value), "Description": desc}, sch_rotation=rot)


def cap(ref, value, a, b, sch, desc, fp=C0402, rot=0, mfr="Murata", mpn=None):
    fields = {"Manufacturer": mfr, "MPN": mpn or MURATA[value], "Description": desc}
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def socket(ref, n, value, pins, sch, desc):
    """A female header for shields: pin 1 is the first signal named in ``pins``."""
    return Part(ref, f"Connector:Conn_01x{n:02d}_Socket", value,
                f"Connector_PinSocket_2.54mm:PinSocket_1x{n:02d}_P2.54mm_Vertical", sch,
                {str(i + 1): net for i, net in enumerate(pins)},
                fields={"Manufacturer": "Samtec", "MPN": f"SSW-1{n:02d}-01-T-S", "Description": desc})


def button(ref, value, net, sch, what):
    return Part(ref, "Switch:SW_Push", value, KMR2, sch, {"1": net, "2": "GND"},
                fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": f"Tactile switch, {what}"})


def nfet(ref, gate, drain, sch, colour):
    return Part(ref, "Transistor_FET:AO3400A", "AO3400A", "Package_TO_SOT_SMD:SOT-23", sch,
                {"G": gate, "S": "GND", "D": drain},
                fields={"Manufacturer": "Alpha & Omega", "MPN": "AO3400A",
                        "Description": f"N-MOSFET, {colour} LED switch: VGS(th) 0.65-1.45 V, RDS(on) < 48 mohm at 2.5 V (AOS AO3400A)"})


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

# MKE16Z64VLF4 (LQFP-48) pins by number, DS section 4.1. Every port pin is used.
MCU = {
    # left side: PTD1 FTM0_CH3, PTD0 FTM0_CH2, PTE11, PTE10 CLKOUT, PTE5 CAN0_TX, PTE4 CAN0_RX,
    # VDD, VDDA, VREFH, VSS/VREFL, PTB7 EXTAL, PTB6 XTAL
    1: "LED_R", 2: "D9", 3: "EXT_PTE11", 4: "EXT_PTE10", 5: "EXT_PTE5", 6: "EXT_PTE4",
    7: "+3V3", 8: "+3V3", 9: "VREFH", 10: "GND", 11: "EXTAL", 12: "XTAL",
    # bottom: PTE3, PTE8 ACMP0_IN3, PTB5 FTM0_CH5/LPSPI0_PCS1, PTB4 FTM0_CH4/LPSPI0_SOUT, PTC3, PTC2,
    # PTD7 LPUART2_TX, PTD6 LPUART2_RX, PTD5, PTC1 FTM0_CH1, PTC0 FTM0_CH0, PTB3 ADC0_SE7
    13: "BTN2", 14: "EXT_PTE8", 15: "D10", 16: "D11", 17: "LED_B", 18: "LED_G",
    19: "EXT_PTD7", 20: "EXT_PTD6", 21: "BTN1", 22: "D5", 23: "D6", 24: "A0",
    # right side: PTB2 ADC0_SE6, PTB1 SE5, PTB0 SE4, PTA7 SE3, PTA6 SE2, VSS, VDD, PTD4, PTD3 NMI_b,
    # PTD2, PTA3 LPI2C0_SCL, PTA2 LPI2C0_SDA
    25: "A1", 26: "A2", 27: "A3", 28: "A4", 29: "A5", 30: "GND",
    31: "+3V3", 32: "D4", 33: "NMI", 34: "D2", 35: "SCL", 36: "SDA",
    # top: PTA1 FTM1_CH1, PTA0, PTC7 LPUART1_TX, PTC6 LPUART1_RX, PTE6, PTE2, PTE1 LPSPI0_SIN,
    # PTE0 LPSPI0_SCK, PTC5 RTC_CLKOUT, PTC4 SWD_CLK, PTA5 RESET_b, PTA4 SWD_DIO
    37: "D3", 38: "D7", 39: "D1", 40: "D0", 41: "D8", 42: "EXT_PTE2",
    43: "D12", 44: "D13", 45: "EXT_PTC5", 46: "SWCLK", 47: "RESET", 48: "SWDIO",
}

PARTS = [
    # ---- USB-C (J1), ESD, fuse, Schottky, VBUS bleed --------------------------------------------
    Part("J1", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (45, 100), {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_DP", "D-": "USB_DM",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12",
                 "Description": "USB-C 2.0 receptacle, 16 pins: USB-UART (CP2102N) and board power"}),
    res("R1", "5.1k", "CC1", "GND", (80, 78), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC1, USB Type-C specification, sink termination)"),
    res("R2", "5.1k", "CC2", "GND", (95, 78), "Resistor 5.1 kohm 1% 0402 (USB-C sink Rd on CC2, USB Type-C specification, sink termination)"),
    Part("U1", "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", (110, 105),
         {"1": "GND", "3": "USB_DP", "2": "USB_DM", "4": "VBUS"},
         fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                 "Description": "USB ESD protection, three diodes to GND on D+, D- and VBUS, no path between them "
                                f"(5.5 V standoff, 30 pF, Littelfuse SP05xxBA; {CP} Figure 2.5)"}),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (140, 82), {"1": "VBUS", "2": "VBUS_F"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                 "Description": "PTC resettable fuse 0.50 A hold, 1.00 A trip, 6 V, R1max 0.70 ohm, 1206 (Littelfuse 1206L series)"}),
    Part("D1", "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F", (170, 95), {"A": "VBUS_F", "K": "+5V"},
         fields={"Manufacturer": "Nexperia", "MPN": "PMEG6010CEH",
                 "Description": "Schottky 60 V 1 A, VF <= 400 mV at 100 mA, <= 530 mV at 500 mA, IR 0.8 uA typ at 5 V "
                                "(Nexperia PMEG6010CEH, 1 July 2023, Table 7): the 5V pin cannot feed the USB host"}),
    res("R5", "5.1k", "VBUS", "GND", (190, 118), f"Resistor 5.1 kohm 1% 0402 (VBUS bleed: with the divider 4.75 kohm, so up to 185 uA of D1 "
        f"leakage keeps the CP2102N VBUS pin under VIL 0.6 V, {CP} Table 3.7; 1.0 mA from a host)", rot=90),

    # ---- 3.3 V LDO, bulk, power LED --------------------------------------------------------------
    Part("U3", "Regulator_Linear:AP7361C-33E", "AP7361C-33", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (95, 190),
         {"VI": "+5V", "VO": "+3V3", "GND": "GND"},
         fields={"Manufacturer": "Diodes Incorporated", "MPN": "AP7361C-33E-13",
                 "Description": f"LDO 3.3 V 1 A, SOT-223, input 2.2-6.0 V ({LDO})"}),
    cap("C1", "4.7u", "+5V", "GND", (70, 185), f"Capacitor 4.7 uF 25 V X5R 0805 (LDO input: at least 1 uF, 4.7 uF as in the typical application, {LDO})", C0805,
        mpn=MURATA["4.7u 25V"]),
    cap("C2", "4.7u", "+3V3", "GND", (120, 185), f"Capacitor 4.7 uF 10 V X7R 0805 (LDO output: at least 2.2 uF, 4.7 uF as in the typical application, {LDO})", C0805),
    res("R3", "680", "+3V3", "LED_PWR_A", (140, 185), "Resistor 680 ohm 1% 0402 (power LED: (3.3 V - 1.9 V) / 680 ohm = 2.1 mA, Kingbright DSAO7432)"),
    Part("D2", "Device:LED_Small", "PWR", "LED_SMD:LED_0603_1608Metric", (158, 185), {"A": "LED_PWR_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LCGCK",
                 "Description": "LED green 0603, VF 1.9 V typ at 2 mA (Kingbright DSAO7432): power (3.3 V)"}),

    # ---- USB-UART: CP2102N on the board's 3.3 V, VBUS sensed -----------------------------------------
    Part("U2", "Interface_USB:CP2102N-Axx-xQFN20", "CP2102N-A02-GQFN20",
         "Package_DFN_QFN:SiliconLabs_QFN-20-1EP_3x3mm_P0.5mm_EP1.8x1.8mm", (205, 280),
         {"VREGIN": "+3V3", "VDD": "+3V3", "GND": "GND", "D+": "USB_DP", "D-": "USB_DM", "VBUS": "BR_VBUS",
          "~{RST}": "BR_RST", "TXD": "BR_TXD", "RXD": "BR_RXD",
          **{p: NC for p in ("1", "2", "10", "11", "13", "14", "15", "16", "19", "20")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN20",
                 "Description": f"USB-UART bridge on LPUART1, from the board's 3.3 V, own regulator unused: VREGIN tied to VDD ({CP} Figure 2.3)"}),
    cap("C3", "4.7u", "+3V3", "GND", (160, 260), f"Capacitor 4.7 uF 10 V X7R 0805 (CP2102N VREGIN, tied to VDD, {CP} Figure 2.3)", C0805),
    cap("C4", "100n", "+3V3", "GND", (160, 282), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VREGIN, tied to VDD, {CP} Figure 2.3)"),
    cap("C5", "4.7u", "+3V3", "GND", (245, 255), f"Capacitor 4.7 uF 10 V X7R 0805 (CP2102N VDD, {CP} Figure 2.3)", C0805),
    cap("C6", "100n", "+3V3", "GND", (260, 255), f"Capacitor 100 nF 16 V X7R 0402 (CP2102N VDD, {CP} Figure 2.3)"),
    res("R4", "1k", "BR_RST", "+3V3", (245, 278), f"Resistor 1 kohm 1% 0402 (CP2102N RSTb pull-up to VDD, {CP} section 2.1)", rot=90),
    res("R6", "22.1k", "VBUS", "BR_VBUS", (125, 310), f"Resistor 22.1 kohm 1% 0402 (CP2102N VBUS divider, {CP} Figure 2.6)", rot=90),
    res("R7", "47.5k", "BR_VBUS", "GND", (150, 310), f"Resistor 47.5 kohm 1% 0402 (CP2102N VBUS divider: 5 V -> 3.41 V > VIH 2.7 V, {CP} Figure 2.6, Table 3.7)", rot=90),
    res("R8", "1k", "BR_TXD", "D0", (250, 302), f"Resistor 1 kohm 1% 0402 (bridge TXD to D0/PTC6: a shield driving D0 fights at most 3.3 mA, {CP} Table 3.7)"),
    res("R9", "1k", "D1", "BR_RXD", (250, 320), "Resistor 1 kohm 1% 0402 (D1/PTC7 to bridge RXD: contention and ESD current limit on a shield pin)"),

    # ---- MKE16Z64VLF4, decoupling, VREFH ----------------------------------------------------------------
    Part("U4", "MCU_NXP_Kinetis:MKE16Z64VLF4", "MKE16Z64VLF4", "Package_QFP:LQFP-48_7x7mm_P0.5mm", (340, 180),
         {str(n): net for n, net in MCU.items()},
         fields={"Manufacturer": "NXP", "MPN": "MKE16Z64VLF4",
                 "Description": f"Kinetis KE16Z, Cortex-M0+ 48 MHz, 64 KB flash, 8 KB SRAM, MSCAN, LQFP-48 ({DS})"}),
    cap("C7", "100n", "+3V3", "GND", (290, 270), f"Capacitor 100 nF 16 V X7R 0402 (CDEC, VDD pin 7 to VSS/VREFL pin 10, {DS} Figure 8, Table 26)"),
    cap("C8", "100n", "+3V3", "GND", (305, 270), f"Capacitor 100 nF 16 V X7R 0402 (CDEC, VDDA pin 8, {DS} Figure 8, Table 26)"),
    cap("C9", "100n", "+3V3", "GND", (320, 270), f"Capacitor 100 nF 16 V X7R 0402 (CDEC, VDD pin 31 / VSS pin 30, {DS} Figure 8, Table 26)"),
    cap("C10", "10u", "+3V3", "GND", (335, 270), f"Capacitor 10 uF 16 V X5R 0805 (bulk, 10 uF or more at the entrance of the 3.3 V supply, {DS} 6.1.2)", C0805),
    cap("C11", "100n", "VREFH", "GND", (290, 300), f"Capacitor 100 nF 16 V X7R 0402 (CREF, VREFH pin 9 to VREFL, {DS} Figure 8, Table 26)"),
    cap("C12", "10n", "VREFH", "GND", (305, 300), f"Capacitor 10 nF 50 V X7R 0402 (VREFH, in parallel with CREF for improved ADC performance, {DS} Table 26 note 1)"),
    cap("C13", "1n", "VREFH", "GND", (320, 300), f"Capacitor 1 nF 50 V C0G 0402 (VREFH, in parallel with CREF for improved ADC performance, {DS} Table 26 note 1)"),
    Part("JP1", "Jumper:SolderJumper_3_Bridged12", "VREFH", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         (350, 300), {"A": "+3V3", "C": "VREFH", "B": "AREF"},
         fields={"Description": f"VREFH source: 1-2 (as delivered) VDDA (3.3 V); cut and bridge 2-3 for the AREF pin (2.5 V to VDDA + 0.1 V, {DS} Table 50)"}),

    # ---- 8 MHz crystal (low-power mode, no RF, no RS) --------------------------------------------------
    Part("Y1", "Device:Crystal_GND24", "8MHz", "Crystal:Crystal_SMD_5032-4Pin_5.0x3.2mm", (430, 92),
         {"1": "XTAL", "3": "EXTAL", "2": "GND", "4": "GND"},
         fields={"Manufacturer": "ECS Inc.", "MPN": "ECS-80-10-30B-CWN-TR",
                 "Description": "Crystal 8 MHz, CL 10 pF, ESR 100 ohm max, C0 5 pF max, 100 uW max, 5.0 x 3.2 mm (ECS ECX-53B)"}),
    cap("C14", "11p", "EXTAL", "GND", (412, 108), "Capacitor 11 pF 50 V C0G 0402 (EXTAL load: 2 x 10 pF - 9 pF strays, AN3208 section 5)"),
    cap("C15", "11p", "XTAL", "GND", (448, 108), "Capacitor 11 pF 50 V C0G 0402 (XTAL load: 2 x 10 pF - 9 pF strays, AN3208 section 5)"),

    # ---- Reset, NMI ---------------------------------------------------------------------------------------
    res("R10", "10k", "RESET", "+3V3", (420, 140), f"Resistor 10 kohm 1% 0402 (RESET_b pull-up, 4.7-10 kohm, {DS} 6.1.4 Figure 27)", rot=90),
    cap("C16", "100n", "RESET", "GND", (435, 140), f"Capacitor 100 nF 16 V X7R 0402 (RESET_b filter, 0.1 uF recommended, {DS} 6.1.4 Figure 27)"),
    button("SW1", "RESET", "RESET", (455, 150), "reset (RESET_b)"),
    res("R11", "10k", "NMI", "+3V3", (475, 140), f"Resistor 10 kohm 1% 0402 (NMI_b pull-up, no capacitor, {DS} 6.1.4 Figure 29)", rot=90),

    # ---- SWD ------------------------------------------------------------------------------------------------
    Part("J2", "Connector:Conn_ARM_JTAG_SWD_10", "SWD", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
         (505, 100), {"VTref": "+3V3", "SWDIO/TMS": "SWDIO", "GND": "GND", "SWCLK/TCK": "SWCLK",
                      "SWO/TDO": NC, "KEY": NC, "NC/TDI": NC, "GNDDetect": "GND", "~{RESET}": "RESET"},
         fields={"Manufacturer": "Samtec", "MPN": "FTSH-105-01-L-DV-K",
                 "Description": f"Arm Cortex Debug 10-pin, 1.27 mm: SWD_DIO PTA4, SWD_CLK PTC4, RESET_b (replaces OpenSDA; {DS} Figure 30)"}),
    res("R12", "10k", "SWDIO", "+3V3", (490, 135), f"Resistor 10 kohm 1% 0402 (SWD_DIO pull-up, {DS} 6.1.4 Figure 30)", rot=90),
    res("R13", "10k", "SWCLK", "GND", (510, 135), f"Resistor 10 kohm 1% 0402 (SWD_CLK pull-down, {DS} 6.1.4 Figure 30)", rot=90),
    cap("C17", "100n", "+3V3", "GND", (528, 135), f"Capacitor 100 nF 16 V X7R 0402 (SWD header VDD, {DS} 6.1.4 Figure 30)"),

    # ---- User buttons ----------------------------------------------------------------------------------------
    button("SW2", "USER1", "BTN1", (430, 345), "user 1 (PTD5)"),
    button("SW3", "USER2", "BTN2", (470, 345), "user 2 (PTE3)"),
    res("R14", "10k", "BTN1", "+3V3", (415, 335), f"Resistor 10 kohm 1% 0402 (user button pull-up; port pulls off at reset, {DS} Table 6)", rot=90),
    res("R15", "10k", "BTN2", "+3V3", (455, 335), f"Resistor 10 kohm 1% 0402 (user button pull-up; port pulls off at reset, {DS} Table 6)", rot=90),

    # ---- RGB LED, switched from 5 V --------------------------------------------------------------------------
    Part("D3", "Device:LED_ABRG", "RGB", "LED_SMD:LED_RGB_Wuerth-PLCC4_3.2x2.8mm_150141M173100", (450, 225),
         {"A": "+5V", "BK": "RGB_BK", "RK": "RGB_RK", "GK": "RGB_GK"},
         fields={"Manufacturer": "Wurth Elektronik", "MPN": "150141M173100",
                 "Description": f"RGB LED common anode, PLCC4 3.2 x 2.8 mm: VF 2.0 / 3.2 / 3.2 V typ at 20 mA ({WE})"}),
    res("R16", "560", "RGB_RK", "RGB_RD", (420, 247), f"Resistor 560 ohm 1% 0402 (red: (4.65 V - 2.0 V) / 560 ohm = 4.7 mA, {WE} VF)", rot=90),
    res("R17", "300", "RGB_GK", "RGB_GD", (450, 247), f"Resistor 300 ohm 1% 0402 (green: (4.65 V - 3.2 V) / 300 ohm = 4.8 mA, {WE} VF)", rot=90),
    res("R18", "300", "RGB_BK", "RGB_BD", (480, 247), f"Resistor 300 ohm 1% 0402 (blue: (4.65 V - 3.2 V) / 300 ohm = 4.8 mA, {WE} VF)", rot=90),
    nfet("Q1", "LED_R", "RGB_RD", (425, 270), "red"),
    nfet("Q2", "LED_G", "RGB_GD", (455, 270), "green"),
    nfet("Q3", "LED_B", "RGB_BD", (485, 270), "blue"),
    res("R19", "100k", "LED_R", "GND", (408, 280), f"Resistor 100 kohm 1% 0402 (Q1 gate held low while PTD1 is analog after reset, {RM} 17.2.2)", rot=90),
    res("R20", "100k", "LED_G", "GND", (438, 280), f"Resistor 100 kohm 1% 0402 (Q2 gate held low while PTC2 is analog after reset, {RM} 17.2.2)", rot=90),
    res("R21", "100k", "LED_B", "GND", (468, 280), f"Resistor 100 kohm 1% 0402 (Q3 gate held low while PTC3 is analog after reset, {RM} 17.2.2)", rot=90),

    # ---- Shield headers, I2C pull-ups, extra I/O header -----------------------------------------------------------
    socket("J3", 10, "D8-SCL", ["D8", "D9", "D10", "D11", "D12", "D13", "GND", "AREF", "SDA", "SCL"], (545, 90),
           "Socket 1x10 2.54 mm, Uno R3 digital D8-D13, GND, AREF, SDA, SCL (pin 1 = D8), 3.3 V logic"),
    socket("J4", 8, "D0-D7", ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7"], (545, 135),
           "Socket 1x8 2.54 mm, Uno R3 digital D0-D7 (pin 1 = D0), 3.3 V logic"),
    socket("J5", 8, "POWER", [NC, "+3V3", "RESET", "+3V3", "+5V", "GND", "GND", NC], (580, 90),
           "Socket 1x8 2.54 mm, Uno R3 power: NC, IOREF (3.3 V), RESET, 3V3, 5V, GND, GND, VIN (not connected)"),
    socket("J6", 6, "A0-A5", ["A0", "A1", "A2", "A3", "A4", "A5"], (580, 135),
           "Socket 1x6 2.54 mm, Uno R3 analog A0-A5 (pin 1 = A0), 0-3.3 V; A4/A5 are not SDA/SCL here"),
    res("R22", "4.7k", "SDA", "+3V3", (493, 172), "Resistor 4.7 kohm 1% 0402 (SDA pull-up: Rp(min) 1.04 kohm, fast mode to 75 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    res("R23", "4.7k", "SCL", "+3V3", (513, 172), "Resistor 4.7 kohm 1% 0402 (SCL pull-up: Rp(min) 1.04 kohm, fast mode to 75 pF, TI SLVA689A Eq. 1 and 6)", rot=90),
    Part("J7", "Connector_Generic:Conn_02x06_Odd_Even", "EXT", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
         (550, 210), {"1": "+3V3", "2": "GND", "3": "EXT_PTE4", "4": "EXT_PTE5", "5": "EXT_PTD6", "6": "EXT_PTD7",
                      "7": "EXT_PTE10", "8": "EXT_PTC5", "9": "EXT_PTE8", "10": "EXT_PTE11", "11": "EXT_PTE2",
                      "12": "GND"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-106-07-G-D",
                 "Description": "Header 2x6 2.54 mm, extra I/O: 3V3, GND, PTE4 CAN0_RX, PTE5 CAN0_TX, PTD6 LPUART2_RX, "
                                "PTD7 LPUART2_TX, PTE10 CLKOUT, PTC5 RTC_CLKOUT, PTE8 ACMP0_IN3, PTE11, PTE2, GND"}),
]
for i, label in enumerate(["top left", "bottom left", "right, upper", "right, lower"]):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole", "M3", HOLE, (60 + 20 * i, 395), {},
                      side="B" if i == 0 else "F",
                      fields={"Description": f"Mounting hole 3.2 mm, unplated, Uno R3 position ({label}), Arduino A000066 section 5.4"}))

# Board placement: (x, y, rotation) in mm, origin top-left. Shield headers and holes where the Uno R3
# drawings put them. USB-C on the left edge with its ESD part, CC resistors, fuse and Schottky (DS
# 6.1.1: connectors on one edge, TVS at the connector), the CP2102N beside it. The MCU sits under the
# digital headers with its analog pins (right side, bottom) facing the analog header. Its 3.3 V and
# VREFH capacitors sit in two rows by pins 7-10, with the VREFH jumper and the 10 uF bulk beyond
# them; the crystal below them, by EXTAL/XTAL (pins 11/12). The SWD header, reset button and reset
# parts are top left of the chip, by PTA4/PTC4/PTA5; the LDO and power LED on the left edge. The RGB
# LED and its switches, the extra I/O header and the user buttons are below and left of the chip,
# where their lines run nowhere near the crystal; the column right of the chip is left to the
# analog lines on their way down to A1-A5.
MCU_AT = (44.0, 25.0)
PLACEMENT = {
    "J3": (D8_PIN[0], D8_PIN[1], 270), "J4": (D0_PIN[0], D0_PIN[1], 270),
    "J5": (POWER_PIN[0], POWER_PIN[1], 90), "J6": (A0_PIN[0], A0_PIN[1], 90),
    **{f"H{i + 1}": (x, y, 0) for i, (x, y) in enumerate(HOLES)},
    "U4": (MCU_AT[0], MCU_AT[1], 0),
    # USB-C, ESD, CC resistors, fuse, Schottky, bleed. The ESD part's D+/D- column (pins 3, 2) faces
    # away from the receptacle, so the pair passes between its VBUS and GND pins into pins 3 and 2
    "J1": (USB_C_EDGE, 12.0, 270), "U1": (12.0, 12.0, 90), "R1": (9.6, 5.9, 0), "R2": (9.6, 18.1, 0),
    "F1": (13.0, 7.0, 0), "D1": (18.0, 7.0, 180), "R5": (10.5, 16.4, 90),
    # CP2102N with D+/D- (pins 4, 5) level with the receptacle's A6/A7. Its four capacitors stand in one
    # row below VDD pin 6 and VREGIN pin 7, the 100 nF ones nearest, all with the 3.3 V pad on top: the
    # 3.3 V line runs along the row's top and stops at the last one, so it walls nothing in, and every
    # ground end faces down into one open stretch of ground. The VBUS divider sits below that stretch,
    # so the sense line from pin 8 runs round the outside of it rather than under a capacitor (a ground
    # pad between that line and a 3.3 V line is an island the pour cannot reach). RSTb's pull-up below
    # pin 9; the UART resistors above TXD/RXD
    "U2": (18.6, 11.5, 0), "C4": (17.75, 14.8, 270), "C6": (16.8, 14.8, 270), "C5": (15.35, 15.0, 270),
    "C3": (13.38, 15.4, 270), "R4": (19.15, 14.9, 270), "R6": (12.6, 19.41, 0), "R7": (14.0, 18.9, 90),
    "R8": (21.6, 7.5, 0), "R9": (21.6, 8.7, 180),
    # LDO and power LED
    "U3": (7.0, 28.0, 0), "C1": (4.0, 22.6, 0), "C2": (4.0, 33.4, 0), "D2": (9.0, 35.5, 0), "R3": (9.0, 37.2, 0),
    # SWD header and its pulls; RESET_b's 100 nF and pull-up just above-left of pin 47; reset button
    "J2": (30.0, 12.0, 0), "C17": (24.2, 10.0, 90), "R12": (36.2, 9.6, 0), "R13": (36.2, 10.9, 0),
    "C16": (38.6, 18.8, 180), "R10": (38.6, 17.6, 180), "SW1": (27.5, 20.0, 0),
    # MCU left, a ladder: the 3.3 V line from pins 7/8 to C8, C7, JP1's 3.3 V pad and the 10 uF bulk,
    # with the 100 nF capacitors hanging above it; below it the VREFH line from pin 9 through C13, C12
    # and C11 (smallest first) to JP1's middle pad, their ground ends on a line from VSS pin 10; JP1's
    # AREF pad below, leaving to the left. The pins 1-6 keep 2.7 mm in front of them for their escapes.
    "C8": (35.8, 24.6, 90), "C7": (34.8, 24.6, 90),
    "C13": (36.3, 26.8, 270), "C12": (35.3, 26.8, 270), "C11": (34.3, 26.8, 270),
    "JP1": (32.3, 26.25, 270), "C10": (29.6, 24.5, 90),
    # crystal below the VREFH capacitors, its courtyard 1 mm from the MCU's: EXTAL pad (3) top left,
    # reached over the top; XTAL pad (1) bottom right, reached down the gap beside the MCU; C14 beside
    # the EXTAL pad, C15 below the XTAL pad
    "Y1": (35.7, 30.9, 90), "C14": (32.6, 29.25, 180), "C15": (36.7, 34.85, 270),
    # MCU right: VDD pin 31, NMI pull-up, I2C pull-ups
    "C9": (50.9, 25.0, 270), "R11": (51.2, 23.0, 90), "R22": (52.5, 20.5, 0), "R23": (52.5, 19.2, 0),
    # RGB LED and its switches under the MCU: blue, green, red left to right, in the order their
    # pins (17, 18, and 1 by way of the chip's underside) arrive
    "Q3": (40.2, 37.4, 0), "Q2": (45.15, 37.4, 0), "Q1": (50.05, 37.4, 0),
    "R21": (37.75, 37.4, 270), "R20": (42.7, 37.4, 270), "R19": (47.6, 37.4, 270),
    "R18": (41.14, 40.5, 90), "R17": (48.9, 40.3, 0), "R16": (50.99, 41.2, 90), "D3": (45.1, 41.0, 180),
    # extra I/O header along the bottom, under the bottom-side pins three of its lines come from
    "J7": (38.0, 47.0, 90),
    # user buttons, lower left
    "SW2": (20.5, 44.5, 0), "SW3": (27.0, 44.5, 0), "R14": (20.5, 41.4, 0), "R15": (27.0, 41.4, 0),
}

# Laid before the autorouter, in this order, and locked (pcb_build.py): Freerouting gives a different
# result on every run, so what the layout guidance asks for is not left to it.
# The USB pair (KLQRUG 9.6.3), D+ then D- for each segment: from the receptacle's A6/A7 through the
# ESD part's pads to the CP2102N, on the top layer. A6 (D+) is above A7 (D-), as pin 4 (D+) is above
# pin 5 at the far end, so the main lines do not cross. Then the second contacts: B7 (D-) joins A7
# behind the pads, under the shell; B6 (D+) can then only reach A6's line through two vias, the
# single crossing a USB-C pair needs, kept in the short stub.
PRIORITY = [(("J1", "A6"), ("U1", "3")), (("U1", "3"), ("U2", "4")),
            (("J1", "A7"), ("U1", "2")), (("U1", "2"), ("U2", "5")),
            (("J1", "B7"), ("J1", "A7"), "join"), (("J1", "B6"), ("J1", "A6"), "join")]
# The CP2102N's VBUS sense (pin 8, beside VREGIN) to its divider before the decoupling ladder below
# closes that side of the chip: left to the router, it was boxed in at the pin.
PRIORITY += [(("U2", "8"), ("R7", "1"))]
# The crystal (KLQRUG 2.1.3.3.1): Y1's ground pads joined under its body first, which also closes the
# gap between its pads to anything else; then pin -> crystal pad -> load capacitor for EXTAL and XTAL
# on the top layer; then the load capacitors' ground ends to Y1's ground.
PRIORITY += [(("Y1", "2"), ("Y1", "4")),
             (("U4", "11"), ("Y1", "3")), (("Y1", "3"), ("C14", "1")),
             (("U4", "12"), ("Y1", "1")), (("Y1", "1"), ("C15", "1")),
             (("C14", "2"), ("Y1", "4")), (("Y1", "4"), ("C15", "2"))]
# Decoupling (DS 6.1.2, Table 26; CP Figure 2.3), each capacitor joined to its own pin: the 3.3 V
# ladder (pins 7 and 8 joined, then C8, C7, JP1 pad 1, C10); the VREFH ladder (pin 9, C13, C12, C11,
# JP1 pad 2) with VSS pin 10 to their ground ends; the CP2102N's VDD and VREGIN pads to each other and
# to their 100 nF and 4.7 uF capacitors along the row's top, with the four ground ends joined along its
# bottom; RESET_b to C16 and R10; the LDO's OUT and IN to C2 and C1.
PRIORITY += [(("U4", "7"), ("U4", "8")), (("U4", "8"), ("C8", "1")), (("C8", "1"), ("C7", "1")),
             (("C7", "1"), ("JP1", "1")), (("JP1", "1"), ("C10", "1")),
             (("U4", "9"), ("C13", "1")), (("C13", "1"), ("C12", "1")), (("C12", "1"), ("C11", "1")),
             (("C11", "1"), ("JP1", "2")),
             (("U4", "10"), ("C13", "2")), (("C13", "2"), ("C12", "2")), (("C12", "2"), ("C11", "2")),
             (("U2", "6"), ("U2", "7")), (("U2", "7"), ("C4", "1")), (("U2", "6"), ("C6", "1")),
             (("C6", "1"), ("C5", "1")), (("C5", "1"), ("C3", "1")),
             (("C4", "2"), ("C6", "2")), (("C6", "2"), ("C5", "2")), (("C5", "2"), ("C3", "2")),
             (("U4", "47"), ("C16", "1")), (("C16", "1"), ("R10", "1")),
             (("U3", "3"), ("C2", "1")), (("U3", "1"), ("C1", "1"))]

_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    # back: under the RGB LED's switches, whose courtyards keep the ground-stitching vias out
    # (pcb_build.stitch avoids front courtyards); line 2 sits between two rows of the 2.54 mm stitching grid
    {"text": "EoS KE16Z Board  rev A", "x": 45.0, "y": 35.9, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 45.0, "y": 37.9, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 45.0, "y": 39.3, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    # front: the USB-C port, the buttons, the SWD header and its pin 1, and the VREFH jumper's two sides
    {"text": "USB UART", "x": 4.3, "y": 5.4, "size": 1.0},
    {"text": "RESET", "x": 27.5, "y": 17.6, "size": 1.0},
    {"text": "USER1", "x": 20.5, "y": 47.4, "size": 1.0},
    {"text": "USER2", "x": 27.0, "y": 47.4, "size": 1.0},
    {"text": "SWD", "x": 30.0, "y": 7.9, "size": 1.0},
    {"text": "1", "x": 26.4, "y": 9.46, "size": 0.8},
    {"text": "3V3", "x": 32.3, "y": 23.3, "size": 0.8},
    {"text": "AREF", "x": 29.5, "y": 27.6, "size": 0.8},
]

BOARD = Board(
    name="eos-ke16z-board",
    title="EoS KE16Z Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["Uno R3 outline (2700 x 2100 mil) and shield header positions: Matthew Beckler, \"Arduino Uno R3\" "
             "dimension drawing v1.05, Wayne and Layne (wayneandlayne.com/files/common/arduino_uno_drawing.svg); "
             "facts only, no file copied",
             "Uno R3 mounting holes (4 x 3.20 mm) and pin order: Arduino UNO R3 product reference manual (SKU A000066), "
             "sections 5 and 5.4 (docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf); facts only",
             "Uno R3 header and hole positions cross-checked against KiCad 10's Module:Arduino_UNO_R3_WithMountingHoles "
             "footprint (KiCad libraries, CC BY-SA 4.0); positions only, the footprint is not used"],
    width=W,
    height=H,
    corner_radius=1.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "+5V", "VBUS", "VBUS_F", "VREFH"],
    priority_routes=PRIORITY,
    # the router necks a track to 0.1124 mm to enter a fine-pitch pad; finish() widens such necks to this
    # floor (0.0073 mm a side, inside the router's 0.01 mm extra clearance) and DRC enforces it, so no track
    # is under the 0.127 mm (5 mil) that low-cost two-layer fabs make
    rules={"min_track": 0.127},
    headings=[((35, 62), "USB-C, ESD, fuse, Schottky, VBUS bleed"), ((35, 165), "3.3 V LDO, power LED"),
              ((35, 230), "USB-UART: CP2102N on 3.3 V, VBUS sensed (R6, R7) and bled (R5)"),
              ((280, 62), "MKE16Z64VLF4"), ((280, 255), "Decoupling, VREFH (DS Figure 8, Table 26)"),
              ((400, 72), "8 MHz crystal (low-power mode)"), ((400, 125), "Reset and NMI (DS 6.1.4)"),
              ((480, 72), "SWD (DS Figure 30)"), ((400, 205), "RGB LED, switched from 5 V"),
              ((400, 320), "User buttons"), ((530, 62), "Uno R3 shield headers"), ((485, 160), "I2C pull-ups"),
              ((525, 190), "Extra I/O"), ((40, 382), "Mounting holes"), ((35, 352), "Power nets")],
    power_block=(40.64, 360.0),
    notes=[((260, 360), "EoS KE16Z Board, rev A. Designed by Kartikeydheer Srivastava. Fits Uno R3 shields; 3.3 V I/O.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Values from NXP KE1xZP48M48SF0 (data sheet) and KE1xZP48M48SF0RM, AN3208, AN1706, ST AN2867;\n"
                       "Silicon Labs CP2102N Rev. 1.5, Diodes DS37274 (AP7361C), Nexperia PMEG6010CEH, Littelfuse, Wurth, AOS.\n"
                       "Firmware: run the 8 MHz oscillator in low-power mode (HGO = 0): high-gain mode would\n"
                       "overdrive the crystal (AN3208 Eqn. 1), and RF must not be fitted (DS Table 40 note 3)."),
           ((400, 372), "Power: USB-C VBUS through F1 and D1 to the 5 V rail (LDO, RGB LED, 5V pin);\n"
                        "D1 keeps a shield's 5 V off the host. The CP2102N runs from 3.3 V and senses VBUS\n"
                        "(R6, R7); R5 bleeds D1's leakage off VBUS, so it connects only with a host present.")],
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS": "Power", "VBUS_F": "Power", "+5V": "Power", "+3V3": "Supply",
                  "USB_DP": "USB", "USB_DM": "USB"},
)
