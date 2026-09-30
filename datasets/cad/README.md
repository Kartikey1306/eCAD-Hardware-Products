# CAD dataset

Each directory here is one dataset item: its source artefacts (for the
mechanical domain, a STEP assembly; for the electrical domain, a SPICE
netlist; for the digital domain, Verilog sources), the design intent they
cannot carry,
machine-readable requirements, and everything derived from them, with a hash
of every file. The item's provenance names its primary domain, and that
domain's adapter (`tools/ecad_model/domains/`) is the only one run for it. Architecture and schemas:
[docs/cad-dataset-engineering-model-v1.md](../../docs/cad-dataset-engineering-model-v1.md);
the electrical domain:
[docs/electrical-domain-v1.md](../../docs/electrical-domain-v1.md); the
digital domain: [docs/digital-domain-v1.md](../../docs/digital-domain-v1.md).

Items are not products. Product discovery only scans `e*_CAD_Design/` and
`future_designs/`, so nothing here enters the product inventory.

## Items

| Item | Design | Domains |
|---|---|---|
| [`robotic_joint_001`](robotic_joint_001) | Single revolute joint: base plate, pillar, shaft, link, payload; eServo-200 drive; actuator not selected | mechanical `AVAILABLE`; electrical `NOT_APPLICABLE` (no netlist; it would also need the unselected motor's data); digital `NOT_APPLICABLE` (no Verilog); the other six `NOT_IMPLEMENTED` (thermal would also need the motor's data) |
| [`servo_supply_001`](servo_supply_001) | 48 V supply input of the eServo-200 drive: hot-plug supply, fuse, precharge resistor with bypass switch, bulk capacitor, 200 W constant-current load, fault switch; a self-authored testbench in which no element is a real part | electrical `AVAILABLE` (the series-precharge supply-input network only); mechanical `NOT_APPLICABLE` (no STEP); digital `NOT_APPLICABLE` (no Verilog); the other six `NOT_IMPLEMENTED` |
| [`uart_loopback_001`](uart_loopback_001) | 8N1 UART loopback: `rtl/uart_tx.v` and `rtl/uart_rx.v`, copied unmodified and bound to their origins by hash (REUSE-1), wired transmitter to receiver by a self-authored declarative top at 50 MHz and 115 200 Bd sending `0x35` and `0xCA`; no board, oscillator or peer device is modelled, and no target device is selected | digital `AVAILABLE` (the UART 8N1 loopback only); mechanical and electrical `NOT_APPLICABLE` (no STEP, no netlist); the other six `NOT_IMPLEMENTED` |

## Commands

```bash
python3 -m pip install -r tools/requirements.txt -r tools/requirements-cad.txt
brew install ngspice          # or: sudo apt install ngspice (the electrical item)
brew install icarus-verilog   # or: sudo apt install iverilog (the digital item)

python3 tools/cad_dataset.py build    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py check    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py validate datasets/cad/robotic_joint_001 --output /tmp/joint-run

python3 tools/cad_dataset.py build    datasets/cad/servo_supply_001
python3 tools/cad_dataset.py check    datasets/cad/servo_supply_001
python3 tools/cad_dataset.py validate datasets/cad/servo_supply_001 --output /tmp/supply-run

python3 tools/cad_dataset.py build    datasets/cad/uart_loopback_001
python3 tools/cad_dataset.py check    datasets/cad/uart_loopback_001
python3 tools/cad_dataset.py validate datasets/cad/uart_loopback_001 --output /tmp/uart-run
```

The electrical and digital items need no CAD kernel: `tools/requirements.txt`
and ngspice, or Icarus Verilog, are enough for all three commands.

`build` regenerates everything under `derived/` and `validation/` plus
`dataset-item.json`, and removes a case document the requirements no longer
compile. `check` exits 1 if a hash is wrong or a derived file no longer
reproduces from the sources. `validate` runs V0–V4 and writes a receipt,
content-addressed evidence, one result per requirement and reference
(`results.json`) and a report. It exits 0 when the run completed, whatever
the verdicts -- including a run that writes no results by design (no adapter
for the domain, requirements that cannot be read, a committed model that
cannot be used; the report says which); 3 when the receipt and report were
written but generating the results failed (the report says why); and 1 when
no receipt was written. It writes one even when the item's inputs cannot be built into a
model, or committed files have drifted from them. It writes none for an item
it refuses before any gate runs: no or an invalid `source/provenance.json`, a
declared artefact that is missing or not a regular file, a symlink, a
directory outside the repository, or a git-ignored path.

The MuJoCo adapter runs `python3` from `PATH`, not the interpreter running the
validator. Run with the interpreter that has `mujoco` installed first on
`PATH`, or V3/V4 cases report `BLOCKED` with `MUJOCO_NOT_INSTALLED`. The
ngspice adapter runs `ngspice` from `PATH`; without it the electrical cases
report `BLOCKED` with `TOOL_NOT_INSTALLED`, and with an ngspice whose
`--version` banner names no version, a case that passed is `BLOCKED` with
`TOOL_VERSION_UNAVAILABLE`. The Icarus Verilog adapter runs `iverilog` and
`vvp` from `PATH`; without them the digital cases report `BLOCKED` with
`TOOL_NOT_INSTALLED` or `VVP_NOT_INSTALLED`.

## Adding an item

1. Create `datasets/cad/<item_id>/source/` with the source artefacts. The
   mechanical domain reads exactly one STEP file; the electrical domain
   exactly one SPICE netlist of the grammar and network class in
   [docs/electrical-domain-v1.md](../../docs/electrical-domain-v1.md); the
   digital domain up to 16 Verilog sources of the grammar and design class
   in [docs/digital-domain-v1.md](../../docs/digital-domain-v1.md).
2. Establish the licence before anything else, and record it by hand in
   `source/provenance.json` (schema `cad-dataset/v1/source-provenance`): the
   primary `domain`, each artefact by `path` and `format`, the script that
   authored an artefact (`generator`, if any), the origin, the SPDX licence,
   the attribution exactly as the licence requires, whether redistribution
   and training use are permitted, and the basis for believing so. A verified
   licence cites its text as a repository file and its SHA-256
   (`license_text`), which `check` re-hashes: `LICENSE` for a self-authored
   item. A third-party file also needs its source URL, what was modified, and
   its licence text even when unverified; once its licence is verified, also
   who verified it and when. An artefact that is a byte-identical copy of a
   repository file outside the item (the digital item's RTL) records that
   file and its SHA-256 as `copied_from` (provenance format 1.1.0), which
   `check` and V0 re-hash; the copy must stay identical to it.
   An unverified licence permits neither redistribution nor training use.
   `build` refuses an item without this file; it never supplies a licence. If
   the licence cannot be established, do not add the file.
3. Write `design/annotations.json`: map every CAD part name to a component and
   material, declare joints (with the `axis_sense` of a positive angle),
   rigid attachments, and components that exist in the design but not in the
   CAD. For a netlist, `circuit_elements` gives each element's name, kind
   and the ratings of the part it stands for, never a value the netlist
   states. For Verilog, only components without CAD, with `digital` facets
   (format 1.2.0), and their relationships; every value the design has is
   in its sources. A value with no value has one of three statuses, each with a note
   saying why: `UNKNOWN` (nobody has established it), `UNSPECIFIED` (the
   governing document, cited by hash, is silent on it) or `NOT_AVAILABLE` (it
   exists in a source this project cannot access or use). Never fill one in to
   make a check run.
4. Write `requirements/requirements.json`. Each entry's unit must be its
   metric's, and its scenario one the domain implements (for mechanical,
   `schemas/engineering-model/v1/mechanical-vocabulary.schema.json`, for
   electrical `electrical-vocabulary.schema.json`, for digital
   `digital-vocabulary.schema.json`); ids are
   unique across references and requirements. Set `illustrative: true` on any
   limit not taken from a customer, standard or certificate.
5. `build`, then `check`, then `validate`, then commit the whole directory.

## Traps

- **Git LFS.** `.gitattributes` routes `*.step` and `*.stl` to Git LFS, but no
  CI workflow checks out LFS content. A STEP file committed with `git-lfs`
  installed is stored as a pointer, and CI sees the pointer. The importer
  names that case explicitly rather than failing on a broken STEP file. The
  committed example is stored as a regular blob.
- **Derived files are never hand-edited.** An edit is detected by `check` as
  drift. Change the input and rebuild. This holds for the electrical deck
  too: ngspice runs `derived/electrical/<item>.cir`, never the netlist, and
  the deck is compared byte for byte -- after `validate` has run it, since
  the committed deck is what the cases name (plan §7.2 SEC-2). The same
  holds for the digital simulation file, `derived/digital/<item>.v`, which
  Icarus compiles instead of the sources.
- **No byte of an item is converted on checkout.** `.gitattributes` marks
  every file under `datasets/cad/` `-text`, with `LICENSE`, the product
  sheet the items cite by hash and the `rtl/uart_tx.v` and `rtl/uart_rx.v`
  the digital item copies, so a `core.autocrlf` checkout cannot change a
  hash.
- **No symlinks.** `build`, `check` and `validate` refuse an item containing a
  symlink anywhere, or whose directory is itself a symlink, or that resolves
  outside the repository. They also refuse an item under a git-ignored path,
  whose files git would not list, and one whose own source artefacts git does
  not list.
- **Committed derived files come from one platform** (macOS arm64). `check`
  compares numbers within a relative tolerance of 1e-9, one tolerance per
  array, so last-digit kernel differences between platforms do not fail it.
  Verified 2026-09-26: on Linux aarch64, `check`, the complete suite and
  `validate` pass, on the mechanical pipeline (`bd999d5`) and again with the
  domain adapters (`bb43124`, again at `000309b` on 2026-09-27); under
  emulation on Linux x86_64, `check` passes
  (verified on the mechanical pipeline only). The MuJoCo stages have not run
  on native x86_64. The digital item's simulation file is compared byte for
  byte; `check` and `validate` of it passed in an ubuntu:22.04 arm64
  container with Icarus Verilog 11.0 (the `hdl` job's steps, `TASKS.md`
  T-013), and have not run on x86_64.
- **Linux needs `libgl1`.** OpenCASCADE's wheel links `libGL.so.1`, which a
  bare Debian image lacks: `apt-get install libgl1`.
