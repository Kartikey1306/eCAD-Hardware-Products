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
