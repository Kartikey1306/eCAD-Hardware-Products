# Development-Board CAD Database (issue #28)

A board-by-board master database of third-party development-board CAD
availability. Every record binds one exact board and hardware revision;
family-level claims are not permitted (see issue #28, sections 9–12).

## What a record may claim

Availability is tri-state per format: `true` (verified present), `false`
(verified absent), `null` (unknown). A positive query matches only `true`, so
unknown is never silently counted as a yes.

Contract `1.1.0` adds the constraint that makes those states mean something:
**a claim is not assertable by hand.**

| State   | What the record must carry                                                |
|---------|---------------------------------------------------------------------------|
| `true`  | a URL and an `evidence.sha256` of bytes that were actually retrieved        |
| `false` | either a 404/410 from the official URL, or an `index_ref` naming an exhaustive official file index, pinned to an immutable revision |
| `null`  | no evidence at all                                                          |

The last row is the one that keeps the database honest. "We have not looked"
and "we looked and it is not published" are different facts, and an unknown
that carried evidence would blur them.

## Why availability is decided from bytes, not from status codes

Both of these were observed against live vendor infrastructure while building
this, and both defeat the obvious implementation:

- `datasheets.raspberrypi.com` answers **HEAD** for the Pico STEP archive with
  `content-type: text/html` and `content-length: 0`, while a **GET** of the same
  URL returns a genuine 266,009-byte ZIP. HEAD produces false *negatives*, so
  `verify.py` only ever issues GET.
- `raspberrypi.com` answers an automated client with a Cloudflare interstitial
  at status **200**. A 200 is not a file, so every response is content-sniffed
  and an HTML body never satisfies a CAD claim.

A third rule follows from the same reasoning: a 404 on a *guessed* URL means the
guess was wrong, not that the vendor publishes nothing. `verify.py` records
`null` for it unless `--absent-on-404` is passed, which is only correct when the
URL came from the vendor's own index.

## Source hierarchy

Per issue #28, section 10, preferred source order is:

1. Manufacturer's official CAD/design-file repository
2. Manufacturer's official product page
3. Manufacturer's official GitHub repository
4. Manufacturer's official documentation
5. Authorized distributor documentation
6. Community repositories only when no official source exists

A manufacturer's GitHub repository has one property no product page has: its
tree is **exhaustive**. That is what makes `available: false` provable, and it is
why `harvest_github.py` exists.

## Record lifecycle

- `incomplete`: identity recorded; no availability determined.
- `partial`: some formats determined, or identity not yet pinned to an exact
  part number, MCU and revision.
- `verified`: every format determined and identity fully pinned.

`record_status` is **derived** from the record by `verify.derive_status()` and
checked in CI, so it cannot drift out of step with the data it summarises.

## Identity: findings and gaps are different facts

Three reserved values keep "nobody has looked" separate from "we looked and there is none".
Only the first blocks a record from reaching `verified`:

| Field | Gap | Finding |
|---|---|---|
| `revision` | `unverified` | `not-stated` — an exhaustive official index names no revision |
| `mcu_soc` | `UNVERIFIED` | `not-applicable` — a passive add-on board (FeatherWing, shield, HAT, cape) |
| `part_number` | `UNVERIFIED` | the manufacturer's own part number |

Collapsing the two would make an unfinished record look identical to a complete one about
a board that genuinely has no revision.

## Tools

The pipeline is: **propose candidates → verify from bytes → read licences → gate**.
No step ever asserts that a file exists; only `verify.py` decides that, and only from
content it retrieved.

```bash
# 1a. Enumerate manufacturer repositories and turn them into records.
#     Coverage grows by editing vendors.json, not by editing code.
python3 tools/devboard_cad/discover_github.py discover --out candidates.json
python3 tools/devboard_cad/discover_github.py emit --manifest candidates.json

# 1b. One repository at a time, when you already know it.
python3 tools/devboard_cad/harvest_github.py harvest \
    --repo adafruit/Adafruit-Feather-RP2040-PCB \
    --board-id adafruit:feather-rp2040 \
    --manufacturer "Adafruit Industries" --family Feather \
    --board "Adafruit Feather RP2040" --part-number 4884 \
    --mcu "Raspberry Pi RP2040" \
    --product-page https://www.adafruit.com/product/4884

# 1c. Manufacturers that do not publish on GitHub, from direct_sources.json.
python3 tools/devboard_cad/seed_direct.py

# 2. Decide availability by retrieving and content-checking each candidate.
python3 tools/devboard_cad/verify.py verify --apply --jobs 8 --quiet

# 3. Read the hardware licence from the manufacturer's own LICENSE or README.
python3 tools/devboard_cad/read_licenses.py

# 4. Gate: schema, uniqueness, filename agreement, derived status, licence citations.
python3 tools/devboard_cad/validate_records.py

# 5. Drift: re-fetch every claimed file and compare digests. Networked, advisory.
python3 tools/devboard_cad/validate_records.py --revalidate
```

### Coverage

29 of the 31 ecosystems in issue #28 §2 have at least one record. Two do not, and both are
access walls rather than gaps in this tooling — each was checked from three directions and
the result recorded rather than worked around:

| Ecosystem | What was tried | Result |
|---|---|---|
| 2.10 Silicon Labs | `silabs.com` document URLs; `docs.silabs.com`; the `SiliconLabs` GitHub org | every file URL returns **403** to an automated client; the org's two hardware repos hold 3 and 6 blobs, no CAD |
| 2.18 Digilent | `digilent.com/reference/...`; `files.digilent.com`; all 16 `Digilent/*-HW` repos | site returns **403**; every `-HW` repo is a *Vivado project* (HDL, constraints, block design), zero CAD files |

Two further negative results worth keeping, so they are not re-investigated:
`Xilinx/XilinxBoardStore` holds DRAM part CSVs, not board CAD, and Terasic's DE-series
pages carry no direct file links.

### Manufacturers that cannot be enumerated

Issue #28 section 10 ranks the official product page and documentation above a repository,
but neither is machine-enumerable, and two failure modes are permanent rather than
incidental:

* `raspberrypi.com` answers an automated client with a Cloudflare interstitial, and its
  document portal is JavaScript-rendered. Its URLs were recovered instead from
  `raspberrypi/documentation`, the manufacturer's own public documentation source, which
  cites official `pip.raspberrypi.com` document IDs.
* `st.com` does not answer an automated client at all. Boards whose files live only there
  cannot be verified by this pipeline, and no record claims otherwise.

Those manufacturers are served by `direct_sources.json`: a human supplies candidate URLs
from the official source and `verify.py` decides. Because a curated list is not
exhaustive, `seed_direct.py` never records `available: false` — absence is only provable
against an index that enumerates everything.

`verify.py` caches responses outside the repository (`~/.cache/devboard-cad`, or
`DEVBOARD_CAD_CACHE`) and rate-limits per host, and it never commits what it
fetched: records hold digests and URLs only. Most board CAD is not
redistributable, which is exactly why `licenses.redistribution_allowed` is a
field rather than an assumption. Only the [mirror](#mirror) copies files, and only
for boards where that field is `true`.

## Licensing

Licensing is tracked separately from file availability, per issue #28 section 12.
File availability is mechanical; reading a vendor's terms is not, and
`commercial_use_allowed` is the field with real downstream consequences. It is
left `null` unless the licence has been read, and CI requires that any non-null
permission is accompanied by a named `hardware_license` and a `license_url`.

`read_licenses.py` reads the manufacturer's own LICENSE or README and matches it against a
table of licences whose terms are already settled. It never interprets novel prose: an
unrecognised statement leaves the record `UNVERIFIED`, which the gate then requires. The
distinction is between reading and inferring — quoting "SparkFun hardware is released
under Creative Commons Share-alike 4.0 International" from `LICENSE.md` is a reading;
concluding a board is probably CC-licensed because its vendor usually is would not be.

One case recurs and is recorded rather than smoothed over: Adafruit's READMEs name
"Creative Commons Attribution/Share-Alike" with no version, and the `license.txt` they
point at is usually absent from the repository. Every CC BY-SA version permits commercial
use and modification under attribution and share-alike — the non-commercial variants are
separately named BY-NC-SA — so the permissions are determinable while the version is not.
Both facts go in the record.

## Mirror

`boards/cad/` holds an unmodified copy of every verified **CAD file** of every board whose
record sets `licenses.redistribution_allowed` to `true` (issue #48). Boards without that
permission keep their link and digest only; nothing of theirs is copied. Documents (schematic
PDFs, drawings, BOMs, datasheets) are not copied either: their records keep the link and
digest, so the folder holds CAD and nothing else.

```
boards/cad/<vendor>/<board>/
  ATTRIBUTION.md   manufacturer, licence, and the source and digest of each file
  cad/             Eagle, KiCad and Altium sources and libraries, Gerber and drill files,
                   Gerber archives, STEP, STL and DXF models
tools/devboard_cad/mirror-manifest.json
                   one entry per file: board, path, formats, source, sha256, size, licence
```

`ATTRIBUTION.md` stays beside the files on purpose: CC BY and CC BY-SA require the credit
and the licence notice to travel with the material, so a board's folder copied on its own
still carries them.

`mirror.py build` copies a file only when all three hold:

1. the board's licence allows redistribution;
2. the bytes have the SHA-256 recorded in `evidence.sha256`, so the mirror can only ever
   hold what the database says was checked;
3. the verifier recorded a CAD format for it (for STEP, the part of `detected_format`
   before the colon), and the bytes are CAD again when read: Eagle, KiCad and Altium
   sources, Gerber and drill files, STEP, STL and DXF models, or an archive containing
   them. A file recorded as CAD whose bytes turn out to be a web page, JSON or a document
   is refused and reported, never skipped silently.

A build rewrites the manifest for the vendors it covers and removes whatever the manifest
no longer names, including a board left without CAD files. `check` fails on a missing
file, a digest mismatch, a stray file anywhere in `boards/cad/`, a missing attribution, or
a board that has lost its licence.

The files are committed as regular files, exactly as published. `.gitattributes`
exempts `boards/cad/*/*/cad/` from the repository's LFS rules and from line-ending
conversion, so every byte matches its digest. Git LFS was the first choice, but GitHub
refuses LFS uploads to a public fork, which is how this repository takes contributions.
Every file is under GitHub's 100 MB limit.

```bash
# Copy the CAD files of one vendor, or of all vendors, reusing files whose digest matches.
python3 tools/devboard_cad/mirror.py build --vendor sparkfun
python3 tools/devboard_cad/mirror.py build

# Fail unless every redistributable CAD file is mirrored and every digest matches.
python3 tools/devboard_cad/mirror.py check
```

To check out only the boards you need:

```bash
git sparse-checkout set --no-cone '/*' '!/boards/cad/*/*/' '/boards/cad/adafruit/feather-rp2040/'
```

`check` also reads Git LFS pointer files: a pointer's `oid` is the SHA-256 of the object
it stands for. If the mirror later moves to LFS
(`git lfs migrate import --include="boards/cad/*/*/cad/**"`), completeness and integrity
stay provable in CI without downloading the binaries. `tests/unit/test_devboard_mirror.py`
runs it against the committed mirror.

## Schema

`schemas/devboard-cad/v1/board-record.schema.json` (contract `1.1.0`; records
written against `1.0.0` remain valid).

## Query

```bash
python3 tools/devboard_cad/query.py list
python3 tools/devboard_cad/query.py with-formats step
python3 tools/devboard_cad/query.py with-formats kicad schematic
python3 tools/devboard_cad/query.py full-stack
python3 tools/devboard_cad/query.py commercial-reuse
python3 tools/devboard_cad/query.py mechanical
python3 tools/devboard_cad/query.py open-electrical
```

These correspond to the six example queries in issue #28, section 11.
