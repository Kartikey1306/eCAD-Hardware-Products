# eCAD multi-domain engineering dataset and validation plan

Scope: issue #27 (Multi-Domain CAD Validation Pipeline), all nine domains plus
cross-domain validation, answering the specification "Multi-Domain eCAD
Engineering Dataset + Validation + AI Foundation" (§31 of it asks for this
document; its section numbers are cited as *spec §n*).

Base: local branch `wip/stack`, code at `bd999d5`, added to by the
documentation commit that carries this file — `master` (751616a) plus the
stack in §1.1. The first implementation stage (§21 item 3) is in progress
on the local branch `feat/multi-domain-foundation`, which forks from this
commit. An independent review of that branch has open findings, so each of
its items is `PARTIAL` here; the branch updates these markers as it closes
them. Nothing here is pushed. Every statement about the
repository was checked against that state. Load-bearing claims carry an
evidence label per `CLAUDE.md`: **Verified** (a command was run and its output
read), **Observed** (visible in the code), **Inferred**, **Assumed**,
**Unknown**.

This revision incorporates an independent five-lens review of the previous
draft (scope, architecture, contracts, accuracy, honesty/coverage), each lens
checked by a separate verifier. Its findings are cited by ID (SCOPE-n, ARCH-n,
…) where they changed the plan.

Implementation state uses exactly four labels (spec §38):

| Label | Meaning |
|---|---|
| `IMPLEMENTED` | Runs end to end on a committed sample, with tests that have been seen failing against broken code. |
| `PARTIAL` | Some stages exist and run; others are missing, or known defects are open. |
| `PLANNED` | Designed here; no code. |
| `BLOCKED` | Cannot proceed without something outside the code: a tool, a licence, a decision, or data. |

These are labels for this document only. Data uses the spec §34 vocabulary
(§12.3).

### Summary (spec §40, A–K)

| | Where |
|---|---|
| A. Repository findings | §1, §4–§6; defects §7 |
| B. Existing architecture | §1–§3 |
| C. Missing pieces | §7.2–§7.3 |
| D. Proposed architecture | §8, §11, §12 |
| E. Dataset schema | §9 |
| F. Engineering model schema | §8 |
| G. Domain roadmap | §10, §21 |
| H. Simulator roadmap | §11.1 |
| I. Training roadmap | §15 |
| J. Test strategy | §16 |
| K. First implementation PR | §21 item 3, with its acceptance criteria |

---

## 1. Current repository architecture

| Area | Location | What it is | State |
|---|---|---|---|
| Product catalogue | `e*_CAD_Design/`, `future_designs/`, `tools/catalog/` | 125 inventoried products (115 design, 10 future concept); 67 generated from `tools/catalog/` (**Verified**) | IMPLEMENTED |
| Legacy validators | `tools/validate_products.py` | BOM arithmetic, datasheet contract, simulation execution, CAD invariants via `kiutils`/`ezdxf`/OpenSCAD. Tolerates findings listed in `tools/product_baseline.json`, where V0–V4 fails closed (§5) | IMPLEMENTED |
| V0–V4 contract | `schemas/hardware-validation/v1/`, `contracts/hardware-validation/v1/` | Receipts, gates, verdicts, evidence index, bundles; 5 `POLICY:` requirements | IMPLEMENTED (merged, PR #30, 751616a) |
| V0–V4 engine | `tools/ecad_validation/` | `engine.py` (V0–V2 via the legacy validators), `cases.py` (V3/V4 from `validation/*/cases.json`), `evidence.py`, `models.py` (typed results, fail-closed aggregation) | PARTIAL — defects open on master, fixed only on unpushed branches (§1.1); V3/V4 exercised by no product; RESULT-2 and STATE-2 (§7.2) open |
| Tool adapters | `tools/ecad_validation/adapters/` | `python_control`, `mujoco`, `ngspice`, `kicad` (kicad-cli DRC), `iverilog`. Four run through the hardened `run_process`; **`iverilog` calls `subprocess.run` directly** with the inherited environment and no output cap (`hdl.py:51-100`, **Observed**). **Only `python_control` and `mujoco` emit metrics**; `ngspice`, `iverilog` and `kicad` decide from the exit code and return none, so their V3/V4 cases can only be `INCONCLUSIVE` (ARCH-2) | PARTIAL |
| CAD dataset + engineering model | `tools/ecad_model/`, `schemas/engineering-model/v1/`, `schemas/cad-dataset/v1/`, `datasets/cad/robotic_joint_001/` | STEP → isolated OpenCASCADE extraction → engineering model with provenance → MJCF → MuJoCo → V0–V4 receipt | PARTIAL — works end to end; the base types are STEP-bound (§7.3) |
| RTL | `rtl/spi_master.v`, `uart_rx.v`, `uart_tx.v` | 352 lines of Verilog | PARTIAL — `tests/test_rtl_models.py` tests Python re-implementations; the HDL is never compiled (**Observed**) |
| PCB artefacts | 67 `.kicad_pcb`, 69 `.net`, 9 `.kicad_sch`, 67 `.dxf`, 67 `.scad` | Generated boards: placed footprints, no pads, no traces, no signal nets, by design (`MEMORY.md`) | PARTIAL — structural checks only |
| Dev-board database | open PR #31 (`schemas/devboard-cad/v1/`, `tools/devboard_cad/`) | Board-record catalogue for issue #28 | PARTIAL — open PR, not merged; complementary (§20 Q6) |
| CI | `.github/workflows/ci.yml` | Test matrix (3 OS × Py 3.10–3.12); `validation-evidence` job; `cad-dataset` job (on the stack only). **Gaps:** ruff and mypy are `continue-on-error` on master (mypy made blocking on unpushed `ci/enforce-type-check`); nothing compiles HDL, runs SPICE, or fetches LFS content | PARTIAL |

### 1.1 Local branches (none pushed; push access is read-only for this account)

| Branch | Head | Content |
|---|---|---|
| `fix/adapter-timeout-decode` | `fea3fc4` | Tool timeouts no longer crash the whole run |
| `ci/enforce-type-check` | `fa49e86` | mypy scoped, pinned, blocking (stacked on the above) |
| `fix/bom-stated-totals` | `9abb06e` | Six BOM totals; 4 of 6 await owner confirmation (`TASKS.md` T-003) |
| `chore/declare-simulation-dependencies` | `ce59617` | matplotlib and scipy, with an import guard |
| `fix/portable-evidence-paths` | `e4b6513` | No host paths in hash-bound legacy evidence |
| `fix/producer-cross-reference-checks` | `6e6aae3` | Producer refuses bundles its own verifier rejects |
| `wip/stack` | the documentation commit carrying this file | `fea3fc4` → `3639778` (the cross-reference fix, cherry-picked; patch-identical to `6e6aae3`) → the mechanical pipeline (`b965aa4`, `17a4770`) → review fixes `f4398f4`, mutation suite `8db907e`, pins `9c5b890`, second-review fixes `c9be0b6`, harness `be63d19`, fixes from a check of this plan's claims `bd999d5` (§7), then the documentation commit |
| `feat/multi-domain-foundation` | on the documentation commit | Forked from the stack; §21 item 3, in progress (marked there) |
| `fix/version-probe-reason-codes` | not written | RESULT-2 (§7.2); planned for §21 item 1 |

`feat/cad-dataset-engineering-model` (`50a8557`) is the pre-review version of
the mechanical pipeline; `wip/stack` supersedes it.

---

## 2. Existing reusable abstractions

| Abstraction | Where | Reuse |
|---|---|---|
| `Adapter`, `Capability`, `AdapterRequest`, `AdapterResult` | `ecad_validation/adapters/base.py` | Every domain's **tool** layer, one adapter per simulator or checker. Needs a metrics-and-outputs step before non-Python tools can produce results (ARCH-2) |
| `run_process` | `ecad_validation/adapters/process.py` | Process hardening, **not a sandbox**: workspace copy, scrubbed environment, timeout, and post-hoc truncation of buffered output. No filesystem or network confinement, no memory or CPU limit (SEC-1). Deletes its workspace before returning, so declared outputs are lost today (ARCH-2) |
| `CheckResult`, `GateResult`, `ProductRunResult`, `Verdict`, `ExecutionStatus` | `ecad_validation/models.py` | Every domain's gate-level results, unchanged |
| Case engine (`execute_cases`, `_compare_golden`, `_compare_corner`) | `ecad_validation/cases.py` | Deterministic numeric comparison for any domain that emits numeric metrics |
| Canonical JSON + SHA-256 | `ecad_validation/hashing.py` | Every digest |
| Quantity with status, source and `derived_from` | `ecad_model/quantity.py`, `engineering-model/v1/common.schema.json` | Every engineering value in every domain |
| Engineering model: components, per-domain facets, joints, relationship graph, unknowns index | `ecad_model/builder.py`, `engineering-model.schema.json` | The shared system model. Facet values are numeric only and relationships link components, not pins or nets (ARCH-1) |
| `CADImporter` + detection by content | `ecad_model/importers/` | A **pattern to copy** for other artefact parsers, not reusable as is: it returns a cad-extraction document, and SPICE decks and Verilog have no byte signature (FACT-6) |
| Requirement compiler | `ecad_model/requirements.py` | The pattern (references → V3, requirements → V4, unknown limit → `BLOCKED`) is general; the code is mechanical-bound: `_case` hard-codes adapter `mujoco` and `simulation/joint_dynamics.py`, and scenarios and derivations are closed mechanical enums (FACT-6) |
| Dataset item: provenance, hashes, integrity vs reproducibility | `ecad_model/dataset.py`, `cad-dataset/v1/` | Every sample, once the STEP-bound parts are generalised (§7.3) |

## 3. Existing validation contracts

- **V0–V4 receipt** (`validation-receipt.schema.json`): per-product, per-gate,
  per-check verdicts, reason codes, metrics, evidence; fail-closed aggregation;
  `execution_complete` separate from `eligible_for_ebuild`. Reason codes are an
  open pattern (`^[A-Z][A-Z0-9_]*$`), so new codes need no contract change.
  Merged; this plan does not change it.
- **Cases** (`validation-cases.schema.json`): V3 `expected_metrics` (value ±
  absolute tolerance), V4 `metric_limits` (minimum/maximum). The adapter is a
  closed enum of five. Merged; a new simulator needs a contract amendment
  (§20 Q9).
- **Requirements** (`requirements.schema.json`): closed and prose-only. Hence
  the separate numeric `engineering-requirements` schema.
- **Evidence index / bundles**: content-addressed evidence, hash-bound
  documents, consumer verification.
- **Engineering-model v1 and cad-dataset v1** (on the stack): quantity, model,
  annotations, requirements; extraction, dataset item, source provenance.
  **Versioning:** these families are declared pre-release until the foundation
  PR merges, and are amended in place until then. From that merge on, the
  repository rule applies: an incompatible change needs a new versioned
  directory (SCOPE-1, §9.3).

## 4. Existing CAD extraction

STEP only, through `cadquery-ocp` 8.0.1 (OpenCASCADE), in a child process via
`run_process`. Per part: name, occurrence, placement, solid and face counts,
volume, area, centre of mass, unit-density inertia about the centre of mass
(**Verified** convention), local bounding box, cylindrical faces. The document
unit is pinned to millimetres because `GetLengthUnit_s` loses its value in the
binding (**Verified**).

Refused explicitly: ASCII STL and binary glTF (recognised by content, no
importer); external document references, before parsing and again when the
reader reports external files after transfer (both layers **Verified** on a
multi-file assembly written by OCCT); sub-assemblies; scaled or mirrored
placements; duplicate part names; Git LFS pointers; anything that is not a
regular file; files over 256 MiB. `build`, `check` and `validate` refuse an
item containing a symlink before reading it; `check` and `validate` refuse an
item git cannot enumerate before the parser runs.

Not extracted: materials carried in STEP, colours, product metadata, mates.

## 5. Existing V0–V4 system

For products, V0 checks schema and artefacts, V1 runs simulations, V2 checks
CAD invariants, V3/V4 run golden and corner cases. The legacy path tolerates
baselined findings; V0–V4 fails closed. On master all 125 products are
`BLOCKED` or `FAIL`, and **V3/V4 never execute**: no product ships
`cases.json` (**Verified**, audit §1).

The dataset runner maps V0–V4 onto a sample: V0 schemas, hashes, provenance
and cited sources; V1 re-extraction and physical sanity; V2 reproducibility,
manifest and cross-references; V3 closed-form goldens; V4 requirements. On a
clean checkout of the stack, `robotic_joint_001` gives V0–V3 `PASS`; in V4
`v4.REQ-XD-001` is `BLOCKED` because the actuator's torque is `UNKNOWN`, and
the other five limits are met, reported `WARNING` (`WITHIN_ILLUSTRATIVE_LIMIT`)
because every limit is illustrative (**Verified**: clean clone of `bd999d5`, macOS arm64; all 76 evidence digests re-hash and the index is bound to the receipt). The
receipt is `BLOCKED` and not eligible for ebuild, as it should be.

## 6. Current dataset capabilities

One sample, `datasets/cad/robotic_joint_001`: self-authored STEP (MIT),
hand-written `source/provenance.json`, annotations, 9 reference values, 6
requirements (all `illustrative`), derived extraction / model / MJCF / cases,
and `dataset-item.json`, which hashes every file and already records
description, artefact type and version, units, coordinate system, created and
collected dates, licence and its verification, and component versions.
`build`, `check`, `validate`. Tests: 95 in the two dataset test files, 245 in
the complete suite (**Verified** at `bd999d5`: all pass on macOS arm64, Python
3.14, CAD tools mandatory). Mutation suite: 68 mutants. Not present: training records, a second domain, a
per-requirement result record, a domain adapter layer.

## 7. What is missing, partial, or unsafe

### 7.1 Defects found by independent review of the mechanical pipeline, and their state

A first independent review of `50a8557` had five lenses. Each finding was
checked by a separate verifier trying to refute it: 41 findings, 38 confirmed,
2 refuted, and 1 (S2) not verified on its own because it duplicates I1, which
was. (These counts are **Unknown** to a reader of the repository: they come
from the review run's journal, which is local to the authoring session.)
"Fixed" means the code changed on `wip/stack`; where the last column names a
test, that test fails without the change. A named mutant is killed by a test
in `tests/mutation/run_mutations.py`, which runs a green baseline first and
names the killing test. At `bd999d5` the unmutated baseline passed and all 68
mutants were killed, each by a named test (38 in `test_cad_dataset.py`, 30 in
`test_engineering_model.py`) (**Verified**, 2026-09-26). A mutant of a dataset item's own
file (its simulation script) is followed by a rebuild of that item, so the
manifest's hash of the script cannot be what kills it (ACC-1). Rows marked
*data or doc change* have no test because nothing executable changed.
Nothing here has landed.

| ID | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| P1 | Rotation sense from a canonical axis sign: a 0.2° yaw of the CAD mirrors the joint range | Fixed: required `axis_sense`; CAD line oriented to it; >60° off → `UNKNOWN` | `test_physics_is_invariant_under_a_rigid_yaw_of_the_whole_design`, `test_the_annotated_sense_sets_the_direction_of_a_positive_angle`, `test_a_sense_far_from_the_cad_axis_is_unknown` · `axis-sense-ignored`, `axis-sense-threshold-off` |
| P2 | Joint realised by its own child: the joint pair itself was excluded, so clearance passed on overlap | Fixed: bearing pair follows the realiser's rigid group; excluding the joint pair is reported as `rom_joint_pair_unchecked` | `test_a_joint_realised_by_its_own_child_excludes_the_joint_pair_openly` · `joint-pair-unchecked-hidden` |
| P3 | Fixed pin on the parent side: bearing never excluded, clearance failed at every pose | Fixed | `test_a_fixed_pin_runs_in_the_child`, `test_a_shaft_on_the_moving_side_runs_in_the_parent` · `fixed-pin-not-excluded`, `bearing-vs-fixed-root` |
| T1 | No test made V0, V1 or V2 fail | Fixed | `test_v0_fails_on_a_hash_mismatch`, `test_v1_fails_on_impossible_joint_limits`, `test_v2_fails_on_a_hand_edited_derived_file_even_with_its_hash_updated` · `integrity-no-byte-compare`, `v1-sanity-skipped`, `v2-reproducibility-skipped` |
| T2 | Clearance tested only with penetration | Fixed | `test_a_positive_clearance_below_the_requirement_fails` · `clearance-by-contact-only` |
| T3 | Rated-move metrics had no reference | Fixed: closed-form minimum-jerk peak speed, acceleration and torque | `test_minimum_jerk_peaks`, `test_rated_move_peak_torque_for_a_point_like_bob` · `min-jerk-velocity-wrong`, `min-jerk-accel-wrong`, `move-torque-ignores-gravity`, `proxies-push-on-statics` |
| T4 | Rated-payload override never observed | Fixed: applied to reference and simulation alike | `test_the_payload_override_is_applied_to_every_reference` · `payload-override-ignored`, `payload-override-not-applied` |
| T5 | `Rᵀ I R` in place of `R I Rᵀ` survived | Fixed | `test_inertia_rotates_as_r_i_r_transpose` · `inertia-rt-i-r` |
| T6 | Every fixture axis was +Y and horizontal | Fixed | `test_period_of_a_tilted_axis_uses_the_perpendicular_gravity`, rigid-yaw test · `g-perp-is-gravity`, `lever-ignores-origin` |
| T7 | Coaxial faces at different axial positions untested | Fixed | `test_coaxial_faces_at_different_axial_positions_share_one_axis` · `coaxial-ignores-axial-offset` |
| T8 | Hand-edited manifest or simulation script undetected | Fixed: every file hashed; manifest regenerated and compared | `test_an_edited_simulation_script_breaks_integrity`, `test_an_unrecorded_file_breaks_integrity`, `test_a_hand_edited_domain_status_is_caught` · `unrecorded-files-allowed`, `manifest-check-off` |
| T9 | Tests pinned to the sample's current gaps | Refuted as a defect (latent); a fixture-built ordering test was added anyway | `test_index_is_sorted_whatever_the_facet_order` · `unknowns-unsorted` |
| T10 | Reproducibility tolerance unpinned | Fixed | `test_scalars`, `test_arrays_scale_by_their_largest_element` · `reltol-too-loose`, `per-element-tolerance` |
| T11 | Documented refusals deletable without a failure | Fixed | `TestImporterRefusals`, `test_builder_refuses_inconsistent_annotations`, `test_mechanical_model_refuses_what_it_cannot_represent` · `mirrored-placement-allowed`, `duplicate-names-allowed`, `nested-assembly-allowed` |
| T12 | Receipt requirement binding and trace components untested | Fixed: both halves | `test_committed_item_meets_every_measurable_check`, `test_the_trace_names_both_sides_for_clearance_and_marks_illustrative_limits` · `requirement-binding-dropped`, `clearance-trace-one-side` |
| T13 | Free-swing crossing interpolation and equilibrium angle unchecked | Fixed: `equilibrium_angle` reference | `test_period_of_a_tilted_axis_uses_the_perpendicular_gravity` · `crossing-not-interpolated` |
| I1 = S2 | Per-element reproducibility tolerance fails on Linux kernel noise | Fixed: one tolerance per array, scaled by its largest element | as T10; Linux: §20 R1 |
| I2 | MuJoCo not importable by `python3` on `PATH` → no receipt | Fixed (stacked on the cross-reference fix): a `BLOCKED` receipt | `test_an_unavailable_simulator_gives_a_blocked_receipt_not_a_crash` |
| I3 | Output evidence index does not conform to the contract schema | Refuted (it never claimed to); made conformant anyway | validated against the contract schema on every run |
| I4 | Receipt tool records wrong; CAD kernel missing | Fixed | `test_committed_item_meets_every_measurable_check` · `validator-invocation-wrong`, `kernel-missing-from-receipt` |
| I5 = H5 | Trace omitted the fixed side of the clearance requirement | Fixed | as T12 |
| I6 = H13 | Transitive CAD dependencies unpinned; size and licence notes macOS-only | Fixed: `tools/constraints-cad.txt` pins all 23 with declared licences; resolves on Linux x86_64 and aarch64 (**Verified**) | `test_cad_dataset_job_cannot_skip_silently` |
| H1 | `build` stamped every item self-authored MIT | Fixed: hand-written `source/provenance.json` | `test_building_without_provenance_is_refused` · `provenance-not-required` |
| H2 | Domains without a validator reported `blocked` | Fixed: status from the platform, not the sample | `test_a_hand_edited_domain_status_is_caught` |
| H3 | Cited datasheet hash never checked | Fixed; a citation outside the repository is not read | `test_a_cited_datasheet_that_changed_is_caught`, `test_a_citation_outside_the_repository_is_not_read` · `cited-sources-unchecked`, `citation-outside-repository-read` |
| H4 | Manifest domain statuses unverified | Fixed | as T8 |
| H6 | Recorded validator invocation does not run | Fixed | as I4 |
| H7, H11 | Task ledger: stale test count; mutation `PASS` with no command or artefact | Fixed: `TASKS.md` T-010 regenerated from the runs in §16; harness committed | data or doc change |
| H8 | Attribution named a party `LICENSE` does not | Fixed | data or doc change |
| H9 | Densities cited an unnamed handbook | Fixed: `ESTIMATED`, stating no handbook was consulted | data or doc change |
| H10 | "Illustrative" label lost from cases, receipt, trace and report | Fixed: required `illustrative` flag | as T12 |
| H12 | Doc overstated STL/glTF recognition | Fixed | data or doc change |
| S1 | STEP external references escaped the isolated workspace | Fixed: refused before parsing and after transfer | `test_external_document_references_are_refused_before_parsing`, `test_external_files_the_reader_loads_are_refused_after_transfer`; `../` by the `external_references` doctest · `external-references-allowed`, `string-literals-not-stripped`, `reader-extern-files-unchecked` |
| S3 | `build` wrote through committed symlinks | Fixed; `check` also refuses symlinked items before reading | `test_build_does_not_write_through_a_symlink`, `test_check_refuses_a_symlinked_directory_before_reading_through_it` · `symlinks-allowed`, `check-follows-symlinks` |
| S4 | An item git cannot enumerate made every check vacuous | Fixed; refused before the parser runs | `test_an_item_git_cannot_enumerate_is_refused_not_skipped` · `ignored-item-allowed`, `check-skips-enumeration` |
| S5 | Every extraction failure recorded as `unavailable` | Fixed: rejected → `FAIL`, crash or timeout → `INCONCLUSIVE`, no kernel → `BLOCKED` | `test_each_failure_kind_has_its_own_verdict` · `rejection-reported-unavailable` |
| S6 | A FIFO hung `check`; oversized files read whole | Fixed: every read of item content into memory goes through one regular-file and size guard (the first fix covered only the CAD file, FACT-3); the input digest streams git-listed regular files in 1 MiB chunks and skips anything else | `test_a_fifo_is_refused_without_blocking`, `test_a_fifo_among_the_inputs_is_refused_without_blocking`, `test_oversized_input_is_refused_before_reading` · `fifo-allowed`, `item-read-unguarded` |

### 7.2 Defects found by the review of this plan

| ID | Defect | State |
|---|---|---|
| STATUS-3 | A missing physical input (a part with no material) gave V1 `FAIL DATASET_INPUT_INVALID`, against spec §34 | Fixed on the stack: `BLOCKED MISSING_REQUIRED_INPUT` · `test_a_missing_input_is_blocked_not_a_design_failure` · `missing-input-reported-fail` |
| TRAIN-1 | The provenance schema accepted `license_verified: false` with training use permitted (spec §22) | Fixed on the stack: an unverified licence permits neither · `test_an_unverified_licence_permits_neither_redistribution_nor_training` · `unverified-licence-permits-use` |
| HONESTY-1 | The receipt's `eligible_for_ebuild` is overall `PASS`, so a sample whose illustrative limits all pass would read as release-eligible (latent: `REQ-XD-001` keeps today's receipt `BLOCKED`) | Fixed on the stack: a met illustrative limit is `WARNING` `WITHIN_ILLUSTRATIVE_LIMIT`, which the contract treats as blocking · `test_only_a_real_requirement_can_pass`, `test_committed_item_meets_every_measurable_check` · `illustrative-limit-passes` |
| STATE-2 | V3/V4 execution records and receipt `tools[]` embed the host interpreter's absolute path (`process.py` argv[0], `python_control.py:82`, `cases.py:401`), in 14 of 30 hash-bound evidence files of a dataset run; `fix/portable-evidence-paths` covers only `engine.py` (spec §24) | Open. Existing merged code; extends that fix branch |
| FACT-3, -11, -12 | The first S6 fix guarded only the CAD file; `check` read inputs before refusing symlinks or unenumerable items; the post-transfer external-file refusal was untested | Fixed on the stack (rows S1, S3, S4, S6 above) |
| ACC-9 | `validate` did not refuse a symlinked item (only `build` and `check` did) | Fixed on the stack · `test_check_refuses_a_symlinked_directory_before_reading_through_it` (now `check` and `validate`) · `validate-follows-symlinks` |
| ACC-1 | The simulation-script mutants were killed only by the manifest's hash of the script, so no behavioural test was shown to catch wrong physics there | Fixed in the harness: the item is rebuilt after such a mutant; results in §16 |
| RESULT-2 | On a failed version probe the adapters emit reason codes containing `:`, spaces or `-` (`capabilities.py:45/54/79`); the receipt then fails its own schema and none is written | Open. Existing merged code; fix branch `fix/version-probe-reason-codes`, §21 item 1 |
| ARCH-7 | `python_control` reports the validator's interpreter version, not the model's packages, and may run a different interpreter; receipt tool records were last-writer-wins per `tool_id` | Tool records fixed on the stack: one record per tool keeps only what all its checks share · `test_committed_item_meets_every_measurable_check` · `tool-record-last-writer-wins`. The `python_control` half is open: a prerequisite of the first Python-model domain (§21 item 7) |
| RESULT-8 | Version probes take the first output line; ngspice's is a banner (**Inferred**, ngspice not installed here) | Open; prerequisite of the electrical domain |
| MAP-1 | A `BLOCKED` V3 reference falls back to contract domain `integrated_physics` because only `requirements[]` is searched | Fixed on `feat/multi-domain-foundation` (the lookup covers references); no observable effect for mechanical |

### 7.3 Missing (spec capabilities with no code)

With no code anywhere: training records; electrical, digital, PCB, power,
control, EM, thermal and full-system domains; cross-domain rules beyond a
model-quantity limit (`from_result`, `depends_on`); non-STEP importers.

In progress on `feat/multi-domain-foundation` only, not on the stack (§21 item 3, `PARTIAL`): the
`UNSPECIFIED` and `NOT_AVAILABLE` statuses with one null predicate; the
domain adapter layer, with the mechanical domain refactored onto it;
artefact-neutral sources; tolerance, unit checking and per-domain
vocabularies for requirements; per-requirement results with per-metric
fidelity, inputs and their statuses; propagation of input status
(`AI_ASSUMPTION` → `INCONCLUSIVE`); the spec §4 metadata; the hashed licence
text.

**STEP-bound base types on the stack** (SCOPE-2, FACT-6). `design.source_cad` is required
with format `step`; the manifest requires `source.cad` and
`inputs.annotations`; its derived roles are mechanical; `Item` refuses a
directory without exactly one `source/*.step`; V1 and V2 are hard-wired to
CAD re-extraction. No non-CAD sample can produce a valid model or manifest.

### 7.4 Good foundation

Quantity provenance with `derived_from`; content-hash integrity separate from
tolerance-based reproducibility; hand-written licence provenance;
`UNKNOWN` limit → `BLOCKED`; isolated extraction; no synthesised simulator
version for a `PASS` (`cases.py:439-454`); `implemented` only from the
platform, never from sample data.

---

## 8. Proposed common engineering-model schema

### 8.1 Value status

| Status | Meaning | `value` | Schema rule |
|---|---|---|---|
| `MEASURED` | Observed on a physical artefact | number | source kind `measurement` |
| `SPECIFIED` | Stated by a datasheet, requirement, CAD property or the design | number | — |
| `DERIVED` | Computed from recorded values | number | `derived_from` non-empty |
| `SIMULATED` | Output of a simulation | number | source kind `simulation` |
| `ESTIMATED` | An engineering estimate | number | `note` required |
| `AI_ASSUMPTION` | Proposed by a model | number | source kind `ai` |
| `UNKNOWN` | Nobody has established it, including "not yet selected" | `null` | `note` required |
| `UNSPECIFIED` | The governing source was consulted and is silent | `null` | source with the silent document's `sha256`, checked like any citation |
| `NOT_AVAILABLE` | Exists in a source this project cannot access or use | `null` | `source.ref` naming that source, and `note` |

The per-status rules make the three null statuses distinguishable by a
checker, not only by the author's choice of label (STATUS-2). Corrections to
the spec's own examples: its thermal example labels a simulation result
`MEASURED` (correct: `SIMULATED`); it uses `DATASHEET` as a status (status and
source are different axes: `SPECIFIED` with `source.kind = datasheet`); it
lists `NOT_RUN` and `BLOCKED` among value placeholders, which are result
verdicts (§12), never value statuses.

**One null predicate.** About ten sites test `== "UNKNOWN"` today
(`quantity.py:96`, `common.schema.json:88-96`, `builder.py:208,419`,
`dataset.py` domain reasons, sanity and blocked checks, `requirements.py:57,278`,
`mjcf.py:86`). Each is replaced by one `is_null(status)` predicate, with a
test per site; without it an `UNSPECIFIED` density raises `TypeError` and no
receipt is written, and an `UNSPECIFIED` limit compiles to
`{"maximum": null}` (STATUS-1). Each unknowns-index entry and each `BLOCKED`
finding also carries the actual status. (In progress on
`feat/multi-domain-foundation`.)

**Status propagation.** A result's inputs are the model paths its metric
depends on, plus the limit's model quantity when the limit is one, and the
transitive `derived_from` leaves of all of them, each with its status (§12.2,
SCOPE-7). The rule is applied in `dataset.validate` after `execute_cases` and
before gate aggregation, so the receipt and the per-requirement result agree,
in this order (the first that applies wins):

1. any null-status leaf → `BLOCKED`, `MISSING_REQUIRED_INPUT`;
2. any `AI_ASSUMPTION` leaf → a V4 `PASS` or `FAIL` becomes `INCONCLUSIVE`,
   `INPUT_IS_AI_ASSUMPTION`; V3 is unaffected, since a golden compares two
   computations on the same inputs (AI-1);
3. a met illustrative limit → `WARNING`, `WITHIN_ILLUSTRATIVE_LIMIT`.

`ESTIMATED` leaves do not change the verdict and are listed in the result.

The `AI_ASSUMPTION` rule is the conservative default for §20 Q7; the case
engine stays status-blind.

### 8.2 Structure

Unchanged from the stack, with these changes:

- **Artefact-neutral sources.** `design.source_cad` becomes `design.sources[]`,
  each `{path, format, sha256}`, where `path` and `format` are one of the
  artefacts the provenance declares. CAD geometry stays optional per
  component (`cad_ref: null` already exists).
- **Per-domain facet vocabulary.** Each domain adapter publishes its facet
  names, units and metric names with units (§11), so cross-domain rules and
  unit checks name parameters, not free text (REQ-3).
- **Fidelity per metric, not per domain** (ARCH-8, SCOPE-12). The adapter
  declares a `model_fidelity` for each metric it produces:
  `EXACT_GEOMETRY`, `REDUCED_ORDER`, `SIMPLIFIED` or `EMPIRICAL`. Mechanical
  statics and dynamics use exact CAD mass properties (`EXACT_GEOMETRY`); the
  range-of-motion clearance runs on bounding-box proxies (`SIMPLIFIED`,
  conservative).
- **Where other domains' structure lives.** Netlists, HDL modules and board
  layers are the artefact, not something written from components and facets.
  An artefact-first domain's adapter parses its artefact into components and
  facets for cross-domain rules, and keeps the artefact itself as its domain
  model (ARCH-1). Nets and pins are not added to the engineering model until a
  cross-domain rule needs them.

Spec entity names map as follows. Mechanical: Part → component with
`cad_ref`; Link → rigid group root; Joint → joint; Material → `material`;
Mass/Inertia/CoordinateFrame → `physical`/`placement`; CollisionGeometry →
the MJCF proxies (domain model). Circuit/Net/PowerRail, Module/Signal/Clock,
Layer/Trace/Via, PowerStage, Plant/Controller, Coil/Excitation and
HeatSource/ThermalInterface are domain-model concepts owned by their adapters,
with the parameters other domains consume published as facets.

## 9. Proposed dataset schema

### 9.1 Layout

The sample layout stays `datasets/cad/<sample>/` until the first sample whose
primary domain is not mechanical (SCOPE-8, LAYOUT-1). Moving now would
rewrite hash-bound provenance: the sample's own path appears 7 times in
hand-written annotations and about 100 times in derived files, and every
changed path would hide in the same diff as the refactor that criterion 1 of
§21 item 3 compares. Before any move, embedded references become sample-relative. The
target layout is a decision for the maintainer (§20 Q8): the spec's
`dataset/<domain>/<sample>/`, or `datasets/<sample>/` with domains in
metadata, which fits a sample that serves several domains
(`robotic_joint_001` is the planned sample for mechanical, control,
cross-domain and full system).

| Spec (§3) | This repository | Why |
|---|---|---|
| `dataset/` | `datasets/` | Existing name |
| `source/` | `source/` — the artefact, its authoring script, `provenance.json` | — |
| `input/` | `design/` — annotations: intent the artefact cannot carry | Existing name |
| `extracted/`, `engineering_model/` | `derived/` — regenerated by `build`, verified by `check` | One regenerated tree is simpler to verify |
| `requirements/` | `requirements/` | — |
| `simulation/` | `simulation/` — case scripts | — |
| `validation/` | `validation/{golden,corners}/cases.json` — compiled | — |
| `evidence/` | written per run to the output directory, not committed | Timestamps make it non-reproducible |
| `training/` | not produced yet (§15) | Spec §37 |
| `metadata.json` | `dataset-item.json` | Renaming changes a schema identifier and 30 references for no added field (SCOPE-9) |
| `README.md` | per sample | — |

### 9.2 Metadata: spec §4 keys

| Spec §4 key | Manifest path | State |
|---|---|---|
| `sample_id` | `item_id` | exists |
| `domain` | `domain` (primary) | **new** |
| `source` | `source.origin`, `source.<artefacts>` | exists; generalised in PR 3 (§8.2) |
| `license` | `source.license.spdx`, `attribution`, `basis` | exists |
| `license_verified` | `source.license.license_verified` | exists; implication rule (§18) |
| `source_url` | `source_url`, copied from the provenance's `origin.url` | `origin.url` exists for third party; absent today for a self-authored sample. **New in PR 3:** a top-level `source_url`, `null` only for `self_authored` (schema-enforced) |
| `artifact_type`, `artifact_version` | same | exist |
| `hash` | `hash`: digest of every git-listed file of the sample except `dataset-item.json` itself, so it can be stored there. The receipt's `input_sha256` covers the same files plus the manifest | **new** (on the foundation branch) |
| `created_at`, `collected_at` | same | exist |
| `author` | `source.origin.author` | exists |
| `description`, `units`, `coordinate_system` | same | exist |
| `extraction_version` | `versions.extraction` | exists |
| `engineering_model_version` | `versions.engineering_model` | exists |
| `simulation_version` | `versions.simulation`: digest of the committed simulation scripts | **new**. Never the simulator's version, which belongs to a run (STATUS-5) |
| `validation_version` | `versions.validation_contract` | exists |

### 9.3 Versioning (SCOPE-1)

- Schema families: `engineering-model/v1` and `cad-dataset/v1` are declared
  pre-release until PR 3 merges, in `docs/cad-dataset-engineering-model-v1.md`
  (Versioning) on the stack, so PR 2 lands them labelled. After PR 3, a
  compatible addition stays in v1 and an incompatible change needs v2.
- Producers: one version constant per producer (importer, builder, each domain
  model writer, compiler, validator) in place of the single shared
  `MODEL_VERSION`, so a change to one bumps one.
- A per-requirement result identifies the model by the SHA-256 of
  `engineering_model.json`, separately from the schema version (RESULT-5).

## 10. Domain-by-domain plan

| # | Domain | Current | MVP sample | Open-source backend | Blockers and prerequisites |
|---|---|---|---|---|---|
| 1 | Mechanical | PARTIAL | `robotic_joint_001` (exists) | MuJoCo | Fixes in §7 are local and unpushed; Linux reproduction (§20 R1) |
| 2 | Electrical | PLANNED | 48 V servo supply input: fuse, inrush limiter, bulk capacitor. Inrush peak vs fuse, steady ripple, component voltage ratings | ngspice (adapter exists, emits no metrics) | Metric parsing and output capture (ARCH-2); version parsing (RESULT-8); ngspice not installed here. **Data:** the eServo-200 sheet gives only 48 V, 5 A, 200 W; fuse, limiter and capacitor values are design choices of a self-authored circuit (`SPECIFIED`, source `design_annotation`, noted as no real part), so no check on a real part's rating can `PASS`; overlaps PR #31's eServo-200 power-budget cases (Q6) |
| 3 | Digital | PLANNED | `rtl/uart_tx.v` + `uart_rx.v` loopback with a Verilog testbench: compile, frame timing at 115200 baud, byte recovery | Icarus Verilog; Verilator later | `iverilog` moved onto `run_process` first (ARCH-10); copied artefacts bound to their origin by hash (REUSE-1); Verilator needs a cases-contract amendment (Q9) |
| 4 | PCB | PLANNED | An existing generated board: outline, layers, placement within outline, netlist ↔ board ↔ BOM reconciliation | kiutils; kicad-cli DRC later | Boards have no pads, traces or signal nets, so DRC, clearance and trace-width checks are `BLOCKED` on the data |
| 5 | Power electronics | PLANNED | Synchronous buck 48 V → 12 V: output ripple, inductor current ripple, switch RMS current | ngspice switching model, or an averaged Python model | Loss parameters from real datasheets, or labelled example design values |
| 6 | Control | PLANNED | PID position loop on `robotic_joint_001`'s CAD-derived plant: overshoot, settling, steady-state error, saturation | Python + scipy | Actuator torque limit, gear ratio, rotor inertia and friction are unknown (the last two not yet even recorded as unknowns): they are declared required inputs, so every loop check on the committed sample is `BLOCKED` until a motor is selected, rather than passing on a plant that silently omits the actuator (INVENT-2). The met and `FAIL` cases come from a test-built copy with actuator values `SPECIFIED` as design annotations, noted as no real motor. PID gains are design annotations; limits are illustrative. Plant inertia published as a `DERIVED` facet (ARCH-3); per-package tool versions (ARCH-7) |
| 7 | Electromagnetic | PLANNED | Air-core solenoid inductance, closed form, `SIMPLIFIED`; FEM later | closed form; Elmer or GetDP later | No open 3D EM solver chosen (Q3) |
| 8 | Thermal | PLANNED | Lumped network for a regulator on a heatsink: junction temperature vs limit, `SIMPLIFIED` | Python lumped network | Real thermal resistances need real datasheets |
| 9 | Cross-domain | PARTIAL | `REQ-XD-001` (holding torque vs actuator capability) exists as a model-quantity limit | — | Results of other domains as inputs (§14) |
| 10 | Full system | BLOCKED | `robotic_joint_001` across mechanical, control, electrical, thermal | orchestrated domain adapters; FMI later | Motor and gearbox not selected (Q5) |

Order follows spec §30. Each domain lands as one PR with: at least one sample;
a met limit (`PASS` against a real requirement, `WARNING` against an
illustrative one), a `FAIL` from a mutated input and a `BLOCKED` from a
missing input; an invalid-input and a boundary sample (spec §21); negative
tests and mutants; per-domain documentation (spec §28); and a CI job that
makes a skip a failure.

## 11. Simulator abstraction

Two layers.

**Tool adapter** (exists: `ecad_validation.adapters.base.Adapter`): run one
tool on declared input files in isolation; report capability, version,
command and metrics. One per simulator. Two changes are needed before
artefact-first domains: `run_process` copies declared outputs out of the
workspace before deleting it, and each adapter gets a metric parser (ngspice
`.meas`/raw file, `vvp` `$display` markers, KiCad DRC report) that turns tool
output into metrics and evidence (ARCH-2).

**Domain adapter** (new, `ecad_model/domains/`). The spec's example
(`prepare`, `run`, `collect_results`, `validate`) adapted to this repository,
where running and deciding already belong to the case engine:

```python
class DomainAdapter(Protocol):
    domain: str

    # input requirements
    def accepted_artifacts(self) -> list[ArtifactKind]: ...          # kinds + importer per kind
    def required_inputs(self, model, requirement) -> list[InputRef]: ...  # model paths or artefact kinds, per requirement

    # engineering model
    def extract(self, sample) -> ModelContribution: ...              # components, facets from the sample's artefacts
    def publish(self, model) -> list[Quantity]: ...                  # DERIVED facets for other domains
    def vocabulary(self) -> Vocabulary: ...                          # facets, metrics with units and fidelity, scenarios, derivations

    # prepare (spec) = domain models + checks + cases
    def write_models(self, model) -> list[DerivedModel]: ...         # path, bytes, role, media type, producer + version, derived_from, comparator
    def sanity_checks(self, model, sample) -> list[Check]: ...       # V1
    def invariant_checks(self, model, derived) -> list[Check]: ...   # V2
    def compile_cases(self, model, requirements) -> CompiledCases: ...  # cases + per-metric dependencies + fidelity

    # run + collect_results (spec) = existing case engine + tool adapters
    def simulation_files(self) -> list[str]: ...                     # case scripts, hashed as inputs
```

`validate` in the spec's sense stays with the existing deterministic
comparators and the status propagation of §8.1; cross-domain evaluation is a
separate post-execution stage (§14). The protocol has no `depends_on` yet:
the cross-domain PR adds it, with each adapter declaring the facets and
results it consumes, and dependency order is defined there. Simulation files
are declared by the adapter and recorded with a media type from their
extension (`.py`, `.v`, `.cir`, …); the compiled case documents stay one pair
per sample, written by the domain-neutral compiler with one version.
Check IDs are namespaced by domain (`v1.mechanical.physical-sanity`) so
several domains fit in one receipt.

The registry is the set of registered adapters in code. It replaces
`VALIDATED_DOMAINS`; the manifest's domain status is derived from it (§12.3).
There is no hand-edited registry file, which would reintroduce H2
(SCOPE-10).

`QUALITY.md` says not to add an abstraction for a second case that does not
exist yet; spec §32 asks for the adapter in the foundation. The spec wins
under `CLAUDE.md` precedence, and the conflict is recorded here. To keep the
protocol honest before a second domain exists, PR 3 checks it against one
artefact-first domain (Icarus: HDL in, non-Python tool, metrics parsed from
output) with a test-only fixture adapter, not a production stub. The protocol
is marked provisional until the electrical domain lands (SEQ-1).

### 11.1 Simulator and importer roadmap (COVER-1)

Every domain has one open, CI-runnable primary backend. Licensed or heavy
alternatives the spec names are optional tool adapters that report `BLOCKED`
(`TOOL_NOT_INSTALLED`) when absent, never a silent skip, and are never
required by CI.

| Domain | Primary (open) | Optional adapters, later | Importers beyond the first |
|---|---|---|---|
| Mechanical | MuJoCo | Gazebo, Isaac Sim | STL (mesh-only, no assembly), IGES, URDF, MJCF, USD; each refuses what it cannot represent |
| Electrical | ngspice | LTspice, PSpice | KiCad schematic → netlist |
| Digital | Icarus Verilog | Verilator, then ModelSim/Questa | — |
| PCB | kiutils; kicad-cli DRC | — | — |
| Power electronics | ngspice / averaged Python | PLECS, Simulink/Simscape | — |
| Control | Python + scipy | Simulink, FMI/FMU | — |
| Electromagnetic | closed forms | Elmer, GetDP (Q3) | — |
| Thermal | lumped Python network | CFD (e.g. OpenFOAM), later | — |
| Full system | orchestrated adapters | FMI co-simulation | — |

Each importer is its own PR after the domain it serves, with the refusal
tests of §16.

## 12. Validation abstraction

### 12.1 Per-requirement result

Gate-level results stay the v1 receipt. Added:
`engineering-model/v1/validation-result.schema.json`, one document per
requirement or reference check, generated from the receipt, the requirements,
the model and the per-check execution records. It replaces `trace.json` and
keeps every trace field (RESULT-6).

| Field (spec §17) | Source | Null when |
|---|---|---|
| `validation_id` | `<sample_id>:<check_id>` | never |
| `domain` | the requirement's engineering domain (never the receipt's contract domain, MAP-1) | never |
| `kind` | `reference` (V3), `requirement` or `illustrative requirement` (V4), as `trace.json` has it | never |
| `requirement`, `title`, `source`, `metric` | the requirement's or reference's own fields | never |
| `component` | the requirement's component | V3: references name none |
| `cad_components` | the source parts the metric depends on, from the adapter; both sides for clearance | never (may be empty) |
| `illustrative` | the requirement's flag; `false` for a reference, which is computed, not chosen | never |
| `status`, `reason_code`, `findings` | copied verbatim from the receipt check; a test asserts equality | never |
| `measured_value` | the check's metric; for a `BLOCKED` requirement whose limit alone is null, the same metric and scenario from the check that measured it, named in `measured_by` (RESULT-3) | no metric was recorded |
| `expected_value`, `operator`, `applied_bound` | the requirement's limit (V3: value, operator `within`); the bound actually compiled (§14) | the limit's status is null |
| `unit` | the requirement, checked against the adapter's metric vocabulary | never |
| `tolerance` | V3 absolute tolerance; V4 requirement tolerance, default 0 | never |
| `simulator`, `simulator_version`, `configuration` | the case's adapter; tool version, command and arguments from that check's hash-bound execution record (`cases.py:398-418`) — never from receipt `tools[]` (RESULT-1). `configuration` also carries the scenario parameters, time step and seed (spec §24); the execution record omits the seed today, so recording it is part of PR 3 | no execution record; the schema forbids null with `PASS` |
| `model_version`, `model_sha256` | engineering-model schema version; SHA-256 of `engineering_model.json` | never |
| `model_fidelity` | the adapter's declaration for this metric | never |
| `inputs` | transitive `derived_from` leaves with statuses; scenario overrides as their own entries sourced from the requirement (RESULT-4) | never (may be empty for V0–V2) |
| `timestamp` | `receipt.completed_at`, so regeneration is byte-identical (RESULT-7) | never |
| `environment` | OS, architecture and interpreter of the run, and the digest of `tools/constraints-cad.txt` with the installed versions of the tools the case used (spec §24, COVER-4) | never |
| `source_dirty` | the receipt's `source.dirty` | never |
| `input_hash` | `receipt.source.input_sha256`; scope: the sample's git-listed files, not code or out-of-sample citations | never |
| `receipt_sha256`, `evidence` | the receipt's digest in full; the check's evidence IDs and digests | never |

Results are written as canonical JSON to `results.json`, bound to the receipt
by its full digest; each result cites its check's evidence digests. They are
not entries of the contract's evidence index, whose entries belong to receipt
checks. `regenerate_results` rebuilds the file from the receipt and evidence
alone, byte for byte. Verdicts are the v1 set: `PASS`, `FAIL`,
`WARNING`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`.

### 12.2 Dependencies

`compile_cases` returns, for each metric, the model paths it depends on
(reference derivations already compute these and discard them). For the
mechanical domain the dependency of a simulated metric is coarse and honest:
every geometric component's mass properties, placement and (for clearance)
bounding box, the joint, and gravity. Status propagation (§8.1) and `inputs`
(§12.1) both read these.

### 12.3 Domain status vocabulary

Data uses the spec §34 words: `AVAILABLE` (a registered adapter validates it)
and `NOT_IMPLEMENTED`. Each entry's reason lists the sample's null-status
inputs for that domain. `IMPLEMENTED`/`PARTIAL`/`PLANNED`/`BLOCKED` stay
labels of this document (FACT-14, STATUS-4).

## 13. Evidence and provenance design

Existing and kept: content-addressed evidence; exact hashes; generated
evidence recorded as bytes; the dataset pipeline's own records use
sample-relative paths. Not yet portable (spec §24): legacy V0–V2 product
evidence embeds host paths until `fix/portable-evidence-paths` lands (FACT-5),
and V3/V4 execution records and receipt `tools[]` embed the host
interpreter's absolute path, which that branch does not cover (STATE-2).

Added:

- Per-requirement results list the model paths each consumed, with statuses,
  so `source → value → simulation → validation → evidence` is a query.
- Per-check execution records carry the tool version, command and settings;
  receipt `tools[]` is not used for per-check data.
- Cross-domain results reference the checks they compare by `check_id` within
  a receipt, and by (`validation_id`, `receipt_sha256`) across receipts.
- Results are written for every run and carry `source_dirty`; only training
  records (§15) require a clean tree.

## 14. Requirements model

Existing `engineering-requirements` schema: reference values (V3, closed-form
derivations) and requirements (V4: metric, scenario, `<=`/`>=`, limit as a
number or a model-quantity path, required `illustrative` flag). Changes:

- **Tolerance** on inequalities: `tolerance ≥ 0`, applied in code as 0 when
  absent. Compile rule: `<=` → `maximum = limit + tolerance`; `>=` →
  `minimum = limit − tolerance`. The result carries both the limit and the
  applied bound. Tests at `limit ± tolerance` and one ε beyond (REQ-1).
- **Units**: every requirement's and reference's unit is checked against the
  adapter's metric vocabulary at compile time, with a mutant for a wrong unit
  (REQ-3).
- **Per-domain vocabularies**: scenarios and derivations are declared by each
  adapter and validated by it; the schema stops enumerating mechanical ones.
- **Cross-domain** (`from_result`), in the cross-domain PR: the measured side
  is another check's metric, evaluated after execution by a comparator in
  `ecad_model` that reuses `_compare_corner`; a referenced `BLOCKED`,
  `INCONCLUSIVE` or AI-dependent result propagates as in §8.1; `cross_domain`
  is added to the domain enum and `CONTRACT_DOMAIN`. Its verdict is a V4
  receipt check, aggregated like any other. Until then, `REQ-XD-001` stays a
  model-quantity limit (REQ-2, ARCH-3).

**`WARNING`** means a limit was met that qualifies nothing: today, only an
illustrative one (`WITHIN_ILLUSTRATIVE_LIMIT`, on the stack). Margin bands are
not introduced until a real requirement asks for one.

The deterministic layer decides every verdict. No model decides whether
4.8 ≤ 5.0.

## 15. Training-data format

Specification only; no schema or generator in the foundation (spec §37: first
reliable evidence; SCOPE-11). A training record will be a generated
projection of one per-requirement result:

```json
{
  "record_id": "robotic_joint_001:v4.REQ-MECH-002:<receipt_sha256>",
  "task": "simulation_result_to_explanation",
  "domain": "mechanical",
  "illustrative": true,
  "input": {"artifact_sha256": "…", "engineering_model_sha256": "…", "requirements_sha256": "…"},
  "execution": {"simulator": "mujoco", "version": "3.14.0", "configuration": {"…": "from the execution record"}},
  "result": {"status": "WARNING", "reason_code": "WITHIN_ILLUSTRATIVE_LIMIT", "measurements": {"…": "…"}},
  "model_fidelity": "EXACT_GEOMETRY",
  "inputs": [{"path": "components/payload/physical/mass", "status": "DERIVED"}, {"path": "components/payload/material/density", "status": "ESTIMATED"}],
  "evidence": ["<evidence_id>"],
  "explanation": {"text": "…", "source": "template"},
  "provenance": {"sample_id": "robotic_joint_001", "license": "MIT", "license_verified": true}
}
```

Rules: the licence gate reads `source.license` only; a record is never emitted
when `license_verified` or `training_use_permitted` is false, when the receipt
was produced from a dirty tree, or when an evidence digest does not re-hash;
records from illustrative limits are marked so, and records are filterable by
`model_fidelity` and by the weakest input status (a record resting on an
`ESTIMATED` or `AI_ASSUMPTION` input says so). Checks with no engineering
requirement (V0–V2, compile failures, DRC) will need check-level records for
the spec §20 explanation tasks (MAP-1). Records are regenerated from
receipts and not committed until a storage policy exists (Q1).

**Training roadmap** (spec §37 order, not reversed): (1) reliable evidence
per domain, i.e. every domain PR of §21; (2) generated records, with the
licence and dirty-tree gates above, in PR 13; (3) retrieval and templated
explanations over them; (4) small domain models, only once a domain has
verified samples of every class spec §21 names (simple, medium and complex;
PASS and FAIL; edge cases; missing information; invalid; boundary); (5)
larger models later, never deciding a verdict.

## 16. Test strategy

From `TESTING.md` and from both reviews:

- Every gate has a test that makes it fail.
- A mutation suite per domain, run locally and in a scheduled CI job; a
  green baseline is required first, and every kill names its test.
  Current: 68 mutants on the mechanical domain, all killed at `bd999d5` after a
  green baseline (**Verified**); each kill names its test.
- Property tests: rigid transforms of a whole design leave every physical
  metric unchanged.
- Reference values for every simulated metric with a closed form.
- Fixtures that do not decay: tests assert rules on fixtures they build.
- Provenance tests: every `PASS` result's inputs are non-null; every result's
  evidence resolves; every null status gives `BLOCKED` at every site (§8.1).
- Untrusted-input tests per importer: non-regular files, symlinks, external
  references, oversize, unenumerable samples — each through `check` and
  `validate`, not only the importer.
- Every public function's example runs as a doctest.

## 17. CI strategy

- The main matrix runs everything that needs no external tool; tool-dependent
  tests skip with a reason.
- One job per domain toolchain (`cad-dataset` exists; `spice`, `hdl`, `kicad`
  to come), each setting `ECAD_REQUIRE_<DOMAIN>_TOOLS=1` so a skip is a
  failure, and running the complete suite through `run_all_tests.py`.
- System libraries are installed explicitly: OpenCASCADE's wheel fails to
  import on a bare Debian image without `libGL.so.1` (**Verified**,
  `python:3.12-slim`, both architectures). Whether the `ubuntu-22.04` runner
  image ships it is **Unknown**, so the job installs it.
- Every job pins its tool versions, including transitive Python packages
  (`tools/constraints-cad.txt`).
- Derived files are reproduced on Linux before a PR merges (§20 R1).
- LFS: see §18.

## 18. Licence and provenance strategy

- Self-authored samples: the repository's MIT licence, attribution copied
  from `LICENSE`, `license_verified = true` with the basis stated.
- Every verified licence (PR 3): a licence-text reference `{path, sha256}`
  that `check` re-hashes — `LICENSE` for a self-authored sample. A verified
  third-party licence also needs `verified_by` and `verified_at`. A
  self-authored sample does not: no named person verified it, its terms are
  the repository's own `LICENSE`, and inventing a verifier would be the kind
  of claim spec §34 forbids. A cited source (a datasheet) records its own
  licence basis once the first third-party citation exists.
- Third-party artefacts: `source_url`, licence identifier, attribution,
  modifications, `redistribution_permitted`, `training_use_permitted`, and a
  licence-text reference `{path, sha256}` that `check` re-hashes (today
  `license_text_sha256` names no file, TRAIN-1). Unverified licences permit
  nothing (schema-enforced on the stack). Unverified artefacts are not
  committed.
- Candidate sources (ABC, ShapeNet, GrabCAD, FreeCAD examples) are evaluated
  per file: GrabCAD models carry per-model terms.
- **Git LFS** (FACT-8): `.gitattributes` routes every CAD, PCB, DXF, schematic
  and PDF type to LFS, yet all 144 such tracked files are plain blobs, so CI
  gets real content today. The hazard is a contributor with `git-lfs`
  committing pointers that CI (no `lfs: true`) and the importer then reject.
  The attributes and the content must be made consistent before samples are
  added in any domain (Q1).
- Artefacts reused from elsewhere in the repository (`rtl/*.v`, boards) are
  copied into the sample with their origin path and SHA-256 recorded and
  checked by `check` and V0 (REUSE-1).

## 19. Recommended MVP examples

As §10. Selection rule: open tooling, CI-runnable, small, deterministic, and
each exercising one met limit (`PASS`, or `WARNING` when illustrative), one
`FAIL` from a mutated input and one `BLOCKED` from a missing input. A
manufacturer datasheet a sample needs is either committed, when its licence
permits, or cited by URL and the SHA-256 of a download that is not committed
and is verified on demand (planned with the first such sample, §10 rows 5
and 8). They reuse artefacts already in the repository where
possible (`rtl/*.v`, the generated boards, the eServo-200 product sheet). No
MVP may invent a manufacturer, dimension, material, mass, rating, thermal
property, simulator result, requirement or licence (spec §4). Each MVP's PR
lists every input value with its source and status:

- a value the designer of a self-authored sample chose is `SPECIFIED`, source
  `design_annotation`, with a note that it is no real part's value;
- a property of an unselected or unknown part is `UNKNOWN`, so what rests on
  it is `BLOCKED`;
- a first-party product sheet in this repository (such as the eServo-200
  sheet, a design-phase concept) is cited with source kind
  `product_specification`, distinct from a manufacturer's `datasheet`
  (INVENT-1; a vocabulary addition in PR 3);
- example limits are `illustrative`, so meeting them is `WARNING`.

An MVP with no real part can therefore never `PASS` on a part rating.

## 20. Risks and unresolved questions

| # | Question | Needs |
|---|---|---|
| Q1 | Large artefacts: Git LFS (then CI must fetch it) or plain blobs with the LFS attributes removed, or external storage with hashed manifests? | Maintainer decision |
| Q2 | Should the receipt eventually carry the engineering domain (a v2 contract)? Until then results take it from the requirement (§12.1) | Maintainer decision; not blocking |
| Q3 | Which open EM solver: Elmer, GetDP, or closed forms only for now? | Technical evaluation |
| Q4 | Who supplies real requirements? Every current limit is illustrative | Product owner |
| Q5 | Motor and gearbox for `robotic_joint_001`; until chosen, electrical, thermal, control saturation and full-system checks stay `BLOCKED` | Design decision |
| Q6 | Relation to open PR #31 (dev-board database). Its board records are a component catalogue that samples should reference rather than duplicate. It also adds eServo-200 V3/V4 `python_control` cases (a 48 V bus-current and power-budget model), which overlap the electrical MVP and, once merged, make §5's "V3/V4 never execute on master" false (RISK-1) | Coordination with its author |
| Q7 | `AI_ASSUMPTION` inputs: `INCONCLUSIVE` (implemented as the default) or excluded entirely? | Maintainer decision |
| Q8 | Dataset layout: by primary domain (spec §3) or one directory per sample with domains in metadata? | Maintainer decision, before the first non-mechanical sample |
| Q9 | New simulators (Verilator, Elmer, FMI) need the merged cases contract's adapter enum amended, or an open adapter ID checked against the registry | Maintainer decision |
| Q10 | The spec orders mechanical after the foundation; this plan lands the existing mechanical work first, because spec §35 asks to preserve it and the review evidence is tied to it | Confirm |
| R1 | Cross-platform reproduction. **Verified** at `bd999d5`: Linux aarch64 (`python:3.12-slim`, pinned wheels, only `git` and `libgl1` added) passes `check`, the complete suite (245) and gives the same `validate` verdicts as macOS. **Verified** at `c9be0b6`: Linux x86_64 under emulation passes `check`. **Not run**: MuJoCo stages on native x86_64, because the emulated CPU has no AVX | A native x86_64 run, which the `cad-dataset` CI job provides on its first execution |
| R2 | Several domains need system tools CI must install; install time and flakiness are unknown | CI trial |
| R3 | Push access is read-only for this account; nothing can land without a fork or restored access | Access decision |
| R4 | PR 3 regenerates mutation and reproduction evidence and re-anchors the mutation suite | Budgeted in §21 |
| R5 | `run_process` is process hardening, not a sandbox: case scripts, SPICE decks (whose `.control` blocks can run shell commands) and HDL run with the user's full filesystem and network access (SEC-1, spec §25–26) | Rule until confinement exists: simulation scripts are authored and reviewed in this repository, never taken from a third-party sample. Container or seccomp confinement with memory and CPU limits before any untrusted SPICE, HDL or third-party script runs |

## 21. Proposed PR sequence

1. **Existing fix branches** (§1.1): independent of this plan; land first.
   `fix/version-probe-reason-codes` (RESULT-2) is still to be written; it sits
   on the mechanical path, since `detect_mujoco` emits one of the bad codes.
2. **Mechanical domain**: `wip/stack` (§7.1, §7.2). Before the foundation, a
   departure from spec §30 for the reason in Q10. Its documentation declares
   the two schema families pre-release (§9.3).
3. **Foundation** (spec §32; the first stage to implement). Each item is
   marked with its state on `feat/multi-domain-foundation`. All are `PARTIAL`
   at this commit: code and tests exist for each, and an independent review
   of the branch has findings still open against them:
   - versioning (§9.3): per-producer version constants — PARTIAL;
   - status types, one null predicate at every site, per-status rules
     (§8.1) — PARTIAL; status propagation (§8.1) — PARTIAL;
   - artefact-neutral base types: `design.sources`, the manifest's source
     artefacts, domain-qualified derived roles, `Item` finding its sources
     through provenance, annotations that may carry no parts or materials
     (§8.2, SCOPE-2) — PARTIAL;
   - provenance: primary domain and declared artefacts; licence-text
     reference checked; `verified_by`/`verified_at`; spec §4 keys mapped
     (§9.2, §18); source kind `product_specification` (§19) — PARTIAL;
   - dataset metadata: `domain`, `hash`, `versions.simulation`, `source_url`
     (§9.2) — PARTIAL;
   - requirements: tolerance, unit checking, per-domain vocabularies (§14) —
     PARTIAL;
   - common validation result: schema and generator, replacing `trace.json`,
     per-metric fidelity and dependencies (§12) — PARTIAL;
   - evidence: results hash-bound and indexed; per-check execution records
     as the source of simulator versions, recording the seed and the
     environment (§12.1, §13) — PARTIAL;
   - `DomainAdapter` protocol, in-code registry, mechanical refactored onto
     it, domain-namespaced check IDs, domain status in the spec §34 words
     plus `NOT_APPLICABLE`, the receipt-side MAP-1 fix (§11, §12.3) —
     PARTIAL, provisional.

   Not in scope: renaming `dataset-item.json`, moving `datasets/cad/`,
   training records, any new domain, `from_result`.

   Acceptance criteria (SCOPE-3):
   1. No derived number changes. Checked two ways against PR 2's head, on the
      platform that produced the committed files: `git diff` of the rebuilt
      sample touches no numeric value (the extraction, domain model and case
      documents are byte-identical; the model and manifest change only in
      the listed structural fields); and `validate` gives the same
      `check_id → (verdict, metrics)` map. Named exceptions (ARCH-9):
      `v1.cad-extraction-and-physical-sanity` → `v1.mechanical.extraction-and-sanity`;
      `v2.cad-model-invariants` → `v2.dataset-reproduction` plus
      `v2.mechanical.model-invariants`; reason codes
      `REQUIREMENT_INPUT_UNKNOWN` → `MISSING_REQUIRED_INPUT`,
      `PHYSICAL_SANITY_*` → `DOMAIN_SANITY_*`, and `CAD_REJECTED`,
      `CAD_EXTRACTION_CRASHED`, `CAD_EXTRACTION_TIMED_OUT`,
      `CAD_KERNEL_UNAVAILABLE` → `SOURCE_REJECTED`, `EXTRACTION_CRASHED`,
      `EXTRACTION_TIMED_OUT`, `EXTRACTOR_UNAVAILABLE`.
   2. No mechanical names (`mjcf`, `mujoco`, `derived/mechanical`, `.step`)
      in `dataset.py` or `requirements.py` outside the mechanical adapter
      (`grep -nE "mjcf|mujoco|derived/mechanical|\.step"` finds nothing).
   3. No existing assertion is deleted or weakened; the mutation suite is
      re-anchored with a green baseline and zero survivors, including new
      mutants for the null predicate, dropped `illustrative`, domain status,
      a wrong requirement unit, tolerance on each operator, the AI rule, and
      `rom_` fidelity.
   4. For each of `UNKNOWN`, `UNSPECIFIED`, `NOT_AVAILABLE`, as a density and
      as a limit: `BLOCKED MISSING_REQUIRED_INPUT` with the status and the
      path, and a schema-valid receipt.
   5. With a requirement that is *not* illustrative, an `AI_ASSUMPTION`
      density, and separately an `AI_ASSUMPTION` limit quantity, give
      `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` both when the limit is met and
      when it is violated (AI-1, SCOPE-7).
   6. A test-only sample with no STEP, read by the test-only adapter of
      criterion 10, builds a schema-valid model and manifest in which its
      domain is `AVAILABLE`, mechanical `NOT_APPLICABLE` and every other
      domain `NOT_IMPLEMENTED`; without that adapter registered, `build`
      refuses and `validate` is `BLOCKED DOMAIN_NOT_IMPLEMENTED`.
   7. One result per V3/V4 check; `status` equals the receipt verdict;
      every evidence digest re-hashes; a `PASS` result has a
      `simulator_version`; regeneration from one receipt is byte-identical;
      every `rom_` result has `model_fidelity = SIMPLIFIED` (SCOPE-12).
   8. The manifest's domain status is derived from the registry, and a test
      forging it fails `check`.
   9. After the merge, the versioning rule of §9.3 applies; the pre-release
      declaration is removed from the schema documentation.
   10. The protocol is exercised end to end by a test-only artefact-first
       adapter (Verilog in, no CAD kernel, no simulator) (§11).
4. **Electrical**: ngspice supply sample; output capture and metric parsing;
   version parsing; `spice` CI job. First artefact-first domain; the protocol
   stops being provisional here, and the PR lists every protocol change the
   domain forced with the matching change to the mechanical adapter
   (SCOPE-15).
5. **Digital**: `rtl/` UART loopback on Icarus. First, `iverilog` onto
   `run_process`, with a test and a mutant that both the compile and the run
   step get the scrubbed environment and the output cap (ARCH-10); `hdl` CI
   job; `tests/test_rtl_models.py` unchanged.
6. **PCB**: generated boards through kiutils; DRC `BLOCKED` on data until
   routed boards exist.
7. **Power electronics**. First, the `python_control` fix of ARCH-7 (report
   the model's package versions, run the interpreter it probed), since this
   is the first domain that may run a Python model.
8. **Control**: plant as a published facet (§10 row 6).
9. **Electromagnetic** (`SIMPLIFIED`).
10. **Thermal** (`SIMPLIFIED`).
11. **Cross-domain rules** over domain results (`from_result`, `depends_on`).
12. **Full system**: blocked on Q5.
13. **AI explanation** over per-requirement results, evidence-referenced,
    never deciding a verdict; training records (§15).
14. **Recorded demonstration**, then an interactive 3D view, only after 2–12
    produce trustworthy results.

The dataset move (Q8) goes in the first PR with a non-mechanical primary
sample, as a pure move commit whose only diffs are paths and regenerated
hashes, followed by a Linux reproduction run.
