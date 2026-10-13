"""EoS TM4C123 Board: a BoosterPack-compatible (40-pin) TM4C123GH6PM board, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-tm4c123-board/LICENSE.txt.

A 50.8 x 60 mm two-layer board for the TI TM4C123GH6PM (Arm Cortex-M4F, LQFP-64) that takes
40-pin BoosterPack plug-in modules ("BoosterPack-compatible" is nominative use: the board is not
a TI product). It does the job of TI's EK-TM4C123GXL but is drawn from the chip makers'
documents only: no design file of TI's (schematic, layout, CAD, Gerbers, BOM) was opened.
Sources:

* TI SPMS376E, "Tiva TM4C123GH6PM Microcontroller Data Sheet" (June 12, 2014): "the data sheet".
* TI SPMA059, "System Design Guidelines for the TM4C123x Family" (October 2013): "SPMA059".
* TI "BoosterPack Pinout Standard" (updated Sept 1, 2013, ti.com/jp/ww/launchpad/dl/
  boosterpack-pinout.pdf), and the 40-pin figure of TI's "BoosterPack Standards and Design
  Guide" (processors.wiki.ti.com, archived 2017-11-03) for the header numbering.

BoosterPack headers (facts from those two documents, used as positions and signal names only).
All holes on a 0.1 in grid; the outer headers J1 and J2 are 1.8 in (45.72 mm) apart, the inner
J3 and J4 1.6 in apart, each 0.1 in inside its outer header, all four with pin 1 level at the
top. J1 runs 1-10 and J3 21-30 downwards; J2 runs 20 down to 11 and J4 40 down to 31. A
BoosterPack is 2.0 in wide, reaches 350 mil above pin 1 and should end 0.15 in below the last
pin, so the board is 50.8 mm wide with the headers centred; under the BoosterPack sit only low
parts (the tallest a SOT-223), while the jumper, the debug header, the buttons and the LEDs are
outside it. The
two 2x10 parts here are J1 (columns J1 and J3) and J2 (columns J4 and J2); no other part takes
the names J3 or J4. Standard signal, then the TM4C123GH6PM pin chosen for it (data sheet Table
10-2, GPIOPCTL encodings):

  J1:  1 3.3 V | 2 analog PB5/AIN11 | 3 UART RX PB0/U1Rx | 4 UART TX PB1/U1Tx | 5 GPIO PD6 |
       6 analog PE4/AIN9 | 7 SPI CLK PA2/SSI0Clk | 8 GPIO PB6 | 9 I2C SCL PD0/I2C3SCL |
       10 I2C SDA PD1/I2C3SDA
  J3:  21 5 V | 22 GND | 23 PB4/AIN10 | 24 PE5/AIN8 | 25 PD2/AIN5 | 26 PD3/AIN4 |
       27 PE3/AIN0 | 28 PE2/AIN1 (23-28 analog) | 29, 30 reserved: not connected
  J2:  20 GND | 19 PWM PA6/M1PWM2 | 18 SPI CS (wireless) PA3/SSI0Fss | 17 GPIO** PF0 |
       16 RST | 15 SPI MOSI PA5/SSI0Tx | 14 SPI MISO PA4/SSI0Rx | 13 SPI CS (display) PE1 |
       12 SPI CS (other) PB7 | 11 GPIO PF4
  J4:  40 PWM PF3/M1PWM7 | 39 PWM PF2/M1PWM6 | 38 PWM PF1/M1PWM5 | 37 PWM PA7/M1PWM3 |
       36 capture PC4/WT0CCP0 | 35 capture PC5/WT0CCP1 | 34 PC6 | 33 PC7 | 32 PD7 | 31 PE0

The pins were picked by side of the package so that most lines run straight across: the chip
is turned 90 degrees, its PB4-PB5/PD0-PD3/PE4-PE5 side facing J1/J3 and its PA/PF side facing
J4/J2. The 2013 standard marks J3.29 and J3.30 "reserved", so they stay open; PB2 is the one
spare GPIO and is not connected. Every TM4C123GH6PM GPIO is interrupt-capable, as the standard's
"(!)" pins require. PF0 (J2.17, the standard's de-prioritised "GPIO**") and PD7 (J4.32) come
out of reset locked, being NMI-capable (data sheet Table 10-1): firmware writes 0x4C4F434B to
GPIOLOCK (offset 0x520) and sets the pin's bit in GPIOCR (offset 0x524) of port F (APB base
0x40025000) or port D (0x40007000) before GPIODEN/GPIOPUR take effect (section 10.2.4). PB0,
PB1 and PE3 need a 1-10 kohm external pull-up when used as inputs (Table 24-31): PB0 and PB1
(the UART) get 4.7 kohm here; PE3 is offered as AIN0, and a BoosterPack using it as a digital
input must pull it up. PB0, PB1, PD4 and PD5 are not 5 V tolerant (section 10.1).

Every value follows a datasheet:

* Supply (SPMA059 3.5): a single 3.3 V rail on VDD and VDDA (VDD 3.15-3.63 V, data sheet Table
  24-5). 0.1 uF at each VDD pin (11, 26, 42, 54; SPMA059 3.5.3: "one decoupling capacitor
  adjacent to each VDD power and ground pin pair"): C1 is joined straight to VDD pin 11 and GND
  pin 12 before the autorouter runs, C3 sits straight above pin 42 (1.3 mm of track), and pin 42 is
  joined to pin 11 under the chip, inside the pad ring, since the USB pair and the oscillator lines
  close it in outside; VDDA on the VDD net with 1 uF and 0.01 uF
  (SPMA059 Table 9, 64-pin LQFP); 10 uF bulk near the chip (combined VDD + VDDA bulk "typically
  between 2 uF and 22 uF"). X5R/X7R, 6.3-25 V parts (SPMA059 3.5.3).
* VDDC, the core LDO's filter: CLDO 2.5-4.0 uF with ESR 10-100 mohm, as close as possible to pin
  56 (data sheet Table 24-12). SPMA059 3.5.2 recommends 10 % ceramics totalling 3.3-3.4 uF, and
  for the 64-pin LQFP 2.2 uF, 1.0 uF and 0.1 uF closest to pin 56 and 0.1 uF at pin 25: 3.4 uF,
  3.06-3.74 uF at +-10 %, inside 2.5-4.0 uF. VDDC feeds nothing else (SPMA059 3.5.2 note).
* Main oscillator: NDK NX3225GA-16.000M-STD-CRG-2 (NDK NX3225GA sheet: CL 8 pF, ESR 80 ohm max
  for 13-20 MHz, drive 10 uW, 200 uW max). It is one of the crystals TI simulated (data sheet
  Table 24-19), which gives C1 = C2 = 12 pF and Rs = 2 kohm, worst-case drive 188 uW, below the
  crystal's 200 uW. Check against the data sheet's formula: CL = C1 C2 / (C1 + C2) + CSHUNT =
  6 + (C0 1.0 + CPKG 0.5 + CPCB 0.5) = 8 pF. 16 MHz needs ESR <= 100 ohm (Table 24-18). Rs sits
  between OSC1 and the crystal (Table 24-19 text). Pads 2 and 4 to ground (NDK: "better to
  connect with a GND"). USB needs this crystal: "MOSC must be the clock source" (section 18.3).
  Layout (SPMA059 3.7.2: "minimize both the loop area ... and the overall trace length", ideally
  under 6 mm, never over 18 mm; Rs "located between capacitor C2 and the OSC1 pin"): Rs sits
  straight above OSC1 (pin 41), the crystal above Rs with its pad 3 over it, C13 beside Rs and C12
  beside pad 1. Laid first, on the top layer with no via: OSC1 3.9 mm to Rs and 0.9 mm on to the
  crystal, OSC0 8.4 mm, up between the crystal's pads to pad 1; 0.8 mm or more from the USB pair.
* Hibernation oscillator: Abracon ABS07-32.768KHZ-T (ABS07 datasheet, revised 08-10-22: CL 12.5
  pF, ESR 70 kohm max at -40..+85 C, C0 2.0 pF max, drive 0.5 uW max). Data sheet Table 24-17:
  C1, C2 12-24 pF and CL = C1 C2 / (C1 + C2) + CPKG + CPCB with 0.5 + 0.5 pF nominal; SPMA059
  3.7.1.2 puts a typical design's stray at "approximately 2pF to 4pF" and gives C1 = C2 =
  (CL - 3 pF) x 2 (Eq. 5) = 19 pF, so 20 pF is fitted: CL 12-14 pF with 2-4 pF of stray, 11 pF
  with the data sheet's nominal 1 pF. Above 18 pF firmware sets OSCDRV (HIBCTL), which allows ESR
  up to 75 kohm, covering the crystal's 70 kohm; CSHUNT = 1.0 + 2.0 = 3.0 pF <= 4 pF; the
  oscillator's 0.25 uW drive is below the crystal's 0.5 uW. GNDX goes to ground with the load
  capacitors (Table 7-1). Measure the RTC against a reference and trim in firmware if needed.
* Hibernation: VBAT from 3.3 V through a BAT54J Schottky (Nexperia BAT54J, 1 October 2022: VF
  <= 240 mV at 0.1 mA), then RBAT = 51 ohm and CBAT = 0.1 uF next to pin 37 (data sheet Figures 7-2
  and 7-3; SPMA059 Figure 22). Their 5.1 us time constant keeps VBAT's rise under the 0.7 V/us
  VBATRMP limit of Table 24-25 even for a step: 3.1 V / 5.1 us = 0.6 V/us. VBAT is then about
  3.06-3.3 V with VDD at 3.3 V, inside
  1.8-3.6 V and a diode drop under VDD, which section 7.3.4 asks for ("ensure that VDD is higher
  than VBAT ... or else the Hibernation module draws power from the battery"). A diode, not a
  coin cell: the module keeps the RTC and battery-backed memory whenever USB power is present,
  in VDD3ON mode (section 7.3.3, Figure 7-3); the board carries no lithium cell to ship, replace
  or protect against reverse charging, and no 20 mm holder. Nothing survives unplugging, and
  HIB cannot switch the regulator off (VBAT would go with it), so HIB goes to a test point
  (TP1); SPMA059 4.10 allows it unconnected. WAKE: 1 Mohm pull-up to VBAT's supply and a button
  to ground (SPMA059 4.10; data sheet Figure 7-3 R_PU = 1 Mohm); assertion >= 100 ns (Table 24-26).
  The button reaches WAKE through 470 ohm (R32) placed at the pin, so the long line to the
  bottom-edge button is on the far side of a series resistor, as SPMA059 3.6 asks for a switch
  line (470 ohm, the RS value of data sheet Figure 5-3); pressed, WAKE reads 3.3 V x 470 / 1 M.
* Reset: data sheet Figure 5-3, "Reset circuit controlled by switch": RPU = 10 kohm, C1 = 10 nF
  at the pin, RS = 470 ohm in series with the button (SPMA059 3.6 asks for a series resistor
  too). C16 is 4.2 mm from pin 38 by its pre-laid line and RS 10.0 mm, both on the chip's side of the
  device USB pair, so the run to the bottom-edge button is RST_SW, behind 470 ohm and the 10 nF, not
  RST itself (SPMA059 3.6: keep the reset trace away from the board edge). RST also reaches the
  debug header and BoosterPack J2.16.
* USB ESD, both ports: an SP0503BAHTG at each connector (Littelfuse SP05xxBA datasheet: three
  channels, each a TVS to a common ground pin, 5.5 V standoff, <= 100 nA leakage at 5 V, 30 pF
  at 2.5 V), on VBUS, D+ and D-. It is the part the CP2102N data sheet shows on its USB pins
  (Figures 2.5 and 2.6), and SPMA059 4.1 asks for ESD suppressors at the connector. Unlike a
  rail-type array (a USBLC6, whose I/O diodes run to its VBUS pin), it has no path from D+ or D-
  into VBUS, so a D+ pull-up still on after a host leaves cannot hold VBUS up through it and hide
  the unplug from either chip's VBUS sense.
* USB device (data sheet chapter 18, SPMA059 4.1): USB0DP/USB0DM (PD5/PD4) straight to the
  connector through the SP0503BAHTG; the PHY has its own 1.5 kohm D+ pull-up, so no external
  resistors (18.2 note). Layout (SPMA059 4.1: ESD part "directly on the signal traces" and "as
  close as possible to the USB connector", "maintain symmetry", "avoid vias"): the pair is laid
  first, D+ then D-, from J6's B6/B7 through U3's pads (channels swapped, pin 3 D+ and pin 2 D-, so
  the lines do not cross) and down a channel 1 mm left of the chip's pins, 0.7 mm apart (0.5 mm
  gap), stepping right into pins 44/43 at the chip, on the top layer with no via. As laid: D+ 24.91
  mm and D- 24.82 mm from contact to pin. The second contacts join on the top layer too: A6 to B6
  (2.66 mm) behind A7, A7 to B7 (1.96 mm) in front of A6.
  USB-C sink: 5.1 kohm Rd on CC1 and CC2 (TI SLVSFJ9 section 10.3.14.2: "a sink exposes
  independent Rd terminations on its CC1 and CC2 pins", "Rd 5.1 kOhm"). VBUS sense: this board can
  power the MCU from the debug port while the device port is unplugged, which is a self-powered
  device, so firmware must watch VBUS on a GPIO and drop the D+ pull-up when it goes (section
  18.3). SPMA059 4.1.1 says PB1 is only 5 V tolerant once set up as USB0VBUS and asks for "an
  alternate 5-V tolerant Fail-Safe GPIO" when 5 V can arrive earlier, with 100 ohm in series
  against ESD. Here VBUS reaches PB3 through 10 kohm / 15 kohm: 5.5 V gives 3.3 V and 4.4 V gives 2.64 V,
  above VIH = 0.65 VDD = 2.36 V at VDD 3.63 V (Table 24-6), and the pin never sees 5 V even
  with the MCU unpowered, which section 24.13.1 limits to 10,000 hours in a device's life. So
  firmware runs the controller as a forced device (USBGPCS DEVMODOTG/DEVMOD, section 18.2 note)
  and reads PB3; PB0 and PB1 are free for the BoosterPack UART. The divider's 25 kohm to ground
  also bleeds VDEV: with no host, PB3 reads low (under VIL = 0.35 VDD = 1.16 V) unless something
  pushes over 77 uA into VDEV, and nothing on the board can (the ESD array leaks to ground, and
  JP1 joins VDEV to 5 V only when the device port is the supply).
* Debug: a 10-pin Cortex Debug header (SPMA059 Table 11) on PC0-PC3 (TCK/SWCLK, TMS/SWDIO, TDI,
  TDO/SWO) and RST, in place of TI's on-board ICDI, whose firmware is TI's: Samtec FTSH-105-01-
  L-DV-K, the keyed variant, so a reversed cable cannot short VTref to ground. The autorouter
  lays these lines; the last full build measured 34-42 mm, under the 2 in (51 mm) beyond which
  SPMA059 3.8 asks for an external TCK pull, so the internal pull-ups suffice. The next build's
  routed lengths must be checked against that limit again.
* USB-UART: CP2102N-A02-GQFN20 (Silicon Labs CP2102N data sheet Rev. 1.5) on UART0, PA0/PA1,
  the debug UART SPMA059 4.3 recommends. It runs from the board's 3.3 V with its own regulator
  unused (Figure 2.3: VREGIN tied to VDD, 3.0-3.6 V in), so it is powered whenever the MCU is and
  neither can drive the other's pins while unpowered: an unpowered CP2102N's RXD is rated only to
  VIO + 2.5 V (Table 3.10), 2.5 V with VIO at 0, which a 3.3 V TX would exceed. On this QFN-20
  part VIO is VDD. 4.7 uF and 0.1 uF on each power pin (VREGIN and VDD, tied together here): C23,
  0.1 uF, is the capacitor nearest pins 6 and 7 ("placed as close to the pins as possible", Figure
  2.3); C21, VREGIN's 0.1 uF, is reached through C22 and C20 and is not close. 1 kohm RSTb pull-up to VDD
  (section 2.1). Its USB pair is laid like the device pair: contacts A7 (D-) and A6 (D+), the ESD
  part's pads 3 and 2 inline, the CP2102N's pins 5 and 4, top layer, no via, 17.36 mm and 17.29 mm
  as laid. The CP2102N numbers D+ before D- counter-clockwise, so only the receptacle's middle
  contacts give the pair the order it needs; B6 joins A6 on the top layer behind A7, and B7, which
  cannot reach A7 without crossing D+, joins it through the bottom layer (two vias, 3.63 mm). TXD
  and RXD meet the MCU through 1 kohm each, which caps a fight between the
  two drivers (PA0 set as an output by mistake) at 3.3 mA; at the CP2102N's 3 Mbaud top rate the
  1 kohm and ~10 pF of pin load (8 pF GPIO, Table 24-29) make a 10 ns edge, 3 % of a bit.
  U0Tx has a 100 kohm pull-up (R33), so the CP2102N sees an idle line until the ROM boot loader
  drives it (data sheet section 8.2.2.1: "put a pull-up or pull-down on U0Tx ... A pull-up is
  preferred"). VBUS sense: the 22.1 kohm / 47.5 kohm divider of the self-powered Figure 2.6
  (the CP2102N runs from the board's 3.3 V, not from VBUS) from the debug port's VBUS, which
  section 2.3 requires: 5 V reads 3.41 V and 4.4 V reads 3.0 V, above VIH = VIO - 0.6 V = 2.7 V
  (Table 3.7). With the board powered from the device port and no debug host, the CP2102N must
  read that pin low, at or below VIL = 0.6 V (Table 3.7), or it would turn on its D+ pull-up with
  no host: the pin may rise to 0.6 V when VDBG reaches 0.6 x 69.6 / 47.5 = 0.88 V. A 5.1 kohm
  bleed (R31) from VDBG to ground puts 4.75 kohm in parallel with the divider, so up to 185 uA
  pushed into VDBG is harmless. Nothing on the board pushes that much: JP1 joins VDBG to the 5 V
  rail only when the debug port is the supply, the SP0503BAHTG leaks to ground (<= 100 nA), and
  there is no diode or power path from the 5 V rail or the other port into VDBG. With a host
  attached the bleed costs 1.0 mA (5 mW). If the debug host is plugged in while the board is
  unpowered, the divider feeds 3.41 V into an unpowered VBUS pin; the data sheet's section 2.3
  note accepts this: "the current limitation of the resistor divider prevents high VBUS pin
  leakage current, even though the VIO + 2.5 V specification is not strictly met while the
  device is not powered".
* Power: each USB-C port has a 500 mA polyfuse (Littelfuse 1206L050YR: 0.50 A hold, 1.00 A trip,
  6 V, revised 10/29/21); JP1 picks the 5 V source, 1-2 device port, 2-3 debug port. Either port
  can power the board, and JP1 takes one shunt, which bridges 1-2 or 2-3 but never 1-3, so one
  host can never feed the other. 5 V feeds BoosterPack J3.21 and the AP7361C-33 LDO (Diodes DS37274
  Rev. 5-2: 1 A, input 2.2-6.0 V, >= 1 uF in, >= 2.2 uF ceramic out; 4.7 uF each), which feeds
  the MCU, the CP2102N (9.5-13.7 mA, CP2102N Table 3.2), J1.1 and the debug header's VTref. At
  300 mA from 5 V it dissipates 0.51 W, 56 C above ambient at the SOT-223's 110 C/W, so 300 mA is
  the 3.3 V budget: the board itself takes up to about 72 mA (MCU 54.9 mA max at 80 MHz with every
  peripheral on, data sheet Table 24-41; CP2102N 13.7 mA; power LED 2.1 mA; LED bases 1 mA), which
  leaves about 225 mA for BoosterPacks on J1.1. With JP1 removed the board runs from 5 V on J3.21;
  with JP1 fitted, J3.21 is an output (as the BoosterPack standard has it) and must not be fed, or
  the 5 V would reach the selected host. J1.1 is always an output: fed with 3.3 V while 5 V is
  absent, it would put the LDO's OUT above IN + 0.3 V, its absolute maximum (DS37274 p. 4). The
  silkscreen says "J1.1, J3.21 = OUT". Not assessed: the attach inrush (4.7 uF on 5 V and about
  26 uF on 3.3 V behind the LDO, whose start-up is 150 us typical with 2.2 uF, DS37274 tST).
  Power LED: Kingbright APTD1608LCGCK (DSAO7432, VF 1.9 V typ, 2.1 V max at 2 mA) through 680
  ohm: (3.3 - 1.9) / 680 = 2.1 mA.
* RGB LED on PF1 (red), PF2 (blue), PF3 (green): Wurth 150141M173100 (WL-SFTW datasheet,
  2021-12-10: common anode pin 1, cathodes 2 blue, 3 red, 4 green; VF at 20 mA 2.0/2.4 V red,
  3.2/3.6 V green and blue, typ/max). Green and blue need up to 3.6 V, more than a 3.3 V pin can
  give (VOH >= 2.4 V, Table 24-6), so the anode is on 5 V and an MMBT3904 per colour sinks the
  cathode (onsemi MMBT3904LT1/D Rev. 14: hFE >= 70 at 1 mA, VCE(sat) <= 0.2 V, VBE(sat) <= 0.85
  V). Base 4.7 kohm from the pin, 47 kohm base-emitter: IB >= (2.4 - 0.85) / 4.7 k - 0.85 / 47 k
  = 0.31 mA. The LED current is under 5.25 V / 470 ohm = 11.2 mA even with no LED drop, so the
  forced gain stays under 36, below the 70 minimum, and the transistor saturates; with the pin floating at reset (<= 1 uA leakage, Table 24-29) the base
  sits under 0.05 V, so the LED stays dark. Cathode resistors from VF at 20 mA (an upper bound
  for these currents): red 1 kohm, (5.0 - 2.0 - 0.2) / 1 k = 2.8 mA; green 1 kohm, 1.6 mA (the
  green die is 3.5 times brighter, 950 against 270 mcd at 20 mA); blue 470 ohm, 3.4 mA. The pins
  also reach BoosterPack PWM positions: a BoosterPack sees the 4.7 kohm base load only.
* Buttons on PF4 and PF0 (to ground; firmware enables the internal 13-30 kohm pull-ups,
  Table 24-29). Both pins also go to the BoosterPack, so each button has 1 kohm in series: a
  BoosterPack driving the pin high into a pressed button sees 3.3 mA, and the pressed pin reads
  at most 3.3 x 1 / (1 + 13) = 0.24 V, under VIL = 0.35 VDD = 1.16 V (Table 24-6).

* BoosterPack headers: Samtec SSW-110-23-F-D, female with long male leads, the stackable part
  TI's BoosterPack Pinout Standard (Sept 1, 2013) p. 2 asks for ("All LaunchPads & BoosterPacks
  must use female headers with long male leads") and recommends. PA3 (SSI0Fss, J2.18) has a
  10 kohm pull-up (R34), as SPMA059 4.2 asks for on SSIxFSS, so a BoosterPack's SPI device sees
  no access before firmware has set the pins up.

Two layers: SPMA059 3.3.2 accepts two when no interface is timing-critical, the USB run to the
connector is short (about 25 mm here, straight) and power and ground are routed well; ground is
poured on both sides. 3.3 V and VDDC are 0.3 mm tracks, since they enter the 0.5 mm-pitch LQFP and
QFN pads.

Schematic symbol: KiCad 10 has no TM4C123GH6PM (only the USB-less TM4C1230/1231), so U1 uses
EoS_MCU:TM4C123GH6PM, drawn from the data sheet's Table 23-2 for this board (see the README).
"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
HDR = "Connector_PinHeader_2.54mm:PinHeader_"
KMR2 = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
DS = "TI SPMS376E"
GUIDE = "TI SPMA059"
RD = "TI SLVSFJ9 section 10.3.14.2: a sink exposes Rd = 5.1 kohm on CC1 and CC2"
STACK = "female, long male leads, as TI's BoosterPack Pinout Standard (Sept 1, 2013) p. 2 asks and recommends"
CP2102N = "Silicon Labs CP2102N data sheet Rev. 1.5"


def res(ref, value, a, b, sch, desc):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields={"Description": desc})


def cap(ref, value, a, b, sch, desc, fp=C0402, mpn=None):
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b},
                fields={"Description": desc, **({"Manufacturer": "Murata", "MPN": mpn} if mpn else {})})


def button(ref, value, a, sch, desc):
    return Part(ref, "Switch:SW_Push", value, KMR2, sch, {"1": a, "2": "GND"},
                fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": desc})


def usb_c(ref, prefix, sch, desc):
    return Part(ref, "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                sch, {"VBUS": f"VBUS_{prefix}", "GND": "GND", "CC1": f"{prefix}_CC1", "CC2": f"{prefix}_CC2",
                      "D+": f"{prefix}_D+", "D-": f"{prefix}_D-", "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
                fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12", "Description": desc})


def esd(ref, prefix, sch, swap=False):
    """SP0503BAHTG: pin 1 the common (ground), pins 2-4 one TVS each (Littelfuse SP05xxBA pinout).
    Pins 2, 3 and 4 are the same diode to the common anode, so ``swap`` puts D+ on pin 3 and D- on
    pin 2 where that keeps the pair from crossing."""
    dp, dm = ("3", "2") if swap else ("2", "3")
    return Part(ref, "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", sch,
                {"1": "GND", dp: f"{prefix}_D+", dm: f"{prefix}_D-", "4": f"VBUS_{prefix}"},
                fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                        "Description": "USB ESD, 3 TVS channels to ground (VBUS, D+, D-), 5.5 V standoff, at the connector; "
                                       f"no path from D+/D- into VBUS (Littelfuse SP05xxBA; {CP2102N} Figure 2.6)"})


def fuse(ref, a, b, sch, what):
    return Part(ref, "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", sch, {"1": a, "2": b},
                fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                        "Description": f"PTC fuse 0.50 A hold, 1.00 A trip, 6 V, 1206, {what} (Littelfuse 1206L)"})


def driver(n, colour, pin, cathode, r_led, sch_x):
    """One RGB channel: the GPIO drives an MMBT3904 through 4.7 kohm, 47 kohm holds it off at reset,
    and the cathode resistor sets the current from the 5 V anode supply."""
    q, base, col = f"Q{n}", f"Q{n}_B", f"Q{n}_C"
    vf = {"red": ("2.0", "2.8 mA"), "green": ("3.2", "1.6 mA"), "blue": ("3.2", "3.4 mA")}[colour]
    return [
        Part(q, "Transistor_BJT:MMBT3904", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", (sch_x, 325),
             {"B": base, "E": "GND", "C": col},
             fields={"Manufacturer": "onsemi", "MPN": "MMBT3904LT1G",
                     "Description": f"NPN, {colour} LED switch (onsemi MMBT3904LT1/D Rev. 14: hFE >= 70 at 1 mA)"}),
        res(f"R{19 + n}", "4.7k", pin, base, (sch_x - 15, 320),
            f"Resistor 4.7 kohm 1% 0402, {colour} base: >= 0.31 mA from VOH 2.4 V ({DS} Table 24-6), VBE(sat) 0.85 V"),
        res(f"R{22 + n}", "47k", base, "GND", (sch_x - 15, 340),
            f"Resistor 47 kohm 1% 0402, {colour} base pull-down: off while {pin} floats at reset"),
        res(f"R{25 + n}", r_led, cathode, col, (sch_x, 305),
            f"Resistor {r_led} ohm 1% 0402, {colour} LED: (5.0 - {vf[0]} - 0.2) / {r_led} = {vf[1]} "
            "(VF at 20 mA, Wurth 150141M173100)"),
    ]


W, H = 50.8, 60.0
ROW0 = 26.0                          # y of J1.1, J3.21, J4.40 and J2.20
J1_X, J2_X = 2.54, 48.26             # outer headers 1.8 in apart, centred on the 2.0 in board
MCU = (W / 2, ROW0 + 4.5 * 2.54)     # chip centred between the header rows

# BoosterPack signals by header pin (TI BoosterPack Pinout Standard, 2013).
J1_PINS = ["+3V3", "PB5", "PB0", "PB1", "PD6", "PE4", "PA2", "PB6", "PD0", "PD1"]     # J1.1 .. J1.10
J3_PINS = ["+5V", "GND", "PB4", "PE5", "PD2", "PD3", "PE3", "PE2", NC, NC]            # J3.21 .. J3.30
J4_PINS = ["PF3", "PF2", "PF1", "PA7", "PC4", "PC5", "PC6", "PC7", "PD7", "PE0"]      # J4.40 .. J4.31
J2_PINS = ["GND", "PA6", "PA3", "PF0", "RST", "PA5", "PA4", "PE1", "PB7", "PF4"]      # J2.20 .. J2.11

# TM4C123GH6PM LQFP-64 pins (data sheet Table 23-2), by number.
U1_NETS = {
    "1": "PB6", "2": "+3V3", "3": "GND", "4": "PB7", "5": "PF4", "6": "PE3", "7": "PE2", "8": "PE1", "9": "PE0",
    "10": "PD7", "11": "+3V3", "12": "GND", "13": "PC7", "14": "PC6", "15": "PC5", "16": "PC4",
    "17": "U0RX", "18": "U0TX", "19": "PA2", "20": "PA3", "21": "PA4", "22": "PA5", "23": "PA6", "24": "PA7",
    "25": "VDDC", "26": "+3V3", "27": "GND", "28": "PF0", "29": "PF1", "30": "PF2", "31": "PF3", "32": "WAKE",
    "33": "HIB", "34": "XOSC0", "35": "GND", "36": "XOSC1", "37": "VBAT", "38": "RST", "39": "GND", "40": "OSC0",
    "41": "OSC1", "42": "+3V3", "43": "DEV_D-", "44": "DEV_D+", "45": "PB0", "46": "PB1", "47": NC,
    "48": "VBUS_SENSE", "49": "SWO", "50": "TDI", "51": "SWDIO", "52": "SWCLK", "53": "PD6", "54": "+3V3",
    "55": "GND", "56": "VDDC", "57": "PB5", "58": "PB4", "59": "PE4", "60": "PE5", "61": "PD0", "62": "PD1",
    "63": "PD2", "64": "PD3",
}

PARTS = [
    # ---- TM4C123GH6PM -----------------------------------------------------------------------------
    Part("U1", "EoS_MCU:TM4C123GH6PM", "TM4C123GH6PM", "Package_QFP:LQFP-64_10x10mm_P0.5mm", (300, 210), U1_NETS,
         fields={"Manufacturer": "Texas Instruments", "MPN": "TM4C123GH6PMI",
                 "Description": f"Arm Cortex-M4F MCU, 80 MHz, 256 kB flash, USB 2.0 FS, LQFP-64 ({DS}); "
                                "pin 47 (PB2) is the spare GPIO, left open (Table 23-7: NC acceptable)"}),
    cap("C1", "100n", "+3V3", "GND", (360, 120), f"Capacitor 100 nF X7R 16 V 0402, VDD pin 11, joined to pins 11 and 12 "
        f"first ({GUIDE} 3.5.3: adjacent to each VDD and ground pin pair)", mpn="GRM155R71C104KA88D"),
    cap("C2", "100n", "+3V3", "GND", (372.7, 120), f"Capacitor 100 nF X7R 16 V 0402, VDD pin 26 ({GUIDE} 3.5.3)",
        mpn="GRM155R71C104KA88D"),
    cap("C3", "100n", "+3V3", "GND", (385.4, 120), f"Capacitor 100 nF X7R 16 V 0402, VDD pin 42, straight above it ({GUIDE} 3.5.3)",
        mpn="GRM155R71C104KA88D"),
    cap("C4", "100n", "+3V3", "GND", (398.1, 120), f"Capacitor 100 nF X7R 16 V 0402, VDD pin 54 ({GUIDE} 3.5.3)",
        mpn="GRM155R71C104KA88D"),
    cap("C5", "1u", "+3V3", "GND", (410.8, 120), f"Capacitor 1 uF X7R 16 V 0603, VDDA pin 2 ({GUIDE} Table 9, 64-pin LQFP)",
        C0603, mpn="GRM188R71C105KA12D"),
    cap("C6", "10n", "+3V3", "GND", (423.5, 120), f"Capacitor 10 nF X7R 50 V 0402, VDDA pin 2 ({GUIDE} Table 9)",
        mpn="GRM155R71H103KA88D"),
    cap("C11", "10u", "+3V3", "GND", (436.2, 120), f"Capacitor 10 uF X5R 10 V 0805, VDD/VDDA bulk: 2-22 uF ({GUIDE} 3.5.3)",
        C0805, mpn="GRM21BR61A106KE19L"),
    cap("C7", "2.2u", "VDDC", "GND", (360, 150), f"Capacitor 2.2 uF X7R 10 V 10% 0603, VDDC, closest to pin 56 ({DS} "
        f"Table 24-12 CLDO 2.5-4.0 uF; {GUIDE} 3.5.2)", C0603, "GRM188R71A225KE15D"),
    cap("C8", "1u", "VDDC", "GND", (372.7, 150), f"Capacitor 1 uF X7R 16 V 10% 0603, VDDC at pin 56 ({GUIDE} 3.5.2)",
        C0603, mpn="GRM188R71C105KA12D"),
    cap("C9", "100n", "VDDC", "GND", (385.4, 150), f"Capacitor 100 nF X7R 16 V 10% 0402, VDDC at pin 56 ({GUIDE} 3.5.2)",
        mpn="GRM155R71C104KA88D"),
    cap("C10", "100n", "VDDC", "GND", (398.1, 150), f"Capacitor 100 nF X7R 16 V 10% 0402, VDDC at pin 25 ({GUIDE} 3.5.2)",
        mpn="GRM155R71C104KA88D"),

    # ---- Oscillators --------------------------------------------------------------------------------
    Part("Y1", "Device:Crystal_GND24", "16MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", (380, 190),
         {"1": "OSC0", "3": "OSC1_X", "2": "GND", "4": "GND"},
         fields={"Manufacturer": "NDK", "MPN": "NX3225GA-16.000M-STD-CRG-2",
                 "Description": f"Crystal 16 MHz, CL 8 pF, ESR 80 ohm max, 3.2 x 2.5 mm; simulated by TI ({DS} Table 24-19)"}),
    res("R12", "2.0k", "OSC1", "OSC1_X", (400, 180), f"Resistor 2.0 kohm 1% 0402, Rs between OSC1 and Y1 ({DS} Table 24-19 "
        "for NX3225GA-16.000M-STD-CRG-2)"),
    cap("C12", "12p", "OSC0", "GND", (365, 205), f"Capacitor 12 pF C0G 50 V 5% 0402, OSC0 load ({DS} Table 24-19)",
        mpn="GRM1555C1H120JA01D"),
    cap("C13", "12p", "OSC1_X", "GND", (395, 205), f"Capacitor 12 pF C0G 50 V 5% 0402, OSC1 load ({DS} Table 24-19)",
        mpn="GRM1555C1H120JA01D"),
    Part("Y2", "Device:Crystal_Small", "32.768kHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", (380, 235),
         {"1": "XOSC0", "2": "XOSC1"},
         fields={"Manufacturer": "Abracon", "MPN": "ABS07-32.768KHZ-T",
                 "Description": "Crystal 32.768 kHz, CL 12.5 pF, ESR 70 kohm max, 3.2 x 1.5 mm (Abracon ABS07); "
                                "firmware sets OSCDRV"}),
    cap("C14", "20p", "XOSC0", "GND", (365, 250), f"Capacitor 20 pF C0G 50 V 5% 0402, XOSC0 load: (12.5 - 3) x 2 = 19 pF "
        f"({GUIDE} 3.7.1.2 Eq. 5), above 18 pF so OSCDRV = 1 ({DS} Table 24-17)", mpn="GRM1555C1H200JA01D"),
    cap("C15", "20p", "XOSC1", "GND", (395, 250), f"Capacitor 20 pF C0G 50 V 5% 0402, XOSC1 load ({GUIDE} 3.7.1.2 Eq. 5; "
        f"{DS} Table 24-17)", mpn="GRM1555C1H200JA01D"),

    # ---- Reset, hibernation -------------------------------------------------------------------------
    res("R13", "10k", "RST", "+3V3", (420, 180), f"Resistor 10 kohm 1% 0402, RST pull-up ({DS} Figure 5-3)"),
    cap("C16", "10n", "RST", "GND", (432.7, 180), f"Capacitor 10 nF X7R 50 V 0402, RST, at the pin ({DS} Figure 5-3)",
        mpn="GRM155R71H103KA88D"),
    res("R14", "470", "RST", "RST_SW", (445.4, 180), f"Resistor 470 ohm 1% 0402, in series with the reset button, at the "
        f"chip end of the button line, 10 mm from pin 38 ({DS} Figure 5-3; {GUIDE} 3.6)"),
    button("SW1", "RESET", "RST_SW", (460, 185), "Tactile switch, reset (RST through 470 ohm)"),
    Part("D3", "Diode:BAT54J", "BAT54J", "Diode_SMD:D_SOD-323F", (420, 225), {"A": "+3V3", "K": "VBAT_IN"},
         fields={"Manufacturer": "Nexperia", "MPN": "BAT54J",
                 "Description": "Schottky 30 V, VF <= 240 mV at 0.1 mA (Nexperia BAT54J): VBAT from 3.3 V, below VDD "
                                f"({DS} section 7.3.4)"}),
    res("R15", "51", "VBAT_IN", "VBAT", (435, 225), f"Resistor 51 ohm 5% 0402, RBAT ({DS} Figures 7-2 and 7-3; {GUIDE} "
        "Figure 22)"),
    cap("C17", "100n", "VBAT", "GND", (447.7, 225), f"Capacitor 100 nF X7R 16 V 0402, CBAT at VBAT pin 37 ({DS} Figures 7-2 "
        "and 7-3)", mpn="GRM155R71C104KA88D"),
    res("R16", "1M", "WAKE", "VBAT_IN", (420, 255), f"Resistor 1 Mohm 1% 0402, WAKE pull-up to VBAT's supply ({GUIDE} "
        f"4.10; {DS} Figure 7-3)"),
    button("SW4", "WAKE", "WAKE_SW", (440, 260), f"Tactile switch, WAKE to ground through R32: wakes from hibernation "
           f"({GUIDE} 4.10)"),
    res("R32", "470", "WAKE", "WAKE_SW", (432, 270), f"Resistor 470 ohm 1% 0402, in series with the WAKE button, at the pin: "
        f"the series resistor {GUIDE} 3.6 asks for on a switch line, the value of {DS} Figure 5-3's RS"),
    Part("TP1", "Connector:TestPoint", "HIB", "TestPoint:TestPoint_Pad_D1.0mm", (460, 230), {"1": "HIB"},
         fields={"Description": f"Test point, HIB (low in hibernation); not used to switch the supply ({GUIDE} 4.10)"}),

    # ---- USB device port (TM4C123 USB0) ---------------------------------------------------------------
    usb_c("J6", "DEV", (40, 190), "USB-C 2.0 receptacle, 16 pins: the TM4C123's own USB device port"),
    esd("U3", "DEV", (95, 190), swap=True),   # D+ on the left at the connector, the ESD part and the chip
    res("R3", "5.1k", "DEV_CC1", "GND", (75, 165), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC1 ({RD})"),
    res("R4", "5.1k", "DEV_CC2", "GND", (87.7, 165), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC2 ({RD})"),
    fuse("F2", "VBUS_DEV", "VDEV", (120, 175), "device port"),
    res("R10", "10k", "VDEV", "VBUS_SENSE", (140, 190), f"Resistor 10 kohm 1% 0402, VBUS sense to PB3: 5.5 V gives 3.3 V "
        f"({GUIDE} 4.1.1, >= 100 ohm in series)"),
    res("R11", "15k", "VBUS_SENSE", "GND", (152.7, 205), f"Resistor 15 kohm 1% 0402, VBUS sense: 4.4 V gives 2.64 V > VIH "
        f"({DS} Table 24-6)"),

    # ---- Debug USB port: CP2102N on UART0 ---------------------------------------------------------------
    usb_c("J5", "DBG", (40, 90), "USB-C 2.0 receptacle, 16 pins: the CP2102N serial port"),
    esd("U2", "DBG", (95, 90)),   # turned 180 degrees: pad 3 (D-) faces contact A7 and pad 2 (D+) faces A6
    res("R1", "5.1k", "DBG_CC1", "GND", (75, 65), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC1 ({RD})"),
    res("R2", "5.1k", "DBG_CC2", "GND", (87.7, 65), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC2 ({RD})"),
    fuse("F1", "VBUS_DBG", "VDBG", (120, 75), "debug port"),
    Part("U5", "Interface_USB:CP2102N-Axx-xQFN20", "CP2102N-A02-GQFN20",
         "Package_DFN_QFN:SiliconLabs_QFN-20-1EP_3x3mm_P0.5mm_EP1.8x1.8mm", (170, 100),
         {"VREGIN": "+3V3", "VDD": "+3V3", "GND": "GND", "D+": "DBG_D+", "D-": "DBG_D-", "VBUS": "BR_VBUS",
          "~{RST}": "BR_RST", "TXD": "BR_TXD", "RXD": "BR_RXD",
          **{p: NC for p in ("RS485/GPIO.1", "CLK/GPIO.0", "NC", "~{SUSPEND}", "~{WAKEUP}", "SUSPEND", "~{CTS}",
                             "~{RTS}", "~{RXT}/GPIO.3", "~{TXT}/GPIO.2")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN20R",
                 "Description": f"USB-UART bridge on the board's 3.3 V, its regulator unused ({CP2102N} Figure 2.3)"}),
    cap("C20", "4.7u", "+3V3", "GND", (215, 70), f"Capacitor 4.7 uF X5R 10 V 0603, CP2102N VREGIN, beside C21 ({CP2102N} "
        "Figure 2.3)", C0603, mpn="GRM188R61A475KE15D"),
    cap("C21", "100n", "+3V3", "GND", (227.7, 70), f"Capacitor 100 nF X7R 16 V 0402, CP2102N VREGIN (tied to VDD; C23 is "
        f"the 0.1 uF nearest the pins) ({CP2102N} Figure 2.3)", mpn="GRM155R71C104KA88D"),
    cap("C22", "4.7u", "+3V3", "GND", (240.4, 70), f"Capacitor 4.7 uF X5R 10 V 0603, CP2102N VDD, behind C23 ({CP2102N} "
        "Figure 2.3)", C0603, mpn="GRM188R61A475KE15D"),
    cap("C23", "100n", "+3V3", "GND", (253.1, 70), f"Capacitor 100 nF X7R 16 V 0402, CP2102N VDD, nearest the pins "
        f"({CP2102N} Figure 2.3)", mpn="GRM155R71C104KA88D"),
    res("R5", "22.1k", "VDBG", "BR_VBUS", (215, 125), f"Resistor 22.1 kohm 1% 0402, CP2102N VBUS divider ({CP2102N} Figure 2.6)"),
    res("R6", "47.5k", "BR_VBUS", "GND", (227.7, 140), f"Resistor 47.5 kohm 1% 0402, CP2102N VBUS divider: 3.41 V from 5 V "
        f"({CP2102N} Figure 2.6)"),
    res("R7", "1k", "BR_RST", "+3V3", (240.4, 125), f"Resistor 1 kohm 1% 0402, CP2102N RSTb pull-up to VDD ({CP2102N} 2.1)"),
    res("R8", "1k", "BR_TXD", "U0RX", (253.1, 125), "Resistor 1 kohm 1% 0402, CP2102N TXD to PA0/U0Rx: caps a driver "
        "fight at 3.3 mA"),
    res("R9", "1k", "U0TX", "BR_RXD", (265.8, 125), "Resistor 1 kohm 1% 0402, PA1/U0Tx to CP2102N RXD: caps a driver "
        "fight at 3.3 mA"),
    res("R33", "100k", "U0TX", "+3V3", (265.8, 140), f"Resistor 100 kohm 1% 0402, U0Tx pull-up: holds the line idle until the "
        f"ROM boot loader drives it ({DS} section 8.2.2.1: a pull-up is preferred)"),
    res("R31", "5.1k", "VDBG", "GND", (240.4, 140), "Resistor 5.1 kohm 1% 0402, VBUS bleed: with the divider 4.75 kohm, so up "
        f"to 185 uA into VDBG keeps the CP2102N VBUS pin under VIL 0.6 V ({CP2102N} Table 3.7); 1.0 mA from a host"),

    # ---- 5 V selection, 3.3 V ---------------------------------------------------------------------------
    Part("JP1", "Connector_Generic:Conn_01x03", "PWR SEL", HDR + "1x03_P2.54mm_Vertical", (165, 170),
         {"1": "VDEV", "2": "+5V", "3": "VDBG"},
         fields={"Description": "Jumper: 1-2 powers the board from the device port (J6), 2-3 from the debug port (J5); "
                                "removed, 5 V can come in on BoosterPack J3.21"}),
    Part("U4", "Regulator_Linear:AP7361C-33E", "AP7361C-33", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (200, 180),
         {"VI": "+5V", "VO": "+3V3", "GND": "GND"},
         fields={"Manufacturer": "Diodes Incorporated", "MPN": "AP7361C-33E-13",
                 "Description": "LDO 3.3 V 1 A, SOT-223; input 2.2-6.0 V (Diodes DS37274 Rev. 5-2)"}),
    cap("C18", "4.7u", "+5V", "GND", (225, 175), "Capacitor 4.7 uF X5R 10 V 0805, LDO input (DS37274: >= 1 uF)",
        C0805, mpn="GRM21BR61A475KA73L"),
    cap("C19", "4.7u", "+3V3", "GND", (237.7, 175), "Capacitor 4.7 uF X5R 10 V 0805, LDO output (DS37274: >= 2.2 uF ceramic)",
        C0805, mpn="GRM21BR61A475KA73L"),
    res("R19", "680", "+3V3", "LED_PWR_A", (215, 205), "Resistor 680 ohm 1% 0402, power LED: (3.3 - 1.9) / 680 = 2.1 mA "
        "(Kingbright DSAO7432)"),
    Part("D1", "Device:LED_Small", "PWR", "LED_SMD:LED_0603_1608Metric", (232, 205), {"A": "LED_PWR_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LCGCK",
                 "Description": "LED green 0603, 3.3 V present (VF 1.9 V typ at 2 mA, DSAO7432)"}),

    # ---- Debug header -----------------------------------------------------------------------------------
    Part("J7", "Connector:Conn_ARM_JTAG_SWD_10", "Cortex Debug", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
         (520, 290), {"VTref": "+3V3", "SWDIO/TMS": "SWDIO", "GND": "GND", "SWCLK/TCK": "SWCLK", "SWO/TDO": "SWO",
                      "KEY": NC, "NC/TDI": "TDI", "GNDDetect": "GND", "~{RESET}": "RST"},
         fields={"Manufacturer": "Samtec", "MPN": "FTSH-105-01-L-DV-K",
                 "Description": f"Arm Cortex Debug 10-pin, 1.27 mm, keyed (pin 7 KEY), SWD/JTAG on PC0-PC3 and RST "
                                f"({GUIDE} Table 11)"}),

    # ---- BoosterPack headers ----------------------------------------------------------------------------
    Part("J1", "Connector_Generic:Conn_02x10_Odd_Even", "BoosterPack J1/J3", HDR + "2x10_P2.54mm_Vertical", (500, 120),
         {**{str(2 * k + 1): J1_PINS[k] for k in range(10)}, **{str(2 * k + 2): J3_PINS[k] for k in range(10)}},
         fields={"Manufacturer": "Samtec", "MPN": "SSW-110-23-F-D",
                 "Description": "BoosterPack J1 (odd pins: J1.1-J1.10, outer) and J3 (even pins: J3.21-J3.30, inner), "
                                f"2x10 2.54 mm, {STACK}"}),
    Part("J2", "Connector_Generic:Conn_02x10_Odd_Even", "BoosterPack J4/J2", HDR + "2x10_P2.54mm_Vertical", (550, 120),
         {**{str(2 * k + 1): J4_PINS[k] for k in range(10)}, **{str(2 * k + 2): J2_PINS[k] for k in range(10)}},
         fields={"Manufacturer": "Samtec", "MPN": "SSW-110-23-F-D",
                 "Description": "BoosterPack J4 (odd pins: J4.40 down to J4.31, inner) and J2 (even pins: J2.20 down "
                                f"to J2.11, outer), 2x10 2.54 mm, {STACK}"}),
    res("R17", "4.7k", "PB0", "+3V3", (480, 175), f"Resistor 4.7 kohm 1% 0402, PB0 (U1Rx) pull-up: 1-10 kohm ({DS} Table 24-31)"),
    res("R18", "4.7k", "PB1", "+3V3", (492.7, 175), f"Resistor 4.7 kohm 1% 0402, PB1 (U1Tx) pull-up: 1-10 kohm ({DS} Table 24-31)"),
    res("R34", "10k", "PA3", "+3V3", (505.4, 175), f"Resistor 10 kohm 1% 0402, PA3 (SSI0Fss, J2.18) pull-up: no SPI access "
        f"before firmware sets the pin up ({GUIDE} 4.2)"),

    # ---- User I/O -----------------------------------------------------------------------------------------
    res("R29", "1k", "PF4", "PF4_SW", (40, 280), "Resistor 1 kohm 1% 0402, PF4 button: limits a BoosterPack driving J2.11 "
        "to 3.3 mA"),
    button("SW2", "PF4", "PF4_SW", (60, 285), "Tactile switch, user button on PF4"),
    res("R30", "1k", "PF0", "PF0_SW", (85, 280), "Resistor 1 kohm 1% 0402, PF0 button: limits a BoosterPack driving J2.17 "
        "to 3.3 mA"),
    button("SW3", "PF0", "PF0_SW", (105, 285), f"Tactile switch, user button on PF0 (locked NMI pin: unlock with GPIOLOCK/"
           f"GPIOCR, {DS} 10.2.4)"),
    Part("D2", "Device:LED_ABRG", "RGB", "LED_SMD:LED_RGB_Wuerth-PLCC4_3.2x2.8mm_150141M173100", (215, 285),
         {"A": "+5V", "BK": "LED_BK", "RK": "LED_RK", "GK": "LED_GK"},
         fields={"Manufacturer": "Wurth Elektronik", "MPN": "150141M173100",
                 "Description": "LED RGB, common anode, PLCC-4 3528 (WL-SFTW): 1 anode, 2 blue, 3 red, 4 green"}),
    *driver(1, "red", "PF1", "LED_RK", "1k", 170),
    *driver(2, "green", "PF3", "LED_GK", "1k", 215),
    *driver(3, "blue", "PF2", "LED_BK", "470", 260),
]
for i in range(4):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
                      (300 + 15 * i, 370), {"1": "GND"}, fields={"Description": "Mounting hole M3, grounded"}))

# Board placement: (x, y, rotation) in mm, origin top-left. Top edge, left to right: the debug
# header, the 5 V jumper, the device USB-C, the power LED, the debug USB-C. The device USB-C and its
# ESD part sit 1 mm left of the chip's USB pins (44 D+, 43 D-), so the pair runs straight down from
# the connector through the ESD part, 0.7 mm apart, on the top layer, and steps right into the pins
# only at the chip: the column above pins 43/42 is left for VDD pin 42's capacitor and the 16 MHz
# crystal's load capacitor. Left of the pair the LDO, its capacitors and the device port's fuse,
# with room between them and J7/H1 for the SWD lines; right of it the 16 MHz crystal group straight
# above pins 40-42, then the reset, VBAT and 32.768 kHz parts, and the CP2102N under the debug port.
# The chip sits between the headers, turned 90 degrees so its USB and oscillator pins face up, its
# PA/PF side faces J4/J2 and its analog side faces J1/J3. Below the BoosterPack (0.15 in under the
# last pin) the four buttons and the RGB LED, with its drivers just above.
DEV_X = 22.9    # J6 and U3 centre: the channel at x 22.55/23.25, 1 mm left of U1 pins 44/43 (x 23.65/24.15)
PLACEMENT = {
    "U1": (MCU[0], MCU[1], 90),
    "J1": (J1_X, ROW0, 0), "J2": (J2_X - 2.54, ROW0, 0),
    "H1": (3.7, 15.0, 0), "H2": (W - 3.7, 15.0, 0), "H3": (3.7, H - 3.7, 0), "H4": (W - 3.7, H - 3.7, 0),
    # top edge: each receptacle's origin USB_C_EDGE from the edge it faces (HRO's recommended layout)
    "J7": (7.4, 5.0, 0), "JP1": (15.0, 6.98, 180), "J6": (DEV_X, USB_C_EDGE, 180),
    "D1": (34.9, 2.0, 0), "R19": (34.9, 3.9, 0), "J5": (42.6, USB_C_EDGE, 180),
    # 3.3 V regulator: IN, GND, OUT along its lower edge, the capacitors just below
    "U4": (15.7, 13.4, 90), "C18": (13.4, 19.2, 0), "C19": (17.6, 19.6, 0),
    # device port: the ESD part straight below the connector, each CC resistor under its pad, the fuse
    "U3": (DEV_X, 12.2, 180), "R4": (20.85, 9.55, 270), "R3": (24.95, 9.55, 270), "F2": (20.5, 16.6, 270),
    "R10": (19.9, 25.8, 90), "R11": (18.8, 25.8, 90),
    # debug port: the ESD part turned so its D- and D+ pads face contacts A7 and A6, each CC resistor
    # on its own contact's side of the pair, the fuse clear of the pair's path; the CP2102N below it
    "U2": (42.6, 10.3, 180), "R1": (45.6, 10.2, 270), "R2": (37.3, 12.6, 90), "F1": (34.6, 13.5, 270),
    "U5": (39.1, 20.6, 0), "R5": (35.3, 19.6, 90), "R6": (35.3, 21.7, 90), "R7": (34.0, 20.6, 90), "R31": (34.0, 18.4, 90),
    "R8": (43.0, 19.7, 90), "R9": (43.0, 21.8, 90), "R33": (43.0, 23.9, 270),
    "C23": (38.2, 24.7, 0), "C22": (38.2, 26.3, 0), "C21": (41.5, 24.7, 0), "C20": (41.6, 26.3, 0),
    # VDD pin 42's capacitor straight above it; Rs straight above OSC1 (pin 41), the OSC1-side load
    # capacitor beside Rs, and the crystal above Rs (OSC1 into pad 3, OSC0 up between the crystal's
    # pads into pad 1), the OSC0 load capacitor beside pad 1
    "C3": (24.45, 29.75, 90), "R12": (25.45, 27.5, 90), "C13": (24.5, 27.75, 270), "Y1": (26.1, 24.8, 180),
    "C12": (27.2, 21.9, 90),
    # reset capacitor and CBAT on the lines from pins 38 and 37, RBAT and the diode beyond them, the
    # reset pull-up and the button's series resistor next to the chip, the 32.768 kHz crystal by
    # pins 34/36, the HIB test point, and WAKE's pull-up and series resistor at pin 32
    "C16": (28.6, 27.9, 90), "C17": (30.0, 28.6, 90), "R15": (31.1, 28.6, 270), "D3": (31.6, 24.6, 0),
    "Y2": (33.8, 29.2, 0), "C15": (32.55, 26.9, 90), "C14": (35.05, 26.9, 90), "TP1": (36.6, 31.2, 0),
    "R32": (32.95, 32.5, 90), "R16": (33.95, 32.5, 90),
    "R13": (30.5, 22.0, 90), "R14": (29.4, 22.0, 90),
    # decoupling around the chip
    "C4": (16.8, 35.0, 90), "C7": (16.6, 37.6, 90), "C8": (14.9, 37.6, 90), "C9": (13.4, 37.6, 90),
    "C2": (33.8, 35.6, 90), "C10": (33.8, 37.7, 90),
    "C1": (26.9, 45.3, 0), "C6": (22.4, 45.9, 0), "C5": (22.4, 47.6, 0), "C11": (30.0, 46.4, 0),
    # UART pull-ups by J1.3/J1.4, the SSI0Fss pull-up by J2.18
    "R17": (9.6, 30.0, 90), "R18": (10.7, 30.0, 90), "R34": (42.6, 29.6, 90),
    # buttons and RGB LED along the bottom edge, drivers above them
    "SW2": (10.6, 56.4, 0), "SW3": (17.2, 56.4, 0), "SW4": (23.8, 56.4, 0), "SW1": (30.4, 56.4, 0),
    "D2": (38.0, 56.4, 0),
    "R29": (10.6, 52.6, 0), "R30": (17.2, 52.6, 0),
    # red, green, blue drivers in three columns: base and pull-down resistors above, cathode resistor below
    "R20": (33.0, 45.9, 0), "R23": (35.0, 45.9, 0), "Q1": (34.0, 48.8, 0), "R26": (34.0, 52.0, 0),
    "R21": (37.0, 45.9, 0), "R24": (39.0, 45.9, 0), "Q2": (38.0, 48.8, 0), "R27": (38.0, 52.0, 0),
    "R22": (41.0, 45.9, 0), "R25": (43.0, 45.9, 0), "Q3": (42.0, 48.8, 0), "R28": (42.0, 52.0, 0),
}
# Laid before the autorouter, in this order, and locked (pcb_build.py priority_routes):
# * The MCU's USB pair, D+ then D-: connector to ESD part to chip, each line through its ESD pad with
#   no stub, on the top layer, down the channel and into pins 44/43. Then the receptacle's second
#   contacts: A6 (D+) joins D+ behind A7, which leaves A7 (D-) the way in front of A6 to B7.
# * The debug port's pair, the same way: connector, ESD part, CP2102N, top layer, no via. The
#   CP2102N numbers D+ (4) before D- (5) counter-clockwise, the opposite of pins 44/43 here, so the
#   pair reaching it must have D+ on its left: only the receptacle's middle contacts (A7 D-, A6 D+)
#   give that order, and they run through U2 (turned so its pads 3 and 2 face them) to the
#   CP2102N's pins 5 and 4. B6 joins A6 behind A7; B7 can reach A7 only by crossing D+ or that
#   link, so its join, the one connection that must change layer, takes two vias (and is in the
#   signal path only with the plug the other way up).
# * The 16 MHz lines, top layer, no via: OSC1 into Rs, Rs to the crystal's pad 3 and its load
#   capacitor C13; OSC0 up between the crystal's pads into pad 1 and on to C12.
# * VDD pin 42 to C3, and pin 42 to VDD pin 11 under the chip (inside the pad ring), since the USB
#   pair and the oscillator lines close it in outside.
# * HIB to its test point out of the pin row's end, then the 32.768 kHz lines (pin -> crystal ->
#   load capacitor), VBAT to CBAT, RST to C16 and on to R14 and R13, so the pins beside them keep
#   their way out. Last, VDD pin 11 and GND pin 12 to C1, and the CP2102N's GND pin 3, which the
#   pair passes, to its exposed pad.
PRIORITY = [(("J6", "B6"), ("U3", "3")), (("U3", "3"), ("U1", "44")),
            (("J6", "B7"), ("U3", "2")), (("U3", "2"), ("U1", "43")),
            (("J6", "A6"), ("J6", "B6"), "join"), (("J6", "A7"), ("J6", "B7"), "join"),
            (("J5", "A6"), ("U2", "2")), (("U2", "2"), ("U5", "4")),
            (("J5", "A7"), ("U2", "3")), (("U2", "3"), ("U5", "5")),
            (("J5", "B6"), ("J5", "A6"), "join"), (("J5", "B7"), ("J5", "A7"), "join"),
            (("U1", "41"), ("R12", "1")), (("R12", "2"), ("Y1", "3")), (("R12", "2"), ("C13", "1")),
            (("U1", "40"), ("Y1", "1")), (("Y1", "1"), ("C12", "1")),
            (("U1", "42"), ("C3", "1")), (("U1", "42"), ("U1", "11")),
            (("U1", "33"), ("TP1", "1")),
            (("U1", "34"), ("Y2", "1")), (("Y2", "1"), ("C14", "1")),
            (("U1", "36"), ("Y2", "2")), (("Y2", "2"), ("C15", "1")),
            (("U1", "37"), ("C17", "1")),
            (("U1", "38"), ("C16", "1")), (("C16", "1"), ("R14", "1")), (("R14", "1"), ("R13", "1")),
            (("U1", "11"), ("C1", "1")), (("U1", "12"), ("C1", "2")),
            (("U5", "3"), ("U5", "21"))]
_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS TM4C123 Board  rev A", "x": W / 2, "y": 40.0, "size": 1.0, "layer": "B_SilkS", "bold": True,
     "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": W / 2, "y": 42.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": W / 2, "y": 43.4, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    # front, all 1.0 mm text: header names above their columns, the jumper's two positions (beside JP1's
    # pins 1 and 3, upright), which USB-C is which, that J1.1 and J3.21 are outputs, and what each
    # button and LED is
    *[{"text": t, "x": x, "y": ROW0 - 2.6, "size": 1.0} for t, x in (("J1", J1_X), ("J3", J1_X + 2.54),
                                                                      ("J4", J2_X - 2.54), ("J2", J2_X))],
    {"text": "DEV", "x": 17.3, "y": 6.98, "size": 1.0, "angle": 90},
    {"text": "DBG", "x": 17.3, "y": 2.6, "size": 1.0, "angle": 90},
    {"text": "USB", "x": 30.0, "y": 6.2, "size": 1.0}, {"text": "UART", "x": 42.2, "y": 13.6, "size": 1.0},
    {"text": "J1.1, J3.21 = OUT", "x": 13.0, "y": 21.3, "size": 1.0},
    {"text": "SWD", "x": 7.4, "y": 9.7, "size": 1.0},
    *[{"text": t, "x": x, "y": 53.9, "size": 1.0} for t, x in (("PF4", 10.6), ("PF0", 17.2), ("WAKE", 23.8),
                                                                ("RESET", 30.4))],
    {"text": "RGB", "x": 38.0, "y": 53.7, "size": 1.0},   # clear of D2's outline at y 54.74
]

BOARD = Board(
    name="eos-tm4c123-board",
    title="EoS TM4C123 Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["BoosterPack header positions (0.1 in grid, outer headers 1.8 in apart, inner 1.6 in, pin 1 rows level) "
             "and signal assignment from TI's BoosterPack Pinout Standard (updated Sept 1, 2013) and the 40-pin figure "
             "of TI's BoosterPack Standards and Design Guide (processors.wiki.ti.com, archived 2017-11-03); used as "
             "facts only"],
    width=W,
    height=H,
    corner_radius=2.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    priority_routes=PRIORITY,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "+5V", "VDDC", "VBAT"],
    headings=[((30, 45), "Debug USB-C, ESD (SP0503), fuse"), ((150, 45), "CP2102N USB-UART (on 3.3 V, VBUS sense + bleed)"),
              ((30, 150), "Device USB-C, ESD (SP0503), fuse, VBUS sense"), ((150, 150), "5 V select, 3.3 V LDO, power LED"),
              ((265, 145), "TM4C123GH6PM"), ((350, 100), "Decoupling, VDDC (SPMA059 3.5)"),
              ((350, 170), "16 MHz and 32.768 kHz crystals"), ((410, 165), "Reset (Fig. 5-3)"),
              ((410, 210), "Hibernation: VBAT, WAKE, HIB"), ((470, 95), "BoosterPack headers (40-pin standard)"),
              ((455, 270), "Cortex Debug header"), ((30, 265), "User buttons, RGB LED"), ((290, 355), "Mounting holes")],
    power_block=(40.64, 385.0),
    notes=[((330, 300), "EoS TM4C123 Board, rev A, BoosterPack-compatible (40-pin). Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Values from TI SPMS376E (TM4C123GH6PM) and SPMA059; Silicon Labs CP2102N Rev. 1.5; Diodes DS37274; Littelfuse SP05xxBA;\n"
                       "NDK NX3225GA; Abracon ABS07; Nexperia BAT54J; onsemi MMBT3904; Wurth 150141M173100; Kingbright.\n"
                       "Firmware: set OSCDRV (C14/C15 20 pF); USB as a forced device, VBUS on PB3;\n"
                       "unlock PF0 and PD7 (GPIOLOCK 0x4C4F434B, GPIOCR) before using them.\n"
                       "JP1 (one shunt): 1-2 device port powers the board, 2-3 debug port; do not feed J3.21 with JP1 fitted,\n"
                       "nor J1.1 ever (3.3 V output). 3.3 V budget 300 mA in all, about 225 mA of it for BoosterPacks.\n"
                       "CP2102N on 3.3 V; R31 bleeds VDBG so its VBUS pin reads low with no debug host. J3.29/J3.30, PB2 open.")],
    # 3.3 V and VDDC at 0.3 mm: they enter the LQFP-64's and the QFN-20's 0.3 mm pads at 0.5 mm pitch,
    # which a 0.4 mm track cannot (the router needs 0.39 mm from a pad's centre line to the next pad)
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS_DBG": "Power", "VBUS_DEV": "Power", "VDBG": "Power", "VDEV": "Power", "+5V": "Power",
                  "+3V3": "Supply", "VDDC": "Supply", "DBG_D+": "USB", "DBG_D-": "USB", "DEV_D+": "USB",
                  "DEV_D-": "USB"},
)
