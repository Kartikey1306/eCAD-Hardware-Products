<!-- generated: eos-ai-scaffold -->
# Tasks

Working ledger for `eCAD-Hardware-Products`. The planner writes entries; each owning role
updates its own row. Roles are in [AGENTS.md](./AGENTS.md), the workflow in
[ORCHESTRATION.md](./ORCHESTRATION.md), the gate in [VERIFY.md](./VERIFY.md).

Status is one of: `todo`, `in-progress`, `blocked`, `review`, `done`.

## Active

| ID | Task | Owner | Mode | Status | Depends on |
|----|------|-------|------|--------|------------|
| T-002 | Author catalogs for the 260 remaining product directories | — | build | todo | T-001 |
| T-003 | Resolve the 6 unresolved BOM total mismatches | — | fix | blocked | owner decision on which figure is authoritative |
| T-004 | Verify component MPNs and unit costs against a distributor source | — | verify | todo | T-001 |
| T-005 | Seed the HEALTH-RING biosensor simulation and resolve its HbA1c spec margin | — | fix | blocked | owner decision: widen spec or improve design |
| T-006 | Route the generated boards and add pin-level signal nets | — | build | todo | T-002 |
| T-008 | Assign real IPC-7351 land patterns to every placed footprint | — | build | todo | T-007 |
| T-009 | Run DRC and export fabrication outputs (needs KiCad installed) | — | verify | blocked | KiCad unavailable: `apt` needs root |
| T-010 | CAD dataset, engineering semantic model, and robotic-joint mechanical validation (issue #27) | — | build | review | independent review |
| T-011 | Multi-domain foundation: domain adapters, null statuses, per-requirement results, spec §4 metadata (plan §21 item 3) | — | build | review | T-010 |
| T-012 | Electrical domain: the servo supply input on ngspice (plan §21 item 4) | — | build | review | T-011 |

### T-008 — Real land patterns

Owner: unassigned
Mode: build
Status: todo

Goal
: Every placed footprint carries pads from a verified IPC-7351 land pattern or a
  manufacturer drawing, replacing the body-and-courtyard placement models.

Why it is not done
: Package bodies are currently *estimated* from family and pin count, except for
  the chip passives in `cad_geometry.EXACT_PACKAGES`, which use standard land
  patterns. Pads are omitted entirely rather than invented — an invented land
  pattern looks fabricable and is not.

Acceptance criteria
: - Every footprint has pads matching a cited source.
  - `cad_geometry.package_model()` reports `exact: True` for every package used.

### T-009 — DRC and fabrication outputs

Owner: unassigned
Mode: verify
Status: blocked — KiCad is not installed and `apt` requires a password

Goal
: `kicad-cli pcb drc` passes on every board, and Gerber, drill and pick-and-place
  outputs are produced.

Note
: `kiutils` parses the board files in pure Python, which is what the current CAD
  validation uses. It cannot run DRC or export fabrication data. Nothing in this
  repository has been DRC-checked.

### T-005 — HEALTH-RING simulation is unseeded and sits on its spec limit

Owner: unassigned
Mode: fix
Status: blocked — needs an owner decision

Goal
: The PPG biosensor simulation is reproducible, and its HbA1c result either
  meets the stated specification with margin or the specification is corrected.

Evidence
: Measured 2026-08-08 over 8 consecutive runs of
  `eosHealth_CAD_Design/HEALTH-RING/simulation/ppg_biosensor_sim.py`:
  HbA1c mean error 0.409%, 0.509%, 0.632%, 0.409%, 0.451%, 0.578%, 0.424%,
  0.643% against a 0.5% specification. Exited non-zero on 4 of 8 runs.

Risks
: Seeding the RNG to a value that happens to pass would hide the marginal
  design rather than fix it. The seed and the design margin are separate
  decisions and both need making.

### T-006 — Route the generated boards

Owner: unassigned
Mode: build
Status: todo

Goal
: The generated `.kicad_pcb` files carry placed footprints, routed traces and
  copper pours, and the `.net` files carry pin-level signal connectivity.

Note
: What exists today is a starting board — outline, layer stack, design rules —
  and a netlist of components and power nets. This is stated in each generated
  `fabrication_notes.md` and in the `.net` header. It is deliberately not
  presented as a finished design.

### T-002 — Author catalogs for the remaining product directories

Owner: unassigned
Mode: build
Status: todo
Depends on: T-001 (complete)

Goal
: Every name in `tools/catalog/taxonomy.json` resolves to a product directory
  containing a datasheet, a costed BOM, a runnable simulation, and hardware trees.

Acceptance criteria
: - `python3 tools/generate_products.py --coverage` reports 337/337.
  - `python3 tools/validate_products.py --run` exits 0 with no new baseline entries.
  - No new entry is added to `tools/product_baseline.json`.

Files in scope
: `tools/catalog/divisions/*.json`, `tools/catalog/components.json`

Out of scope
: The sixteen hand-authored product directories that predate the catalog.

Verification
: | Check | Command | Result |
  |-------|---------|--------|
  | Coverage | `python3 tools/generate_products.py --coverage` | `74/337` at 2026-08-08 |
  | Contract | `python3 tools/validate_products.py --run` | `PASS` for what exists |

### T-003 — Resolve the six unresolved BOM total mismatches

Owner: unassigned
Mode: fix
Status: blocked — needs the product owner to say which figure is authoritative

Goal
: Each BOM's stated total equals the sum of its line items, with the correction
  applied to whichever side is actually wrong.

Affected
: `eConsumer/smart_devices` (+$1.00), `eDefense/tactical_communications` (+$1.00),
  `eosHealth/HEALTH-BAND-Neuro` (+$2.65), `eosHealth/HEALTH-KEY-ULTRA` (-$6.30),
  `eosHealth/HEALTH-LAB` (+$1.30), `eosHealth/HEALTH-RING` (-$5.00)

Risks
: Editing the total to match the sum hides a genuinely missing line item; editing
  a line item to match the total invents a cost. Neither is safe to guess.

### T-010 — CAD dataset, engineering model, robotic-joint mechanical validation

Owner: unassigned
Mode: build
Status: review (local branch `wip/stack`; not pushed)
Depends on: `fix/adapter-timeout-decode` and `fix/producer-cross-reference-checks` (cherry-picked as `3639778`, patch-identical); both are in the stack below this work

Goal
: A STEP design becomes an engineering model whose every value states its
  source and status, and one domain -- mechanical -- is validated end to end
  through the existing V0-V4 contract, on an architecture the other domains
  attach to without changing it.

Acceptance criteria (verbatim from the issue #27 implementation plan)
: - "Build the CAD dataset + engineering semantic model + first robotic-joint
    mechanical validation example, with enough structure that the exact same
    data architecture can support the next eight domains."

Files in scope
: `schemas/engineering-model/v1/`, `schemas/cad-dataset/v1/`, `tools/ecad_model/`,
  `tools/cad_dataset.py`, `tools/requirements-cad.txt`, `tools/constraints-cad.txt`,
  `datasets/cad/`, `tests/unit/test_engineering_model.py`,
  `tests/unit/test_cad_dataset.py`, `tests/mutation/run_mutations.py`, the
  `cad-dataset` job in `.github/workflows/ci.yml`, documentation,
  `ECAD_MULTI_DOMAIN_DATASET_PLAN.md`.

Out of scope
: Every domain other than mechanical; importers other than STEP; the v1
  receipt contract, which is reused unchanged; the product inventory. The
  multi-domain foundation is planned in `ECAD_MULTI_DOMAIN_DATASET_PLAN.md`
  §21 item 3 and in progress on the local branch
  `feat/multi-domain-foundation`, which builds on this one.

Risks
: MuJoCo stages have not run on native Linux x86_64: under emulation on Apple
  silicon the CPU has no AVX and `import mujoco` aborts, so only OpenCASCADE
  reproduction was verified there. Whether the `ubuntu-22.04` runner image
  ships `libGL.so.1` is unknown; the job installs `libgl1`. `cadquery-ocp`
  cannot be installed on the Python 3.10 legs, where the dataset tests skip by
  design. Push access is read-only for this account.

Verification (code at `bd999d5`, 2026-09-26)
: | Check | Command | Result |
  |-------|---------|--------|
  | Complete suite, CAD tests mandatory | `ECAD_REQUIRE_CAD_TOOLS=1 python3 run_all_tests.py` | `PASS` -- 245 passed, 0 skipped (macOS arm64, Python 3.14.4) |
  | Lint, new code | `ruff check tools/ecad_model tools/cad_dataset.py tests/unit/test_cad_dataset.py tests/unit/test_engineering_model.py tests/unit/test_ci_and_runner.py tests/mutation datasets/cad --select=E,F,W --ignore=E501` | `PASS` -- no findings |
  | Type check | `mypy tools run_all_tests.py tests/mutation/run_mutations.py --ignore-missing-imports --no-strict-optional` | `PASS` for new code -- the 11 errors reported are the same set as on `fea3fc4`, all in existing modules |
  | Derivation reproduces from the CAD | `python3 tools/cad_dataset.py check datasets/cad/robotic_joint_001` | `PASS` -- exit 0 |
  | V0-V4 receipt on a clean clone | `python3 tools/cad_dataset.py validate datasets/cad/robotic_joint_001 --output <dir>` | `PASS` as designed -- V0-V3 PASS; V4 BLOCKED: five illustrative limits met (WARNING) and REQ-XD-001 BLOCKED on the unselected actuator; not eligible for ebuild; 76 evidence digests re-hash |
  | Test discrimination | `python3 tests/mutation/run_mutations.py --workers 3` | `PASS` -- 68 of 68 mutants killed, after the unmutated baseline passed; each kill names the failing test |
  | Skip cannot go silent | the two dataset test files with `OCP`/`mujoco` absent, with and without `ECAD_REQUIRE_CAD_TOOLS=1` | `PASS` -- 45 skipped, each with a reason / all 45 red (25 failed, 20 errors) |
  | Linux aarch64 | the CI job's steps in `python:3.12-slim` with only `git` and `libgl1` added, offline from the pinned wheels | `PASS` -- `check` exit 0; 245 passed; `validate` gives the same gate verdicts as macOS |
  | Linux x86_64 | `check` in `python:3.12-slim` under emulation | `PASS` for OpenCASCADE reproduction (`check` exit 0, at `c9be0b6`). MuJoCo stages `NOT RUN`: the emulated CPU has no AVX and `import mujoco` aborts |
  | Pinned set resolves on Linux | `pip download -r tools/requirements.txt -r tools/requirements-cad.txt -c tools/constraints-cad.txt` for x86_64 and aarch64, Python 3.12 | `PASS` -- all 23 pins resolve unchanged |
  | Independent review | two reviews and a check of the plan's claims against the code, each finding checked by a separate verifier | `PASS` -- every confirmed finding within this task is fixed on the stack (`f4398f4`, `c9be0b6`, `bd999d5`); five in existing merged code or later domains are open, each listed with its owner in the plan §7.2 |

### T-011 — Multi-domain foundation: domain adapters, null statuses, per-requirement results

Owner: unassigned
Mode: build
Status: review (local branch `feat/multi-domain-foundation`; not pushed)
Depends on: T-010 (`wip/stack`, which this branch builds on)

Goal
: The dataset pipeline knows no engineering domain: each domain attaches
  through one adapter, a value can be missing in the three ways the
  specification distinguishes, every requirement gets a result that says what
  was measured against what on which inputs, and the dataset metadata and
  licence provenance are what the specification asks for.

Acceptance criteria (verbatim from `ECAD_MULTI_DOMAIN_DATASET_PLAN.md` §21 item 3)
: 1. "No derived number changes." (with the named exceptions listed there)
  2. "No mechanical names (`mjcf`, `mujoco`, `derived/mechanical`, `.step`) in `dataset.py` or `requirements.py` outside the mechanical adapter"
  3. "No existing assertion is deleted or weakened; the mutation suite is re-anchored with a green baseline and zero survivors"
  4. "For each of `UNKNOWN`, `UNSPECIFIED`, `NOT_AVAILABLE`, as a density and as a limit: `BLOCKED MISSING_REQUIRED_INPUT` with the status and the path, and a schema-valid receipt."
  5. "With a requirement that is *not* illustrative, an `AI_ASSUMPTION` density, and separately an `AI_ASSUMPTION` limit quantity, give `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` both when the limit is met and when it is violated"
  6. "A test-only sample with no STEP ... its domain is `AVAILABLE`, mechanical `NOT_APPLICABLE` and every other domain `NOT_IMPLEMENTED`; without that adapter registered, `build` refuses and `validate` is `BLOCKED DOMAIN_NOT_IMPLEMENTED`."
  7. "One result per requirement and reference, naming the receipt check that decided it ..."
  8. "The manifest's domain status is derived from the registry, and a test forging it fails `check`."
  9. "The versioning rule of §9.3 replaces the pre-release declaration in the schema documentation, taking effect at the merge."
  10. "The protocol is exercised end to end by a test-only artefact-first adapter"

Files in scope
: `tools/ecad_model/` (domains/, results.py, dataset.py, requirements.py,
  quantity.py, builder.py, mjcf.py), `schemas/engineering-model/v1/`,
  `schemas/cad-dataset/v1/`, `datasets/cad/robotic_joint_001/`,
  `tests/unit/test_engineering_model.py`, `tests/unit/test_domain_adapter.py`,
  `tests/unit/test_cad_dataset.py`, `tests/mutation/run_mutations.py`,
  documentation, the plan.

Out of scope
: Any domain but mechanical; renaming `dataset-item.json` or moving
  `datasets/cad/`; training records; cross-domain rules (`from_result`).

Risks
: The adapter protocol is provisional: one production domain uses it, and the
  test-only Verilog adapter runs no simulator, so no metric has yet been
  parsed from a non-Python tool. The engineering-model and cad-dataset v1
  schemas change in place relative to the stack; they are declared stable
  from this branch's merge.

Verification (2026-09-26/27; code at `000309b` unless a row names another commit. `000309b` differs from `dbf73e1` only in one test fixture; `dbf73e1` from `bb43124` by the fourth review's fixes)
: | Check | Command | Result |
  |-------|---------|--------|
  | Complete suite, CAD tests mandatory | `ECAD_REQUIRE_CAD_TOOLS=1 python3 run_all_tests.py` | `PASS` -- 332 passed, 0 skipped, on a clean clone, the tree clean afterwards (macOS arm64, Python 3.14.4) |
  | Lint, new code | `ruff check tools/ecad_model tools/cad_dataset.py tests/unit/test_cad_dataset.py tests/unit/test_engineering_model.py tests/unit/test_domain_adapter.py tests/unit/test_ci_and_runner.py tests/mutation datasets/cad --select=E,F,W --ignore=E501` | `PASS` -- no findings |
  | Type check | `mypy tools run_all_tests.py tests/mutation/run_mutations.py --ignore-missing-imports --no-strict-optional` | `PASS` for new code -- the same 11 errors in the same seven existing modules as at `bd999d5`; none in `tools/ecad_model` |
  | Derivation reproduces | `python3 tools/cad_dataset.py check datasets/cad/robotic_joint_001` on a clean clone of `dbf73e1` | `PASS` -- exit 0 |
  | Criterion 1 on a clean clone of `dbf73e1` | `validate`, then every check's verdict and metrics against the clean-clone receipt of `bd999d5`, and the results against those of `bb43124` | `PASS` -- the 19 checks both runs have give identical verdicts and metrics; `v2.cad-model-invariants` is split into `v2.dataset-reproduction` and `v2.mechanical.model-invariants`, both `PASS`; the other differences are the named renames. V0-V3 `PASS`, V4 `BLOCKED` as designed; 94 evidence digests re-hash (the rise from 82 is the recorded inputs of each check); 15 results, bound to the receipt, identical to `bb43124`'s apart from run-bound fields |
  | Criterion 2 | `grep -nE "mjcf\|mujoco\|derived/mechanical\|\.step" tools/ecad_model/dataset.py tools/ecad_model/requirements.py` | `PASS` -- no match |
  | Test discrimination | `python3 tests/mutation/run_mutations.py --workers 7` (and `--only` for the second part) | `PASS` -- at `dbf73e1`, 222 of 222 mutants killed in two runs, each after the unmutated baseline passed (54, then the other 168), each kill naming its test (96 by `test_engineering_model.py`, 84 by `test_domain_adapter.py`, 42 by `test_cad_dataset.py`). The two earlier full runs each left one survivor that was a missing test, closed by `b4fca10` and `7b58a76` |
  | Skip cannot go silent (at `bb43124`) | the dataset test files with `OCP`/`mujoco` absent, with and without `ECAD_REQUIRE_CAD_TOOLS=1` | `PASS` -- the 50 CAD tests skip, each with a reason, and the 122 fast tests (the adapter fixture included) still pass / with `ECAD_REQUIRE_CAD_TOOLS=1` all 50 are red (26 failed, 24 errors) |
  | Linux aarch64 | the CI job's steps in `python:3.12-slim` with only `git` and `libgl1` added, offline from the pinned wheels, on a clean clone of `000309b` | `PASS` -- `check` exit 0; 332 passed; `validate` gives the same gate verdicts as macOS. One subtest is skipped on Python 3.12, with its reason: the document nested too deeply to *check* cannot be built there, because 3.12's JSON parser and `repr` stop at the same depth (about 10 000); the too-deep-to-parse case runs. At `dbf73e1` this subtest failed in its fixture, the reason for `000309b` |
  | Linux x86_64 | -- | `NOT RUN` on this branch; MuJoCo cannot run under emulation here (T-010) |
  | Independent review | four reviews, each finding checked by a separate verifier: five lenses on the foundation; a check of every fix; a focused review of the second round and the documentation; the same of the third | `PASS` -- 59 findings confirmed (2 refuted); then 49 found fixed and 10 partly, with new defects in the fixes; then 19 more, none refuted; then 22 more, none refuted. All closed on `dbf73e1` (plan §7.5). The fourth round's fixes have had no review of their own. One defect in merged code is open: ENGINE-1 (plan §7.2) |

### T-012 — Electrical domain: the servo supply input on ngspice

Owner: unassigned
Mode: build
Status: review (local branch `feat/domain-electrical`; not pushed; no independent review yet)
Depends on: T-011 (`feat/multi-domain-foundation` at `042f934`, which this branch builds on)

Goal
: A SPICE netlist becomes an engineering model whose every value states its
  source and status, ngspice runs a deck written from that model, and the
  electrical domain is validated end to end through the same V0-V4 runner as
  mechanical, on a sample that invents no part, rating or requirement.

Acceptance criteria (verbatim from `ECAD_MULTI_DOMAIN_DATASET_PLAN.md` §21 item 4)
: 1. "ngspice supply sample"
  2. "output capture and metric parsing"
  3. "version parsing"
  4. "`spice` CI job"
  5. "First artefact-first domain; the protocol stops being provisional here, and the PR lists every protocol change the domain forced with the matching change to the mechanical adapter (SCOPE-15)."

Acceptance criteria (verbatim from the plan §10, for every domain)
: 6. "Each domain lands as one PR with: at least one sample; a met limit (`PASS` against a real requirement, `WARNING` against an illustrative one), a `FAIL` from a mutated input and a `BLOCKED` from a missing input; an invalid-input and a boundary sample (spec §21); negative tests and mutants; per-domain documentation (spec §28); and a CI job that makes a skip a failure."

State of each criterion (the plan §21 item 4 carries the same markers)
: 1. IMPLEMENTED: `datasets/cad/servo_supply_001` builds, checks and validates as designed (Verification).
  2. IMPLEMENTED for ngspice (ARCH-2, the ngspice half); the `run_process` output copy is not needed by ngspice and stays open for the HDL and KiCad domains.
  3. IMPLEMENTED (RESULT-8); RESULT-2 is PARTIAL, fixed on the ngspice path only.
  4. PARTIAL: the job is written and its shape is tested; it has never run, and ngspice is not pinned (BLOCKED until the runner's version is known).
  5. IMPLEMENTED: `domains/base.py` and the plan §11 state the protocol stable and list its one change, `Extraction.producer`.
  6. Sample IMPLEMENTED. Met limit: `WARNING` against the illustrative limits IMPLEMENTED; `PASS` against a real requirement only on a test-built copy with a fixture rating, since no real part is selected. `FAIL` from a mutated input IMPLEMENTED (test-built copies, real ngspice). `BLOCKED` from a missing input IMPLEMENTED (the committed sample). Invalid-input and boundary samples PARTIAL: test-built copies, not committed items (plan §20 Q17). Negative tests IMPLEMENTED; mutants PARTIAL: the 63 new ones were run (Verification), the full run of all 285 was not. Documentation IMPLEMENTED (`docs/electrical-domain-v1.md`). CI job PARTIAL, as in 4.

Files in scope
: `tools/ecad_model/spice.py`, `tools/ecad_model/domains/` (electrical.py,
  base.py, mechanical.py, `__init__.py`), `tools/ecad_model/__init__.py`,
  `tools/ecad_model/dataset.py`, `tools/ecad_validation/adapters/ngspice.py`,
  `tools/ecad_validation/adapters/capabilities.py`,
  `schemas/engineering-model/v1/` (engineering-model, design-annotations,
  electrical-vocabulary), `datasets/cad/servo_supply_001/`, the regenerated
  `datasets/cad/robotic_joint_001/dataset-item.json`, `.gitattributes`,
  `tests/unit/test_spice_netlist.py`, `tests/unit/test_ngspice_adapter.py`,
  `tests/unit/test_electrical_domain.py`, `tests/unit/test_electrical_spice.py`,
  the edited `test_domain_adapter.py`, `test_engineering_model.py` and
  `test_ci_and_runner.py`, `tests/mutation/run_mutations.py`, the `spice` job
  in `.github/workflows/ci.yml`, documentation, the plan.

Out of scope
: Other network classes, element types, analyses and subcircuits; LTspice and
  PSpice; a KiCad schematic importer; the SEC-2 runner guard (its own
  foundation change, plan §7.2); the general RESULT-2 fix; moving
  `datasets/cad/` (the brief kept the layout, plan §20 Q8); training records.

Risks
: The CI runner's ngspice is Unknown until the `spice` job runs: ngspice-36
  and 44.2 were checked only through their recorded output, and a version
  that prints differently makes cases `INCONCLUSIVE` or `BLOCKED`, loudly.
  The reference tolerances rest on ngspice-47 on macOS arm64. ngspice's stdout
  can differ run to run in its progress report (plan §20 Q11). A committed
  case document still runs before the runner decides what counts (SEC-2).
  The mutation harness now needs ngspice, the CAD kernel and MuJoCo on one
  machine. Push access is read-only for this account.

Verification (2026-09-27, macOS arm64, Python 3.14.4, ngspice-47; code at `37b2de7` plus this change's docstring fix)
: | Check | Command | Result |
  |-------|---------|--------|
  | Complete suite, CAD and ngspice tests mandatory | `ECAD_REQUIRE_CAD_TOOLS=1 ECAD_REQUIRE_SPICE_TOOLS=1 python3 run_all_tests.py -q -p no:cacheprovider --tb=short` | `PASS` -- 397 passed, 0 failed, 0 skipped, exit 0 (249 s); the tree unchanged afterwards. The 63 electrical tests (16 parser, 14 ngspice adapter, 26 domain, 7 real ngspice) are among them |
  | Lint, changed Python | `ruff check <the 17 Python files changed since 042f934> --select=E,F,W --ignore=E501` | `PASS` -- "All checks passed!" |
  | Type check | `mypy tools run_all_tests.py tests/mutation/run_mutations.py --ignore-missing-imports --no-strict-optional` | `PASS` for new code -- "Found 11 errors in 7 files (checked 44 source files)", the baseline set, none in `tools/ecad_model` |
  | Derivation reproduces, clean copy | `python3 tools/cad_dataset.py check datasets/cad/servo_supply_001`, then `build`, then `git status --short` | `PASS` -- `check` exit 0; `build` exit 0, five files written, 0 lines of `git status` |
  | V0-V4 receipt, clean copy | `python3 tools/cad_dataset.py validate datasets/cad/servo_supply_001 --output <dir>` | `PASS` as designed -- exit 0; V0-V3 `PASS`; V4 `BLOCKED`: REQ-EL-001..004 `WARNING WITHIN_ILLUSTRATIVE_LIMIT`, REQ-EL-005..007 `BLOCKED MISSING_REQUIRED_INPUT` (48.0, 0.0533906, 372.465 measured by `v3.REF-EL-001`); not eligible; 16 results bound to the receipt; 82 evidence digests re-hash; ngspice version `47` |
  | FAIL from a mutated input, real ngspice | clean copies with `R_PRE ... 1` and with the bypass command at 5 ms, rebuilt, `check`, `validate` | `PASS` -- REQ-EL-001 `FAIL CORNER_LIMITS_FAILED` at 40.6812 A, every reference `PASS`; REQ-EL-002 `FAIL` at 31.2169 V, REF-EL-003 `BLOCKED REFERENCE_NOT_APPLICABLE`; both overall `FAIL` |
  | Without ngspice | `validate` with ngspice absent from `PATH` | `PASS` -- 13 cases `BLOCKED TOOL_NOT_INSTALLED`, 3 `BLOCKED MISSING_REQUIRED_INPUT`, no simulator version in any of the 16 results |
  | Without the CAD kernel | `check`, `build`, `validate` in a virtualenv with only `tools/requirements.txt` and pytest (no OCP, no MuJoCo) | `PASS` -- all exit 0, tree unchanged, same gate verdicts |
  | Skip cannot go silent | `pytest tests/unit/test_electrical_spice.py` with ngspice absent from `PATH`, without and with `ECAD_REQUIRE_SPICE_TOOLS=1` | `PASS` -- 7 skipped, each with its reason / 7 failed |
  | Mechanical sample unchanged | `git diff 042f934 HEAD -- datasets/cad/robotic_joint_001/`; `check datasets/cad/robotic_joint_001` on the clean copy | `PASS` -- one entry changed (electrical `NOT_IMPLEMENTED` -> `NOT_APPLICABLE`); `check` exit 0 |
  | ngspice behaviour the grammar and the docs rely on | probe decks run with `ngspice -b ... </dev/null`, each in its own directory | `PASS` -- reproduced on ngspice-47: `-r` makes no `.meas` and `-o` moves them to the log; `numdgt=12` still prints six digits; a failed `.meas` goes to stderr with exit 0; a duplicate name prints twice; `1M`, `1MEG`, `10uF`, `10F`, `2kohm`, `1ms`, `1mil` read as the traps say; `gnd` is ground; a `pa_00` node is taken over; the title line swallows a card; `+` joins lines; a card after `.end` is read and a missing `.end` accepted; a dangling node is accepted; `.control` `shell`, a working-directory `.spiceinit` (not with `-n`), a `*#` line (even with `-n`) and a `*ng_script` title all ran; `noacct` removes the operating-point table and statistics but not the progress report, and `norefvalue` removes that |
  | Test discrimination, the 63 new mutants | `python3 tests/mutation/run_mutations.py --workers 4 --only <21 names>`, then a scratch driver calling the harness's `run()` for the other 50 (two runs of 25, 5 workers) | `PASS` -- 63 of 63 killed, none survived, each kill naming its test. The harness reported "baseline green" and killed 13 before a 470 s wall-clock limit stopped it; `run()` (the same copy, edit, rebuild and suites, without a second baseline, on the same code and tests) killed 25 of 25 and 25 of 25. Several are killed first by a module's doctests, which run first, rather than by the test the design names |
  | Test discrimination, all 285 mutants | `python3 tests/mutation/run_mutations.py` | `NOT RUN` -- only the 63 new mutants were run in this change; the 222 of the foundation were last run at `dbf73e1` (T-011) |
  | CI `spice` job | the job itself | `NOT RUN` -- push access is read-only; its shape is tested by `test_spice_job_cannot_skip_silently` |
  | ngspice-36 and 44.2 | a real run of either | `NOT RUN` in this session; the adapter tests replay their output as recorded in arm64 containers earlier on 2026-09-27 (`MEMORY.md`) |
  | Linux | the `spice` job's steps in a container | `NOT RUN` |
  | Independent review | CLAUDE.md rule 4 | `NOT RUN` |

## Completed

| ID | Task | Owner | Verified by | Evidence |
|----|------|-------|-------------|----------|
| T-001 | Product data validation engine, generator, component library, taxonomy manifest, and 67 products | — | `validate_products.py --run` · `generate_products.py --check` · `unittest discover` | `132/132 targets passed`, `0 file(s) stale`, `Ran 76 tests ... OK` (2026-08-08) |
| T-007 | CAD generation and tool-backed CAD validation for every catalog-managed product | — | `validate_products.py --run --render` | `132/132 targets passed`; 67 enclosures rendered by OpenSCAD 2021.01, 67 boards parsed by kiutils, 67 outlines parsed by ezdxf (2026-08-08) |

---

## Task template

```markdown
### T-000 — <short title>

Owner: <role>
Mode: <see MODES.md>
Status: todo
Depends on: <task ids, or none>

Goal
: <one sentence: what is true afterwards that is not true now>

Acceptance criteria
: - <observable, checkable statement>
  - <observable, checkable statement>

Files in scope
: <paths the owner is expected to touch>

Out of scope
: <what this task deliberately does not change>

Risks
: <what could break, and what would reveal it>

Verification
: | Check | Command | Result |
  |-------|---------|--------|
  | <name> | `<command>` | `NOT RUN` |
```

## Verification commands for this repository

No verification command was detected at the repository root. Establish the build and test commands before reporting any check as `PASS`; until then every check is `UNKNOWN`.

## Rules

- One task per unit of work that can be verified on its own.
- Acceptance criteria are written before work starts and are not edited to match
  what was built. If they were wrong, say so and rewrite them explicitly.
- A task reaches `done` only when the definition of done in
  [ORCHESTRATION.md](./ORCHESTRATION.md) is met and the verification commands
  were actually run.
- `blocked` requires a note naming what it is blocked on and who can unblock it.
