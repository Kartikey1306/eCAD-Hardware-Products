# eCAD multi-domain engineering dataset and validation plan

Scope: issue #27 (Multi-Domain CAD Validation Pipeline), all nine domains plus
cross-domain validation, answering the specification "Multi-Domain eCAD
Engineering Dataset + Validation + AI Foundation" (§31 of it asks for this
document; its section numbers are cited as *spec §n*).

Base: local branch `wip/stack`, code at `bd999d5`, added to by the
documentation commit that carries this file — `master` (751616a) plus the
stack in §1.1. The first implementation stage (§21 item 3) is on the local
branch `feat/multi-domain-foundation`, which forks from that commit, and
§21 item 3 marks the state of each of its items there. The electrical domain
(§21 item 4) is on the local branch `feat/domain-electrical`, which forks
from the foundation's documentation commit `042f934`; this copy of the plan
is that branch's, and §21 item 4 marks the state of each of its items there.
Nothing here is pushed. Every statement about the
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
| Tool adapters | `tools/ecad_validation/adapters/` | `python_control`, `mujoco`, `ngspice`, `kicad` (kicad-cli DRC), `iverilog`. Four run through the hardened `run_process`; **`iverilog` calls `subprocess.run` directly** with the inherited environment and no output cap (`hdl.py:51-100`, **Observed**). **Only `python_control` and `mujoco` emit metrics**; `ngspice`, `iverilog` and `kicad` decide from the exit code and return none, so their V3/V4 cases can only be `INCONCLUSIVE` (ARCH-2). On `feat/domain-electrical`, `ngspice` returns the `.meas` results its deck declares (§7.2 ARCH-2) | PARTIAL |
| CAD dataset + engineering model | `tools/ecad_model/`, `schemas/engineering-model/v1/`, `schemas/cad-dataset/v1/`, `datasets/cad/robotic_joint_001/` | STEP → isolated OpenCASCADE extraction → engineering model with provenance → MJCF → MuJoCo → V0–V4 receipt | PARTIAL — works end to end; the base types are STEP-bound (§7.3) |
| RTL | `rtl/spi_master.v`, `uart_rx.v`, `uart_tx.v` | 352 lines of Verilog | PARTIAL — `tests/test_rtl_models.py` tests Python re-implementations; the HDL is never compiled (**Observed**) |
| PCB artefacts | 67 `.kicad_pcb`, 69 `.net`, 9 `.kicad_sch`, 67 `.dxf`, 67 `.scad` | Generated boards: placed footprints, no pads, no traces, no signal nets, by design (`MEMORY.md`) | PARTIAL — structural checks only |
| Dev-board database | open PR #31 (`schemas/devboard-cad/v1/`, `tools/devboard_cad/`) | Board-record catalogue for issue #28 | PARTIAL — open PR, not merged; complementary (§20 Q6) |
| CI | `.github/workflows/ci.yml` | Test matrix (3 OS × Py 3.10–3.12); `validation-evidence` job; `cad-dataset` job (on the stack only). **Gaps:** ruff and mypy are `continue-on-error` on master (mypy made blocking on unpushed `ci/enforce-type-check`); nothing compiles HDL, runs SPICE, or fetches LFS content. `feat/domain-electrical` adds a `spice` job, which has never run (§17) | PARTIAL |

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
| `feat/multi-domain-foundation` | code at `000309b`, then its documentation | Forked from the stack's documentation commit: five feature commits, the fixes of two reviews (`2beb77a`), one test (`b4fca10`), documentation (`793c770`), the fixes of a third review (`bb43124`), one test (`7b58a76`), documentation (`7d16314`), the fixes of a fourth review (`dbf73e1`), one test fixture made portable to Python 3.12 (`000309b`); §21 item 3 (each item marked there) |
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
  **Versioning:** the stack declares these families pre-release, amended in
  place until the foundation lands. The foundation branch removes that
  declaration: from its merge on, the repository rule applies, and an
  incompatible change needs a new versioned directory (SCOPE-1, §9.3).

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
per-requirement result record, a domain adapter layer. The last three exist
on the local branches of §21 items 3 and 4; the second sample,
`datasets/cad/servo_supply_001`, is electrical (§10 row 2).

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
| T12 | Receipt requirement binding and trace components untested | Fixed: both halves | `test_committed_item_meets_every_measurable_check`, `test_the_trace_names_both_sides_for_clearance_and_marks_illustrative_limits` (on this branch `test_the_results_name_both_sides_for_clearance_and_mark_illustrative_limits`) · `requirement-binding-dropped`, `clearance-trace-one-side` |
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
| ACC-9 | `validate` did not refuse a symlinked item (only `build` and `check` did) | Fixed on the stack · `test_check_refuses_a_symlinked_directory_before_reading_through_it` (now `check` and `validate`) · `validate-follows-symlinks` (on this branch folded into `check-follows-symlinks`: `Item` refuses before either reads) |
| ACC-1 | The simulation-script mutants were killed only by the manifest's hash of the script, so no behavioural test was shown to catch wrong physics there | Fixed in the harness: the item is rebuilt after such a mutant; results in §16 |
| RESULT-2 | On a failed version probe the adapters emit reason codes containing `:`, spaces or `-` (`capabilities.py:45/54/79`); the receipt then fails its own schema and none is written | Open. Existing merged code; fix branch `fix/version-probe-reason-codes`, §21 item 1. PARTIAL on `feat/domain-electrical`, the ngspice path only: the adapter maps `VERSION_PROBE_ERROR:<message>` and `VERSION_PROBE_EXIT_-<n>` to reason codes and puts the raw text in the summary, and the mapping is deleted when the general fix lands · `test_a_version_probe_failure_gives_a_reason_the_receipt_accepts` · `ngspice-reason-unsanitised` |
| ARCH-7 | `python_control` reports the validator's interpreter version, not the model's packages, and may run a different interpreter; receipt tool records were last-writer-wins per `tool_id` | Tool records fixed on the stack: one record per tool keeps only what all its checks share · `test_committed_item_meets_every_measurable_check` · `tool-record-last-writer-wins`. The `python_control` half is open: a prerequisite of the first Python-model domain (§21 item 7) |
| RESULT-8 | Version probes take the first output line; ngspice's is a banner: ngspice-47's `--version` prints `******` first and names itself on the second line, `** ngspice-47 : Circuit level simulation program` (**Verified**, 2026-09-27) | Fixed on `feat/domain-electrical`: an ngspice-only `VERSION_PATTERNS` entry reads `47` (and `36`, `44.2` from their recorded banners); no match is version `None`, which the existing policy turns from `PASS` into `BLOCKED TOOL_VERSION_UNAVAILABLE`; every other tool keeps the first-line rule · `test_the_ngspice_version_comes_from_its_banner`, `test_probes_of_other_tools_still_take_their_first_line` · `ngspice-version-first-line`, `ngspice-version-invented`, `ngspice-version-minor-dropped`, `probe-pattern-for-every-tool` |
| ARCH-2 | Only `python_control` and `mujoco` return metrics. ngspice ran with `-o ngspice.log -r ngspice.raw`: with `-r` batch mode makes no `.meas` ("No .measure possible in batch mode (-b) with -r rawfile set!", exit 0), and with `-o` the results go to a log inside the workspace `run_process` deletes (**Verified**, ngspice-47, 2026-09-27) | ngspice half fixed on `feat/domain-electrical`: `ngspice -b <deck>` and nothing else; the metrics are the `.meas` results the deck declares, read from stdout only when exactly one line reports the name with a finite plain-decimal value; truncated output is `INCONCLUSIVE OUTPUT_TRUNCATED` with no metrics; exit != 0 stays `FAIL` · the 14 tests of `test_ngspice_adapter.py` · `ngspice-rawfile-requested` … `ngspice-oversize-deck-read`. Open: `run_process` copying declared outputs out of the workspace, and the iverilog and kicad parsers (§21 items 5 and 6) |
| SEC-2 | The dataset runner executes a committed case document (`dataset.py`, before the stale-case filter) before it decides which of its cases count. A hand-edited committed ngspice deck, or a forged committed case whose inputs include a `.spiceinit`, would run before it is marked stale, and ngspice runs `.control` `shell` blocks under `-b` and a working-directory `.spiceinit` (**Verified**, ngspice-47, 2026-09-27) | Open. `feat/domain-electrical` narrows the source path: the netlist parser refuses `.control`, `*#` and every other directive, so the deck `build` writes from the model carries none. It does not close it: ngspice runs the committed deck, which equals the regenerated one only while V2's reproduction check passes, and a hand-edited committed deck's `.control` `shell` block ran during `validate` before V2 and the stale-case filter flagged it (**Verified** by the review of the branch, 2026-09-28; the first version of this row said ngspice only ran the regenerated deck, which was false). The same holds for the Python case scripts. V2 and `check` report an edited deck, after it has run; no guard stops the run. Proposed for its own foundation change: run a committed document only if every case equals a fresh one and every derived input reproduces, else run nothing and report `CASE_DOCUMENT_NOT_RUN`. It narrows the decision recorded in `MEMORY.md` (committed case documents run), so it needs the maintainer's acceptance |
| MAP-1 | A `BLOCKED` V3 reference falls back to contract domain `integrated_physics` because only `requirements[]` is searched | Fixed on `feat/multi-domain-foundation` (the lookup covers references); no observable effect for mechanical |
| ENGINE-1 | The case engine does not survive every case document: it reports one it cannot parse as `FAIL` with no evidence (`cases.py:157-170`), which the receipt contract forbids, so the receipt fails its own schema; it reads the document as UTF-8 and catches only `OSError` and `JSONDecodeError`, so a document in UTF-16 raises out of it; a document nested deeply enough raises `RecursionError` from its parse or its schema check; and a metric that is not a finite number makes `canonical_json_bytes` raise (`cases.py:410`). In each case no receipt is written, and an exception loses the verdicts of every case in the document (**Verified** through the dataset runner, 2026-09-26/27) | Open in merged code. The dataset runner on `feat/multi-domain-foundation` cites the document as the evidence, and turns an engine exception into a gate-level `INCONCLUSIVE` `CASE_ENGINE_ERROR` with each entry `INCONCLUSIVE` (crashed); the product pipeline still has the defect. Fix belongs with §21 item 1 |

### 7.3 Missing (spec capabilities with no code)

With no code anywhere: training records; electrical, digital, PCB, power,
control, EM, thermal and full-system domains; cross-domain rules beyond a
model-quantity limit (`from_result`, `depends_on`); non-STEP importers.

On `feat/multi-domain-foundation` only, not on the stack (§21 item 3 marks each): the
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
version for a `PASS` (`cases.py:439-454`); a domain's status only from the
platform, never from sample data.

### 7.5 Defects found by independent review of the foundation, and their state

The foundation branch had its own five-lens review (correctness, contracts,
untrusted input, test adequacy, acceptance), each finding checked by a
separate verifier trying to refute it: 61 findings, 59 confirmed, 2 refuted
(FK-F5, a domain-status reason read as a claim about requirements; FK-F13, a
forged-status test that already tests what it should). (These counts are
**Unknown** to a reader of the repository: they come from the review run's
journal, local to the authoring session.) IDs carry the lens: FC
correctness, FK contracts, FU untrusted input, FT tests, FA acceptance.
Several lenses often found one defect; rows group them. Every fix is on
`feat/multi-domain-foundation`; each named mutant is in
`tests/mutation/run_mutations.py`, and §16 records the run that killed it.

| IDs | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| FC-F1, FU-F4 | `validate` recompiled the committed model unguarded: a requirement V1 had already refused (a wrong unit; a move derivation on a scenario without its parameters) crashed it before any receipt | Fixed: V3/V4 take what is blocked from the fresh derivation; the vocabulary requires each scenario's parameters and pairs move derivations with the rated move | `test_a_requirement_that_cannot_compile_still_gives_a_receipt`, `test_each_scenario_carries_what_its_case_reads` · `cases-run-without-derivation`, `rated-move-parameters-optional`, `free-swing-amplitude-optional`, `move-derivation-any-scenario` |
| FC-F2 | Input statuses were kept only at leaves: an `AI_ASSUMPTION` naming a parent was walked past and the verdict stood | Fixed: every non-`DERIVED` quantity on the way is an input | `test_an_assumption_that_names_a_parent_is_still_an_input` · `assumption-with-parents-walked-past`, `inputs-not-transitive` |
| FC-F3 | A `derived_from` that does not resolve raised after every case had run, so no receipt | Fixed: reported, never raised (`INCONCLUSIVE` `INPUT_NOT_RESOLVABLE`); `build` refuses a model whose lineage cannot be followed | `test_an_unresolvable_path_is_reported_not_raised`, `test_lineage_problems_name_a_dangling_parent_and_a_cycle`, `test_a_model_whose_lineage_cannot_be_followed_is_not_built` · `unresolvable-input-raises`, `unresolved-ignored`, `unresolved-overrides-blocked`, `lineage-dangling-allowed`, `lineage-cycle-allowed`, `lineage-unchecked-at-build` |
| FC-F5, FU-F3 | `except LookupError` also caught `KeyError`/`IndexError`: an invalid item was reported as its domain `NOT_IMPLEMENTED` | Fixed: `DomainNotImplemented`, decided before deriving; any error the inputs provoke is `DATASET_INPUT_INVALID` | `test_an_error_the_item_provokes_is_its_fault_not_a_missing_domain` · `item-error-crashes-validate` |
| FC-F4 | A vector limit quantity raised `TypeError` in the tolerance fold | Fixed: refused as not a single number | `test_a_limit_quantity_that_is_not_one_number_is_refused` · `vector-limit-accepted` |
| FC-F6 | A case document the requirements no longer compile stayed on disk and was executed | Fixed: `build` removes it, V2 reports it, `validate` never runs it | `test_a_case_document_the_requirements_no_longer_compile_is_removed_and_never_run` · `stale-case-document-run`, `-kept`, `-unreported` |
| FK-F6 | With no adapter registered, the committed cases still ran | Fixed: every requirement `BLOCKED` `DERIVATION_NOT_AVAILABLE`, nothing runs | `test_without_its_adapter_the_domain_is_not_implemented_and_nothing_runs` · `cases-run-without-derivation` |
| FC-F7, FK-F2, FU-F2, FT-F1, FT-F2, FA-RES-1 | Regeneration read the working tree and the regenerating host's platform, bound to an old receipt | Fixed: the run's environment is recorded in its `v0.pinned-clean-source` evidence; case documents and execution records come from verified evidence; refused unless the item's digest equals the receipt's | `test_results_regenerate_identically_anywhere_from_what_the_run_recorded`, `test_an_item_changed_after_the_run_is_not_regenerated` · `environment-from-this-process`, `environment-tools-empty`, `constraints-digest-dropped`, `regenerate-ignores-item-changes` |
| FU-F1 | Regeneration trusted the run directory's paths, bytes and records | Fixed: receipt schema-checked and for this item; evidence read only at its content address and with its digest; a record counts only for its own check | `test_forged_or_misplaced_evidence_is_refused`, `test_a_record_is_the_execution_of_the_check_that_cites_it_or_nothing`, `test_a_run_of_one_item_is_not_regenerated_for_another` · `evidence-digest-unchecked`, `evidence-path-trusted`, `receipt-not-schema-checked`, `receipt-for-another-item`, `execution-record-of-another-check` |
| FU-F5, FC-F11, FA-ACC-7a | Results iterated the requirements and filled `NOT_RUN` for a requirement no check covered; optional case fields were indexed; golden and corner cases shared one key space; results were written after the receipt | Fixed: each result names the check that decided it (its own or the gate-level stand-in), none decided is an error; ids unique across both arrays; a non-numeric metric is null with a finding; results written after the receipt (round 2, below) | `test_a_result_names_the_check_that_stood_in_when_none_could_be_named`, `test_a_measurement_is_borrowed_only_by_a_requirement_blocked_on_its_limit`, `test_an_id_shared_by_a_reference_and_a_requirement_is_refused` · `results-decided-by-nothing`, `result-status-recomputed`, `non-number-measured`, `duplicate-ids-allowed` |
| FA-HON-1, FK-F3, FC-F8 | `AVAILABLE` for any domain whose format was present, though only the primary domain's adapter runs | Fixed: primary only; the others `NOT_APPLICABLE` | `test_only_the_sample_s_primary_domain_is_available` · `secondary-domain-available`, `status-from-registry-alone` |
| FK-F1, FK-F8, FT-F6, FA-NULL-1 | Dynamics metrics omitted the joint range, references omitted gravity, and gravity was read without the null predicate | Fixed | `TestMechanicalDependencies`; the slow `AI_ASSUMPTION joint range` case · `range-not-an-input`, `gravity-not-an-input`, `clearance-reads-mass`, `reference-inputs-empty`, `reference-gravity-unlisted`, `gravity-read-unchecked`, `weightless-design-crashes` |
| FK-F11 | The AI rule relabelled a crash or a misconfiguration as an AI problem | Fixed: only the comparator's `PASS`/`FAIL` | `test_only_a_comparator_verdict_is_withheld_for_an_ai_assumption` · `ai-rule-on-any-verdict`, `ai-rule-dropped`, `ai-rule-spares-a-pass` |
| FK-F12, FA-RES-2, FC-F9 | Any result without its own metric borrowed one; a scenario identifier was an input with a value status; the V3 bound was not what the comparator evaluates | Fixed | `test_a_measurement_is_borrowed_only_by_a_requirement_blocked_on_its_limit`, `test_each_check_has_one_result_that_copies_the_receipt_and_cites_its_evidence` · `borrowed-for-any-verdict`, `sibling-arguments-ignored`, `scenario-inputs-include-identifiers`, `scenario-inputs-dropped`, `v3-bound-as-min-max` |
| FK-F4, FT-F12 | The results schema accepted combinations the contract forbids | Fixed: six cross-field rules | `test_the_results_schema_refuses_what_the_result_contract_forbids` · the eight `results-…` mutants (`results-pass-without-version`, `results-reference-illustrative` — replaced in round 2 by `results-reference-any-operator` — `results-kind-disagrees`, `results-illustrative-pass`, `results-pass-unmeasured`, `results-null-input-not-blocked`, `results-assumption-passes`, `results-comparator-reason-on-assumption`) |
| FK-F7, FT-F9, FT-F10 | The manifest schema lacked the provenance's licence rules; `source_url` and two provenance licence rules were untested | Fixed | `test_the_manifest_restates_the_licence_rules_of_the_provenance`, `test_a_third_party_sample_records_its_source_url`, `test_a_verified_licence_cites_its_text_and_a_third_party_one_its_verifier` · `manifest-unverified-permits-use`, `manifest-verified-uncited`, `manifest-third-party-verifier-optional`, `manifest-modifications-optional`, `source-url-dropped`, `source-url-null-for-third-party`, `provenance-verified-at-optional`, `provenance-third-party-uncited` |
| FA-ACC-4, FC-F10 | V1 `MISSING_REQUIRED_INPUT` named a mass rather than the density it rests on, and only the first | Fixed: every root null value, as `<STATUS>: <path>` | `test_a_missing_input_is_blocked_not_a_design_failure`, `test_every_missing_value_is_named_not_only_the_first` · `missing-input-paths-dropped`, `missing-input-not-traced-to-its-root`, `null-mass-loses-its-inputs`, `mjcf-single-missing-unnamed` |
| FU-F6, FU-F7 | `integrity` read manifest paths outside the item (a hash oracle); an item that is itself a symlink was followed | Fixed | `test_a_manifest_path_outside_the_item_is_not_read`, `test_an_item_is_refused_before_it_is_read` · `manifest-path-outside-item-read`, `item-root-symlink-followed`, `item-outside-repository-read` |
| FC-F14, FA-PLAN-1(e) | With no extraction file the model's lineage omitted the artefacts; a design source's format was not checked against the provenance | Fixed | the fixture's lineage assertion, `test_a_source_the_provenance_does_not_declare_is_a_divergence` · `model-lineage-omits-artefacts`, `undeclared-source-format-allowed` |
| FT-F3–F5, F7, F8, F11, F13–F15 | Single-line mutants of new code survived every test | Fixed: a test and a mutant each | beyond the rows above: `reference-unit-unchecked`, `foreign-reference-compiled`, `reference-scenarios-unchecked`, one `schema-…` mutant per per-status rule of `common.schema.json` (7), `unknown-comparator-accepted`, `unknown-fidelity-accepted`, `exact-comparator-ignored`, `manifest-domain-hard-coded`, `extraction-schema-not-checked`, `declared-source-missing-unnamed`, `unlisted-sources-skipped`, `expected-value-dropped`, `applied-bound-dropped`, `seed-dropped`, `illustrative-label-dropped`, `result-illustrative-flag-dropped`, `null-input-not-blocking`, `null-input-only-unknown` |
| FT-F8 | An existing schema test's fixture failed on the note rule, not the rule its label names | Fixed: the fixture carries a note | `test_schema_enforces_the_same_rules` · `schema-unknown-may-carry-value` |
| FC-F12 | The report pointed at a `results.json` that was never written | Fixed: it says why none was written | `test_without_its_adapter_the_domain_is_not_implemented_and_nothing_runs` |
| FC-F13, FK-F10, FA-ACC-2 | Criterion 2's grep matched a doctest | Fixed: a neutral tool id | *code change only* |
| FA-PLAN-1(b) | The validator reported the model-format version as its own | Fixed: `VALIDATOR_VERSION` | *value unchanged; no test* |
| FA-ACC-1, FA-ACC-3, FA-ACC-9, FA-ACC-10, FA-PLAN-1, FK-F9 | The plan and the documentation overstated or were stale: criterion 1's exceptions, no dropped-illustrative mutant, the schema documentation not updated, the §11 claim, the item markers | Fixed: §11, §12, §21 item 3 here, and `docs/cad-dataset-engineering-model-v1.md` | *doc change* |

A second review then checked each fix against its finding: 49 fixed, 10
partly fixed, and new defects in the fixes, nearly all of one kind — a
receipt still lost when committed files had drifted from the inputs; each
claim was checked by a separate verifier, and one (N-docs-9) was refuted.
Round 2 closed them:

| IDs | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| FC-F1, FU-F4 (partly), N-code-2, N-contracts-2, N-docs-1 | On a built item, an entry V1 refused (a move derivation on a static sweep, an unknown metric) still crashed the results, which were built before the receipt | Fixed: every adapter call in the results is guarded, an unknown metric's fidelity is `null`, and the receipt is written before the results | `test_a_refused_entry_on_a_built_item_still_gives_a_receipt_and_results`, `test_a_metric_the_domain_does_not_produce_has_no_fidelity`, `test_a_failure_to_build_the_results_still_leaves_the_receipt` · `results-inputs-unguarded`, `unknown-metric-fidelity-crashes`, `results-before-receipt` |
| FC-F11, FA-ACC-7a (partly), N-correctness-1, N-acceptance-1, N-code-1 | An entry the fresh derivation compiles but the committed document lacks had no check, and the results raised | Fixed: `BLOCKED` `COMMITTED_CASE_MISSING` | `test_a_requirement_added_without_a_rebuild_is_blocked_not_lost` · `committed-case-missing-unreported` |
| N-correctness-2, N-acceptance-2, N-contracts-3 | A committed case for an entry the fresh derivation blocks ran beside the fresh `BLOCKED` check: a duplicate check id, no receipt | Fixed: a stale case is not counted, and the blocked check says so | `test_a_stale_case_for_a_requirement_now_blocked_is_discarded_not_duplicated` · `stale-case-unnoted`; `test_a_stale_case_in_a_document_still_compiled_is_not_counted` (added after the full mutation run left it alive) · `stale-committed-case-counted` |
| FA-NULL-1 (partly), N-acceptance-3, N-code-4 | V3 checks were never propagated, so a reference resting on a null input kept its `PASS` and broke the results schema | Fixed: V3 inputs are propagated too (the AI rule stays on requirements) | `test_a_null_input_blocks_a_reference_as_it_blocks_a_requirement` · `v3-inputs-ignored` |
| N-correctness-3, N-code-3, N-untrusted-input-1 | A committed model that does not parse, or is not a model, crashed V3/V4 or the results | Fixed: it is schema-checked first; V3/V4 `BLOCKED` `COMMITTED_MODEL_INVALID`; no results, and the report says why | `test_an_unusable_committed_model_gives_a_receipt_without_results` · `committed-model-schema-unchecked` |
| N-code-5, N-acceptance-4 | A committed derived file or manifest that does not parse crashed V2 (already so on the stack); a case document that does not parse left a receipt that fails its schema (ENGINE-1, §7.2) | Fixed in the runner: reported as divergences, and the document cited as evidence | `test_committed_files_that_do_not_parse_are_divergences_not_crashes` · `reproducibility-parse-crash`, `manifest-shape-crash`, `uncited-engine-failure-kept` |
| N-untrusted-input-3, N-acceptance-5, N-code-6 | Regeneration raised undocumented errors on a malformed record, and rebuilt results for a run that wrote none | Fixed | `test_a_malformed_environment_record_is_refused`, `test_a_run_that_wrote_no_results_has_none_to_regenerate` · `environment-shape-unchecked`, `regenerate-no-results-unchecked` |
| N-correctness-4 | With no extraction file, the model's lineage listed other domains' artefacts | Fixed: only its adapter's formats | the lineage assertion in `test_only_the_sample_s_primary_domain_is_available` · `lineage-fallback-all-sources` |
| N-contracts-1, N-tests-1, FT-F12 (partly) | `results-reference-illustrative` was an equivalent mutant: another rule already forced the flag | Fixed: the redundant clause removed; the mutant now drops the operator rule | `test_the_results_schema_refuses_what_the_result_contract_forbids` · `results-reference-any-operator` |
| N-untrusted-input-2, N-tests-2 | The misplaced-evidence test passed on the receipt schema, never reaching the content-address check | Fixed: a schema-valid path that is not the content address | `test_forged_or_misplaced_evidence_is_refused` · `evidence-path-trusted` |
| N-tests-3 | Two restated manifest licence rules had no test | Fixed | `test_the_manifest_restates_the_licence_rules_of_the_provenance` · `manifest-third-party-uncited`, `manifest-verified-at-optional` |
| FT-F7 (partly) | No result assertion on `>=` or on a tolerance | Fixed | `test_a_reference_and_a_requirement_run_and_give_their_results` · `result-operator-fixed`, `result-tolerance-dropped` |
| FT-F15 (partly) | No reference ran through a non-mechanical adapter | Fixed: the fixture gains a derivation, and a test-only stand-in for the Icarus adapter drives the engine's `PASS` paths | `test_a_reference_and_a_requirement_run_and_give_their_results` |
| FA-ACC-1, FA-ACC-3, N-docs-3 (partly) | No clean-tree comparison or mutation result recorded for this branch | Recorded in §16 and `TASKS.md` T-011 | *verification record* |
| N-docs-1–8, 10–17 | Documentation claims the code did not bear out (a receipt "whatever the item does", `SOURCE_REJECTED` for a content refusal, `cad_ref` as a generic check, the gravity sentence, the README's Linux claim and verifier rule, `--stop-timeout`, §8.1, §11, §12.1, stale wording) | Fixed | *doc change* |

A third, focused review then examined the second round and the final
documentation: 19 findings, all confirmed by a separate verifier, none
refuted. Most shared one gap — committed cases were reconciled with the fresh
derivation by id only, so an edited limit, tolerance or metric still decided
its check (on `robotic_joint_001`, a limit tightened to 1.0 N·m without a
rebuild reported `PASS` against the committed 2.5 N·m). Round 3 (`bb43124`)
closed them:

| IDs | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| R-2, R-3, S-1, S-3, D-1, D-3 | A committed case with the right id but other content (limit, tolerance, metric) was counted; with a changed metric the results then failed their own schema and the command line exited 1 though a receipt existed | Fixed: `BLOCKED` `COMMITTED_CASE_STALE`, naming what differs | `test_a_committed_case_the_requirements_no_longer_compile_to_is_not_counted`, `test_a_limit_tightened_without_a_rebuild_is_not_judged_against_the_old_one` · `content-stale-case-counted` |
| R-1 | The case engine raised out of `validate` on a document not in UTF-8, or on a non-finite metric | Fixed here for those two; a `RecursionError` from the engine was closed in round 4 (below): gate-level `INCONCLUSIVE` `CASE_ENGINE_ERROR`, every compiled entry `BLOCKED`; ENGINE-1 widened (§7.2) | `test_a_case_document_the_engine_cannot_run_still_gives_a_receipt` · `engine-error-crashes` |
| R-5, S-5 | A result took a bound and seed from a case its check never ran, and a limit value the fresh derivation found missing | Fixed: a case only when the result's own check ran it; a limit is null when the check was blocked on it | `test_a_committed_case_the_requirements_no_longer_compile_to_is_not_counted`, `test_a_stale_case_for_a_requirement_now_blocked_is_discarded_not_duplicated` · `case-without-execution-used`, `null-limit-from-findings-ignored` |
| S-2 | The AI rule read only the committed model's statuses: a relabel without a rebuild was missed | Fixed: statuses from both models, the stricter decides; the result's listed inputs followed in round 4 (below) | `test_an_input_relabelled_without_a_rebuild_is_judged_by_what_it_is_now` · `fresh-statuses-ignored` |
| S-4, D-2 | The results read a case document the engine had refused on its schema, and crashed on its shape | Fixed: only schema-valid documents are read | `test_a_case_document_that_breaks_its_schema_is_not_read_for_results`; `test_a_forged_case_document_is_not_read_for_results` (added after the full mutation run left it alive: in a real run no executed check cites such a document, so only regeneration from a forged run reaches the check) · `results-cases-schema-unchecked` |
| R-3 (exit code) | A results failure after the receipt exited 1, which means "no receipt" | Fixed: `ResultsNotWritten`, exit 2 | `test_the_command_line_says_when_the_receipt_was_written_without_its_results` · `results-failure-exit-code` |
| R-4 | The four gate-level check ids could be an entry's id, colliding with the check that stands in for the gate | Fixed: reserved; a committed case under such an id was still counted until round 4 (below) | `test_an_id_the_case_engine_uses_for_a_whole_gate_is_refused` · `reserved-ids-allowed` |
| S-6 | JSON nested too deeply raised `RecursionError` from parsing, schema checking or comparison | Fixed for the item's own documents; case documents (through the engine), the manifest comparison and the receipt were closed in round 4 (below): malformed input, a `ValueError` or a reported problem | `test_json_nested_too_deeply_is_malformed_input_not_a_crash` · `deep-json-crashes` |
| S-7 | Regeneration trusted the item digest for a model git ignores, which the digest does not cover | Fixed: refused | `test_a_model_outside_the_receipt_s_digest_is_not_regenerated_from` · `regenerate-unlisted-model` |
| D-4 | MEMORY.md still promised a receipt "whatever the item does"; the refusals before any gate were not listed | Fixed: the refusals are listed in the README and the architecture document | *doc change* |
| D-5, D-6, D-7 | Three names in this section were wrong or stale | Fixed | *doc change* |

A fourth review then examined the third round and the documentation: 22
findings, all confirmed, none refuted. The substantive one: a case whose
limits still matched was counted even when the domain model it runs on no
longer reproduced (on `robotic_joint_001` with the densities doubled and no
rebuild, REQ-MECH-001 was judged on the old MJCF). Round 4 (`dbf73e1`)
closed them. Its own fixes have not had a review of their own.

| IDs | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| R4-2 | A committed case whose derived input (the MJCF) no longer reproduces was counted | Fixed: `COMMITTED_CASE_STALE`, naming the input | `test_a_case_whose_derived_input_no_longer_reproduces_is_not_counted`, `test_a_design_edited_without_a_rebuild_is_not_judged_on_the_old_model` · `input-staleness-ignored` |
| R4-1, S4-1, D4-1 | A `RecursionError` from the case engine (a case document nested too deeply to parse or to check) lost the receipt | Fixed: `CASE_ENGINE_ERROR` | `test_a_case_document_the_engine_cannot_run_still_gives_a_receipt` · `engine-recursion-crashes` |
| R4-3 | An engine exception marked every entry `BLOCKED` though nothing was missing, and the loss of their verdicts was not said | Fixed: `INCONCLUSIVE` (crashed); ENGINE-1 says the verdicts are lost | the same test · `engine-error-marked-blocked` |
| R4-4 | An infinity was "within tolerance" of any number, in V2 and in case reconciliation | Fixed: untrusted JSON refuses `Infinity`/`NaN`; non-finite comparisons are exact | `TestNonFiniteNumbers` · `infinite-constants-accepted`, `infinity-equals-anything` |
| R4-5, S4-7, D4-3 | A result's inputs came from the committed model only, so a relabel did not show | Fixed: the inputs each check was judged on are recorded with it and listed | `test_an_input_relabelled_without_a_rebuild_is_judged_by_what_it_is_now` · `inputs-not-recorded`, `recorded-inputs-ignored` |
| R4-6, S4-4 | A failure serialising the results escaped the `ResultsNotWritten` guard | Fixed: inside the guard (no input reaches it now that non-finite numbers are refused) | *no trigger left; no mutant* |
| R4-7 | Entries of a document the engine refused as a whole were called missing | Fixed: `CASE_DOCUMENT_REFUSED` | `test_a_case_document_the_engine_refuses_is_named_not_called_missing` · `refusal-unlabelled` |
| S4-2 | A manifest nested too deeply crashed V2's comparison | Fixed: a reported divergence | `test_a_manifest_nested_too_deeply_is_a_divergence_not_a_crash` · `manifest-deep-crash` |
| S4-3, D4-2 | A receipt nested too deeply raised `RecursionError` from regeneration | Fixed: `ValueError` | `test_a_receipt_nested_too_deeply_is_refused_not_a_crash` · `regenerate-deep-receipt` |
| S4-5 | Exit 2 for "receipt without results" is argparse's usage-error code | Fixed: 3 | `test_the_command_line_says_when_the_receipt_was_written_without_its_results` · `results-failure-exit-code` |
| S4-6, D4-4 | A committed case under a gate-level id was counted | Fixed: only the engine's own gate-level verdicts count | `test_a_committed_case_under_a_gate_level_id_is_not_counted` · `gate-level-id-counted` |
| S4-8 | A V3 result whose adapter crashed lost the bound its case was compiled to | Fixed | `test_a_reference_whose_adapter_crashed_still_shows_its_compiled_bound` · `crashed-case-bound-dropped` |
| D4-5, D4-6, D4-7 | The README's exit codes, MEMORY.md's refusal list, and this section's rows overstated what was closed | Fixed | *doc change* |

### 7.6 Defects found by independent review of the electrical branch, and their state

`feat/domain-electrical` at `bf04f1b` had two independent reviews,
correctness and security (CS) and honesty and tests (HT), each of which
reproduced every finding below with its own scripts (both on 2026-09-28).
The fixes are `11b19b1` (spice), `555bfd7` (electrical), `ec37115`
(tests), the documentation commit `5917365` that adds this section, and
`49887ac`, which brings the parser test's netlist and deck, left behind by
`555bfd7`, back to the committed files; each named
mutant is in `tests/mutation/run_mutations.py`, and §16 records the run
that killed it. The fixes have had no review of their own.

| ID | Finding (as confirmed) | State | Test · mutant |
|---|---|---|---|
| CS-1 | The node grammar accepted names ngspice-47 reads as its own inside a `.meas`: with the rail named `time`, `v(time)` read the time axis and a real limit "bus peak ≤ 45 V" passed at 0.1; `all`/`allv` read another vector; a node or a model `temper` crashed ngspice; `limit`, `gauss`, `agauss`, `unif`, `aunif` inside `par()` made it exit 1 | Fixed: nodes are `0` or `n_[a-z0-9_]{1,30}`, models `SW_[A-Z0-9_]{1,29}`, in the parser and the model schema; `gnd` and `pa_N` keep their named refusals. 174 names probed on ngspice-47: 12 misread as nodes and 2 as models (`TEMPER`, and `GND`, never found), none with the prefixes | `test_names_are_canonical_unique_and_never_ground_aliases_or_par_nodes`, `test_a_name_ngspice_reads_as_its_own_is_refused_before_ngspice_runs`, `test_a_circuit_member_needs_format_1_1_0` · `spice-node-prefix-dropped`, `spice-model-prefix-dropped`, `schema-node-prefix-dropped`, `schema-model-prefix-dropped` |
| CS-2 | Nothing checked that the fault switch closes inside the transient: with V_FLT rising over 100 ms it closed at 150 ms, after T_END, V1 passed, `fault_input_current_a` read the pre-fault 4.17 A and a real 10 A limit on it passed | Fixed: extraction refuses a fault switch that never exceeds VT + VH, or closes too late for the rail to settle (30 τ_f) before T_END; the reference form's own condition. The bypass's timing was already a V1 finding (it must close before the load) and the settled forms check their windows | `test_a_fault_the_transient_cannot_measure_is_refused` · `el-fault-window-unchecked`, `el-fault-that-never-closes-accepted`, `el-fault-hysteresis-ignored-at-extraction` |
| CS-3 | A zero or negative capacitance, a capacitance of 1e150 or a zero RON raised `ZeroDivisionError`/`OverflowError` from the closed forms, which `compile_cases` runs before V1, so `validate`, `build` and `check` ended in a traceback and no receipt was written | Fixed: extraction refuses a resistance, capacitance or switch resistance that is not positive and a ramp still rising at the bypass command; `reference_value` turns an `ArithmeticError` or a non-finite value into `ReferenceBlocked`; the runner's V1 guard catches `ArithmeticError`. `build` and `check` still end in a traceback on any refused netlist, as before (their `ExtractionError`, now with the reason) | `test_values_the_closed_forms_divide_by_are_refused_and_never_cost_a_receipt`, `test_a_reference_does_not_apply_where_its_assumptions_fail`, `test_an_arithmetic_error_the_item_provokes_still_gives_a_receipt` · `el-nonpositive-value-accepted`, `el-ramp-after-bypass-accepted`, `el-arithmetic-error-raised`, `el-non-finite-reference-kept`, `runner-arithmetic-error-crashes` |
| CS-4 | The precharge forms ignored the fault switch's off resistance; the docstring's 4.8e-8 A bound held for 1 GΩ only, and with a valid ROFF of 1 kΩ V1 passed but REF-EL-002, 003, 004 failed | Fixed: the four forms fold R_off,F in as a Thevenin source; they agree with ngspice-47 at 1 kΩ, 100 Ω and 1 GΩ (13 variants, 2026-09-28). Not the not-applicable alternative (`MEMORY.md`) | `test_references_are_the_closed_forms_written_out_here`, `test_the_precharge_forms_hold_with_a_leaky_fault_switch` · `el-precharge-fault-divider-ignored`, `el-precharge-fault-current-ignored` |
| CS-5 | The inrush window stops at T_BYP: a bypass at 14.5 ms drew a 28.3 A surge after it that no metric saw, and REQ-EL-001 (≤ 10 A) passed | Fixed: a tenth metric, `startup_peak_current_a`, over [0, T_FLT]; REF-EL-010 (its form: the larger of the precharge peak and the settled load current, not applicable when the surge is the peak, since ngspice samples that step 3e-4 to 8e-4 low) and REQ-EL-008 (illustrative, 10 A). At 14.5 ms, REQ-EL-008 fails at 28.3205 A on ngspice-47; the nine existing metrics keep their meanings | `test_a_surge_after_an_early_bypass_fails_the_startup_requirement`, `test_references_are_the_closed_forms_written_out_here`, `test_a_reference_does_not_apply_where_its_assumptions_fail` · `el-startup-window-ends-at-bypass`, `el-startup-surge-ignored`, `el-startup-load-ignored`, `el-startup-surge-without-esr`, `el-startup-limit-changed` |
| HT-1 | The documentation said V2's electrical invariants read the committed deck; the runner hands them the freshly regenerated deck | Fixed in the documentation (the runner is unchanged; `MEMORY.md` says why): the invariants check the writer against the reader and the model, and only `v2.dataset-reproduction` reads the committed deck | `test_a_deck_edited_without_a_rebuild_is_divergent_and_not_counted` (the invariants `PASS` on an edited committed deck) · *doc change* |
| HT-2 | Three places said ngspice only ever runs the regenerated deck; a committed deck's `.control shell` ran during `validate` | Fixed in `docs/cad-dataset-engineering-model-v1.md`, `MEMORY.md` and §7.2 SEC-2: ngspice runs the committed deck, equal to the regenerated one only while reproduction passes; the residual risk is a hand-edited committed file running a command before it is flagged stale, as for the Python case scripts. SEC-2 itself stays open, a maintainer's decision | *doc change* |
| HT-3 | Conditions of rules C1, C3, C4 and C7 had no test (V > 0; the bypass ending on the rail; the command node carrying only the command; cn on ground), and a mutant of each survived every suite | Fixed: a netlist for each | `test_only_the_series_precharge_supply_network_is_accepted` · `el-ramp-zero-level`, `el-bypass-other-end`, `el-command-node-shared`, `el-command-cn-ground` |
| HT-4 | `test_spice_job_cannot_skip_silently` passed with the job under `if: false`, `|| true` after the suite, `--ignore` of the electrical tests, or a step-level `ECAD_REQUIRE_SPICE_TOOLS: "0"` | Fixed: a strict reader of the workflow's layout (no YAML parser is installed) asserts the job's keys, its one env entry, the exact suite step, and no `||`, `--ignore`, `--deselect` or `-k`; the cad-dataset test the same way. Each edit fails the new tests and passed the old | `test_spice_job_cannot_skip_silently`, `test_cad_dataset_job_cannot_skip_silently`, `test_the_job_reader_refuses_a_line_it_cannot_place` · *none: the mutation harness does not run `test_ci_and_runner.py`* |
| HT-5 | No test reached the summary's `[:MAX_SUMMARY_PROBLEMS]` cap (and `run`'s docstring said every unread name is named), the path half of "cites the netlist by path and hash", the `powered_by` guard, or the hysteresis in the closing times | Fixed: a test each; the docstring states the cap | `test_the_summary_names_at_most_ten_unread_measurements`, `test_v2_names_every_way_a_deck_can_disagree_with_its_model`, `test_a_reference_does_not_apply_where_its_assumptions_fail`, `test_a_fault_the_transient_cannot_measure_is_refused` · `ng-summary-cap`, `el-invariant-ref-unchecked`, `el-powered-by-any-element`, `el-closes-hysteresis-bypass`, `el-closes-hysteresis-startup`, `el-closes-hysteresis-fault`, `el-closing-time-ignores-hysteresis` |
| HT-6 | Numbers in the documentation: "at least 21 times" (the fault current's ratio is 20.94), 714287 (714286 from the stored golden), 285 mutants (292 at `bf04f1b`) | Fixed: recomputed after the changes (the table of `docs/electrical-domain-v1.md`, §16, `TASKS.md` T-012) | *doc change* |
| HT-7 | Q4 was half dropped: whether the sheet's 5 A is continuous or peak and 200 W input or output power; the netlist and REQ-EL-003 read 200 W / 48 V as the drive's input and compare the input current with 5 A, which the sheet gives for the power stage | Fixed: both labelled assumptions in §20 Q4, the annotations' notes, REQ-EL-003's title and the netlist's comment; the sample rebuilt | *data and doc change* (the rebuilt sample is checked by `test_the_committed_sample_checks_and_rebuilds_to_the_same_bytes`) |
| HT-8 | `test_electrical_spice.py`'s docstring said no expected value comes from the code under test; the value-spelling test expects `1 / parse_value(...)` | Fixed: the docstring calls it a differential test against ngspice and says what that can show | *doc change* |

Two statements in the commit message of `555bfd7` are wrong, and the
commit is not amended: it says 16 new mutants (it adds 15), and that the
stored goldens moved "in the ninth to twelfth figure" (the eighth to
twelfth: `precharge_bus_voltage` moved from 47.9147188794 to
47.9147184047).

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
finding also carries the actual status. (Implemented on
`feat/multi-domain-foundation`.)

**Status propagation.** A check's inputs are what the model paths it depends
on rest on through `derived_from` — its metric's dependencies and the
limit's model quantity for a requirement, the derivation's inputs for a
reference (§12.2) — namely every quantity on the way whose status is not
`DERIVED`, and every `DERIVED` quantity with no model inputs of its own, each
with its status (SCOPE-7). The rule is applied in `dataset.validate` after
`execute_cases` and before gate aggregation, to V3 and V4 checks alike, so
the receipt and the per-requirement result agree, in this order (the first
that applies wins):

1. any null-status input → `BLOCKED`, `MISSING_REQUIRED_INPUT`;
2. any input that does not resolve in the model → `INCONCLUSIVE`,
   `INPUT_NOT_RESOLVABLE`, unless already `BLOCKED`;
3. any `AI_ASSUMPTION` input → the comparator's `PASS` or `FAIL` on a
   requirement (`CORNER_LIMITS_PASSED`/`FAILED`) becomes `INCONCLUSIVE`,
   `INPUT_IS_AI_ASSUMPTION`; a golden is unaffected, since it compares two
   computations on the same inputs (AI-1), and so is a verdict the
   comparator did not reach (a crash, a missing tool);
4. a met illustrative limit → `WARNING`, `WITHIN_ILLUSTRATIVE_LIMIT`.

`ESTIMATED` inputs do not change the verdict and are listed in the result.

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
- **ARCH-1 as amended by the electrical domain** (`feat/domain-electrical`).
  The netlist is the source, but ngspice runs a deck regenerated from the
  engineering model, not the netlist, so the model carries topology: each
  netlist element's component has a `circuit` member (`designator`,
  `element`, `terminals`, a switch's `model`); nets are derived from the
  terminals and never stored; there is no extraction file. Why: the protocol
  hands `write_models`, V1, V2 and the closed forms only the model, so
  without terminals the deck could not be a function of the model and
  "netlist → engineering model → simulator" (spec §36) would be false.
  Rejected: passing extraction files to `write_models` (a protocol change,
  and V1 and V3 still would not see the topology); re-reading the netlist
  inside `write_models` (a hidden input outside `Item.read`); a deck that
  `.include`s the netlist (ngspice would run unparsed text); a top-level
  `circuit` with nets, ports and rails (two sources of truth for
  connectivity). Stored nets, and pins beyond an element's terminals, still
  wait for a cross-domain rule. Maintainer acceptance is open (§20).

Spec entity names map as follows. Mechanical: Part → component with
`cad_ref`; Link → rigid group root; Joint → joint; Material → `material`;
Mass/Inertia/CoordinateFrame → `physical`/`placement`; CollisionGeometry →
the MJCF proxies (domain model). Electrical: Circuit → the model of a
sample whose primary domain is electrical; Component → a component with a
`circuit` member; Node → its terminals; Net → derived from the terminals;
PowerRail, Input and Output → roles of the validated network class, not
stored; ComponentRating → rating facets. Module/Signal/Clock,
Layer/Trace/Via, PowerStage, Plant/Controller, Coil/Excitation and
HeatSource/ThermalInterface are domain-model concepts owned by their adapters,
with the parameters other domains consume published as facets.

## 9. Proposed dataset schema

### 9.1 Layout

The sample layout stays `datasets/cad/<sample>/` until the first sample whose
primary domain is not mechanical (SCOPE-8, LAYOUT-1). The electrical sample
kept it: see §20 Q8. Moving now would
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
  pre-release in `docs/cad-dataset-engineering-model-v1.md` (Versioning) on
  the stack, so PR 2 lands them labelled. PR 3 (this branch) replaces that
  declaration with the rule: from its merge, a compatible addition stays in v1
  and an incompatible change needs v2.
- Producers: one version constant per producer (the STEP importer, the
  builder, each domain adapter's derived outputs, the compiler, the results
  generator, the validator), so a change to one bumps one. `MODEL_VERSION`
  remains only as the version of the engineering-model document format.
- A per-requirement result identifies the model by the SHA-256 of
  `engineering_model.json`, separately from the schema version (RESULT-5).
- In-document versions (the electrical domain, `feat/domain-electrical`): a
  compatible addition to a document format raises that document's minor
  version; the v1 schema accepts every minor version of v1, and requires the
  new one for a document that uses the addition. `model_version` and
  `annotations_version` accept 1.0.0 and 1.1.0; 1.1.0 is required for a
  `circuit` member, an electrical component kind, or `circuit_elements`.
  Mechanical models stay 1.0.0 (`MODEL_VERSION`); the electrical adapter
  writes 1.1.0 (`CIRCUIT_MODEL_VERSION`). Rejected: keeping 1.0.0 for
  documents that use the additions, which would hand a 1.0.0 reader members
  its closed schema refuses. Maintainer acceptance is open (§20).

## 10. Domain-by-domain plan

| # | Domain | Current | MVP sample | Open-source backend | Blockers and prerequisites |
|---|---|---|---|---|---|
| 1 | Mechanical | PARTIAL | `robotic_joint_001` (exists) | MuJoCo | Fixes in §7 are local and unpushed; Linux reproduction (§20 R1) |
| 2 | Electrical | PARTIAL (local branch `feat/domain-electrical`; §21 item 4 marks each part) | `servo_supply_001`: 48 V servo supply input: fuse, precharge resistor with bypass switch, bulk capacitor with series resistance, constant-current drive load, fault switch. | Inrush peak and I²t, precharge, the startup peak with the bypass surge, steady bus voltage and input current, fuse dissipation, prospective short-circuit current; component ratings `BLOCKED` on data | ngspice batch: the deck's `.meas` results read from stdout (ARCH-2, ngspice half) and the version from the banner (RESULT-8) | ngspice-47 is installed here (Homebrew); which ngspice apt installs on the CI runner is Unknown, and it is not pinned. **Data:** the eServo-200 sheet gives only 48 V, 5 A, 200 W; fuse, limiter and capacitor values are design choices of a self-authored circuit (`SPECIFIED` by the netlist, source `design_annotation`, noted as no part's rating) and every part rating is `UNKNOWN`, so no check on a real part's rating can `PASS`; steady ripple is `BLOCKED`: the sheet states neither the drive's input ripple current nor its switching frequency (`UNSPECIFIED`); overlaps PR #31's eServo-200 power-budget cases (Q6) |
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
output into metrics and evidence (ARCH-2). For ngspice the parser exists on
`feat/domain-electrical` and needs no output copy: the `.meas` results are
read from stdout (§7.2 ARCH-2). The output copy and the other parsers wait
for their domains.

**Domain adapter** (`ecad_model/domains/base.py`; stable since the electrical
domain, as the end of this section records). The spec's
example (`prepare`, `run`, `collect_results`, `validate`) adapted to this
repository, where running and deciding already belong to the case engine.
As implemented on the foundation branch:

```python
class DomainAdapter(Protocol):
    domain: str
    formats: FrozenSet[str]          # the artefact formats it reads
    description: str                 # what it validates: the manifest's AVAILABLE reason

    # engineering model
    def extract(self, root, sources, annotations, refs) -> Extraction: ...   # model, its producer, raw extraction files, tool records
    def document_schemas(self) -> Dict[str, str]: ...                        # each extraction file's schema, checked at V0

    # prepare (spec) = domain models + checks + case targets
    def write_models(self, model, sample_id) -> List[DerivedFile]: ...       # path, bytes, role, media type, producer + version, derived_from, comparator
    def sanity_problems(self, model) -> List[str]: ...                       # V1
    def invariant_problems(self, model, extraction_files, domain_models) -> List[str]: ...  # V2
    def case_target(self, sample_id) -> CaseTarget: ...                      # tool adapter, inputs, arguments per scenario
    def simulation_files(self, root) -> List[str]: ...                       # case scripts, hashed as inputs

    # vocabulary and what each check rests on
    def metrics(self) -> Dict[str, Metric]: ...                              # unit and fidelity per metric
    def check_requirements(self, requirements) -> None: ...                  # refuses scenarios and derivations it lacks
    def reference_value(self, model, derivation, scenario) -> Tuple[float, List[str]]: ...  # V3 closed forms
    def reference_inputs(self, model, derivation, scenario) -> List[str]: ...
    def dependencies(self, model, metric, scenario) -> List[str]: ...        # §12.2
    def components_for(self, model, metric) -> List[str]: ...               # source parts a metric depends on
```

Case compilation stays domain-neutral (`requirements.compile_cases`, one
version), fed by `case_target`, `reference_value` and `metrics`.
Designed here but not yet in the protocol: publishing DERIVED facets for
other domains (`publish`) and per-requirement input declarations beyond
`dependencies`; both wait for the first cross-domain rule. `validate` in the
spec's sense stays with the existing deterministic comparators and the status
propagation of §8.1; cross-domain evaluation is a separate post-execution
stage (§14). The protocol has no `depends_on` yet: the cross-domain PR adds
it, with each adapter declaring the facets and results it consumes, and
dependency order is defined there. Simulation files are declared by the
adapter and recorded with a media type from their extension (`.py`, `.v`,
`.cir`, …); the compiled case documents stay one pair per sample. Check IDs
are namespaced by domain (`v1.mechanical.extraction-and-sanity`,
`v2.mechanical.model-invariants`) so several domains fit in one receipt.

The registry is the set of registered adapters in code. It replaces
`VALIDATED_DOMAINS`; the manifest's domain status is derived from it (§12.3).
There is no hand-edited registry file, which would reintroduce H2
(SCOPE-10).

`QUALITY.md` says not to add an abstraction for a second case that does not
exist yet; spec §32 asks for the adapter in the foundation. The spec wins
under `CLAUDE.md` precedence, and the conflict is recorded here. To keep the
protocol honest before a second domain exists, PR 3 checks it against one
artefact-first domain with a test-only fixture adapter, not a production
stub: Verilog in, no CAD kernel, and a requirement compiled through the
fixture's own metric vocabulary into a case the existing engine runs with the
Icarus adapter, which the test reports as not installed so the outcome does
not depend on the machine. No metric is parsed from a tool's output yet; that
waits for a real HDL domain (§21 item 5). The protocol was marked
provisional until the electrical domain landed (SEQ-1).

**Stable since the electrical domain** (`feat/domain-electrical`): two
production domains use the protocol, one CAD-first (mechanical) and one
artefact-first (electrical), and `domains/base.py` says so. The changes the
electrical domain forced (SCOPE-15), each with the matching change to the
mechanical adapter and every other call site:

| Change | Why electrical forced it | Matching mechanical change | Other call sites |
|---|---|---|---|
| `Extraction.producer: Tuple[str, str]`, required, with no default | The runner wrote `producer="ecad_model.builder"` and the builder's version as every model's producer and as `versions.engineering_model`, so the electrical manifest would have claimed the mechanical builder wrote its model | `MechanicalAdapter.extract` passes `("ecad_model.builder", builder.VERSION)`; the mechanical manifest is byte-identical in both fields | `dataset.py` reads the producer at both sites and drops its now-unused `BUILDER_VERSION` import; the test-only Verilog adapter passes its own producer, and a test checks the manifest names it (`test_the_manifest_names_the_fixture_as_its_model_producer`, mutant `model-producer-hard-coded`) |

Considered and not changed: the `write_models` and `case_target`
signatures, which a model that carries topology (§8.2) and scenarios that
are windows of one transient make sufficient; scenario-dependent inputs,
PLANNED as an additive `CaseTarget.scenario_inputs` when a domain needs
them; `publish` and `depends_on`, which still wait for cross-domain rules.
Registry side effects, not protocol changes: `REGISTRY` gains
`ElectricalAdapter`, and the robotic joint's manifest regenerates one entry,
electrical `NOT_IMPLEMENTED` → `NOT_APPLICABLE`. A further protocol change
lists its reason and the matching change to every registered adapter and to
the test fixture.

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
`engineering-model/v1/validation-results.schema.json`, one result per
requirement or reference, each from the receipt check that decided it: its
own `v3.<id>`/`v4.<id>`, or the gate-level check that stands in when the run
compiled or executed none. Nothing is filled in for a requirement no check
decided. It replaces `trace.json` and keeps every trace field (RESULT-6).

| Field (spec §17) | Source | Null when |
|---|---|---|
| `validation_id` | `<sample_id>:<gate>.<requirement id>` | never |
| `check_id` | the receipt check that decided the result | never |
| `domain` | the requirement's engineering domain (never the receipt's contract domain, MAP-1) | never |
| `kind` | `reference` (V3), `requirement` or `illustrative requirement` (V4), as the stack's `trace.json` had it | never |
| `requirement`, `title`, `source`, `metric` | the requirement's or reference's own fields | never |
| `component` | the requirement's component | V3: references name none |
| `cad_components` | the source parts the metric depends on, from the adapter; both sides for clearance | never (may be empty) |
| `illustrative` | the requirement's flag; `false` for a reference, which is computed, not chosen | never |
| `status`, `reason_code`, `findings` | status and reason copied verbatim from the deciding check, and its findings, to which the generator adds a note for a metric that is not a number and for inputs it could not establish; a test asserts equality | never |
| `measured_value` | the check's metric; for a V4 requirement `BLOCKED` only because its limit is null, the same metric with the same compiled arguments from the check that measured it, named in `measured_by` (RESULT-3); no other result borrows one | no metric was recorded |
| `expected_value`, `operator`, `applied_bound` | the requirement's limit (V3: the reference value, operator `within`); the bound as compiled: a V4 minimum or maximum with the tolerance folded in (§14), a V3 `{value, absolute_tolerance}` as the golden comparator evaluates it — taken from a compiled case only when the result's own check ran it | the limit's status is null (in the committed model, or as the check's own finding says) or does not resolve, or no case ran for the result |
| `unit` | the requirement, checked against the adapter's metric vocabulary | never |
| `tolerance` | V3 absolute tolerance; V4 requirement tolerance, default 0 | never |
| `simulator`, `simulator_version`, `configuration` | the case's adapter; tool version, command and arguments from that check's hash-bound execution record (`cases.py:398-418`) — never from receipt `tools[]` (RESULT-1). `configuration` carries the command, the scenario parameters and the seed of the compiled case (spec §24). The time step is fixed in the domain model, which the case cites as evidence, and is not a field; the case engine's execution records are unchanged and still omit the seed | no execution record; the schema forbids null with `PASS` |
| `model_version`, `model_sha256` | engineering-model schema version; SHA-256 of `engineering_model.json` | never |
| `model_fidelity` | the adapter's declaration for this metric | the metric is not one the domain produces (an entry V1 refused) |
| `inputs` | what the metric's dependencies (§12.2) rest on through `derived_from`: every quantity on the way whose status is not `DERIVED`, and every `DERIVED` one with no model inputs, with statuses; numeric scenario parameters as their own entries, `SPECIFIED` by the requirement or reference that states them (RESULT-4) | never (may be empty) |
| `timestamp` | `receipt.completed_at`, so regeneration is byte-identical (RESULT-7) | never |
| `environment` | OS, architecture and interpreter of the run and the digest of `tools/constraints-cad.txt`, as the run recorded them in its `v0.pinned-clean-source` evidence, with the version of every tool the receipt records for the run (spec §24, COVER-4) | never |
| `source_dirty` | the receipt's `source.dirty` | never |
| `input_hash` | `receipt.source.input_sha256`; scope: the sample's git-listed files, not code or out-of-sample citations | never |
| `receipt_sha256`, `evidence` | the receipt's digest in full; the check's evidence IDs and digests | never |

Results are written as canonical JSON to `results.json`, after the receipt
and the evidence index, so nothing the results do can cost a run its receipt;
when none can be built — no adapter, requirements that cannot be read, or a
committed model that is missing or invalid — the report says why. They are
bound to the receipt by its full digest; each result cites its check's evidence digests. They are
not entries of the contract's evidence index, whose entries belong to receipt
checks. `regenerate_results` rebuilds the file byte for byte, on any machine,
from the receipt and the run's stored evidence (case documents, execution
records, environment), each verified against its recorded digest, together
with the item's model and requirements; it refuses unless the item's digest
equals the receipt's `input_sha256`, refuses a run that wrote no results,
and treats the run directory as untrusted (a malformed environment record
is refused too). The schema refuses the combinations the contract forbids (§14,
§8.1): a `PASS` without a simulator version or a measured value, an
illustrative `PASS`, a kind that disagrees with the illustrative flag, a
result on a null-status input that is not `BLOCKED`, and a comparator
verdict resting on an `AI_ASSUMPTION`. Verdicts are the v1 set: `PASS`, `FAIL`,
`WARNING`, `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`.

### 12.2 Dependencies

The adapter says, for each metric, the model paths it depends on
(`dependencies`), and for each reference derivation the paths it reads
(`reference_inputs`). For the mechanical domain the dependency of a simulated
metric is coarse and honest: the joint's axis, origin and range for every
metric (the range is in the MJCF every case runs on); for dynamics, every
moving body's mass properties and placement, and gravity; for clearance,
every body's placement and bounding box. Status propagation (§8.1) and
`inputs` (§12.1) both read these.

### 12.3 Domain status vocabulary

Data uses the spec §34 words: `AVAILABLE` (the sample's primary domain, whose
registered adapter validates it from one of its artefacts: the only adapter
run for a sample) and `NOT_IMPLEMENTED` (no adapter exists), plus
`NOT_APPLICABLE` (an adapter exists but does not run for this sample: no
artefact it reads, or not the primary domain). Each entry's reason lists the
sample's null-status inputs for that domain. `IMPLEMENTED`/`PARTIAL`/`PLANNED`/`BLOCKED` stay
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
  Current: on the stack, 68 mutants of the mechanical domain, all killed at
  `bd999d5` after a green baseline (**Verified**). On the foundation branch,
  200 mutants (the mechanical ones re-anchored, plus the foundation's and
  both reviews'): at `2beb77a`, after a green baseline, 199 killed; the
  survivor, `stale-committed-case-counted`, was a missing test, which
  `b4fca10` adds and a targeted re-run shows killing it. After the third
  review, 210 mutants at `bb43124`, after a green baseline: 209 killed; the
  survivor, `results-cases-schema-unchecked`, was again a missing test, which
  `7b58a76` adds and a targeted re-run shows killing it (**Verified**,
  2026-09-26/27). After the fourth review, 222 mutants at `dbf73e1`, in two
  runs that each began with a green baseline (54, then the other 168 on seven
  workers): 222 killed, none surviving -- 96 by `test_engineering_model.py`,
  84 by `test_domain_adapter.py`, 42 by `test_cad_dataset.py` (**Verified**,
  2026-09-27). Each kill names its test. On `feat/domain-electrical`, 285
  mutants: those 222, their anchors unchanged, and 63 new ones for the
  electrical domain — 18 of the netlist parser, 17 of the electrical
  adapter, 8 of the sample's netlist, annotations, requirements and
  provenance (each followed by a rebuild), 1 of the model's format rule, 13
  of the ngspice adapter, 4 of the version probe, 1 of the model producer
  and 1 of the registry. All 63 new ones were killed, each naming its test,
  after a green baseline on the same code and tests (**Verified**,
  2026-09-27: the harness killed 13 before a wall-clock limit stopped it,
  and its `run()` killed the other 50). At `57f4fee`, which adds docstrings,
  their examples and two tests, one run of all 285 after a green baseline
  killed all 285, none surviving -- 114 by `test_engineering_model.py`, 84
  by `test_domain_adapter.py`, 37 by `test_cad_dataset.py`, 20 by
  `test_electrical_domain.py`, 17 by `test_ngspice_adapter.py`, 13 by
  `test_spice_netlist.py` (**Verified**, 2026-09-27). `bf04f1b` added 7,
  so 292. The review of the branch (§7.6) adds 30 -- 4 for the node and
  model name prefixes, 15 for the electrical fixes, 11 for the branches the
  review found untested -- and re-anchors five to the lines they mutate,
  with the same mutation (`item-error-crashes-validate`,
  `el-esr-left-out-of-references`, `el-ramp-read-as-step`,
  `el-inrush-limit-changed`, `el-illustrative-flag-cleared`): 322 at
  `ec37115`. All 101 of the electrical branch (the 70 it had at `bf04f1b`,
  the 30 new ones and the re-anchored foundation mutant
  `item-error-crashes-validate`) ran at `ec37115` in nine batches of 9 to
  13 (`--only`, `--workers 4`), each on a clean clone after its own green
  baseline: 101 killed, none surviving -- 42 by
  `test_electrical_domain.py`, 22 by `test_engineering_model.py` (the
  modules' doctests), 18 by `test_ngspice_adapter.py`, 16 by
  `test_spice_netlist.py`, 3 by `test_domain_adapter.py` (**Verified**,
  2026-09-28). The other 221 were last run at `57f4fee`; their target lines
  and the tests that killed them are unchanged since, so those kills stand
  (Inferred, not re-run).
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
- One job per domain toolchain (`cad-dataset` exists; `spice` exists on
  `feat/domain-electrical`, placed between `validation-evidence` and
  `cad-dataset` so the existing slice test of `cad-dataset` stays exact, and
  has never run; `hdl`, `kicad` to come), each setting
  `ECAD_REQUIRE_<DOMAIN>_TOOLS=1` so a skip is a failure, and running the
  complete suite through `run_all_tests.py`. In the `spice` job the CAD
  tests skip with their reason (`cad-dataset` runs them), and the real-ngspice
  tests are mandatory.
- System libraries are installed explicitly: OpenCASCADE's wheel fails to
  import on a bare Debian image without `libGL.so.1` (**Verified**,
  `python:3.12-slim`, both architectures). Whether the `ubuntu-22.04` runner
  image ships it is **Unknown**, so the job installs it.
- Every job pins its tool versions, including transitive Python packages
  (`tools/constraints-cad.txt`). Exception, BLOCKED: the `spice` job installs
  ngspice from apt unpinned, because which version the runner gets is Unknown
  until the job runs; it prints the package version and the banner for the
  pinning decision (§20 Q16).
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
| Q4 | Who supplies real requirements? Every current limit is illustrative. The eServo-200 sheet also leaves two readings open that `servo_supply_001` has to take: it gives 5 A in its summary and for its power stage ("3-phase MOSFET bridge, 48V/5A") without saying whether it is continuous or peak, or drawn from the supply; and 200 W without saying whether it is input or output power. The sample **assumes** 200 W is the drive's input (I_LOAD = 200 W / 48 V) and that 5 A bounds the input current (REQ-EL-003), and says so in the netlist's comment, the annotations' notes and REQ-EL-003's title | Product owner |
| Q5 | Motor and gearbox for `robotic_joint_001`; until chosen, electrical, thermal, control saturation and full-system checks stay `BLOCKED` | Design decision |
| Q6 | Relation to open PR #31 (dev-board database). Its board records are a component catalogue that samples should reference rather than duplicate. It also adds eServo-200 V3/V4 `python_control` cases (a 48 V bus-current and power-budget model), which overlap the electrical MVP and, once merged, make §5's "V3/V4 never execute on master" false (RISK-1) | Coordination with its author |
| Q7 | `AI_ASSUMPTION` inputs: `INCONCLUSIVE` (implemented as the default) or excluded entirely? | Maintainer decision |
| Q8 | Dataset layout: by primary domain (spec §3) or one directory per sample with domains in metadata? The first non-mechanical sample, `servo_supply_001` (`feat/domain-electrical`), stays at `datasets/cad/servo_supply_001/`: the brief for that change kept the layout, against §21's rule that the move goes with that sample (an explicit instruction wins, `CLAUDE.md` precedence 1). The layout question itself is still open | Maintainer decision, now before the move rather than before the first non-mechanical sample |
| Q9 | New simulators (Verilator, Elmer, FMI) need the merged cases contract's adapter enum amended, or an open adapter ID checked against the registry | Maintainer decision |
| Q10 | The spec orders mechanical after the foundation; this plan lands the existing mechanical work first, because spec §35 asks to preserve it and the review evidence is tied to it | Confirm |
| Q11 | Add `.options norefvalue` to the electrical deck? On ngspice-47 it removes the progress report (` Reference value : <t>`) that a slowed run writes to stdout, so two runs of one deck would print identical stdout (Verified, 28 parallel runs, 2026-09-27). ngspice-36 (what apt installs on ubuntu:22.04, the CI runner's release) and 44.2 (python:3.12-slim) accept it: under load, without it 36 wrote two or three progress reports per run to stderr and 44.2 two to stdout, with it neither wrote any, and the nine measurement lines were identical across three runs of each deck (Observed, arm64 containers, 2026-09-27; `TASKS.md`). It changes the committed deck's bytes, `spice.read_deck`'s section marker and the recorded-deck test fixtures | Maintainer decision; the runs on ngspice-36 and 44.2 it waited for are made |
| Q12 | Accept ARCH-1 as amended by the electrical domain (§8.2): a component's `circuit` member, nets derived and never stored? | Maintainer decision |
| Q13 | Accept the in-document minor-version rule (§9.3): format 1.1.0 required for a document that uses an addition of 1.1.0? | Maintainer decision |
| Q14 | Land the SEC-2 guard (§7.2) as its own foundation change, before `validate` runs on anything unreviewed? It narrows the recorded decision that committed case documents run | Maintainer decision |
| Q15 | Harden the ngspice tool adapter beyond ARCH-2: `-n` (skip `.spiceinit`) and a deck screen in `NgspiceAdapter` (SEC-1, engine code no named defect covers); and should an ngspice exit status other than 0 become `INCONCLUSIVE` rather than `FAIL` (`python_control` maps it to `FAIL` too)? | Maintainer decision |
| Q16 | Pin ngspice in CI after the `spice` job's first run, or pin a runner image or a container? The banner names only the release (`36`), so the job also prints the package version | Maintainer decision, after the first run |
| Q17 | Commit invalid and boundary electrical samples as dataset items with expected receipts, or keep them test-built copies (today)? | Maintainer decision |
| R1 | Cross-platform reproduction. **Verified** at `bd999d5`: Linux aarch64 (`python:3.12-slim`, pinned wheels, only `git` and `libgl1` added) passes `check`, the complete suite (245) and gives the same `validate` verdicts as macOS; and again on the foundation at `bb43124` (322 tests) and at `000309b` (332 tests). **Verified** at `c9be0b6`: Linux x86_64 under emulation passes `check`. **Not run**: MuJoCo stages on native x86_64, because the emulated CPU has no AVX; any of `feat/domain-electrical` on Linux (its `spice` job would be the first) | A native x86_64 run, which the `cad-dataset` CI job provides on its first execution |
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
   marked with its state on `feat/multi-domain-foundation` at `000309b`: the
   findings of four independent reviews are closed (§7.5; the fourth round's
   fixes have had no review of their own), and the tests have been seen
   killing the mutants of §16:
   - versioning (§9.3): per-producer version constants, and the rule that
     replaces the pre-release declaration — PARTIAL: both exist, but no test
     has been seen failing when a producer's version is not recorded or not
     bumped;
   - status types, one null predicate at every site, per-status rules
     (§8.1) — IMPLEMENTED; status propagation (§8.1), in V3 and V4 —
     IMPLEMENTED;
   - artefact-neutral base types: `design.sources`, the manifest's source
     artefacts, domain-qualified derived roles, `Item` finding its sources
     through provenance, annotations that may carry no parts or materials
     (§8.2, SCOPE-2) — IMPLEMENTED;
   - provenance: primary domain and declared artefacts; licence-text
     reference checked; `verified_by`/`verified_at` for a verified
     third-party licence (§18); spec §4 keys mapped (§9.2); source kind
     `product_specification` (§19) — IMPLEMENTED;
   - dataset metadata: `domain`, `hash`, `versions.simulation`, `source_url`
     (§9.2) — IMPLEMENTED for `domain` and `source_url`; `hash` and
     `versions.simulation` are regenerated and compared by `check`, but no
     mutant of either has been run (PARTIAL for those two);
   - requirements: tolerance, unit checking, per-domain vocabularies (§14) —
     IMPLEMENTED;
   - common validation result: schema and generator, replacing `trace.json`,
     per-metric fidelity and dependencies (§12) — IMPLEMENTED;
   - evidence: results hash-bound; per-check execution records as the source
     of simulator versions; the environment recorded in the run's evidence
     (§12.1, §13) — PARTIAL: results are bound to the receipt by its digest
     but are not entries of its evidence index (by design, §12.1), and the
     seed and time step are not in the case engine's execution records (the
     seed comes from the compiled case, the time step from the domain model
     the case cites);
   - `DomainAdapter` protocol, in-code registry, mechanical refactored onto
     it, domain-namespaced check IDs, domain status in the spec §34 words
     plus `NOT_APPLICABLE`, the receipt-side MAP-1 fix (§11, §12.3) —
     IMPLEMENTED, provisional.

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
      `EXTRACTION_TIMED_OUT`, `EXTRACTOR_UNAVAILABLE`; the contract domain
      of V1 and `v2.mechanical.model-invariants`, `physical_design` →
      `integrated_physics` (the engineering domain's mapping), and of
      `v2.dataset-reproduction`, `data_management`; V2's reason when V1
      derived nothing, `CAD_EXTRACTION_NOT_AVAILABLE` →
      `DERIVATION_NOT_AVAILABLE`; a blocked reference with no missing input,
      `REQUIREMENT_INPUT_UNKNOWN` with no finding → `REFERENCE_NOT_APPLICABLE`
      with its reason as the finding; and the eServo-200 quantities' source
      kind, `datasheet` → `product_specification`, which re-hashes the
      annotations. Two behaviours change only where the committed sample does
      not reach: V3/V4 run no committed case when V1 derives no model, and a
      V1 `MISSING_REQUIRED_INPUT` names each missing value by path.
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
   7. One result per requirement and reference, naming the receipt check that
      decided it, and one for every V3/V4 check that implements a
      requirement; `status` equals that check's verdict; every evidence
      digest re-hashes; a `PASS` result has a `simulator_version`;
      regeneration from one receipt is byte-identical, on another host too,
      and refused once the item has changed; every `rom_` result has
      `model_fidelity = SIMPLIFIED` (SCOPE-12).
   8. The manifest's domain status is derived from the registry, and a test
      forging it fails `check`.
   9. The versioning rule of §9.3 replaces the pre-release declaration in
      the schema documentation, taking effect at the merge.
   10. The protocol is exercised end to end by a test-only artefact-first
       adapter (Verilog in, no CAD kernel): build, check, a requirement
       compiled through its own metric vocabulary into a case the existing
       engine runs with the Icarus adapter (reported not installed, so the
       outcome does not depend on the machine), and a generated result (§11).
       No HDL simulator runs, so no metric is parsed from a tool's output.
4. **Electrical**: ngspice supply sample; output capture and metric parsing;
   version parsing; `spice` CI job. First artefact-first domain; the protocol
   stops being provisional here, and the PR lists every protocol change the
   domain forced with the matching change to the mechanical adapter
   (SCOPE-15). Each item is marked with its state on `feat/domain-electrical`
   (code at `37b2de7`, plus the docstring fix of the documentation commit
   that carries this text), as run on macOS arm64 with ngspice-47, and as
   the review fixes `57f4fee` and `f6dee36` left it where an item names
   them. One verification pass by a separate agent, at `816e625`, found no
   blocking problem and one gap, fixed in `57f4fee`; the fixes have had no
   review of their own (`CLAUDE.md` rule 4):
   - ngspice supply sample, `datasets/cad/servo_supply_001` — IMPLEMENTED:
     `check`, `build` and `validate` on a clean copy give V0–V3 `PASS` and
     V4 `BLOCKED` as designed (`docs/electrical-domain-v1.md`, Example); so
     do the `spice` job's steps at `f6dee36` in arm64 Linux containers on
     ngspice-36 and 44.2; the run on the x86_64 runner is NOT RUN;
   - output capture and metric parsing (ARCH-2, the ngspice half) —
     IMPLEMENTED; the `run_process` output copy is not needed by ngspice and
     stays PLANNED for items 5 and 6;
   - version parsing (RESULT-8) — IMPLEMENTED; RESULT-2 — PARTIAL, the
     ngspice path only (the general fix is item 1);
   - `spice` CI job — PARTIAL: written, placed and tested
     (`test_spice_job_cannot_skip_silently`), never run on a runner; its
     steps pass in the arm64 containers above, after `f6dee36` fixed the
     real-ngspice test that ngspice-36's progress report on stderr failed;
     pinning ngspice — BLOCKED on the runner's unknown version (§20 Q16);
   - the protocol stops being provisional, with the change list (SCOPE-15)
     — IMPLEMENTED (§11);
   - the §10 list: a sample — IMPLEMENTED; a met limit — IMPLEMENTED as
     `WARNING` against illustrative limits, and as `PASS` against a real
     requirement only on a test-built copy with a fixture rating, since no
     real part is selected; a `FAIL` from a mutated input — IMPLEMENTED
     (test-built copies, real ngspice); a `BLOCKED` from a missing input —
     IMPLEMENTED (the committed sample); an invalid-input and a boundary
     sample — PARTIAL: test-built copies, not committed items (§20 Q17);
     negative tests — IMPLEMENTED; mutants — IMPLEMENTED: 322 at
     `ec37115`; the 101 of the electrical branch killed there after green
     baselines, the other 221 last run at `57f4fee` (§16);
     per-domain documentation (spec §28) — IMPLEMENTED; a CI job that makes
     a skip a failure — PARTIAL, as above;
   - part-rating checks that can pass, steady ripple, the fuse's I²t
     against a real part — BLOCKED on data: no part is selected, and the
     eServo-200 sheet states neither the drive's input ripple current nor its
     switching frequency;
   - the SEC-2 runner guard — PLANNED, its own foundation change (§7.2);
   - other elements, sources, analyses and topologies; scenario parameters;
     a KiCad schematic importer; LTspice and PSpice — PLANNED;
   - the dataset move (Q8) — not done: the brief kept the layout.
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
hashes, followed by a Linux reproduction run. The electrical change (item 4)
did not make it: its brief kept the layout, and the move waits for the
maintainer's Q8 decision.
