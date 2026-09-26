# CAD dataset

Each directory here is one dataset item: its source artefacts (for the
mechanical domain, a STEP assembly), the design intent they cannot carry,
machine-readable requirements, and everything derived from them, with a hash
of every file. The item's provenance names its primary domain, and that
domain's adapter (`tools/ecad_model/domains/`) is the only one run for it. Architecture and schemas:
[docs/cad-dataset-engineering-model-v1.md](../../docs/cad-dataset-engineering-model-v1.md).

Items are not products. Product discovery only scans `e*_CAD_Design/` and
`future_designs/`, so nothing here enters the product inventory.

## Items

| Item | Design | Domains |
|---|---|---|
| [`robotic_joint_001`](robotic_joint_001) | Single revolute joint: base plate, pillar, shaft, link, payload; eServo-200 drive; actuator not selected | mechanical `AVAILABLE`; the other eight `NOT_IMPLEMENTED` (electrical and thermal would also need the unselected motor's data) |

## Commands

```bash
python3 -m pip install -r tools/requirements.txt -r tools/requirements-cad.txt

python3 tools/cad_dataset.py build    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py check    datasets/cad/robotic_joint_001
python3 tools/cad_dataset.py validate datasets/cad/robotic_joint_001 --output /tmp/joint-run
```

`build` regenerates everything under `derived/` and `validation/` plus
`dataset-item.json`, and removes a case document the requirements no longer
compile. `check` exits 1 if a hash is wrong or a derived file no longer
reproduces from the sources. `validate` runs V0–V4 and writes a receipt,
content-addressed evidence, one result per requirement and reference
(`results.json`) and a report. It exits 0 when a receipt was produced,
whatever the verdicts; it writes one even when the item's inputs cannot be
built into a model, or committed files have drifted from them.

The MuJoCo adapter runs `python3` from `PATH`, not the interpreter running the
validator. Run with the interpreter that has `mujoco` installed first on
`PATH`, or V3/V4 cases report `BLOCKED` with `MUJOCO_NOT_INSTALLED`.

## Adding an item

1. Create `datasets/cad/<item_id>/source/` with the source artefacts. The
   mechanical domain reads exactly one STEP file.
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
   who verified it and when.
   An unverified licence permits neither redistribution nor training use.
   `build` refuses an item without this file; it never supplies a licence. If
   the licence cannot be established, do not add the file.
3. Write `design/annotations.json`: map every CAD part name to a component and
   material, declare joints (with the `axis_sense` of a positive angle),
   rigid attachments, and components that exist in the design but not in the
   CAD. A value with no value has one of three statuses, each with a note
   saying why: `UNKNOWN` (nobody has established it), `UNSPECIFIED` (the
   governing document, cited by hash, is silent on it) or `NOT_AVAILABLE` (it
   exists in a source this project cannot access or use). Never fill one in to
   make a check run.
4. Write `requirements/requirements.json`. Each entry's unit must be its
   metric's, and its scenario one the domain implements (for mechanical,
   `schemas/engineering-model/v1/mechanical-vocabulary.schema.json`); ids are
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
  drift. Change the input and rebuild.
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
  domain adapters (`2beb77a`); under emulation on Linux x86_64, `check` passes
  (verified on the mechanical pipeline only). The MuJoCo stages have not run
  on native x86_64.
- **Linux needs `libgl1`.** OpenCASCADE's wheel links `libGL.so.1`, which a
  bare Debian image lacks: `apt-get install libgl1`.
