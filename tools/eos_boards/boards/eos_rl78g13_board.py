"""EoS RL78G13 Board: a 30 x 100 mm Renesas RL78/G13 development board, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-rl78g13-board/LICENSE.txt.

An original circuit and layout using only chip datasheets and application notes. The
30 x 100 mm envelope, 25.4 mm header separation, 2.54 mm pitch and header pin functions
come from Renesas R01UH0243ED0000 Rev.1.0 pp.18-20 and the dimension callouts on p.70.
No vendor schematic, copper layout, Gerber or BOM was used. The un-dimensioned longitudinal
header offset is original: pin 1 is 2.54 mm from the bottom edge; this is not a drop-in claim.
The CP2102N replaces the proprietary on-board probe with a USB serial port; J4 accepts an
external E1/E2/E2 Lite probe. All I/O is 3.3 V, not the reference board's 5 V supply.

MCU: Renesas R01DS0131EJ0380 section 1.3.11, and R01UH0146EJ0380 section 2.2
(100 nF supply bypass), section 5.7 (resonator table: NX3215SA 6 pF, 7 pF loads), section 23.1
(REGC 0.47-1 uF). Both supplies share 3.3 V. The main clock uses the internal HOCO;
unused X1/X2 inputs are grounded through 10 kohm resistors per the connections-of-unused-pins table. P137 is input-only
and receives an external 10 kohm pull-up, drawing 0.33 mA with the button held.
Debug: Renesas R20UT1994EJ0940 Table 2-2 and Fig.2-10 provide the 14-pin TOOL0
header and reset-selection jumper. TOOL0 has the Fig.2-5 1 kohm pull-up. JP1 selects
user reset (1-2) or the external probe's RESET_OUT (2-3); in 2-3 RESET_OUT alone drives
RESET, so RESET has the 10 kohm pull-up Fig.2-11 asks for in that case (1-10 kohm). No reset capacitance: hot
plugging the debug cable is unsupported. Connect powered off. USB UART uses UART2,
P13/TxD2 and P14/RxD2, rather than the TOOLRxD/TOOLTxD pins. There is no on-board
programmer or COM-port debug claim. P11/P12 remain free on the expansion header.

Power: TPS7A91, TI SBVS282A Table 7-1: 3.57 kohm / 1.15 kohm gives 3.283 V nominal;
0.1% resistors are specified. Section 7.1.3 allows 10 uF ceramic input and output
(its nominal recommendations already account for 50% derating). NR/SS = 10 nF, SS_CTRL
low. Input is USB VBUS through 1206L050YR and PMEG6010CEH. The CP2102N is always
powered with the MCU; its VBUS sense has the manufacturer's 22.1k/47.5k divider, and
1.5 kohm VBUS bleed gives 1.47 kohm total, keeping 0.5 mA leakage below 0.8 V.
SP0503BAHTG has only common-anode clamps to ground; D+ cannot hold VBUS high.
Only USB powers this board: the VDD header contacts are outputs, and an attached debug
probe must have target power disabled. Do not inject a supply into VDD.

Use one shared 150 mA budget for external VDD loads, after CP2102N Max Power is programmed to 0xFA and the host grants
500 mA (CP2102N Rev.1.5 Table 7.1; factory 0x32 requests only 100 mA). Board operation takes about 31 mA (MCU IDD1
<=7.0 mA, CP2102N 9.5 mA typ, three LEDs 6.2 mA, feedback 0.7 mA, button 0.33 mA, LDO IGND <=3.5 mA, VBUS bleed
3.33 mA); allow 40 mA, so USB is below 190 mA. An attached E1/E2/E2 Lite draws about 20 mA from VDD at 3.3 V
(R20UT1994EJ0940 section 2.5.4) and a low TOOL0 adds 3.3 mA through R16: with a probe fitted, keep external loads
at or below 130 mA. With 4.75 V USB, 0.70 ohm fuse and <=0.53 V diode, IN >=4.087 V;
this exceeds the 3.283 V rail plus TPS7A91's 0.20 V maximum dropout at 1 A. Worst-case
LDO power ignoring upstream drops: (5.25-3.283)*0.190 = 0.374 W. The datasheet's
62.5 C/W JEDEC thetaJA predicts 24 C rise, but that is not a measurement of this PCB;
check temperature on a prototype before raising the budget or ambient temperature.
The always-powered bridge/MCU/LED circuit has no USB SUSPEND load control, and the VBUS bleed
alone draws 5.0 V / 1.5 kohm = 3.33 mA, above USB 2.0's 2.5 mA suspend limit: this board does not
meet USB suspend current. Descriptor programming alone does not establish USB attach or inrush
compliance; these remain prototype validation items, including the input capacitor and downstream startup load.

Layout: the LDO output capacitor is the 3.3 V star point. One branch runs down the free strip outside
J2 to the header VDD pins, the debug connector and their own 10 uF + 100 nF; the MCU and the bridge each
have their own branch, so header current never passes the MCU's bypass capacitors or the crystal.
R01UH0146EJ0380 Figure 5-13(d) forbids a power or ground pattern under the XT1/XT2 wiring and the
resonator: pour keep-outs on both layers leave it bare. The load capacitors' ground (Figure 5-13(f)) is
one loop joined to the MCU's VSS node at a single point, so no other current flows through it.

"""

from __future__ import annotations

from ..design import NC, Board, Part, USB_C_EDGE
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
KMR2 = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
LED0603 = "LED_SMD:LED_0603_1608Metric"
HDR = "Connector_PinHeader_2.54mm:PinHeader_"


def res(ref, value, a, b, sch, desc, rot=0):
    return Part(ref, "Device:R_Small", value, R0402, sch, {"1": a, "2": b}, fields={"Description": desc}, sch_rotation=rot)


def cap(ref, value, a, b, sch, desc, fp=C0402, rot=0, mfr=None, mpn=None):
    fields = {"Description": desc}
    if mpn:
        fields.update({"Manufacturer": mfr, "MPN": mpn})
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields=fields, sch_rotation=rot)


def led(ref, value, anode, sch, mpn, desc):
    return Part(ref, "Device:LED_Small", value, LED0603, sch, {"A": anode, "K": "GND"},
                fields={"Manufacturer": "Kingbright", "MPN": mpn, "Description": desc})


W, H = 30.0, 100.0
ROW0 = H - 2.54                    # original setback; source does not dimension it
J1_PINS = ["GND", "+3V3", "P10", "P11", "P12", "P13", "P14", "P15", "P16", "P17",
           "P55", "P54", "P53", "P52", "P51", "P50", "P60", "P61", "P62", "P63", "P31", "P77",
           "P76", "P75", "P74", "P73", "P72", "P71", "P70", NC]
J2_PINS = ["GND", "+3V3", "P140", "P141", "P00", "P01", "P02", "P03", "P04", "P130", "P20", "P21",
           "P22", "P23", "P24", "P25", "P26", "P27", "RST_N", "P120", "P43", "P42", "P41", "P137",
           "P146", "P147", "P06", "P05", "P30", NC]

MCU_NETS = {
    "P120/ANI19": "P120", "P43": "P43", "P42/TO04": "P42", "P41/TO07": "P41", "P40/TOOL0": "TOOL0", "~{RESET}": "RESET",
    "P124/XT2": "XT2", "P123/XT1": "XT1", "P137/INTP0": "P137", "P122/X2": "P122", "P121/X1": "P121",
    "REGC": "REGC", "VSS": "GND", "EVSS0": "GND", "VDD": "+3V3", "EVDD0": "+3V3",
    "P60/SCLA0": "P60", "P61/SDAA0": "P61", "P62": "P62", "P63": "P63", "P31/TO03": "P31", "P77/KR7": "P77",
    "P76/KR6": "P76", "P75/KR5": "P75", "P74/KR4": "P74", "P73/KR3": "P73", "P72/KR2": "P72", "P71/KR1": "P71",
    "P70/KR0": "P70", "P06/TO06": "P06", "P05/TO05": "P05", "P30/INTP3": "P30",
    "P50/INTP1": "P50", "P51/INTP2": "P51", "P52": "P52", "P53": "P53", "P54": "P54", "P55": "P55",
    "P17/TO02": "P17", "P16/TO01": "P16", "P15/SCK20": "P15", "P14/RxD2": "P14", "P13/TxD2": "P13",
    "P12/TOOLTxD": "P12", "P11/TOOLRxD": "P11", "P10/SCK00": "P10", "P146": "P146", "P147/ANI18": "P147",
    "P27/ANI7": "P27", "P26/ANI6": "P26", "P25/ANI5": "P25", "P24/ANI4": "P24", "P23/ANI3": "P23", "P22/ANI2": "P22",
    "P21/AVREFM": "P21", "P20/AVREFP": "P20", "P130": "P130", "P04/SCK10": "P04", "P03/RxD1": "P03",
    "P02/TxD1": "P02", "P01/TO00": "P01", "P00/TI00": "P00", "P141/INTP7": "P141", "P140/INTP6": "P140",
}

PARTS = [
    Part("J3", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         (40, 105), {"VBUS": "VBUS", "GND": "GND", "CC1": "CC1", "CC2": "CC2", "D+": "USB_DP", "D-": "USB_DM",
                     "SBU1": NC, "SBU2": NC, "SHIELD": "GND"},
         fields={"Manufacturer": "Korean Hroparts", "MPN": "TYPE-C-31-M-12", "Description": "USB Type-C 5 V sink; HRO land pattern origin 3.19 mm from board edge"}),
    res("R1", "5.1k", "CC1", "GND", (75, 88), "Any vendor: 5.1 kohm 1% 1/16 W 0402; USB Type-C Rev.2.4 Table 4-28: sink CC1 Rd"),
    res("R2", "5.1k", "CC2", "GND", (90, 88), "Any vendor: 5.1 kohm 1% 1/16 W 0402; USB Type-C Rev.2.4 Table 4-28: sink CC2 Rd"),
    Part("U2", "Power_Protection:SP0503BAHT", "SP0503BAHTG", "Package_TO_SOT_SMD:SOT-143", (115, 105),
         {"1": "GND", "2": "USB_DP", "3": "USB_DM", "4": "VBUS"}, fields={"Manufacturer": "Littelfuse", "MPN": "SP0503BAHTG", "Description": "SP05xxBA datasheet: 5.5 V common-anode TVS, 30 pF typ; CP2102N Rev.1.5 Fig.2.5"}),
    Part("F1", "Device:Polyfuse_Small", "500mA", "Fuse:Fuse_1206_3216Metric", (145, 88), {"1": "VBUS", "2": "VBUS_F"},
         fields={"Manufacturer": "Littelfuse", "MPN": "1206L050YR", "Description": "1206L series: 0.50 A hold, 1.00 A trip, 6 V; R1max 0.70 ohm; derates to 0.42 A at 40 C"}),
    Part("D1", "Device:D_Schottky", "PMEG6010CEH", "Diode_SMD:D_SOD-123F", (170, 105), {"A": "VBUS_F", "K": "+5V"},
         fields={"Manufacturer": "Nexperia", "MPN": "PMEG6010CEH,115", "Description": "PMEG6010CEH v.4: 60 V 1 A Schottky, VF <=0.53 V at 0.5 A; USB reverse isolation"}),
    res("R7", "1.5k", "VBUS", "GND", (75, 130), "Any vendor: 1.5 kohm 1% 1/16 W 0402 (16.7 mW at 5 V); VBUS bleed: with 69.6 kohm divider, 0.5 mA leakage gives 0.734 V; PMEG6010CEH reverse-leakage characteristic", rot=90),
    Part("U4", "Regulator_Linear:TPS7A91", "TPS7A91", "Package_DFN_QFN:Texas_S-PDSO-N10_EP1.2x2mm", (235, 108),
         {"IN": "+5V", "EN": "+5V", "SS_CTRL": "GND", "NR/SS": "LDO_NR", "FB": "LDO_FB", "OUT": "+3V3", "PG": NC, "GND": "GND"},
         fields={"Manufacturer": "Texas Instruments", "MPN": "TPS7A9101DSKR", "Description": "TPS7A91 SBVS282A: 1 A adjustable LDO, nominal 3.283 V, 1% accuracy, thermal pad grounded"}),
    cap("C13", "10u", "+5V", "GND", (205, 88), "Any vendor: 10 uF 10% 10 V X5R 0805; input capacitor, TI TPS7A91 SBVS282A section 7.1.3 (>=10 uF nominal, 50% derating included)", C0805),
    cap("C14", "10u", "+3V3", "GND", (270, 88), "Any vendor: 10 uF 10% 10 V X5R 0805; output capacitor, TI TPS7A91 SBVS282A section 7.1.3 (10 uF nominal, 50% derating included)", C0805),
    cap("C15", "10n", "LDO_NR", "GND", (215, 132), "Any vendor: 10 nF 10% 16 V X7R 0402; noise reduction/soft-start, TI TPS7A91 SBVS282A section 7.1.2.2"),
    res("R8", "3.57k 0.1%", "+3V3", "LDO_FB", (265, 122), "Any vendor: 3.57 kohm 0.1% 25 ppm/C thin film 1/16 W 0402; feedback upper resistor, TI SBVS282A Table 7-1 gives 3.283 V with 1.15 kohm lower", rot=90),
    res("R9", "1.15k 0.1%", "LDO_FB", "GND", (265, 142), "Any vendor: 1.15 kohm 0.1% 25 ppm/C thin film 1/16 W 0402; feedback lower resistor, TI SBVS282A Table 7-1", rot=90),
    res("R10", "680", "LED_PWR_A", "+3V3", (295, 105), "Any vendor: 680 ohm 1% 1/16 W 0402; (3.283-1.9)/680 = 2.03 mA, Kingbright APTD1608LCGCK VF typical at 2 mA"),
    led("D2", "PWR", "LED_PWR_A", (310, 105), "APTD1608LCGCK", "Kingbright APTD1608LCGCK low-current green LED, 1.9 V typical at 2 mA"),
    Part("U3", "Interface_USB:CP2102N-Axx-xQFN24", "CP2102N-A02-GQFN24", "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
         (150, 255), {"GND": "GND", "D+": "USB_DP", "D-": "USB_DM", "VIO": "+3V3", "VDD": "+3V3", "VREGIN": "+3V3",
                      "VBUS": "CP_VBUS", "~{RST}": "CP_RST", "RXD": "P13", "TXD": "P14", "~{DTR}": NC,
                      **{p: NC for p in ("NC", "~{RI}/CLK", "~{WAKEUP}/GPIO.3", "RS485/GPIO.2", "~{RXT}/GPIO.1",
                                         "~{TXT}/GPIO.0", "~{SUSPEND}", "SUSPEND", "~{CTS}", "~{RTS}", "~{DSR}", "~{DCD}")}},
         fields={"Manufacturer": "Silicon Labs", "MPN": "CP2102N-A02-GQFN24R", "Description": "CP2102N Rev.1.5 Fig.2.3: VIO/VDD/VREGIN from board rail, internal regulator unused"}),
    cap("C16", "4.7u", "+3V3", "GND", (195, 230), "Any vendor: 4.7 uF 10% 10 V X5R 0603; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VDD bypass", C0603),
    cap("C17", "100n", "+3V3", "GND", (210, 230), "Any vendor: 100 nF 10% 10 V X7R 0402; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VDD bypass"),
    cap("C18", "4.7u", "+3V3", "GND", (225, 230), "Any vendor: 4.7 uF 10% 10 V X5R 0603; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VIO bypass", C0603),
    cap("C19", "100n", "+3V3", "GND", (240, 230), "Any vendor: 100 nF 10% 10 V X7R 0402; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VIO bypass"),
    res("R11", "1k", "CP_RST", "+3V3", (195, 280), "Any vendor: 1 kohm 1% 1/16 W 0402; CP2102N RSTb pull-up, Silicon Labs CP2102N Rev.1.5 Fig.2.3"),
    res("R5", "22.1k", "VBUS", "CP_VBUS", (100, 240), "Any vendor: 22.1 kohm 1% 1/16 W 0402; CP2102N VBUS divider upper (47.5 kohm lower), Silicon Labs CP2102N Rev.1.5 Fig.2.5", rot=90),
    res("R6", "47.5k", "CP_VBUS", "GND", (100, 262), "Any vendor: 47.5 kohm 1% 1/16 W 0402; CP2102N VBUS divider lower (22.1 kohm upper), Silicon Labs CP2102N Rev.1.5 Fig.2.5", rot=90),

    cap("C20", "4.7u", "+3V3", "GND", (255, 230), "Any vendor: 4.7 uF 10% 10 V X5R 0603; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VREGIN bypass", C0603),
    cap("C21", "100n", "+3V3", "GND", (270, 230), "Any vendor: 100 nF 10% 10 V X7R 0402; Silicon Labs CP2102N Rev.1.5 Fig.2.3 VREGIN bypass"),
    res("R21", "10k", "P121", "GND", (540, 380), "Any vendor: 10 kohm 1% 1/16 W 0402; unused input-only P121: Renesas R01UH0146EJ0380 Table 2-3 requires resistor to VSS; 10 kohm limits 1 uA leakage to 10 mV"),
    res("R22", "10k", "P122", "GND", (555, 380), "Any vendor: 10 kohm 1% 1/16 W 0402; unused input-only P122: Renesas R01UH0146EJ0380 Table 2-3 requires resistor to VSS; 10 kohm limits 1 uA leakage to 10 mV"),
    Part("U1", "EoS_MCU:R5F100LEAFB", "R5F100LEAFB", "Package_QFP:LQFP-64_10x10mm_P0.5mm", (420, 235), MCU_NETS,
         fields={"Manufacturer": "Renesas", "MPN": "R5F100LEAFB#10", "Description": "RL78/G13 64 KB code flash, 4 KB data flash, 4 KB RAM, LFQFP-64; R01DS0131EJ0380 sections 1.1-1.3.11"}),
    cap("C1", "100n", "+3V3", "GND", (330, 140), "Any vendor: 100 nF 10% 10 V X7R 0402; VDD bypass, Renesas R01UH0146EJ0380 section 2.2 (0.1 uF shortest path to VSS)"),
    cap("C2", "100n", "+3V3", "GND", (345, 140), "Any vendor: 100 nF 10% 10 V X7R 0402; EVDD0 bypass, Renesas R01UH0146EJ0380 section 2.2 (0.1 uF shortest path to EVSS0)"),
    cap("C3", "680n", "REGC", "GND", (360, 140), "680 nF 35 V X7R 10% 0805 REGC bypass; RL78 R01UH0146EJ0380 section 23.1: 0.47-1 uF at 1.8/2.1 V; see README derating evidence", fp=C0805, mfr="Murata", mpn="GCM21BR7YA684KA55L"),
    Part("Y1", "Device:Crystal", "32.768kHz", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", (500, 205), {"1": "XT2", "2": "XT1"},
         fields={"Manufacturer": "NDK", "MPN": "NX3215SA-32.768K-STD-MUA-14", "Description": "NX3215SA: 32.768 kHz CL 6 pF ESR <=70 kohm; Renesas R01UH0146EJ0380 section 5.7 matching table"}),
    cap("C4", "7p C0G", "XT1", "GND", (485, 225), "Any vendor: 7 pF +/-0.25 pF C0G (NP0) 50 V 0402; Renesas R01UH0146EJ0380 section 5.7 XT1 resonator table, NX3215SA CL=6 pF"),
    cap("C5", "7p C0G", "XT2", "GND", (515, 225), "Any vendor: 7 pF +/-0.25 pF C0G (NP0) 50 V 0402; Renesas R01UH0146EJ0380 section 5.7 XT1 resonator table, NX3215SA CL=6 pF"),

    Part("J4", "Connector_Generic:Conn_02x07_Odd_Even", "E2 Lite", HDR + "2x07_P2.54mm_Vertical",
         (505, 305), {"1": NC, "2": "GND", "3": NC, "4": NC, "5": "TOOL0", "6": "RST_N", "7": NC, "8": "+3V3",
                      "9": "+3V3", "10": "E2_RSTOUT", "11": NC, "12": "GND", "13": "E2_RSTOUT", "14": "GND"},
         fields={"Description": "Any vendor: 2x7 2.54 mm male pin header, vertical through-hole, gold, unshrouded and unkeyed (see README); Renesas E1/E2/E2 Lite pinout, R20UT1994EJ0940 Table 2-2; disable probe target-power output; connect with power off"}),
    Part("JP1", "Connector_Generic:Conn_01x03", "RESET SEL", HDR + "1x03_P2.54mm_Vertical", (470, 350),
         {"1": "RST_N", "2": "RESET", "3": "E2_RSTOUT"},
         fields={"Description": "Any vendor: 1x3 2.54 mm male pin header, vertical through-hole, gold; also order 1 x 2.54 mm two-position jumper shunt (1-2 user reset, 2-3 external probe); Renesas R20UT1994EJ0940 Fig.2-10"}),
    res("R14", "22k", "RST_N", "+3V3", (470, 380), "Any vendor: 22 kohm 1% 1/16 W 0402; user-reset pull-up, R01DS0131EJ0380 DC leakage <=1 uA gives <=22 mV droop; shunt separates this from E2 RESET_OUT", rot=90),
    res("R15", "10k", "RESET", "+3V3", (485, 380), "Any vendor: 10 kohm 1% 1/16 W 0402; RESET pull-up, R20UT1994EJ0940 Fig.2-11 asks 1-10 kohm where RESET_OUT alone drives RESET (JP1 2-3); 0.33 mA while held low", rot=90),
    res("R16", "1k", "TOOL0", "+3V3", (500, 380), "Any vendor: 1 kohm 1% 1/16 W 0402; TOOL0 pull-up, Renesas R20UT1994EJ0940 Fig.2-5", rot=90),
    Part("SW1", "Switch:SW_Push", "RESET", KMR2, (470, 335), {"1": "RST_N", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221GLFS", "Description": "C&K KMR221GLFS momentary reset switch, active low"}),
    Part("SW2", "Switch:SW_Push", "USER", KMR2, (330, 330), {"1": "P137", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221GLFS", "Description": "C&K KMR221GLFS momentary user switch on input-only P137/INTP0"}),
    res("R17", "10k", "P137", "+3V3", (315, 315), "Any vendor: 10 kohm 1% 1/16 W 0402; input-only P137 pull-up, R01DS0131EJ0380 DC input leakage <=1 uA gives <=10 mV droop, held button draws 0.328 mA", rot=90),
    res("R18", "750", "LED1_A", "P17", (360, 360), "Any vendor: 750 ohm 1% 1/16 W 0402; (3.283-1.75)/750 = 2.04 mA nominal, Kingbright APTD1608LSURCK VF at 2 mA"),
    led("D3", "LED1", "LED1_A", (375, 360), "APTD1608LSURCK", "Kingbright APTD1608LSURCK low-current red LED, 1.75 V typical at 2 mA; P17 active-high"),
    res("R19", "680", "LED2_A", "P16", (360, 375), "Any vendor: 680 ohm 1% 1/16 W 0402; (3.283-1.85)/680 = 2.11 mA nominal, Kingbright APTD1608LSYCK VF at 2 mA"),
    led("D4", "LED2", "LED2_A", (375, 375), "APTD1608LSYCK", "Kingbright APTD1608LSYCK low-current yellow LED, 1.85 V typical at 2 mA; P16 active-high"),
    Part("J1", "Connector:Conn_01x30_Pin", "J1", HDR + "1x30_P2.54mm_Vertical", (560, 90),
         {str(i + 1): n for i, n in enumerate(J1_PINS)}, fields={"Description": "Any vendor: 1x30 2.54 mm male pin header, vertical through-hole, gold, fitted on the top side; Renesas R01UH0243ED0000 Table 5 pinout, VDD=3.3 V output only, P13/P14 shared with USB UART"}),
    Part("J2", "Connector:Conn_01x30_Pin", "J2", HDR + "1x30_P2.54mm_Vertical", (600, 90),
         {str(i + 1): n for i, n in enumerate(J2_PINS)}, fields={"Description": "Any vendor: 1x30 2.54 mm male pin header, vertical through-hole, gold, fitted on the top side; Renesas R01UH0243ED0000 Table 6 pinout, VDD=3.3 V output only"}),
    # local bulk at the header VDD outputs, on their own feed from the LDO (review M1)
    cap("C22", "10u", "+3V3", "GND", (560, 380), "Any vendor: 10 uF 10% 10 V X5R 0805; header/debug VDD bulk, TI TPS7A91 SBVS282A section 5.3 (COUT >= 10 uF, no maximum)", C0805),
    cap("C23", "100n", "+3V3", "GND", (575, 380), "Any vendor: 100 nF 10% 10 V X7R 0402; header/debug VDD high-frequency bypass"),
]

X0 = 21.0          # USB-C centre
X3 = X0 - 0.75     # ESD and CP2102N centre line
MX, MY = 15.0, 44.0
PLACEMENT = {
    "J1": (27.70, ROW0, 180), "J2": (2.30, ROW0, 180),
    # Pin 1 at the lower left: pins 17-29 (P60-P70) face J1 and pins 49-64 (P27-P20, P130,
    # P04-P00, P141, P140) face J2, each row in its header's order, so both fan straight out.
    # Turned the other way (270), both rows faced the wrong header and had to wrap round the chip.
    "U1": (MX, MY, 90),
    # USB-C on the top edge, ESD and CP2102N straight below (EoS MSP430G2 Board's arrangement, turned 180 degrees)
    "J3": (X0, USB_C_EDGE, 180), "U2": (X3, 12.40, 180), "U3": (X3, 17.30, 270),
    "R1": (X0 + 3.0, 10.40, 180), "R2": (X0 - 2.45, 9.40, 180),
    # VBUS west to the fuse and Schottky, then the LDO by the left header's 3V3 and 5V pins
    "F1": (12.8, 5.4, 90), "D1": (8.0, 5.4, 90), "R7": (15.4, 12.4, 90),
    "U4": (8.0, 11.4, 0), "C13": (13.4, 9.5, 90), "C15": (11.1, 11.4, 0),
    "C14": (4.3, 10.7, 90), "R8": (6.3, 14.4, 90), "R9": (7.5, 14.4, 270),
    # CP2102N: its supply pins (VIO 5, VDD 6, VREGIN 7) come first round its top-left corner, then
    # VBUS sense (8) and RSTb (9). So the bypass capacitors sit in one row west of the chip on a
    # 3.3 V bus from pin 7, ground pads to the north; the VBUS divider sits below that bus and the
    # RSTb pull-up below the chip, so neither line has to cross the supply.
    "C21": (17.15, 15.62, 90), "C17": (16.2, 15.62, 90), "C19": (15.25, 15.62, 90),
    "C16": (14.0, 15.33, 90), "C18": (12.45, 15.33, 90), "C20": (10.9, 15.33, 90),
    "R6": (15.6, 17.4, 180), "R5": (15.6, 18.6, 0), "R11": (19.0, 21.5, 270),
    "SW2": (8.2, 22.4, 0), "R17": (8.2, 25.4, 0),
    # RL78 supplies, REGC, the sub-clock crystal and the X1/X2 pull-downs below the system side:
    # the cluster as before, turned 180 degrees with the chip about its centre, except: C3 sits
    # 0.15 mm further west, so pin 14 reaches C1 directly; C2 sits under C1, 3.3 V under 3.3 V and
    # ground under ground, so no ground route rings the 3.3 V pins (both 0.15 mm east, keeping their 3.3 V
    # side 1.5 mm from the crystal's load capacitor); and R21/R22 sit beside the
    # corner the P121/P122 lines leave by, not below the cluster.
    "C1": (18.85, 52.6, 180), "C2": (18.85, 54.0, 180), "C3": (16.6, 52.65, 270),
    "Y1": (14.5, 55.95, 180), "C4": (17.28, 55.95, 270), "C5": (11.72, 55.95, 270),
    "R21": (20.9, 52.3, 270), "R22": (20.9, 54.2, 270),
    # TOOL0 pull-up and RESET keeper outside the lower-left corner, where boxed pins 5-6 escape
    "R16": (9.9, 51.4, 180), "R15": (9.9, 52.6, 180),
    # bottom: jumper, reset, E2 Lite connector on the bottom edge
    "JP1": (10.18, 64, 0),
    "R14": (10.18, 61.2, 90), "SW1": (10.68, 73.5, 0),
    "J4": (7.38, 88, 90),
    # the header/debug VDD bulk pair, on the bus between J2.2 and J1.2 below the debug connector
    "C23": (12.5, 92.4, 90), "C22": (15.0, 92.0, 90),
    # power and user LEDs in a row below the supply cluster; R10 is the cluster's 3.3 V feed point
    "R10": (19.2, 59.2, 90), "D2": (19.2, 61.7, 90), "R18": (20.8, 59.2, 90), "D3": (20.8, 61.7, 90),
    "R19": (20.8, 65.6, 90), "D4": (20.8, 68.1, 90),
}
PRIORITY = [(("J3", "A6"), ("U2", "2")), (("J3", "A7"), ("U2", "3")), (("J3", "B4"), ("U2", "4")),
            (("U2", "3"), ("U3", "4")), (("U2", "2"), ("U3", "3")),
            (("J3", "B6"), ("U2", "2"), "join"), (("J3", "B7"), ("U2", "3"), "join"),
            # Escape the bridge sense/reset pins before its supply bypass loops enclose them.
            (("U3", "8"), ("R6", "1")), (("R5", "2"), ("R6", "1"), "join"),
            (("U3", "9"), ("R11", "1")),
            (("U1", "7"), ("Y1", "1")), (("Y1", "1"), ("C5", "1")),
            (("U1", "8"), ("Y1", "2")), (("Y1", "2"), ("C4", "1")), (("C4", "2"), ("C5", "2")),
            (("U1", "15"), ("C1", "1")), (("U1", "14"), ("C1", "2")), (("U1", "13"), ("U1", "14"), "join"),
            (("U1", "16"), ("U1", "15"), "join"),
            (("C2", "1"), ("C1", "1")), (("C2", "2"), ("C1", "2")),
            (("U1", "12"), ("C3", "1")), (("C3", "2"), ("C1", "2")),
            # The load capacitors' ground loop meets the MCU's VSS node at one point, C2's ground
            # pad (R01UH0146EJ0380 Figure 5-13(f)): no other ground touches the loop.
            (("C4", "2"), ("C2", "2")),
            # the power LED hangs off the supply cluster, south of it and clear of the crystal
            (("C2", "1"), ("R10", "2")),
            # 3.3 V distribution, all laid here so the router adds no branch of its own (review M1).
            # C14, the LDO output capacitor, is the star point. (1) Headers and debug connector: down
            # the free strip outside J2, then a bus along the bottom edge through their own 10 uF +
            # 100 nF to J1.2, J4 joined to it; the reset/TOOL0 pull-ups take their 3.3 V from J4.8.
            (("C14", "1"), ("J2", "2")),
            (("J2", "2"), ("C23", "1")), (("C23", "1"), ("C22", "1")), (("C22", "1"), ("J1", "2")),
            (("J4", "9"), ("C22", "1"), "join"), (("J4", "8"), ("J4", "9"), "join"),
            # (2) the bridge: through the feedback divider's sense end to its bypass bus
            (("C14", "1"), ("R8", "1")), (("R8", "1"), ("C20", "1")), (("R17", "2"), ("R8", "1")),
            # (3) the MCU: from the same sense point to R11, then the trunk down the free strip
            # inside the MCU's right pad row (those pins all escape outward)
            (("R8", "1"), ("R11", "2")), (("R11", "2"), ("C1", "1")),
            (("U1", "11"), ("R21", "1")), (("U1", "10"), ("R22", "1")),
            (("J2", "24"), ("U1", "9")),
            # Boxed TOOL0 and RESET pins: only the short escape to their resistors at the
            # lower-left corner is laid here; the autorouter carries them on to J4 and JP1.
            (("U1", "5"), ("R16", "1")), (("U1", "6"), ("R15", "1")),
            # their pull-ups' 3.3 V from the header feed at J4.8, nowhere near the crystal
            (("R16", "2"), ("R15", "2")), (("R15", "2"), ("R14", "2")), (("R14", "2"), ("J4", "8")),
            (("U3", "2"), ("U3", "25")),
            # the bridge's three supply pins joined at the chip, then its bypass row on one bus
            (("U3", "5"), ("U3", "6"), "join"), (("U3", "7"), ("U3", "6"), "join"),
            (("C21", "1"), ("U3", "7")), (("C17", "1"), ("C21", "1")), (("C19", "1"), ("C17", "1")),
            (("C16", "1"), ("C19", "1")), (("C18", "1"), ("C16", "1")), (("C20", "1"), ("C18", "1")),
            (("U4", "8"), ("C15", "1")), (("U4", "3"), ("R8", "2")),
            (("U4", "9"), ("C13", "1")), (("U4", "10"), ("U4", "9"), "join"),
            (("U4", "1"), ("C14", "1")), (("U4", "2"), ("U4", "1"), "join"),
            # Schottky into the input capacitor, then EN (pin 7) round C15 to the +5V copper. That
            # loop encloses C15's ground pad: tight, it left the pour there an island with no via.
            (("D1", "1"), ("C13", "1")), (("U4", "7"), ("C13", "1"), "join")]
# Header GPIO lines are left to the autorouter: laid first as long fixed routes, each one
# took the shortest way along the pad ends and sealed in its neighbours (P77 had no escape).
# Top-layer keep-outs (EoS MSP430G2 Board's, turned with the receptacle): in front of the receptacle's data
# pads, so neither duplicated contact is joined under the shell; and west of the ESD array's D- and VBUS pins,
# so the data lines leave through its middle and VBUS comes in from the west, below the keep-out.
KEEPOUTS = [(X0 - 1.15, 4.50, X0 + 1.15, 6.45), (X3 - 2.65, 10.60, X3 - 1.45, 13.10),
            # east of J2's top pin, on both layers: the header feed from C14 takes the strip outside
            # J2 rather than the one inside it, where the J2 pin fan-out runs
            (3.20, 21.00, 5.40, 25.20), (3.20, 21.00, 5.40, 25.20, "B.Cu"),
            # beside C15's ground pad, inside the +5V loop that EN closes round the NR/SS line: the loop
            # goes round this room, so the pour there keeps space for its own ground via. On the bottom
            # too: a VBUS track under the room left no spot that cleared it, and the pad's pour an island.
            (11.95, 11.20, 13.30, 12.40), (11.95, 11.20, 13.30, 12.40, "B.Cu"),
            # the pockets below the boxed pins 9-11 and 5-6, beside the crystal's lines: no track or via there.
            # The second starts 0.95 mm below the pads, so TOOL0 and RESET leave outward and turn west at once.
            (14.97, 50.60, 16.37, 53.00), (12.92, 51.40, 14.02, 52.80),
            # inside the crystal pins 7-8: P137 (pin 9) drops through a via here instead of running
            # along the inner pad ends and sealing pins 1-6 in
            (13.90, 46.60, 14.95, 48.75),
            # the crystal on the bottom layer: nothing under Y1, its loads and its ground loop, or
            # under the XT lines from pins 7-8; on top, a strip off C5's XT2 pad
            (11.20, 53.60, 17.90, 57.60, "B.Cu"), (13.70, 50.50, 15.30, 53.60, "B.Cu"),
            # On top, round the load capacitors' ground loop on its west, south and east sides: the
            # autorouter joins ground pads with tracks, and it ran SW1's ground into that loop. Now the
            # loop meets ground only through its route to C2 (R01UH0146EJ0380 Figure 5-13(f)).
            (10.65, 53.80, 11.25, 58.05), (11.25, 57.45, 18.75, 58.05), (18.15, 55.20, 18.75, 57.45),
            # Keep the middle on the bottom layer, with an inward via corridor beside
            # both 0.5 mm pad rows. A boundary at +/-4.7 mm blocked those escapes.
            (MX - 4.0, MY - 2.7, MX + 4.0, MY + 2.7)]

_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "USB UART", "x": 15.0, "y": 27.5, "size": 0.8},
    {"text": "RESET SEL", "x": 15.4, "y": 66.2, "size": 0.8},
    {"text": "1-2 RUN", "x": 14.6, "y": 67.5, "size": 0.8},
    {"text": "2-3 E2", "x": 14.6, "y": 68.8, "size": 0.8},
    {"text": "RESET", "x": 10.68, "y": 76.2, "size": 0.8},
    {"text": "USER", "x": 8.2, "y": 19.9, "size": 0.8},
    {"text": "PWR", "x": 18.4, "y": 63.9, "size": 0.8},
    {"text": "P17", "x": 21.6, "y": 63.9, "size": 0.8},
    {"text": "P16", "x": 20.8, "y": 70.2, "size": 0.8},
    {"text": "E2 TOOL0", "x": 15.0, "y": 81.5, "size": 0.8},
    {"text": "1", "x": 7.38, "y": 90.2, "size": 0.8},
    {"text": "J2 1 GND", "x": 7.0, "y": 95.0, "size": 0.8},
    {"text": "J1 1 GND", "x": 23.0, "y": 95.0, "size": 0.8},
    {"text": "EoS RL78G13 Board  rev A", "x": 15.0, "y": 80.0, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 15.0, "y": 82.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 15.0, "y": 83.4, "size": 0.8, "layer": "B_SilkS", "mirror": True},
]

BOARD = Board(
    name="eos-rl78g13-board",
    title="EoS RL78G13 Board",
    revision="A",
    date="2026-10-12",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["Board envelope 30 x 100 mm and header separation 25.4 mm: Renesas R01UH0243ED0000 Rev.1.0 p.70 dimension callouts only; "
             "30-way header pitch and pinout: pp.18-20. Longitudinal header offset and circuit/layout are original."],
    width=W,
    height=H,
    corner_radius=1.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    priority_routes=PRIORITY,
    router_keepouts=KEEPOUTS,
    # R01UH0146EJ0380 Figure 5-13(d): no power or ground pattern under the XT1/XT2 wiring or the
    # resonator, on either layer; the top keep-out also keeps the pour off the load capacitors'
    # ground loop, so that loop meets ground only at C2 (Figure 5-13(f))
    pour_keepouts=[(11.20, 50.40, 17.90, 57.10, "B.Cu"), (13.80, 50.45, 15.20, 55.05, "F.Cu"),
                   (11.15, 54.85, 17.85, 57.75, "F.Cu")],
    # a ground via beside each bypass capacitor's ground pad: the CP2102N row (review M3), the MCU's
    # supply pair, the LDO and its input capacitor (m6), the ESD array (m5) and the header bulk pair;
    # and beside the VBUS divider's ground end, whose pour the bypass bus and VBUS wall in
    ground_vias=["C1", "C2", "C16", "C17", "C18", "C19", "C20", "C21", "C13", "U4", "U2", "C22", "C23", "R6"],
    # ground vias turn away from the crystal, so none lands under it
    fanout_avoid=[(16.0, 54.0)],
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"},
    flagged_nets=["GND", "VBUS", "VBUS_F", "+5V"],
    headings=[((35, 76), "USB-C, protection and 3.283 V supply"), ((95, 205), "USB UART2: P13 TX / P14 RX"),
              ((350, 112), "RL78/G13 supplies and 32.768 kHz subclock"), ((470, 280), "External E1/E2 TOOL0 and reset selection"),
              ((550, 65), "30-pin expansion headers: 3.3 V only")],
    notes=[((260, 440), "EoS RL78G13 Board, rev A. Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "USB-only power. Header VDD is 3.283 V output; disable target power on an external probe.\n"
                       "JP1: 1-2 RUN/user reset; 2-3 E1/E2 reset. Connect the debug cable with power off.\n"
                       "J1/J2: R01UH0243ED0000 pp.18-20 pinout, p.70 dimension callouts only; original 2.54 mm end offset.\n"
                       "Sources: R01DS0131EJ0380, R01UH0146EJ0380, R20UT1994EJ0940; CP2102N Rev.1.5; TPS7A91 SBVS282A.\n"
                       "External VDD loads share 150 mA only after CP2102N Max Power=0xFA and host configuration\n"
                       "(130 mA with an E1/E2/E2 Lite fitted); before configuration or with the factory 100 mA\n"
                       "descriptor, keep external load <=50 mA. USB suspend current is not met (VBUS bleed 3.33 mA).")],
    maze_via_cost_mm=5.0,
    netclasses={"Power": {"track": 0.4, "clearance": 0.15}, "Supply": {"track": 0.3, "clearance": 0.15},
                "USB": {"track": 0.2, "clearance": 0.15}, "Ground": {"track": 0.25, "clearance": 0.15}},
    net_to_class={"VBUS": "Power", "VBUS_F": "Power", "+5V": "Supply", "+3V3": "Supply", "REGC": "Supply",
                  "USB_DP": "USB", "USB_DM": "USB", "GND": "Ground"},
)
