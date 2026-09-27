# Changelog

## [Unreleased]

Local branch `feat/domain-electrical`, not pushed and not released. Nothing
here has had an independent review, and the CI `spice` job has never run.

### Added

- The electrical domain (issue #27, plan §21 item 4): a SPICE netlist is
  read by a strict allow-list parser (`tools/ecad_model/spice.py`) into the
  engineering model, the adapter (`tools/ecad_model/domains/electrical.py`)
  writes the ngspice deck from the model, and nine `SIMPLIFIED` metrics are
  compared with closed-form references (V3) and requirements (V4). One
  network class is validated: a series-precharge supply input.
- The dataset item `datasets/cad/servo_supply_001`: the eServo-200 drive's
  48 V supply input as a self-authored testbench in which no element is a
  real part. Its receipt is `BLOCKED` by design: V0-V3 `PASS`, four
  illustrative limits met (`WARNING`), three part-rating limits `BLOCKED`
  because no part is selected.
- Engineering-model format 1.1.0: a component's `circuit` member (designator,
  element, terminals, switch model), six electrical component kinds, and
  `circuit_elements` in the design annotations; the schemas require 1.1.0 for
  a document that uses them. `electrical-vocabulary.schema.json`.
- A CI `spice` job that installs ngspice and runs the complete suite with
  `ECAD_REQUIRE_SPICE_TOOLS=1`, `check` and `validate` on the electrical item.
- `docs/electrical-domain-v1.md`.

### Changed

- The ngspice tool adapter runs `ngspice -b <deck>` only and returns the
  `.meas` results the deck declares, read from stdout (ARCH-2, ngspice half);
  it read none before. Its version comes from the `--version` banner
  (RESULT-8), and a failed version probe gives a reason code the receipt
  accepts (RESULT-2, ngspice path only).
- `Extraction.producer` is required: each domain adapter names the producer
  of its engineering model. The domain adapter protocol is no longer
  provisional.
- The robotic joint's electrical domain is `NOT_APPLICABLE` rather than
  `NOT_IMPLEMENTED`; no derived number changed.
- `.gitattributes` keeps every dataset file, `LICENSE` and the cited product
  sheet byte-exact on checkout.

## [3.0.1] - 2026-05-16

### Production Release — Unified EmbeddedOS-org v3.0.1

This is the synchronized production release across all 18 EmbeddedOS-org repos.

- Refreshed governance: LICENSE, NOTICE, CITATION.cff, SECURITY.md
- CI/CD pipelines hardened: release.yml, book-build.yml, video-build.yml, deploy-pages.yml
- Release artifacts produced for: Linux x64/arm64, macOS x64/arm64, Windows x64, Docker, plus per-repo embedded/mobile/extension targets
- mdBook documentation built and deployed to GitHub Pages
- Promo video rendered and attached as a release asset

## [3.0.0] - 2026-05-13

### Production Release — Unified EmbeddedOS-org v3.0.0

This is the synchronized production release across all 18 EmbeddedOS-org repos.

- Refreshed governance: LICENSE, NOTICE, CITATION.cff, SECURITY.md
- CI/CD pipelines hardened: release.yml, book-build.yml, video-build.yml, deploy-pages.yml
- Release artifacts produced for: Linux x64/arm64, macOS x64/arm64, Windows x64, Docker, plus per-repo embedded/mobile/extension targets
- mdBook documentation built and deployed to GitHub Pages
- Promo video rendered and attached as a release asset

