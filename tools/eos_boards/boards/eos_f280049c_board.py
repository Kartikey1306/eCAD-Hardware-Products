"""EoS F280049C Board: a two-site BoosterPack-compatible (2 x 40-pin) TMS320F280049C board, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-f280049c-board/LICENSE.txt.

A 58.42 x 156.21 mm four-layer board for the TI TMS320F280049C (C2000 real-time MCU, C28x at 100 MHz,
LQFP-100 PZ) with two 40-pin BoosterPack sites ("BoosterPack-compatible" is nominative use: the
board is not a TI product). It does the job of TI's LAUNCHXL-F280049C but is drawn from the chip
makers' documents only: no design file of TI's (schematic, layout, CAD, Gerbers, BOM) was opened.
Sources:

* TI SPRS945H, "TMS320F28004x Real-Time Microcontrollers" (January 2017, revised March 2026):
  "the data sheet". Pins from Table 5-1 (Pin Attributes, 100 PZ column) and Figure 5-1; the PZ
  package drawing PZ0100A (4215169/A) in section 11.
* TI SPRACZ9A, "Hardware Design Guide for F2800x C2000 Real-Time MCU Series" (December 2022):
  "the guide". It covers the F28004x; TI SPRAAS1D says it does not apply to the F28004x, so
  SPRAAS1 is not used.
* TI SPRUII7B Table 1 (p. 3) and Figure 12 (p. 22), published mechanical dimensions only:
  2300 x 6150 mil outline, 50 mil corner radii, header positions and mounting-hole centres.
* TI SPRU655I, "Emulation and Trace Headers Technical Reference Manual" (August 2012), and TI's
  "XDS Target Connection Guide" (software-dl.ti.com/ccs/esd/documents/xdsdebugprobes/
  emu_jtag_connectors.html) for the TI 14-pin JTAG pinout.
* TI "BoosterPack Pinout Standard" (updated Sept 1, 2013) and the 40-pin figure of TI's
  "BoosterPack Standards and Design Guide" (processors.wiki.ti.com, archived 2017-11-03), as on
  EoS TM4C123 Board, for the header positions and signal names.

Chip, package, symbol. U1 is EoS_MCU:TMS320F280049CPZ, a symbol drawn from Table 5-1 (KiCad 10's
MCU_Texas and DSP_Texas libraries have no F28004x part). The footprint is KiCad's
LQFP-100_14x14mm_P0.5mm: TI's PZ0100A drawing gives a 13.8-14.2 mm body, 15.8-16.2 mm across the
leads, 0.5 mm pitch, 0.17-0.27 mm leads, 0.45-0.75 mm feet, 1.6 mm maximum height (JEDEC MS-026),
and its example land pattern 100 x (1.5 x 0.3) mm pads on a 15.4 mm row pitch; KiCad's pads are
1.6 x 0.3 mm on 15.35 mm, so they cover TI's land on every side. No exposed pad on the PZ package
(VSS is pins 5, 45, 72, 86). The chip is turned 270 degrees: its analog pins (1-25 and 26-50)
face the top and the left, toward both sites' analog header pins, and its GPIO sides face the
right-hand headers and the bottom (JTAG, clock, regulator pins).

BoosterPack sites (facts from the two TI documents above, used as positions and signal names
only). Each site follows the 40-pin standard: a 0.1 in grid, outer headers 1.8 in (45.72 mm)
apart, inner headers 1.6 in apart, each 0.1 in inside its outer one, pin-1 rows level; J1 runs
1-10 and J3 21-30 downwards, J2 runs 20 down to 11 and J4 40 down to 31. A BoosterPack is 2.0 in
wide and reaches 350 mil above pin 1 and 0.15 in below the last pin. SPRUII7B Figure 12 places
both sites on a 58.42 x 156.21 mm outline: outer columns x = 6.35/52.07 mm, inner columns
8.89/49.53 mm, site A pin-1 row y = 50.80 mm, site B y = 114.30 mm (63.50 mm separation).
These are mechanical facts only; the circuits and internal placement are independent. Site B's
headers are named J5 (as J1), J7 (as J3), J8 (as J4) and J6 (as J2), pins numbered 40 above site A's,
the naming of TI's 80-pin LaunchPads as this board uses it. The parts are J1 (columns J1, J3), J2
(J4, J2), J5 (J5, J7) and J6 (J8, J6); no other part takes the names J3, J4, J7 or J8.

Thirty-five GPIOs are free for 50 digital BoosterPack positions (the data sheet's 40 GPIOs less
SCIA for the bridge, TDI/TDO for JTAG, X2), so the two sites share what TI's guide says can
ride one bus ("Things like VCC, GND, SPI & I2C can ride the same bus", BoosterPack Pinout
Standard p. 2) and a set of GPIO positions; each site keeps its own UART, PWMs and chip selects.
Shared nets join site A pin n to site B pin n + 40.

  Site A                                        Site B
  J1.2  B3      J1.3  GPIO59 LINA_RX            J5.42 B4/C8   J5.43 GPIO13 SCIB_RX
  J1.4  GPIO22 LINA_TX   J1.5 GPIO33 (shared)   J5.44 GPIO12 SCIB_TX
  J1.6  C0      J1.7  GPIO56 SPIA_CLK (shared)  J5.46 C3
  J1.8  GPIO16 (shared)  J1.9 GPIO27 I2CA_SCL (shared)  J1.10 GPIO26 I2CA_SDA (shared)
  J3.23 A2  J3.24 A3  J3.25 C4  J3.26 C2  J3.27 A1/DACB_OUT  J3.28 A0/DACA_OUT
                                                J7.63 A9  J7.64 A8  J7.65 A4  J7.66 A5  J7.67 C1  J7.68 C5
  J4.40 GPIO6 EPWM4A  J4.39 GPIO14 EPWM8A  J4.38 GPIO9 EPWM5B  J4.37 GPIO5 EPWM3B
                                                J8.80 GPIO3 EPWM2B  J8.79 GPIO2 EPWM2A  J8.78 GPIO0 EPWM1A
                                                J8.77 GPIO7 EPWM4B
  J4.36 GPIO31, J4.35 GPIO17 (capture through the Input X-BAR), J4.34 GPIO4, J4.33 GPIO58,
  J4.32 GPIO57, J4.31 GPIO25: all shared with J8.76-J8.71
  J2.19 GPIO15 EPWM8B  J2.18 GPIO34 (CS)        J6.59 GPIO1 EPWM1B  J6.58 GPIO40 (CS)
  J2.17 GPIO11 (shared, button SW3)  J2.16 XRSn (shared)  J2.15 GPIO8 SPIA_SIMO (shared)
  J2.14 GPIO10 SPIA_SOMI (shared)  J2.11 GPIO23 (shared, button SW2)
  J2.13 GPIO39 (CS)  J2.12 GPIO30 (CS)          J6.53 GPIO24 (CS, boot pin 1)  J6.52 GPIO32 (CS, boot pin 0)
  J3.29, J3.30, J7.69, J7.70: reserved in the 2013 standard, not connected.

Mux positions from Table 5-6 (GPIO Muxed Pins): EPWMxA/B mux 1 on GPIO0-7, 9, 14, 15; SPIA_CLK
mux 1 on GPIO56, SPIA_SIMO mux 7 on GPIO8, SPIA_SOMI mux 7 on GPIO10; I2CA_SDA/SCL mux 11 on
GPIO26/27; SCIB_TX/RX mux 6 on GPIO12/13; LINA_TX mux 9 on GPIO22, LINA_RX mux 9 on GPIO59 (the
LIN module is "UART-compatible", data sheet section 1). The ADC pins left unused (A6, B2/C6, A10,
B0, C14, the PGAx_IN-only pins) are open, which Table 5-10 allows; the five PGAx_GND pins go to
VSSA as Table 5-10 requires. GPIO22 starts in DC-DC mode: firmware clears its GPAAMSEL bit before
using it (Table 5-1). GPIO23 has about 100 pF of internal capacitance and 45 uA leakage (Table
5-1, section 6.6), so it carries a button and a slow shared GPIO.

Every value follows a datasheet:

* Supply (data sheet 6.9.1.4.1: "Connecting all 3.3-V rails together and supplying from a single
  source are strongly recommended"; "supplying VDDA separately typically offers minimal
  benefits"): VDDIO, VDDA and VDDIO_SW all on +3V3, which is the inner layer 2 plane.
* Core 1.2 V from the internal VREG: VREGENZ (pin 73) tied directly to VSS, which enables it
  (Table 5-1; 6.9.1.2.5), so one 3.3 V supply runs the chip. The guide (3.4.3.1) calls the
  internal regulator the cost-effective choice for limited board area; an external 1.2 V supply
  would need its own sequencing (6.9.1.4.3.1). The internal DC-DC is not used: it needs a 2.2 uH
  inductor and 20 uF on VDDIO_SW and costs GPIO22/23 (6.9.1.2.6), and the guide warns of ADC noise
  from it (3.4.3.2). VDD decoupling, data sheet 6.9.1.5.1 (LDO-only): CVDD total 12-27 uF (20
  typical), 0.1-6.75 uF per VDD pin. Configuration 1 of 6.9.1.3.1.2 ("divide CVDD TOTAL equally
  across the VDD pins ... may be used in internal VREG mode"): 4.7 uF X7R 25 V +-10 % 1206 (Murata GRM31CR71E475KA88L) at each of
  pins 4, 46, 71 and 87, 18.8 uF nominal in all. Manufacturer SimSurfing at 10 mVrms, -40..125 C in 5 C steps,
  0..1.375 V gives 4.022..4.562 uF. With -10 % tolerance and an additional 10 % design reserve,
  3.258 uF per pin and 13.03 uF total remain above 12 uF. Nominal +10 % tolerance and +15 % X7R
  drift give 5.946 uF per pin and 23.78 uF total, below 6.75/27 uF. Models are typical, not a
  production guarantee: validate the procured parts at operating bias and temperature. With
  this configuration the VDD pins need not be joined on the board (6.9.1.4.1: "tying the VDD pins
  together is optional as long as each VDD pin has a capacitor connected to pin"; all supply pins
  per rail are tied inside the chip), so each pin and its capacitor form their own net (VDD4,
  VDD46, VDD71, VDD87).
* VDDIO: 0.1 uF at each VDDIO pin (3, 47, 70, 88; CVDDIO_DECAP 0.1 uF, 6.9.1.5.1) and at
  VDDIO_SW (pin 80; CVDDIO_SW 0.1 uF for LDO-only operation), VSS_SW (pin 82) to VSS (Table 5-1).
  VDDA: 2.2 uF on each VDDA pin (11, 34) to VSSA (CVDDA, 6.9.1.5.1; Table 5-1).
* ADC references, internal mode (the guide 3.3.3: "For most applications, the internal voltage
  references offer sufficient performance"): VREFHIA (pin 25) and VREFHIB/VREFHIC (pin 24) each
  get 4.7 uF X7R 25 V 1206 (GRM31CR71E475KA88L) to their VREFLO pin (27, 26), placed at the chip's corner (Table 5-1: "place at
  least a 2.2-uF capacitor on this pin ... as close to the device as possible between the
  VREFHIx and VREFLOx pins. Do not load this pin externally"). SimSurfing at 10 mVrms,
  -40..125 C in 5 C steps, 0..3.625 V gives >= 3.898 uF; -10 % tolerance and a further 10 %
  design reserve leave 3.157 uF, above the 2.2 uF minimum. This is model-backed design margin,
  not a guaranteed lot minimum. VDDA's 2.2 uF in 6.9.1.5.1 is a typical value, unlike this
  VREFHI minimum. VREFLOx and VSSA go to ground.
  One ground plane (inner layer 1) for VSS and VSSA: the guide 4.5 asks for a single plane where
  a clean analog/digital split is not possible, and here analog lines arrive from header pins.
* Clock: a 20 MHz 3.3 V CMOS oscillator, SiTime SiT8008BI-22-33N-20.000000E (SiT8008B data sheet
  rev 1.08: +-25 ppm including aging and temperature, 45-55 % duty, 1 ns typical and 2 ns maximum
  rise/fall at 15 pF, VOH >= 90 % and VOL <= 10 % of VDD, 4.5 mA maximum at 20 MHz; pin 1 "N" =
  no connect; a 0.1 uF bypass is required), into X1 in single-ended mode (data sheet Figure 6-17,
  XTALCR.SE = 1), X2 open (Table 5-10). Keep GPIO19 in input mode with its pull-up disabled
  (Table 5-1) so it does not disturb X1. The data sheet's X1 limits: 2-20 MHz from an external
  oscillator, rise and fall <= 6 ns, 45-55 % high and low time, VIL <= 0.3 VDDIO and VIH >= 0.7
  VDDIO (6.9.3.2.1). Why not the internal oscillators: INTOSC1/2 hold only +-3 % over voltage and
  temperature (6.9.3.5.1), and the guide asks for an external source when CAN is used (3.2.4) and
  for precision better than 1 % (3.6.1). Why not a crystal: the data sheet's crystal method
  (6.9.3.4.4) wants, at 20 MHz, ESR <= 45-50 ohm, a crystal load of 6-12 pF with CL1 = CL2 = 12-24
  pF, and a crystal rated for >= 1 mW drive, or else a damping resistor whose value "should be
  evaluated" with the crystal; the widely stocked 20 MHz SMD crystals that meet the ESR and load
  are rated 100 uW (ECS ECX-53B: 40 ohm, 8-20 pF, 100 uW), and the 1 mW HC-49 parts are stocked
  only with an 18 pF load (Abracon ABLS: 40 ohm, 1000 uW, 18 pF standard), which would need
  26-30 pF per side. An oscillator meets the clock requirement without an untested resistor.
* Reset: 2.2 kohm XRSn pull-up and 100 nF to VSS (data sheet 6.9.2 and Table 5-1: 2.2-10 kohm,
  "100 nF or smaller", so the watchdog can still pull XRSn to VOL within 512 OSCCLK cycles), a
  reset button straight to ground (the open-drain reset source of Figure 6-12); XRSn also reaches
  J2.16 and J6.56. The guide (3.5) asks for a strong pull-up; 2.2 kohm is the strong end.
* Boot (data sheet Table 7-13; the guide 3.2.5): GPIO24 is boot-mode pin 1, GPIO32 pin 0; 11 =
  flash, 01 = SCI/wait, 10 = CAN, 00 = parallel. Each has a 10 kohm pull-up (the guide: weak
  pull-ups where the pin also carries a peripheral, "so the pull-ups can be overdriven") and goes
  to JP1, a 2 x 2 header: a shunt on 1-2 pulls GPIO24 to ground through 1 kohm, on 3-4 GPIO32. The
  pin then reads 3.3 V x 1 / 11 = 0.3 V, under VIL = 0.8 V (6.6); firmware driving the pin high
  with the shunt fitted sources 3.3 mA, inside IOH = 4 mA. Both pins are BoosterPack chip
  selects on site B, which a BoosterPack does not drive, as the guide asks of a boot pin used "as
  outputs whose state is irrelevant during boot"; the pull-ups also hold those chip selects high.
  No shunt boots from flash; 1-2 alone gives SCI boot on SCIA (GPIO28/29, Table 7-18 option 0),
  through the USB bridge.
* JTAG: TI 14-pin header (2 x 7, 0.1 in, pin 6 the key: TI XDS Target Connection Guide; the
  header outline is SPRU655I Figure 4) in place of TI's on-board XDS110, whose firmware is TI's.
  1 TMS, 3 TDI, 7 TDO, 11 TCK, 9 RTCK looped to TCK at the header (SPRU655I Table 13 pin 9), 4
  TDIS, 8, 10, 12 GND (Table 13: TDIS "Connect to target GND", with no resistor), 5 PD/VTref to
  3.3 V through 100 ohm (Table 13 pin 5), 2 TRST open (the data sheet: "This device does not have
  a TRSTn pin"), 13 EMU0 and 14 EMU1 pulled up with 4.7 kohm (the guide Figure 3-16). TMS 2.2
  kohm pull-up (data sheet Table 5-1: "recommended 2.2 kOhm ... to keep JTAG in reset"), TDI and
  TDO 10 kohm (the guide Figure 3-16 and its note: their internal pull-ups are off by default).
  The header is under 6 in from the chip, so no buffers (the guide 3.7.1).
* USB-UART: CP2102N-A02-GQFN20 (Silicon Labs CP2102N data sheet Rev. 1.5) to SCIA on GPIO28
  (SCIA_RX) and GPIO29 (SCIA_TX), the SCI boot pins (data sheet Table 7-18, option 0). It runs
  from the board's 3.3 V with its regulator unused (Figure 2.3: VREGIN tied to VDD, 3.0-3.6 V),
  so it is powered whenever the MCU is and neither drives an unpowered chip (CP2102N inputs
  are rated VIO + 2.5 V unpowered, Table 3.10; the F28004x's 0.3 V above VDDIO, 6.9.1.4.2). 4.7 uF
  and 0.1 uF on VREGIN and on VDD, each 0.1 uF at its pin (Figure 2.3), 1 kohm RSTb pull-up to
  VDD (section 2.1). TXD and RXD reach the MCU through 1 kohm each, which caps a driver fight at
  3.3 mA. SCIA_RX has a 10 kohm pull-up (the guide 3.2.4: a pull-up on SCI-RX, "a good starting
  point ... would be 10 kOhm"). VBUS sense: the 22.1 kohm / 47.5 kohm divider of Figure 2.6 from
  the fused VBUS (5 V reads 3.41 V, above VIH = VIO - 0.6 V = 2.7 V, Table 3.7) plus a 5.1 kohm
  bleed to ground, so the pin reads under VIL = 0.6 V (Table 3.7) unless over 185 uA is pushed
  into that node (0.88 V on 4.75 kohm); the only source is D1's reverse leakage, 0.8 uA typical at
  5 V and 25 C, about 0.1 mA typical at 85 C (Nexperia PMEG6010CEH v.4, Table 7, Figure 2).
  The datasheet does not specify a maximum hot leakage; unplug detection with an external
  5 V supply must be temperature-tested before that behavior can be guaranteed. The section 2.3 note accepts the divider feeding an
  unpowered VBUS pin. ESD: Littelfuse SP0503BAHTG at the connector (three TVS diodes to ground on
  VBUS, D+, D-; 5.5 V standoff, <= 100 nA at 5 V, 30 pF), the part CP2102N Figure 2.5 shows; it
  has no path from D+/D- into VBUS. USB-C as a 5 V sink: 5.1 kohm Rd on CC1 and CC2 (TI SLYY228 p. 54).
* Power: USB VBUS, a Littelfuse 1206L050YR polyfuse (0.50 A hold at 20 C, 0.42 A at 40 C, 1.00 A
  trip, R1max 0.70 ohm; 1206L data sheet, revised 02/26/24), a PMEG6010CEH Schottky (VF <= 400 mV
  at 100 mA, <= 530 mV at 500 mA; Ptot 375 mW on its standard footprint, Tj <= 150 C), then +5V,
  which feeds both sites' 5 V pins (J3.21, J7.61) and the AP7361C-33 LDO (Diodes DS37274 Rev. 5-2:
  1 A, input 2.2-6.0 V, current limit 1.1 A minimum, dropout <= 140 mV at 300 mA for 2.6-3.3 V,
  >= 1 uF in and >= 2.2 uF ceramic out; 4.7 uF in, 10 uF out, "higher capacitance values help to
  improve ... load transient response"). The Schottky keeps a BoosterPack that drives 5 V into
  J3.21 or J7.61 from back-feeding the USB host; that BoosterPack then powers the board.
  Design allowance for the 3.3 V load: the MCU 113 mA (IDDIO) + 30 mA (IDDA), the maxima for the internal VREG
  in operation (data sheet 6.5.2; flash programming needs 106 + 2.5 mA, less); the CP2102N 13.7 mA
  plus 0.23 mA of pull-up (Table 3.2); the oscillator 4.5 mA; the three LEDs about 6.5 mA;
  pull-ups about 5 mA: about 175 mA. The guide (3.4.5) asks for 1.3-2 times the load at the
  regulator: 175 mA x 1.5 = 263 mA, against the AP7361C's 1 A; its 1.1 A current limit exceeds
  the internal VREG's 650 mA typical turn-on inrush (data sheet 6.9.1.5.2, note 5). One shared budget:
  the LDO carries at most 300 mA, which at 5.25 V in dissipates (5.25 - 3.3) x 0.3 = 0.59 W,
  64 C above ambient at the SOT-223's 110 C/W, so the BoosterPacks' 3.3 V pins (J1.1 and J5.41
  together) may take 300 - 175 = 125 mA. The whole board may take 0.38 A from USB: 175 mA for the
  board, 200 mA for the BoosterPacks on both sites' 3.3 V and 5 V pins together (no more than
  125 mA of it on 3.3 V), 1 mA for the bleed; that is under the fuse's 0.42 A hold at 40 C (0.39 A
  at 50 C) and a configured 500 mA USB supply. This does not establish attach or suspend compliance: the
  CP2102N factory power descriptor is 100 mA (Rev. 1.5 Table 4.5), no descriptor image is supplied,
  and its suspend outputs are unused. The MCU remains powered during suspend; qualify this on a
  monitored bench source before claiming USB-compliant bus power. At 0.38 A and 4.75 V from the host the fuse (0.70
  ohm) and D1 (<= 0.53 V) leave +5V >= 3.95 V: the LDO keeps regulating (3.3 V + 0.14 V), but the
  BoosterPack 5 V pins carry 3.95-4.9 V, not a regulated 5 V. D1 then dissipates <= 0.53 V x 0.38
  A = 0.2 W, 66 C above ambient at 330 K/W (standard footprint). J1.1 and J5.41 are outputs only:
  fed while +5V is absent they would lift the LDO's OUT above IN + 0.3 V, its absolute maximum.
  The LDO lists a 150 us typical startup time (DS37274 tST), but this does not establish
  this loaded board's ramp rate; the 8-100 mV/us VDDIO ramp (6.9.1.5.1) needs bench measurement. Power LED: Kingbright APTD1608LCGCK (DSAO7432: VF 1.9 V
  typ at 2 mA) through 680 ohm: 2.1 mA.
* User I/O: red LED (Kingbright APTD1608LSURCK, DSAO7433: VF 1.75 V typ at 2 mA) on GPIO6 and
  yellow (APTD1608LSYCK, DSAO7434: VF 1.85 V) on GPIO14, both site A PWM pins the MCU drives,
  through 680 ohm: 2.3 and 2.1 mA, inside the 4 mA a pin may source (data sheet 6.6). Buttons on
  GPIO23 (J2.11/J6.51) and GPIO11 (J2.17/J6.57) to ground, each through 1 kohm because the pins
  also reach the BoosterPacks: a BoosterPack driving one high into a pressed button sees 3.3 mA.
  GPIO23 has a 10 kohm pull-up, since its leakage (up to 45 uA) is a large share of the 160 uA
  internal pull-up (6.6); pressed it reads 3.3 x 1 / 11 = 0.3 V. GPIO11 uses its internal pull-up
  (160 uA typ): pressed it reads 0.16 V, under VIL = 0.8 V.
* I2C: 2.2 kohm pull-ups on SDA and SCL (the guide 3.2.4 recommends external pull-ups; TI
  SLVA689A Eq. 1: RP(min) = (3.3 - 0.4) V / 3 mA = 0.97 kohm; Eq. 6 with fast mode's 300 ns
  (Table 2-1): 2.2 kohm allows 161 pF of bus).
* BoosterPack headers: Samtec SSW-110-23-F-D, female with long male leads, the stackable part
  TI's BoosterPack Pinout Standard p. 2 asks for and recommends.

Four layers: top signal, inner 1 ground, inner 2 3.3 V, bottom signal. The guide (4.1.3): "A
4-layer board or more is often the best choice for C2000 devices. This enables the designer to
include a clean ground plane and split power plane", and 4.4 asks for a solid ground plane; the
analog pins here run to header pins, so they need that unbroken return; and 80 header pins plus
the LQFP-100's 18 supply pins on four sides would leave no clean ground on two layers.
"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
HDR = "Connector_PinHeader_2.54mm:PinHeader_"
KMR2 = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
LED0603 = "LED_SMD:LED_0603_1608Metric"
DS = "TI SPRS945H"
GUIDE = "TI SPRACZ9A"
CP2102N = "Silicon Labs CP2102N data sheet Rev. 1.5"
RD = "TI SLYY228 p. 54: a sink exposes Rd = 5.1 kohm on CC1 and CC2"
STACK = "female, long male leads, as TI's BoosterPack Pinout Standard (Sept 1, 2013) p. 2 asks and recommends"

# Murata parts, as on EoS TM4C123 Board
C100N = "GRM155R71C104KA88D"     # 100 nF 16 V X7R 0402
C2U2 = "GRM188R71A225KE15D"      # 2.2 uF 10 V X7R 0603
C4U7 = "GRM188R61A475KE15D"      # 4.7 uF 10 V X5R 0603
C4U7_0805 = "GRM21BR61A475KA73L"  # 4.7 uF 10 V X5R 0805
C4U7_LOW_BIAS = "GRM31CR71E475KA88L"  # 4.7 uF 25 V X7R 1206, model-checked core/reference margin
C10U = "GRM21BR61A106KE19L"      # 10 uF 10 V X5R 0805


def res(ref, value, a, b, sch, desc):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields={"Description": desc})


def cap(ref, value, a, b, sch, desc, fp=C0402, mpn=None):
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b},
                fields={"Description": desc, **({"Manufacturer": "Murata", "MPN": mpn} if mpn else {})})


def button(ref, value, a, sch, desc):
    return Part(ref, "Switch:SW_Push", value, KMR2, sch, {"1": a, "2": "GND"},
                fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": desc})


def led(ref, value, anode, sch, mpn, desc):
    return Part(ref, "Device:LED_Small", value, LED0603, sch, {"A": anode, "K": "GND"},
                fields={"Manufacturer": "Kingbright", "MPN": mpn, "Description": desc})


def header(ref, value, odd, even, sch, desc):
    """A 2x10 BoosterPack header part: odd pins down the first column, even pins down the second."""
    return Part(ref, "Connector_Generic:Conn_02x10_Odd_Even", value, HDR + "2x10_P2.54mm_Vertical", sch,
                {**{str(2 * k + 1): odd[k] for k in range(10)}, **{str(2 * k + 2): even[k] for k in range(10)}},
                fields={"Manufacturer": "Samtec", "MPN": "SSW-110-23-F-D", "Description": f"{desc}, 2x10 2.54 mm, {STACK}"})


W, H = 58.42, 156.21
ROW_A, ROW_B = 50.80, 114.30         # SPRUII7B Figure 12: 2000/4500 mil from top
OUT_L, IN_L, IN_R, OUT_R = 6.35, 8.89, 49.53, 52.07  # 250/350/1950/2050 mil
MX, MY = W / 2, 93.98               # independent MCU position between the sites

# BoosterPack signals by header pin (TI BoosterPack Pinout Standard, 2013).
J1_PINS = ["+3V3", "B3", "GPIO59", "GPIO22", "GPIO33", "C0", "GPIO56", "GPIO16", "GPIO27", "GPIO26"]  # J1.1 .. J1.10
J3_PINS = ["+5V", "GND", "A2", "A3", "C4", "C2", "A1_DACB", "A0_DACA", NC, NC]                        # J3.21 .. J3.30
J4_PINS = ["GPIO6", "GPIO14", "GPIO9", "GPIO5", "GPIO31", "GPIO17", "GPIO4", "GPIO58", "GPIO57", "GPIO25"]  # J4.40 .. J4.31
J2_PINS = ["GND", "GPIO15", "GPIO34", "GPIO11", "XRSN", "GPIO8", "GPIO10", "GPIO39", "GPIO30", "GPIO23"]     # J2.20 .. J2.11
J5_PINS = ["+3V3", "B4", "GPIO13", "GPIO12", "GPIO33", "C3", "GPIO56", "GPIO16", "GPIO27", "GPIO26"]  # J5.41 .. J5.50
J7_PINS = ["+5V", "GND", "A9", "A8", "A4", "A5", "C1", "C5", NC, NC]                                  # J7.61 .. J7.70
J8_PINS = ["GPIO3", "GPIO2", "GPIO0", "GPIO7", "GPIO31", "GPIO17", "GPIO4", "GPIO58", "GPIO57", "GPIO25"]  # J8.80 .. J8.71
J6_PINS = ["GND", "GPIO1", "GPIO40", "GPIO11", "XRSN", "GPIO8", "GPIO10", "GPIO24", "GPIO32", "GPIO23"]     # J6.60 .. J6.51

# TMS320F280049C PZ pins (data sheet Table 5-1, 100 PZ column), by number.
U1_NETS = {
    "1": "SCIA_RX", "2": "XRSN", "3": "+3V3", "4": "VDD4", "5": "GND", "6": NC, "7": NC, "8": "B3", "9": "A2",
    "10": "A3", "11": "+3V3", "12": "GND", "13": "GND", "14": "GND", "15": "GND", "16": NC, "17": "C4", "18": NC,
    "19": "C0", "20": NC, "21": "C2", "22": "A1_DACB", "23": "A0_DACA", "24": "VREFHIBC", "25": "VREFHIA",
    "26": "GND", "27": "GND", "28": "C5", "29": "C1", "30": NC, "31": "C3", "32": "GND", "33": "GND", "34": "+3V3",
    "35": "A5", "36": "A4", "37": "A8", "38": "A9", "39": "B4", "40": NC, "41": NC, "42": "GND", "43": NC, "44": NC,
    "45": "GND", "46": "VDD46", "47": "+3V3", "48": NC, "49": NC, "50": "GPIO13",
    "51": "GPIO12", "52": "GPIO11", "53": "GPIO33", "54": "GPIO16", "55": "GPIO17", "56": "GPIO24", "57": "GPIO25",
    "58": "GPIO26", "59": "GPIO27", "60": "TCK", "61": "TDO", "62": "TMS", "63": "TDI", "64": "GPIO32",
    "65": "GPIO56", "66": "GPIO57", "67": "GPIO58", "68": NC, "69": "X1", "70": "+3V3", "71": "VDD71", "72": "GND",
    "73": "GND", "74": "GPIO8", "75": "GPIO4",
    "76": "GPIO3", "77": "GPIO2", "78": "GPIO1", "79": "GPIO0", "80": "+3V3", "81": "GPIO23", "82": "GND",
    "83": "GPIO22", "84": "GPIO7", "85": "GPIO40", "86": "GND", "87": "VDD87", "88": "+3V3", "89": "GPIO5",
    "90": "GPIO9", "91": "GPIO39", "92": "GPIO59", "93": "GPIO10", "94": "GPIO34", "95": "GPIO15", "96": "GPIO14",
    "97": "GPIO6", "98": "GPIO30", "99": "GPIO31", "100": "SCIA_TX",
}

PARTS = [
    # ---- TMS320F280049C ----------------------------------------------------------------------------
    Part("U1", "EoS_MCU:TMS320F280049CPZ", "TMS320F280049CPZ", "Package_QFP:LQFP-100_14x14mm_P0.5mm", (300, 230),
         U1_NETS, fields={"Manufacturer": "Texas Instruments", "MPN": "F280049CPZS",
                          "Description": f"C2000 real-time MCU, C28x 100 MHz, 256 KB flash, LQFP-100 PZ ({DS}); internal "
                                         "VREG (VREGENZ to VSS), X2 open, unused ADC and PGA_IN pins open (Table 5-10)"}),
    cap("C10", "4.7u", "VDD4", "GND", (360, 120), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VDD pin 4: CVDD_DECAP 0.1-6.75 uF a pin, "
        f"CVDD 12-27 uF in all, 4 x 4.7 uF ({DS} 6.9.1.5.1, Configuration 1 of 6.9.1.3.1.2)", C1206, C4U7_LOW_BIAS),
    cap("C17", "4.7u", "GND", "VDD46", (372.7, 120), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VDD pin 46 ({DS} 6.9.1.5.1)", C1206, C4U7_LOW_BIAS),
    cap("C20", "4.7u", "GND", "VDD71", (385.4, 120), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VDD pin 71 ({DS} 6.9.1.5.1)", C1206, C4U7_LOW_BIAS),
    cap("C22", "4.7u", "VDD87", "GND", (398.1, 120), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VDD pin 87 ({DS} 6.9.1.5.1)", C1206, C4U7_LOW_BIAS),
    cap("C11", "100n", "GND", "+3V3", (410.8, 120), f"Capacitor 100 nF X7R 16 V 0402, VDDIO pin 3 to VSS pin 5 (CVDDIO_DECAP "
        f"0.1 uF, {DS} 6.9.1.5.1)", mpn=C100N),
    cap("C18", "100n", "+3V3", "GND", (423.5, 120), f"Capacitor 100 nF X7R 16 V 0402, VDDIO pin 47 to VSS pin 45 ({DS} 6.9.1.5.1)",
        mpn=C100N),
    cap("C19", "100n", "+3V3", "GND", (436.2, 120), f"Capacitor 100 nF X7R 16 V 0402, VDDIO pin 70 ({DS} 6.9.1.5.1)", mpn=C100N),
    cap("C23", "100n", "GND", "+3V3", (448.9, 120), f"Capacitor 100 nF X7R 16 V 0402, VDDIO pin 88 to VSS pin 86 ({DS} 6.9.1.5.1)",
        mpn=C100N),
    cap("C24", "100n", "+3V3", "GND", (461.6, 120), f"Capacitor 100 nF X7R 16 V 0402, VDDIO_SW pin 80 to VSS_SW pin 82 "
        f"(CVDDIO_SW 0.1 uF, LDO only, {DS} 6.9.1.5.1)", mpn=C100N),
    cap("C13", "2.2u", "+3V3", "GND", (360, 150), f"Capacitor 2.2 uF X7R 10 V 0603, VDDA pin 11 to VSSA (CVDDA 2.2 uF, {DS} "
        "6.9.1.5.1, Table 5-1)", C0603, C2U2),
    cap("C16", "2.2u", "+3V3", "GND", (372.7, 150), f"Capacitor 2.2 uF X5R 10 V 10% 0402, VDDA pin 34 to VSSA/PGA_GND pins 33 "
        f"and 32 ({DS} 6.9.1.5.1, Table 5-1)", mpn="GRM155R61A225KE01D"),
    cap("C14", "4.7u", "GND", "VREFHIA", (385.4, 150), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VREFHIA (pin 25) to VREFLOA (pin 27), "
        f"internal reference ({DS} Table 5-1: at least 2.2 uF, as close as possible)", C1206, C4U7_LOW_BIAS),
    cap("C15", "4.7u", "GND", "VREFHIBC", (398.1, 150), f"Capacitor 4.7 uF X7R 25 V 10% 1206, VREFHIB/C (pin 24) to VREFLOB/C (pin "
        f"26) ({DS} Table 5-1)", C1206, C4U7_LOW_BIAS),

    # ---- Clock, reset -------------------------------------------------------------------------------
    Part("Y1", "Oscillator:SiT8008xx-2x-xxN", "20MHz", "Oscillator:Oscillator_SMD_SiT_PQFN-4Pin_3.2x2.5mm", (380, 200),
         {"1": NC, "2": "GND", "3": "X1", "4": "+3V3"},
         fields={"Manufacturer": "SiTime", "MPN": "SiT8008BI-22-33N-20.000000E",
                 "Description": "MEMS oscillator 20 MHz 3.3 V LVCMOS, +-25 ppm, 45-55 % duty, 2 ns max rise/fall (SiT8008B rev "
                                f"1.08) into X1, single-ended mode ({DS} Figure 6-17, 6.9.3.2.1)"}),
    cap("C21", "100n", "GND", "+3V3", (400, 200), "Capacitor 100 nF X7R 16 V 0402, oscillator VDD (SiT8008B: 0.1 uF or more "
        "is required)", mpn=C100N),
    res("R16", "2.2k", "XRSN", "+3V3", (420, 180), f"Resistor 2.2 kohm 1% 0402, XRSn pull-up: 2.2-10 kohm ({DS} 6.9.2; {GUIDE} "
        "3.5: a strong pull-up)"),
    cap("C12", "100n", "XRSN", "GND", (432.7, 180), f"Capacitor 100 nF X7R 16 V 0402, XRSn filter: 100 nF or smaller ({DS} "
        "6.9.2, Table 5-1)", mpn=C100N),
    button("SW1", "RESET", "XRSN", (450, 185), f"Tactile switch, reset: XRSn to ground, the open-drain reset source of {DS} "
           "Figure 6-12"),

    # ---- JTAG ---------------------------------------------------------------------------------------
    Part("J10", "Connector_Generic:Conn_02x07_Odd_Even", "TI JTAG 14", HDR + "2x07_P2.54mm_Vertical", (520, 230),
         {"1": "TMS", "2": NC, "3": "TDI", "4": "GND", "5": "JTAG_PD", "6": NC, "7": "TDO", "8": "GND", "9": "TCK",
          "10": "GND", "11": "TCK", "12": "GND", "13": "EMU0", "14": "EMU1"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-107-07-G-D",
                 "Description": "TI 14-pin JTAG header, 2x7 0.1 in, pin 6 removed as the key (TI XDS Target Connection "
                                "Guide; SPRU655I Figure 4): 1 TMS, 2 TRST (open, no TRSTn on the chip), 3 TDI, 4 TDIS, 5 PD, "
                                "7 TDO, 9 RTCK = TCK, 11 TCK, 13/14 EMU0/1, 8/10/12 GND"}),
    res("R17", "2.2k", "TMS", "+3V3", (490, 260), f"Resistor 2.2 kohm 1% 0402, TMS pull-up ({DS} Table 5-1: recommended 2.2 "
        "kohm, keeps JTAG in reset)"),
    res("R18", "10k", "TDI", "+3V3", (502.7, 260), f"Resistor 10 kohm 1% 0402, TDI pull-up ({GUIDE} Figure 3-16; internal "
        "pull-up off by default)"),
    res("R19", "10k", "TDO", "+3V3", (515.4, 260), f"Resistor 10 kohm 1% 0402, TDO pull-up ({GUIDE} Figure 3-16 and note)"),
    res("R20", "100", "JTAG_PD", "+3V3", (528.1, 260), "Resistor 100 ohm 1% 0402, JTAG PD/VTref: 3.3 V current limited via "
        "100 ohm (TI SPRU655I Table 13, pin 5)"),
    res("R21", "4.7k", "EMU0", "+3V3", (540.8, 260), f"Resistor 4.7 kohm 1% 0402, EMU0 pull-up at the header ({GUIDE} Figure "
        "3-16)"),
    res("R22", "4.7k", "EMU1", "+3V3", (553.5, 260), f"Resistor 4.7 kohm 1% 0402, EMU1 pull-up at the header ({GUIDE} Figure "
        "3-16)"),

    # ---- Boot mode --------------------------------------------------------------------------------------
    Part("JP1", "Connector_Generic:Conn_02x02_Odd_Even", "BOOT", HDR + "2x02_P2.54mm_Vertical", (545, 300),
         {"1": "GPIO24", "2": "BOOT1_PD", "3": "GPIO32", "4": "BOOT0_PD"},
         fields={"Manufacturer": "Samtec", "MPN": "TSW-102-07-G-D",
                 "Description": f"Boot jumpers: 1-2 pulls GPIO24 (boot pin 1) low, 3-4 GPIO32 (boot pin 0); none = flash, "
                                f"1-2 = SCI, 3-4 = CAN, both = parallel I/O ({DS} Table 7-13)"}),
    res("R29", "10k", "GPIO24", "+3V3", (520, 300), f"Resistor 10 kohm 1% 0402, GPIO24 boot pull-up, weak so a peripheral can "
        f"overdrive it ({GUIDE} 3.2.5); also holds chip select J6.53 high"),
    res("R30", "10k", "GPIO32", "+3V3", (520, 325), f"Resistor 10 kohm 1% 0402, GPIO32 boot pull-up ({GUIDE} 3.2.5); also holds "
        "chip select J6.52 high"),
    res("R31", "1k", "BOOT1_PD", "GND", (575, 300), f"Resistor 1 kohm 1% 0402, GPIO24 boot pull-down through JP1: 0.3 V < VIL "
        f"0.8 V with R29 ({DS} 6.6), 3.3 mA if firmware drives the pin high"),
    res("R32", "1k", "BOOT0_PD", "GND", (575, 325), f"Resistor 1 kohm 1% 0402, GPIO32 boot pull-down through JP1 ({DS} 6.6)"),

    # ---- USB-C, ESD, fuse, Schottky, 3.3 V ------------------------------------------------------------------
    Part("J9", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (40, 100), {"VBUS": "VBUS", "GND": "GND", "CC1": "USB_CC1", "CC2": "USB_CC2", "D+": "USB_D+", "D-": "USB_D-",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12",
                 "Description": "USB-C 2.0 receptacle, 16 pins: power and the CP2102N serial port"}),
    Part("U3", "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", (95, 100),
         {"1": "GND", "2": "USB_D+", "3": "USB_D-", "4": "VBUS"},
         fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG",
                 "Description": "USB ESD, 3 TVS channels to ground (VBUS, D+, D-), 5.5 V standoff, at the connector; no path "
                                f"from D+/D- into VBUS (Littelfuse SP05xxBA; {CP2102N} Figure 2.5)"}),
    res("R1", "5.1k", "USB_CC1", "GND", (75, 75), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC1 ({RD})"),
    res("R2", "5.1k", "USB_CC2", "GND", (87.7, 75), f"Resistor 5.1 kohm 1% 0402, USB-C sink Rd on CC2 ({RD})"),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (120, 85), {"1": "VBUS", "2": "VBUS_F"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR",
                 "Description": "PTC fuse 0.50 A hold (0.42 A at 40 C), 1.00 A trip, 6 V, R1max 0.70 ohm, 1206 (Littelfuse 1206L)"}),
    Part("D1", "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F", (145, 85), {"A": "VBUS_F", "K": "+5V"},
         fields={"Manufacturer": "Nexperia", "MPN": "PMEG6010CEH,115",
                 "Description": "Schottky 60 V 1 A, VF <= 400 mV at 100 mA, <= 530 mV at 500 mA (Nexperia PMEG6010CEH v.4): "
                                "a BoosterPack's 5 V cannot reach the USB host"}),
    res("R3", "5.1k", "VBUS_F", "GND", (120, 110), "Resistor 5.1 kohm 1% 0402, VBUS bleed: with the CP2102N divider 4.75 kohm, so "
        f"up to 185 uA of D1 leakage keeps the bridge's VBUS pin under VIL 0.6 V ({CP2102N} Table 3.7); 1.0 mA from a host"),
    Part("U4", "Regulator_Linear:AP7361C-33E", "AP7361C-33", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", (200, 100),
         {"VI": "+5V", "VO": "+3V3", "GND": "GND"},
         fields={"Manufacturer": "Diodes Incorporated", "MPN": "AP7361C-33E-13",
                 "Description": "LDO 3.3 V 1 A, current limit 1.1 A min, SOT-223; input 2.2-6.0 V (Diodes DS37274 Rev. 5-2); "
                                "300 mA budget (0.59 W, 64 C rise)"}),
    cap("C1", "4.7u", "GND", "+5V", (225, 90), "Capacitor 4.7 uF X5R 10 V 0805, LDO input (DS37274: >= 1 uF)", C0805, C4U7_0805),
    cap("C2", "10u", "GND", "+3V3", (237.7, 90), "Capacitor 10 uF X5R 10 V 0805, LDO output (DS37274: >= 2.2 uF ceramic; more "
        "helps load transients, as the MCU's 650 mA VREG inrush, SPRS945H 6.9.1.5.2)", C0805, C10U),
    res("R4", "680", "+3V3", "LED_PWR_A", (215, 125), "Resistor 680 ohm 1% 0402, power LED: (3.3 - 1.9) / 680 = 2.1 mA "
        "(Kingbright DSAO7432)"),
    led("D2", "PWR", "LED_PWR_A", (232, 125), "APTD1608LCGCK", "LED green 0603, 3.3 V present (VF 1.9 V typ at 2 mA, DSAO7432)"),

    # ---- CP2102N USB-UART on SCIA -----------------------------------------------------------------------
    Part("U2", "Interface_USB:CP2102N-Axx-xQFN20", "CP2102N-A02-GQFN20",
         "Package_DFN_QFN:SiliconLabs_QFN-20-1EP_3x3mm_P0.5mm_EP1.8x1.8mm", (150, 170),
         {"VREGIN": "+3V3", "VDD": "+3V3", "GND": "GND", "D+": "USB_D+", "D-": "USB_D-", "VBUS": "BR_VBUS",
          "~{RST}": "BR_RST", "TXD": "BR_TXD", "RXD": "BR_RXD",
          **{p: NC for p in ("RS485/GPIO.1", "CLK/GPIO.0", "NC", "~{SUSPEND}", "~{WAKEUP}", "SUSPEND", "~{CTS}",
                             "~{RTS}", "~{RXT}/GPIO.3", "~{TXT}/GPIO.2")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN20R",
                 "Description": f"USB-UART bridge on SCIA (the SCI boot pins), on the board's 3.3 V, its regulator unused "
                                f"({CP2102N} Figure 2.3)"}),
    cap("C3", "100n", "GND", "+3V3", (195, 150), f"Capacitor 100 nF X7R 16 V 0402, CP2102N VDD (pin 6), at the pin ({CP2102N} "
        "Figure 2.3)", mpn=C100N),
    cap("C4", "100n", "GND", "+3V3", (207.7, 150), f"Capacitor 100 nF X7R 16 V 0402, CP2102N VREGIN (pin 7), at the pin "
        f"({CP2102N} Figure 2.3)", mpn=C100N),
    cap("C5", "4.7u", "+3V3", "GND", (220.4, 150), f"Capacitor 4.7 uF X5R 10 V 0603, CP2102N VDD ({CP2102N} Figure 2.3)",
        C0603, C4U7),
    cap("C6", "4.7u", "+3V3", "GND", (233.1, 150), f"Capacitor 4.7 uF X5R 10 V 0603, CP2102N VREGIN ({CP2102N} Figure 2.3)",
        C0603, C4U7),
    res("R5", "1k", "BR_RST", "+3V3", (195, 190), f"Resistor 1 kohm 1% 0402, CP2102N RSTb pull-up to VDD ({CP2102N} 2.1)"),
    res("R6", "22.1k", "VBUS_F", "BR_VBUS", (207.7, 190), f"Resistor 22.1 kohm 1% 0402, CP2102N VBUS divider ({CP2102N} Figure 2.6)"),
    res("R7", "47.5k", "BR_VBUS", "GND", (220.4, 190), f"Resistor 47.5 kohm 1% 0402, CP2102N VBUS divider: 3.41 V from 5 V "
        f"({CP2102N} Figure 2.6, Table 3.7)"),
    res("R8", "1k", "BR_TXD", "SCIA_RX", (233.1, 190), "Resistor 1 kohm 1% 0402, CP2102N TXD to GPIO28/SCIA_RX: caps a driver "
        "fight at 3.3 mA"),
    res("R9", "1k", "SCIA_TX", "BR_RXD", (245.8, 190), "Resistor 1 kohm 1% 0402, GPIO29/SCIA_TX to CP2102N RXD: caps a driver "
        "fight at 3.3 mA"),
    res("R10", "10k", "SCIA_RX", "+3V3", (258.5, 190), f"Resistor 10 kohm 1% 0402, SCI-RX pull-up ({GUIDE} 3.2.4: a good starting "
        "point is 10 kohm)"),

    # ---- User I/O --------------------------------------------------------------------------------------------
    res("R11", "680", "GPIO6", "LED_R_A", (40, 290), "Resistor 680 ohm 1% 0402, red LED: (3.3 - 1.75) / 680 = 2.3 mA (Kingbright "
        f"DSAO7433), inside IOH 4 mA ({DS} 6.6)"),
    led("D3", "RED", "LED_R_A", (55, 290), "APTD1608LSURCK", "LED red 0603, user LED on GPIO6 (EPWM4A, J4.40)"),
    res("R12", "680", "GPIO14", "LED_Y_A", (75, 290), "Resistor 680 ohm 1% 0402, yellow LED: (3.3 - 1.85) / 680 = 2.1 mA "
        "(Kingbright DSAO7434)"),
    led("D4", "YEL", "LED_Y_A", (90, 290), "APTD1608LSYCK", "LED yellow 0603, user LED on GPIO14 (EPWM8A, J4.39)"),
    res("R13", "1k", "GPIO23", "SW2_A", (40, 330), "Resistor 1 kohm 1% 0402, GPIO23 button: limits a BoosterPack driving J2.11 "
        "or J6.51 to 3.3 mA"),
    button("SW2", "GPIO23", "SW2_A", (60, 335), "Tactile switch, user button on GPIO23 (J2.11/J6.51)"),
    res("R15", "10k", "GPIO23", "+3V3", (155.4, 330), f"Resistor 10 kohm 1% 0402, GPIO23 pull-up: its leakage, up to 45 uA, is a "
        f"large part of the 160 uA internal pull-up ({DS} 6.6)"),
    res("R14", "1k", "GPIO11", "SW3_A", (85, 330), "Resistor 1 kohm 1% 0402, GPIO11 button: limits a BoosterPack driving J2.17 "
        "or J6.57 to 3.3 mA"),
    button("SW3", "GPIO11", "SW3_A", (105, 335), f"Tactile switch, user button on GPIO11 (J2.17/J6.57; internal pull-up, {DS} 6.6)"),
    res("R23", "2.2k", "GPIO26", "+3V3", (130, 330), "Resistor 2.2 kohm 1% 0402, I2C SDA pull-up: RP(min) 0.97 kohm, fast mode "
        "to 161 pF (TI SLVA689A Eq. 1 and 6)"),
    res("R24", "2.2k", "GPIO27", "+3V3", (142.7, 330), "Resistor 2.2 kohm 1% 0402, I2C SCL pull-up (TI SLVA689A Eq. 1 and 6)"),

    # ---- BoosterPack headers ------------------------------------------------------------------------------------
    header("J1", "BoosterPack A J1/J3", J1_PINS, J3_PINS, (420, 300),
           "Site A BoosterPack J1 (odd pins: J1.1-J1.10, outer) and J3 (even pins: J3.21-J3.30, inner)"),
    header("J2", "BoosterPack A J4/J2", J4_PINS, J2_PINS, (475, 300),
           "Site A BoosterPack J4 (odd pins: J4.40 down to J4.31, inner) and J2 (even pins: J2.20 down to J2.11, outer)"),
    header("J5", "BoosterPack B J5/J7", J5_PINS, J7_PINS, (420, 345),
           "Site B BoosterPack J5 (odd pins: J5.41-J5.50, outer) and J7 (even pins: J7.61-J7.70, inner)"),
    header("J6", "BoosterPack B J8/J6", J8_PINS, J6_PINS, (475, 345),
           "Site B BoosterPack J8 (odd pins: J8.80 down to J8.71, inner) and J6 (even pins: J6.60 down to J6.51, outer)"),
]
for i in range(4):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole", "M3 clearance", "MountingHole:MountingHole_3.2mm_M3",
                      (250 + 15 * i, 395), {}, fields={"Description": "Non-plated M3 clearance hole, 3.2 mm; centre from SPRUII7B Figure 12 (100 mil from each edge), drill 0.152 mm larger than TI's 120 mil nominal"}))

# Board placement: (x, y, rotation) in mm, origin top-left. Top strip: the 3.3 V path and the reset
# button on the left (polyfuse, Schottky, LDO, power LED), the USB-C with its ESD part and the
# CP2102N in the middle, the user buttons and LEDs on the right. Then site A, the MCU between the two
# sites, site B, and the bottom strip with the JTAG header and the boot jumpers. The MCU is turned
# 270 degrees: pins 1-25 along its top, 26-50 down its left, 51-75 along its bottom, 76-100 up its
# right. Each decoupling capacitor sits just outside the pin row, in line with its pin.
PLACEMENT = {
    "U1": (MX, MY, 270),
    "J1": (OUT_L, ROW_A, 0), "J2": (IN_R, ROW_A, 0), "J5": (OUT_L, ROW_B, 0), "J6": (IN_R, ROW_B, 0),
    "H1": (2.54, 2.54, 0), "H2": (W - 2.54, 2.54, 0), "H3": (2.54, H - 2.54, 0), "H4": (W - 2.54, H - 2.54, 0),
    # top strip, left: polyfuse, Schottky, reset button, LDO with its capacitors, power LED
    "F1": (21.8, 9.6, 180), "D1": (16.6, 9.6, 0), "R3": (19.6, 12.3, 0), "SW1": (17.5, 15.0, 0),
    "U4": (9.0, 13.0, 0), "C1": (2.3, 10.7, 90), "C2": (2.3, 15.3, 90), "D2": (2.3, 19.3, 90), "R4": (2.3, 21.75, 90),
    # USB-C (origin USB_C_EDGE from the top edge, HRO's recommended layout), the ESD part straight below its
    # data contacts, each CC resistor on its own contact's side, the CP2102N below with D- and D+ facing up
    "J9": (30.0, USB_C_EDGE, 180), "U3": (30.0, 10.3, 180), "R1": (33.0, 10.2, 270), "R2": (26.6, 10.4, 90),
    "U2": (30.5, 17.0, 270), "C3": (27.2, 15.2, 0), "C4": (27.2, 16.3, 0), "C5": (24.9, 15.3, 90), "C6": (24.9, 18.4, 90),
    "R6": (26.7, 17.4, 0), "R5": (27.2, 18.45, 180), "R7": (27.2, 19.5, 0),
    "R8": (34.1, 17.0, 0), "R9": (34.1, 18.1, 0), "R10": (34.1, 19.2, 0),
    # top strip, right: user buttons and LEDs, outside site A's BoosterPack (which starts 8.89 mm above J1.1)
    "SW2": (38.6, 10.2, 0), "SW3": (44.4, 10.2, 0),
    "D3": (37.4, 14.4, 0), "D4": (40.4, 14.4, 0), "R11": (37.4, 16.1, 0), "R12": (40.4, 16.1, 0),
    "R13": (43.6, 14.0, 0), "R14": (43.6, 15.1, 0), "R15": (43.6, 16.2, 0),
    # MCU top side (pins 1-25): VDD4 and VDDIO3 capacitors in line with their pins, the reset RC above
    # them on XRSn's way up (pins 1 and 2 go straight up past them), VDDA11
    "C10": (29.9, 43.5, 90), "C11": (29.9, 47.25, 0), "C12": (34.5, 39.0, 90), "R16": (33.0, 39.0, 90),
    "C13": (26.15, 46.0, 90),
    # the ADC references at the top-left corner, each capacitor's ground end toward its VREFLO pin
    "C14": (15.3, 48.6, 90), "C15": (12.8, 48.6, 90),
    # left side (pins 26-50): VDDA34, VDD46, VDDIO47
    "C16": (16.15, 53.98, 90), "C17": (12.6, 60.48, 0), "C18": (16.15, 60.48, 90),
    # bottom side (pins 51-75): VDDIO70, VDD71, the oscillator below X1 (pin 69) with its bypass
    "C19": (27.5, 68.9, 0), "C20": (29.9, 68.1, 90), "Y1": (28.85, 73.0, 90), "C21": (26.4, 73.0, 90),
    # right side (pins 76-100): VDD87, VDDIO88, VDDIO_SW80
    "C22": (38.5, 56.98, 0), "C23": (34.65, 56.97, 90), "C24": (34.65, 59.98, 90),
    # I2C pull-ups by site B's SDA/SCL pins
    "R23": (8.0, 85.0, 90), "R24": (9.2, 85.0, 90),
    # bottom strip: TI 14-pin JTAG header, its resistors, boot jumpers and their resistors
    "J10": (29.5, 94.1, 270), "R17": (28.6, 90.6, 90), "R18": (27.4, 90.6, 90), "R19": (20.6, 90.6, 90),
    "R20": (23.2, 90.6, 90), "R21": (13.6, 90.6, 90), "R22": (14.9, 90.6, 90),
    "JP1": (36.5, 93.6, 0), "R31": (41.8, 92.2, 0), "R32": (41.8, 94.8, 0), "R29": (41.8, 89.6, 0), "R30": (41.8, 97.4, 0),
}
# Independent circuit groups translated into the published outline/header frame.
# Header and hole positions above already use that frame; internal placements do not copy TI's.
_mcu_group = {"C10", "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18", "C19", "C20", "C21", "C22", "C23", "C24", "R16", "Y1"}
_bottom_group = {"J10", "JP1", "R17", "R18", "R19", "R20", "R21", "R22", "R29", "R30", "R31", "R32"}
for _ref, (_x, _y, _angle) in list(PLACEMENT.items()):
    if _ref in {"U1", "J1", "J2", "J5", "J6", "H1", "H2", "H3", "H4"}:
        continue
    _dy = 37.50 if _ref in _mcu_group else 57.21 if _ref in _bottom_group else 50.20 if _ref in {"R23", "R24"} else 0.0
    PLACEMENT[_ref] = (round(_x + 3.81, 4), round(_y + _dy, 4), _angle)

# Laid before the autorouter, in this order, and locked (pcb_build.py priority_routes):
# * The USB pair, as on EoS TM4C123 Board's debug port: contact A6 (D+) to the ESD part's pad 2 and on
#   to the CP2102N's pin 4, A7 (D-) to pad 3 and pin 5, each line through its ESD pad with no stub, top
#   layer; then the duplicated contacts, B6 to A6 behind A7 and B7 to A7 (which must cross D+).
# * The CP2102N's ground pin 3 (beside D+) to its exposed pad, VDD and VREGIN to their 0.1 uF.
# * X1, from pin 69 straight down to the oscillator's output.
# * The ADC references: VREFHIA and VREFHIB/C to their 4.7 uF, and each capacitor's ground end to its
#   VREFLO pin, so the loop closes at the chip (Table 5-1).
# * Every decoupling capacitor to its pin, and VREGENZ (pin 73) to VSS (pin 72).
# * RTCK to TCK at the JTAG header.
PRIORITY = [(("J9", "A6"), ("U3", "2")), (("U3", "2"), ("U2", "4")),
            (("J9", "A7"), ("U3", "3")), (("U3", "3"), ("U2", "5")),
            (("J9", "B6"), ("J9", "A6"), "join"), (("J9", "B7"), ("J9", "A7"), "join"),
            (("U2", "9"), ("R5", "1")),  # boxed RSTb route before bridge fan-out/decoupling
            (("U2", "3"), ("U2", "21")), (("U2", "12"), ("U2", "21")), (("U2", "6"), ("C3", "2")), (("U2", "7"), ("C4", "2")),
            (("U1", "25"), ("C14", "2")), (("C14", "1"), ("U1", "27")),
            (("U1", "24"), ("C15", "2")), (("C15", "1"), ("U1", "26")),
            (("U1", "4"), ("C10", "1")), (("U1", "3"), ("C11", "2")), (("U1", "5"), ("C11", "1")),
            (("U1", "11"), ("C13", "1")), (("U1", "12"), ("U1", "13")), (("U1", "13"), ("U1", "14")), (("U1", "15"), ("U1", "14")),
            (("U1", "34"), ("C16", "1")), (("U1", "32"), ("C16", "2")), (("U1", "33"), ("U1", "32")),
            (("U1", "46"), ("C17", "2")), (("U1", "47"), ("C18", "1")), (("U1", "45"), ("C18", "2")),
            (("U1", "71"), ("C20", "2")), (("U1", "73"), ("U1", "72")), (("U1", "73"), ("C20", "1")),
            (("U1", "70"), ("C19", "1")), (("C20", "1"), ("C19", "2")),
            (("U1", "69"), ("Y1", "3")), (("Y1", "4"), ("C21", "2")),
            (("U1", "87"), ("C22", "1")), (("U1", "88"), ("C23", "2")), (("U1", "86"), ("C23", "1")),
            (("U1", "80"), ("C24", "1")), (("U1", "82"), ("C24", "2")),
            (("J10", "9"), ("J10", "11"))]
_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS F280049C Board  rev A", "x": MX, "y": 78.0, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": MX, "y": 80.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": MX, "y": 81.6, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    # front: header names above their columns, the 3.3 V pins being outputs, buttons, LEDs, JTAG, boot
    *[{"text": t, "x": x, "y": ROW_A - 2.6, "size": 1.0} for t, x in (("J1", OUT_L), ("J3", IN_L), ("J4", IN_R), ("J2", OUT_R))],
    *[{"text": t, "x": x, "y": ROW_B - 2.6, "size": 1.0} for t, x in (("J5", OUT_L), ("J7", IN_L), ("J8", IN_R), ("J6", OUT_R))],
    {"text": "3V3 OUT", "x": 9.0, "y": ROW_A - 2.6, "size": 0.8},
    {"text": "USB", "x": 22.5, "y": 6.0, "size": 1.0}, {"text": "PWR", "x": 4.6, "y": 19.3, "size": 0.8},
    {"text": "RESET", "x": 15.9, "y": 12.4, "size": 1.0},
    {"text": "GPIO23", "x": 38.6, "y": 12.6, "size": 0.8}, {"text": "GPIO11", "x": 44.4, "y": 20.2, "size": 0.8},
    {"text": "LED6", "x": 37.0, "y": 17.5, "size": 0.8}, {"text": "LED14", "x": 41.0, "y": 17.5, "size": 0.8},
    {"text": "JTAG", "x": 10.2, "y": 97.0, "size": 1.0},
    {"text": "BOOT", "x": 37.8, "y": 91.0, "size": 0.8},
    {"text": "SCI", "x": 33.3, "y": 93.6, "size": 0.8}, {"text": "CAN", "x": 33.3, "y": 96.14, "size": 0.8},
]

for _t in TEXTS:
    if _t.get("layer") == "B_SilkS":
        _t["y"] += 50.20
    elif _t["text"] not in {"J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"}:
        _t["x"] += 3.81
        if _t["text"] in {"JTAG", "BOOT", "SCI", "CAN"}:
            _t["y"] += 57.21

BOARD = Board(
    name="eos-f280049c-board",
    title="EoS F280049C Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["Outline, corner radii, header positions and mounting-hole centres: TI SPRUII7B Table 1 and Figure 12, mechanical facts only; hole drill enlarged from 3.048 to 3.2 mm for M3 clearance",
             "BoosterPack header positions (0.1 in grid, outer headers 1.8 in apart, inner 1.6 in, pin 1 rows level) "
             "and signal assignment from TI's BoosterPack Pinout Standard (updated Sept 1, 2013) and the 40-pin figure "
             "of TI's BoosterPack Standards and Design Guide (processors.wiki.ti.com, archived 2017-11-03); used as "
             "facts only",
             "TI 14-pin JTAG header pinout from TI's XDS Target Connection Guide and SPRU655I (Emulation and Trace Headers "
             "Technical Reference Manual); used as facts only"],
    width=W,
    height=H,
    corner_radius=1.27,
    thickness=1.6,
    layers=4,
    planes=[("GND", "In1.Cu"), ("+3V3", "In2.Cu")],
    fanout_avoid=[(MX, MY)],
    fanout_first=["C11"],          # its +3V3 via goes in before the /VDD4 route boxes it in
    # the corner column beside pin 1, on top: with vias kept 0.1 mm off pads the /VDD4 route would
    # otherwise run up it and wall in pin 1 (SCIA_RX); this sends /VDD4 to the bottom layer
    router_keepouts=[(35.5, 84.0, 35.95, 87.6)],
    parts=PARTS,
    priority_routes=PRIORITY,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "+5V", "VDD4", "VDD46", "VDD71", "VDD87"],
    headings=[((30, 60), "USB-C, ESD (SP0503), polyfuse, Schottky"), ((170, 60), "3.3 V LDO, power LED"),
              ((120, 140), "CP2102N USB-UART on SCIA (on 3.3 V, VBUS sense + bleed)"),
              ((265, 165), "TMS320F280049C (LQFP-100 PZ)"), ((350, 100), "Decoupling (SPRS945H 6.9.1.5.1)"),
              ((350, 140), "VDDA and ADC references"), ((370, 175), "20 MHz oscillator, reset"),
              ((480, 200), "TI 14-pin JTAG"), ((505, 280), "Boot mode (GPIO24, GPIO32)"),
              ((390, 280), "BoosterPack sites A and B (40-pin standard each)"), ((30, 270), "User LEDs, buttons, I2C pull-ups"),
              ((240, 380), "Mounting holes")],
    power_block=(40.64, 375.0),
    notes=[((30, 225), "EoS F280049C Board, rev A, two BoosterPack-compatible (40-pin) sites. Designed by Kartikeydheer Srivastava.\n"
                        "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                        "Values from TI SPRS945H (TMS320F28004x) and SPRACZ9A; TI SPRU655I; Silicon Labs CP2102N Rev. 1.5;\n"
                        "Diodes DS37274; Littelfuse SP05xxBA and 1206L; Nexperia PMEG6010CEH; SiTime SiT8008B; Kingbright; TI SLVA689A.\n"
                        "Firmware: X1 single-ended (XTALCR.SE = 1); clear GPAAMSEL for GPIO22; LIN-A in SCI mode for site A's UART.\n"
                        "JP1: none = flash boot, 1-2 = SCI boot (USB bridge), 3-4 = CAN, both = parallel.\n"
                        "Budget: BoosterPacks 200 mA in all from 3.3 V and 5 V pins, no more than 125 mA from 3.3 V.\n"
                        "J1.1 and J5.41 (3.3 V) are outputs only; the 5 V pins carry USB VBUS less a fuse and a Schottky.")],
    # 3.3 V, the core nets and the references at 0.3 mm: they enter the LQFP-100's and the QFN-20's
    # 0.3 mm pads at 0.5 mm pitch, which a 0.4 mm track cannot (EoS TM4C123 Board, same rule)
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}},
    net_to_class={"VBUS": "Power", "VBUS_F": "Power", "+5V": "Power",
                  "+3V3": "Supply", "VDD4": "Supply", "VDD46": "Supply", "VDD71": "Supply", "VDD87": "Supply",
                  "VREFHIA": "Supply", "VREFHIBC": "Supply", "USB_D+": "USB", "USB_D-": "USB"},
)
