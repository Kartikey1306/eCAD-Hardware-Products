"""EoS Sense Cape: a sensor cape for BeagleBoard.org PocketBeagle, designed by Kartikeydheer Srivastava.

Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved: this design file is not under
the repository's MIT licence; see boards/eos/eos-sense-cape/LICENSE.txt.

PocketBeagle plugs in on top through two 2x18 sockets placed exactly where its P1 and P2
headers are. Its outline and header positions are read from BeagleBoard.org's own PocketBeagle
board file (CC BY 4.0): a 55 x 35 mm board with 10 mm corners, P2 centred at (27.5, 4.8) mm
and P1 at (27.5, 30.2) mm. The cape runs 25 mm further down, so its sensors, LEDs and buttons
are not under PocketBeagle.

Every value follows the part's datasheet:

* BME280 (temperature, humidity, pressure) on I2C1 at 0x76: CSB tied directly to VDDIO selects
  I2C, and SDO to GND gives 0x76; 100 nF on VDD and on VDDIO (Bosch BST-BME280-DS002).
* LIS3DH accelerometer on I2C1 at 0x18: CS tied high selects I2C, and SA0 to GND gives 0x18;
  RES (pin 10) to GND; ADC1-3 unused, left open; 100 nF ceramic and 10 uF aluminium at pin 14
  (ST DocID 17530). INT1 goes to P2.03.
* Each address pin reaches GND through a 3-pad solder jumper bridged to GND as delivered (JP2
  for the BME280, JP3 for the LIS3DH); re-bridged to 3.3 V they answer at 0x77 and 0x19.
* APDS-9306-065 ambient light sensor on I2C1 at 0x52 (its only address): 1 uF bypass, 10 kohm
  pull-up on the open-drain INT, which goes to P2.06 (Broadcom AV02-4755EN).
* 24LC256 EEPROM on I2C2 at 0x57 for the cape's identity: A0-A2 tied high; WP must be tied
  high or low (Microchip DS20001203), so it goes through a solder jumper, bridged to GND (write
  enabled) as delivered.
* PocketBeagle has no pull-ups on I2C1 or I2C2 (no resistor touches those nets in its board
  file), so the cape fits 4.7 kohm on each line.
* Analog inputs use only AIN5 (P2.35) and AIN6 (P1.02). PocketBeagle feeds those through its
  own 10 kohm + 10 kohm divider (its R5 array), so 0-3.3 V arrives at the processor as
  0-1.65 V, under the 1.8 V limit by construction. The 1.8 V-only inputs (AIN0-4, AIN7) carry
  nothing from the cape. AIN5 reads a 10 kohm NTC against a 10 kohm 0.1 % resistor from 3.3 V.
  AIN6 reads a 10 kohm trimmer across 3.3 V.
* Two buttons (P2.02, P2.04) with 10 kohm pull-ups and 100 nF debounce, and two LEDs on the
  PWM outputs P1.36 (PWM0A) and P2.01 (PWM1A).
* A Qwiic / STEMMA QT connector on I2C1 (pin 1 GND, 2 3.3 V, 3 SDA, 4 SCL).

Power is PocketBeagle's 3.3 V output (VDD_3V3B on P1.14 and P2.23). The cape draws under 15 mA
with both LEDs lit.
"""

from __future__ import annotations

from ..design import NC, Board, Part
from .owner import CONTACT, LICENCE, LICENCE_TERMS, OWNER

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
SOCKET_MODEL = ("${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_2x18_P2.54mm_Vertical.step",
                (2.54, 0.0, 0.0))   # the socket model's second row sits on the header footprint's


def res(ref, value, a, b, sch, desc=None, mpn=None):
    return Part(ref, "Device:R_Small", value, R0603, sch, {"1": a, "2": b},
                fields={"Description": desc or f"Resistor {value} 1% 0603", **({"MPN": mpn} if mpn else {})})


def cap(ref, value, a, b, sch, desc, fp=C0603):
    return Part(ref, "Device:C_Small", value, fp, sch, {"1": a, "2": b}, fields={"Description": desc})


# PocketBeagle's header signals, by pin, as its own board file names them. Pins the cape does not
# use are left unconnected (NC), so the sockets pass them through untouched.
P1 = {14: "+3V3", 15: "GND", 16: "GND", 22: "GND", 2: "AIN6", 26: "I2C2_SDA", 28: "I2C2_SCL", 36: "LED1"}
P2 = {23: "+3V3", 15: "GND", 21: "GND", 9: "I2C1_SCL", 11: "I2C1_SDA", 1: "LED2", 2: "BTN1", 4: "BTN2",
      3: "ACC_INT1", 6: "ALS_INT", 35: "AIN5"}

W, H = 55.0, 60.0
P2_PIN1 = (27.5 - 21.59, 4.8 + 1.27)     # PocketBeagle: P2 centre (27.5, 4.8), pin 1 at (-21.59, +1.27)
P1_PIN1 = (27.5 - 21.59, 30.2 + 1.27)    # P1 centre (27.5, 30.2)

PARTS = [
    # ---- PocketBeagle sockets -------------------------------------------------------------------
    Part("J1", "Connector_Generic:Conn_02x18_Odd_Even", "PocketBeagle P1",
         "Connector_PinHeader_2.54mm:PinHeader_2x18_P2.54mm_Vertical", (60, 120),
         {str(n): P1.get(n, NC) for n in range(1, 37)}, model=SOCKET_MODEL,
         fields={"Manufacturer": "Samtec", "MPN": "SSW-118-01-T-D",
                 "Description": "Socket 2x18 2.54 mm for PocketBeagle P1 (pin numbers as on PocketBeagle)"}),
    Part("J2", "Connector_Generic:Conn_02x18_Odd_Even", "PocketBeagle P2",
         "Connector_PinHeader_2.54mm:PinHeader_2x18_P2.54mm_Vertical", (60, 230),
         {str(n): P2.get(n, NC) for n in range(1, 37)}, model=SOCKET_MODEL,
         fields={"Manufacturer": "Samtec", "MPN": "SSW-118-01-T-D",
                 "Description": "Socket 2x18 2.54 mm for PocketBeagle P2 (pin numbers as on PocketBeagle)"}),
    cap("C1", "10u", "+3V3", "GND", (120, 330), "Capacitor 10 uF 10 V X5R 0805 (3.3 V entry)", C0805),

    # ---- I2C1: sensors and Qwiic ------------------------------------------------------------------
    res("R1", "4.7k", "I2C1_SDA", "+3V3", (150, 90), "Resistor 4.7 kohm 1% 0603 (I2C1 SDA pull-up)"),
    res("R2", "4.7k", "I2C1_SCL", "+3V3", (165, 90), "Resistor 4.7 kohm 1% 0603 (I2C1 SCL pull-up)"),
    Part("U1", "Sensor:BME280", "BME280", "Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
         (200, 110), {"VDD": "+3V3", "VDDIO": "+3V3", "GND": "GND", "CSB": "+3V3", "SDI": "I2C1_SDA",
                      "SCK": "I2C1_SCL", "SDO": "BME_SDO"},
         fields={"Manufacturer": "Bosch Sensortec", "MPN": "BME280",
                 "Description": "Temperature, humidity and pressure sensor, I2C 0x76"}),
    cap("C2", "100n", "+3V3", "GND", (225, 100), "Capacitor 100 nF X7R 0603 (BME280 VDD)"),
    Part("JP2", "Jumper:SolderJumper_3_Bridged12", "0x76", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         (200, 140), {"A": "GND", "C": "BME_SDO", "B": "+3V3"},
         fields={"Description": "BME280 address: 1-2 (as delivered) 0x76, cut and bridge 2-3 for 0x77"}),
    cap("C3", "100n", "+3V3", "GND", (240, 100), "Capacitor 100 nF X7R 0603 (BME280 VDDIO)"),
    Part("U2", "Sensor_Motion:LIS3DH", "LIS3DH", "Package_LGA:LGA-16_3x3mm_P0.5mm_LayoutBorder3x5y",
         (200, 180), {"VDD": "+3V3", "VDD_IO": "+3V3", "GND": "GND", "10": "GND", "12": "GND",
                      "CS": "+3V3", "SPC": "I2C1_SCL", "SDI": "I2C1_SDA", "SDO": "ACC_SA0",
                      "INT1": "ACC_INT1", "INT2": NC, "ADC1": NC, "ADC2": NC, "ADC3": NC, "2": NC, "3": NC},
         fields={"Manufacturer": "STMicroelectronics", "MPN": "LIS3DHTR",
                 "Description": "3-axis accelerometer, I2C 0x18"}),
    cap("C4", "100n", "+3V3", "GND", (230, 170), "Capacitor 100 nF X7R 0603 (LIS3DH pin 14)"),
    Part("JP3", "Jumper:SolderJumper_3_Bridged12", "0x18", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         (200, 215), {"A": "GND", "C": "ACC_SA0", "B": "+3V3"},
         fields={"Description": "LIS3DH address: 1-2 (as delivered) 0x18, cut and bridge 2-3 for 0x19"}),
    Part("C5", "Device:C_Polarized_Small", "10u", "Capacitor_SMD:CP_Elec_4x5.4", (245, 170),
         {"1": "+3V3", "2": "GND"},
         fields={"Manufacturer": "Panasonic", "MPN": "EEE-1CA100SR",
                 "Description": "Capacitor 10 uF 16 V aluminium electrolytic, 4 x 5.4 mm (LIS3DH pin 14, as ST specifies)"}),
    Part("U3", "Sensor_Optical:APDS-9306-065", "APDS-9306-065", "OptoDevice:Broadcom_DFN-6_2x2mm_P0.65mm",
         (200, 250), {"VDD": "+3V3", "GND": "GND", "SCL": "I2C1_SCL", "SDA": "I2C1_SDA", "INT": "ALS_INT", "NC": NC},
         fields={"Manufacturer": "Broadcom", "MPN": "APDS-9306-065",
                 "Description": "Ambient light sensor, I2C 0x52"}),
    cap("C6", "1u", "+3V3", "GND", (230, 245), "Capacitor 1 uF X7R 0603 (APDS-9306 VDD, as Broadcom specifies)"),
    res("R3", "10k", "ALS_INT", "+3V3", (245, 245), "Resistor 10 kohm 1% 0603 (APDS-9306 INT pull-up)"),
    Part("J3", "Connector:Conn_01x04_Pin", "Qwiic", "Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
         (290, 110), {"1": "GND", "2": "+3V3", "3": "I2C1_SDA", "4": "I2C1_SCL"},
         fields={"Manufacturer": "JST", "MPN": "SM04B-SRSS-TB", "Description": "Qwiic / STEMMA QT, I2C1"}),

    # ---- I2C2: cape identity EEPROM -----------------------------------------------------------------
    res("R4", "4.7k", "I2C2_SDA", "+3V3", (330, 90), "Resistor 4.7 kohm 1% 0603 (I2C2 SDA pull-up)"),
    res("R5", "4.7k", "I2C2_SCL", "+3V3", (345, 90), "Resistor 4.7 kohm 1% 0603 (I2C2 SCL pull-up)"),
    Part("U4", "Memory_EEPROM:24LC256", "24LC256", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", (370, 110),
         {"A0": "+3V3", "A1": "+3V3", "A2": "+3V3", "GND": "GND", "SDA": "I2C2_SDA", "SCL": "I2C2_SCL",
          "WP": "EE_WP", "VCC": "+3V3"},
         fields={"Manufacturer": "Microchip", "MPN": "24LC256-I/SN", "Description": "256 kbit I2C EEPROM, 0x57"}),
    cap("C7", "100n", "+3V3", "GND", (395, 100), "Capacitor 100 nF X7R 0603 (EEPROM)"),
    Part("JP1", "Jumper:SolderJumper_3_Bridged12", "WP", "Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
         (370, 150), {"A": "GND", "C": "EE_WP", "B": "+3V3"},
         fields={"Description": "EEPROM write protect: 1-2 (as delivered) writable, cut and bridge 2-3 to protect"}),

    # ---- Analog: NTC on AIN5, trimmer on AIN6 --------------------------------------------------------
    res("R6", "10k", "+3V3", "AIN5", (330, 200), "Resistor 10 kohm 0.1% 25 ppm 0603 (NTC divider)", "ERA-3AEB103V"),
    Part("TH1", "Device:Thermistor_NTC", "10k", "Resistor_SMD:R_0603_1608Metric", (345, 210), {"1": "AIN5", "2": "GND"},
         fields={"Manufacturer": "Murata", "MPN": "NCP18XH103F03RB",
                 "Description": "NTC thermistor 10 kohm 1%, B25/50 3380 K, 0603"}),
    cap("C8", "100n", "AIN5", "GND", (360, 210), "Capacitor 100 nF X7R 0603 (AIN5 filter)"),
    Part("RV1", "Device:R_Potentiometer_Trim", "10k", "Potentiometer_SMD:Potentiometer_Bourns_3314J_Vertical",
         (330, 260), {"1": "+3V3", "2": "AIN6", "3": "GND"},
         fields={"Manufacturer": "Bourns", "MPN": "3314J-1-103E", "Description": "Trimmer 10 kohm, 4 mm SMD"}),
    cap("C9", "100n", "AIN6", "GND", (350, 260), "Capacitor 100 nF X7R 0603 (AIN6 filter)"),

    # ---- Buttons and LEDs ------------------------------------------------------------------------------
    Part("SW1", "Switch:SW_Push", "BTN1", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", (440, 110),
         {"1": "BTN1", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, P2.02"}),
    res("R7", "10k", "BTN1", "+3V3", (460, 100), "Resistor 10 kohm 1% 0603 (button pull-up)"),
    cap("C10", "100n", "BTN1", "GND", (475, 110), "Capacitor 100 nF X7R 0603 (button debounce, 1 ms)"),
    Part("SW2", "Switch:SW_Push", "BTN2", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", (440, 160),
         {"1": "BTN2", "2": "GND"}, fields={"Manufacturer": "C&K", "MPN": "KMR221G LFS", "Description": "Tactile switch, P2.04"}),
    res("R8", "10k", "BTN2", "+3V3", (460, 150), "Resistor 10 kohm 1% 0603 (button pull-up)"),
    cap("C11", "100n", "BTN2", "GND", (475, 160), "Capacitor 100 nF X7R 0603 (button debounce, 1 ms)"),
    res("R9", "680", "LED1", "LED1_A", (440, 220), "Resistor 680 ohm 1% 0603 (LED, about 2 mA)"),
    Part("D1", "Device:LED_Small", "RED", "LED_SMD:LED_0603_1608Metric", (460, 220), {"A": "LED1_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LSURCK", "Description": "LED red 0603, PWM0A (P1.36)"}),
    res("R10", "680", "LED2", "LED2_A", (440, 250), "Resistor 680 ohm 1% 0603 (LED, about 2 mA)"),
    Part("D2", "Device:LED_Small", "YEL", "LED_SMD:LED_0603_1608Metric", (460, 250), {"A": "LED2_A", "K": "GND"},
         fields={"Manufacturer": "Kingbright", "MPN": "APTD1608LSYCK", "Description": "LED yellow 0603, PWM1A (P2.01)"}),
]
for i in range(2):
    PARTS.append(Part(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M2", "MountingHole:MountingHole_2.2mm_M2_Pad_Via",
                      (60 + 20 * i, 360), {"1": "GND"}, fields={"Description": "Mounting hole M2, grounded"}))

# Board placement: (x, y, rotation) in mm, origin top-left. PocketBeagle covers y 0-35; its sockets
# are placed by pin 1 (the header footprint's origin), rotated so pins run along x with the odd row
# below, as on PocketBeagle. Under PocketBeagle: only low parts (EEPROM, pull-ups, jumper).
PLACEMENT = {
    "J2": (P2_PIN1[0], P2_PIN1[1], 90), "J1": (P1_PIN1[0], P1_PIN1[1], 90),
    "C1": (24.0, 25.0, 0),
    # under PocketBeagle, between the sockets
    "U4": (27.5, 15.5, 0), "C7": (33.0, 14.0, 90), "JP1": (20.5, 15.5, 90),
    "R4": (33.0, 17.5, 0), "R5": (33.0, 19.5, 0), "R1": (17.0, 17.5, 0), "R2": (17.0, 19.5, 0),
    # sensors and controls, below PocketBeagle
    "U1": (8.0, 44.0, 0), "C2": (8.0, 40.6, 0), "C3": (11.4, 44.0, 90), "JP2": (8.0, 48.0, 0),
    "U2": (19.0, 44.0, 0), "C4": (19.0, 40.6, 0), "C5": (19.0, 50.4, 90), "JP3": (14.5, 47.5, 90),
    "U3": (27.5, 56.0, 0), "C6": (24.8, 56.0, 90), "R3": (30.2, 56.0, 90),
    "J3": (51.2, 44.0, 90),
    "R6": (29.0, 39.5, 0), "TH1": (29.0, 41.5, 0), "C8": (29.0, 43.5, 0),
    "RV1": (37.0, 41.5, 0), "C9": (37.0, 46.0, 0),
    "SW1": (35.5, 54.5, 0), "R7": (35.5, 51.0, 0), "C10": (31.5, 52.2, 90),
    "SW2": (43.5, 54.5, 0), "R8": (43.5, 51.0, 0), "C11": (39.6, 51.0, 0),
    "R9": (41.3, 36.6, 0), "D1": (44.8, 36.6, 180), "R10": (41.3, 38.6, 0), "D2": (44.8, 38.6, 180),
    "H1": (6.5, 53.5, 0), "H2": (50.5, 51.5, 0),
}
_unplaced = sorted({p.ref for p in PARTS} - set(PLACEMENT))
assert not _unplaced, f"parts without a board position: {_unplaced}"
for _p in PARTS:
    _p.pcb = PLACEMENT[_p.ref]

TEXTS = [
    {"text": "EoS Sense Cape  rev A", "x": 27.5, "y": 37.2, "size": 1.0, "bold": True},
    {"text": "EoS Sense Cape for PocketBeagle  rev A", "x": 27.5, "y": 44.0, "size": 1.0, "layer": "B_SilkS", "bold": True, "mirror": True},
    {"text": "(c) 2026 Kartikeydheer Srivastava", "x": 27.5, "y": 46.0, "size": 0.8, "layer": "B_SilkS", "mirror": True},
    {"text": "All rights reserved", "x": 27.5, "y": 47.4, "size": 0.8, "layer": "B_SilkS", "mirror": True},
]

BOARD = Board(
    name="eos-sense-cape",
    title="EoS Sense Cape for PocketBeagle",
    revision="A",
    date="2026-10-11",
    company=OWNER,
    licence=LICENCE,
    contact=CONTACT,
    licence_terms=LICENCE_TERMS,
    credits=["PocketBeagle outline and P1/P2 header positions taken from BeagleBoard.org PocketBeagle "
             "(github.com/beagleboard/pocketbeagle), (c) 2017 Jason Kridner (Texas Instruments), Aron Phillips "
             "(GHI Electronics), Michael Welling (QWERTY Embedded), CC BY 4.0 "
             "(creativecommons.org/licenses/by/4.0); used unchanged, as positions only"],
    width=W,
    height=H,
    corner_radius=10.0,
    thickness=1.6,
    layers=2,
    parts=PARTS,
    power_nets={"GND": "power:GND", "+3V3": "power:+3V3"},
    flagged_nets=["GND", "+3V3"],
    headings=[((40, 75), "PocketBeagle P1 and P2 (sockets)"), ((140, 75), "I2C1 pull-ups"),
              ((190, 75), "BME280 (0x76)"), ((190, 155), "LIS3DH (0x18)"), ((190, 230), "APDS-9306-065 (0x52)"),
              ((280, 75), "Qwiic (I2C1)"), ((320, 75), "Cape EEPROM on I2C2 (0x57)"),
              ((320, 180), "AIN5: NTC (PocketBeagle halves it: 0-1.65 V)"), ((320, 240), "AIN6: trimmer"),
              ((430, 75), "Buttons"), ((430, 200), "LEDs on PWM0A / PWM1A"), ((40, 345), "Mounting holes"),
              ((35, 300), "Power nets")],
    power_block=(40.64, 315.0),
    notes=[((260, 320), "EoS Sense Cape for PocketBeagle, rev A. Designed by Kartikeydheer Srivastava.\n"
                       "Copyright (c) 2026 Kartikeydheer Srivastava. All rights reserved; see LICENSE.txt.\n"
                       "Socket positions from BeagleBoard.org's PocketBeagle board file (CC BY 4.0).\n"
                       "Analog inputs: AIN5 and AIN6 only; PocketBeagle's 10k/10k divider keeps them under 1.8 V.\n"
                       "No pull-ups on PocketBeagle's I2C1/I2C2: R1, R2, R4, R5 provide them.")],
    netclasses={"Power": {"track": 0.25, "clearance": 0.15}},   # 3.3 V: narrow enough to enter the 0.5 mm-pitch LGA pads
    net_to_class={"+3V3": "Power"},
)
