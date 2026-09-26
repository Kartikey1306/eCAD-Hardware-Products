# CAD dataset

Each directory here is one dataset item: a CAD design, the design intent the
CAD cannot carry, machine-readable requirements, and everything derived from
them, with a hash of every file. Architecture and schemas:
[docs/cad-dataset-engineering-model-v1.md](../../docs/cad-dataset-engineering-model-v1.md).

Items are not products. Product discovery only scans `e*_CAD_Design/` and
`future_designs/`, so nothing here enters the product inventory.

## Items

| Item | Design | Domains |
|---|---|---|
| [`robotic_joint_001`](robotic_joint_001) | Single revolute joint: base plate, pillar, shaft, link, payload; eServo-200 drive; actuator not selected | mechanical implemented; the other eight not implemented (electrical and thermal would also need the unselected motor's data) |

## Commands

```bash
python3 -m pip install -r tools/requirements.txt -r tools/requirements-cad.txt

python3 tools/cad_dataset.py build    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py check    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py validate datasets/cad/robotic_joint_001 --output /tmp/joint-run
```

`build` regenerates everything under `derived/` and `validation/` plus
`dataset-item.json`. `check` exits 1 if a hash is wrong or a derived file no
longer reproduces from the CAD. `validate` runs V0–V4 and writes a receipt,
content-addressed evidence, a requirement trace and a report. It exits 0 when
a receipt was produced, whatever the verdicts.

The MuJoCo adapter runs `python3` from `PATH`, not the interpreter running the
validator. Run with the interpreter that has `mujoco` installed first on
`PATH`, or V3/V4 cases report `BLOCKED` with `MUJOCO_NOT_INSTALLED`.

## Adding an item

1. Create `datasets/cad/<item_id>/source/` with exactly one STEP file.
2. Establish the licence before anything else, and record it by hand in
   `source/provenance.json` (schema `cad-dataset/v1/source-provenance`): the
   origin, the SPDX licence, the attribution exactly as the licence requires,
   whether redistribution and training use are permitted, and the basis for
   believing so. A third-party file also needs its source URL, what was
   modified, and the SHA-256 of the upstream licence text. `build` refuses an
   item without this file; it never supplies a licence. If the licence cannot
   be established, do not add the file.
3. Write `design/annotations.json`: map every CAD part name to a component and
   material, declare joints (with the `axis_sense` of a positive angle),
   rigid attachments, and components that exist in the design but not in the
   CAD. A value nobody knows is `UNKNOWN` with a note saying why. Never fill
   one in to make a check run.
4. Write `requirements/requirements.json`. Set `illustrative: true` on any
   limit not taken from a customer, standard or certificate.
5. `build`, then `check`, then `validate`, then commit the whole directory.

## Traps

- **Git LFS.** `.gitattributes` routes `*.step` and `*.stl` to Git LFS, but no
  CI workflow checks out LFS content. A STEP file committed with `git-lfs`
  installed is stored as a pointer, and CI sees the pointer. The importer
  names that case explicitly rather than failing on a broken STEP file. The
  committed example is stored as a regular blob.
- **Derived files are never hand-edited.** An edit is detected by `check` as
  drift. Change the input and rebuild.
- **No symlinks.** `build`, `check` and `validate` refuse an item containing a
  symlink anywhere. They also refuse an item under a git-ignored path, whose
  files git would not list.
- **Committed derived files come from one platform** (macOS arm64). `check`
  compares numbers within a relative tolerance of 1e-9, one tolerance per
  array, so last-digit kernel differences between platforms do not fail it.
  Verified 2026-09-25: `check` passes on Linux aarch64 and, under emulation, on
  Linux x86_64; the complete suite and `validate` also pass on Linux aarch64.
  The MuJoCo stages have not run on native x86_64.
- **Linux needs `libgl1`.** OpenCASCADE's wheel links `libGL.so.1`, which a
  bare Debian image lacks: `apt-get install libgl1`.
