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
`DEVBOARD_CAD_CACHE`) and rate-limits per host. **Vendor files are never
committed**: records hold digests and URLs only. Most board CAD is not
redistributable, which is exactly why `licenses.redistribution_allowed` is a
field rather than an assumption.

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
