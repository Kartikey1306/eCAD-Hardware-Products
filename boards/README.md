# Boards Catalog

Development boards and kits relevant to the EmbeddedOS (EoS) ecosystem:
what the OS supports today, and where hardware/CAD work is heading.

Tracked by [#28](https://github.com/embeddedos-org/eCAD-Hardware-Products/issues/28)
("Development boards, kits, and CAD design-file reference"), which scopes the
full catalog across Arduino/AVR, Raspberry Pi, ESP32/ESP8266, STM32, Nordic,
FPGA, robotics, and AI-accelerator families.

## Boards with EoS descriptors today

These boards have first-class descriptors in
[`eos/boards/`](https://github.com/embeddedos-org/eos/tree/master/boards)
(`boards/*.yaml`: MCU, memory map, peripherals, linker script). The table
below is generated from those descriptors — the single source of truth.

| Board (descriptor) | MCU | Family | Vendor | Core |
|---|---|---|---|---|
| `am64x` | AM6442 | Sitara | Texas Instruments | cortex-a53 |
| `esp32` | ESP32-D0WDQ6 | ESP32 | Espressif | lx6 |
| `hiletgo-esp-wroom-32` | ESP32-D0WDQ6 | ESP32 | Espressif | lx6 |
| `imx8m` | MIMX8MM6 | i.MX8M | NXP | cortex-a53 |
| `nrf52840` | NRF52840 | nRF52 | Nordic Semiconductor | cortex-m4f |
| `qemu-arm64` | — | — | — | — |
| `raspberrypi4` | — | — | — | — |
| `samd51` | ATSAMD51J20A | SAMD51 | Microchip | cortex-m4f |
| `sifive_u` | FU740-C000 | HiFive | SiFive | u74 |
| `stm32f4` | STM32F407VG | STM32F4 | ST Microelectronics | cortex-m4 |
| `stm32h743` | — | — | ST Microelectronics | — |
| `stm32mp1` | — | — | ST Microelectronics | — |
| `tms570` | TMS570LC4357 | TMS570 | Texas Instruments | cortex-r5f |

("—" = not specified in the descriptor; contributions welcome.)

## Generic targets

Beyond the named boards, `eos/boards/` ships 71 `generic-*` descriptors
covering CPU families without a specific board attached (e.g.
`generic-cortex-m4`, `generic-esp32s3`, `generic-riscv*`, `generic-avr`,
`generic-8051`). These are the bring-up starting point for a new board in
the same family: copy the closest generic descriptor, fill in the concrete
MCU, memory map, and peripherals, and submit it against `eos`.

## Adding a board

1. Add `boards/<name>.yaml` in `eos` following the existing schema
   (`board.name/mcu/family/arch/core/vendor/clock_hz/memory/peripherals`).
2. If this repo should carry the CAD side (schematic, PCB, 3D model),
   open an issue here referencing the `eos` descriptor and attach the
   design files under the matching `*_CAD_Design/` domain directory.

## Incoming (no EoS descriptor yet) — October 2026

Boards on the #28 watchlist with no `eos/boards/` descriptor yet. Entries
stay here (not in the table above) until a descriptor lands; specs are
minimal until datasheet review.

| Board | Vendor | Family | Notes |
|---|---|---|---|
| FRDM-IMXRT1186 | NXP | i.MX RT1186 | FRDM dev board for the RT1186 crossover MCU |
| ESP32-C5 Pico | Espressif | ESP32-C5 | RISC-V + 802.15.4/Wi-Fi 6; Thread/Matter candidate |
| ESP-Mosaico (S31) | — | — | Specs pending datasheet review |
| VENTUNO Q | — | STM32H5 (STM32H5F5) | Cortex-M33 target; specs pending datasheet review |

## Roadmap (from #28)

- Per-family pages (Arduino, Pi, ESP32, STM32, nRF, FPGA, robotics kits)
  with CAD design-file references.
- Mapping each catalog entry to its EoS support tier (descriptor,
  BSP, EoSim model).
- Kit/cookbook entries: "what to buy to run EoS on <board>".
