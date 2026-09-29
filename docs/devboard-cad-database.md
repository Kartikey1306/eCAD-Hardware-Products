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

## Tools

```bash
# 1. Propose candidates from a manufacturer's official repository, pinned to a commit.
#    Presence is only ever proposed here; absence is proven from the tree.
python3 tools/devboard_cad/harvest_github.py harvest \
    --repo adafruit/Adafruit-Feather-RP2040-PCB \
    --board-id adafruit:feather-rp2040 \
    --manufacturer "Adafruit Industries" --family Feather \
    --board "Adafruit Feather RP2040" --part-number 4884 \
    --mcu "Raspberry Pi RP2040" \
    --product-page https://www.adafruit.com/product/4884

# 2. Decide availability by retrieving and content-checking each candidate.
python3 tools/devboard_cad/verify.py verify adafruit__feather-rp2040 --apply

# 3. Gate: schema, uniqueness, filename agreement, derived status. Offline.
python3 tools/devboard_cad/validate_records.py

# 4. Drift: re-fetch every claimed file and compare digests. Networked, advisory.
python3 tools/devboard_cad/validate_records.py --revalidate
```

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
