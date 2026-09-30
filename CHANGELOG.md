# Changelog

## [Unreleased]

Local branch `feat/domain-electrical`, not pushed and not released. It had
two independent reviews at `bf04f1b` (2026-09-28), whose findings are fixed
below (plan §7.6); the fixes have had no review of their own, and the CI
`spice` job has never run.

### Added

- The electrical domain (issue #27, plan §21 item 4): a SPICE netlist is
  read by a strict allow-list parser (`tools/ecad_model/spice.py`) into the
  engineering model, the adapter (`tools/ecad_model/domains/electrical.py`)
  writes the ngspice deck from the model, and ten `SIMPLIFIED` metrics are
  compared with closed-form references (V3) and requirements (V4). One
  network class is validated: a series-precharge supply input.
- The dataset item `datasets/cad/servo_supply_001`: the eServo-200 drive's
  48 V supply input as a self-authored testbench in which no element is a
  real part. Its receipt is `BLOCKED` by design: V0-V3 `PASS`, five
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

### Fixed (review of the electrical branch, plan §7.6)

- Netlist node names start with `n_` and switch model names with `SW_`:
  ngspice read a node named `time` in a `.meas` as the time axis, so a real
  limit on the bus peak passed at 0.1, and other names crashed or stopped
  it (CS-1).
- Extraction refuses a netlist the deck's windows cannot measure: a fault
  switch that does not close and settle before T_END (a limit on the fault
  current had passed on the pre-fault current), a non-positive resistance,
  capacitance or switch resistance, and a ramp still rising at the bypass
  command; a closed form that divides by zero or overflows is
  `REFERENCE_NOT_APPLICABLE`, and no item can cost the receipt (CS-2, CS-3).
- The precharge closed forms include the open fault switch's off
  resistance (CS-4).
- A tenth metric, `startup_peak_current_a`, sees the surge when an early
  bypass closes, which the inrush window missed; REF-EL-010 and REQ-EL-008
  compare and limit it (CS-5).
- Documentation that said ngspice only runs the regenerated deck, or that
  V2's invariants read the committed deck; untested conditions and
  branches; a CI test that let a skip hide (HT-1 to HT-8).

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

