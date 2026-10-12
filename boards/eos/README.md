# EmbeddedOS development boards

Original boards designed by Kartikeydheer Srivastava, all rights reserved (see [Licence](#licence)).
Each board is written as a design file in [tools/eos_boards/boards](../../tools/eos_boards/boards). One command builds the
board's schematic, layout, routing, checks and fabrication outputs; see
[tools/eos_boards/README.md](../../tools/eos_boards/README.md).

| Board | What it is | Layers | ERC | DRC errors | Unconnected | Parity |
|---|---|---|---|---|---|---|
| [EoS Learn RP2350](eos-learn-rp2350) | RP2350A teaching board; Raspberry Pi's own core layout, reproduced to the nanometre | 4 | 0 | 0 | 0 | 0 |
| [EoS Sense Cape](eos-sense-cape) | Sensor cape for PocketBeagle; fit checked pin for pin against PocketBeagle's board file | 2 | 0 | 0 | 0 | 0 |
| [EoS Probe S3](eos-probe-s3) | ESP32-S3 SWD/JTAG + UART debug probe, 1.65–5.5 V targets | 2 | 0 | 0 | 0 | 0 |
| [EoS CM5 Base](eos-cm5-base) | Raspberry Pi CM5 carrier: USB-C power, Gigabit Ethernet, USB 2.0 host, microSD, 40-pin GPIO; connectors checked pad for pad against the CM5 | 4 | 0 | 0 | 0 | 0 |
| [EoS CM4 Base](eos-cm4-base) | Raspberry Pi CM4 carrier: USB-C power, one USB 2.0 port switched between USB-C (device) and USB-A (host), Gigabit Ethernet, microSD, 40-pin GPIO | 4 | 0 | 0 | 0 | 0 |
| [EoS Motion Wing](eos-motion-wing) | FeatherWing: ADXL343 accelerometer and ADT7410 temperature sensor on I2C, address and interrupt jumpers | 2 | 0 | 0 | 0 | 0 |
| [EoS ESP32 DevKit](eos-esp32-devkit) | ESP32-WROOM-32E board: USB-C, CP2102N USB-UART with auto-program, 3.3 V 1 A, DevKitC V4 header grid | 2 | 0 | 0 | 0 | 0 |

Each board folder contains:

- the KiCad project;
- Gerbers and drill files;
- BOM and pick-and-place files;
- a STEP model;
- the schematic as a PDF;
- renders;
- `build-report.json`, which records the check counts.

The KiCad projects open in KiCad 10 or later; the boards are saved in KiCad 10's format.
The Gerbers, drill files, BOM, STEP and PDF need no KiCad at all.

None of these boards has been manufactured or tested on the bench. Each README says what was
checked and what was not.

## Licence

These boards are **not open source**, and they are **not** under the MIT licence that
covers this repository's own code. They are Copyright (c) 2026 Kartikeydheer Srivastava, all
rights reserved. Each board's `LICENSE.txt` has the full terms. In short:

- **Anyone** may view them, download or clone this repository, open the files to look at them
  and run its tests. Copying or changing the designs, making boards from them or selling them
  needs Kartikeydheer Srivastava's written permission, which may be given for a fee. To ask,
  write to kartikeydheer@gmail.com.
- **EmbeddedOS (EoS) Research Foundation** may, free of charge, publish them and its own
  changed versions for viewing, change them for its own projects, and make and lend boards for
  its own development, research, teaching and demonstrations. It may not sell boards or pass
  the designs on. Kartikeydheer Srivastava can withdraw this permission with 30 days' notice
  by email or letter.
- **Third-party material** keeps its own licence: Raspberry Pi's RP2350A core layout (MIT) on
  EoS Learn RP2350, and footprints, symbols and 3D models from KiCad's libraries. Each board's
  `LICENSE.txt` lists what it uses.

What the licence covers:

- every board folder here, except the generic symbol libraries copied into a board's
  `hardware/symbols/`, which are MIT like the generator that writes them;
- in `tools/eos_boards`: the boards' design files `boards/eos_*.py`, `boards/owner.py`, the
  licence terms `boards/licence_terms.txt`, and the footprint library drawn for the module
  carriers, `footprints/EoS_Connectors.pretty`.

The rest of `tools/eos_boards` (the generator, the reference extractors and `symbols/`) and
its tests stay under the repository's MIT licence.
