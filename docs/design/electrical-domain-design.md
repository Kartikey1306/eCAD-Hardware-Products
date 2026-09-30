> **Status of this document.** This is the design the electrical domain was
> built from, written before any code (2026-09-27): three independent designs,
> each with a different priority (the smallest change, data honesty, reuse by
> later domains), scored by a fourth reviewer who checked their claims against
> the code and ngspice and wrote this synthesis. It is kept as the record of what
> was decided and why, not as a description of the code. Where the
> implementation departs from it, the decision and its reason are in
> `MEMORY.md` (for example: `MAX_PWL_POINTS` is 16, node names carry an `n_`
> prefix, and a tenth metric, `startup_peak_current_a`, was added after the
> branch review). The code, `docs/electrical-domain-v1.md` and `TASKS.md` T-012
> describe what exists and what verified it. The scratch evidence the design
> cites (`design-scratch/...`) was produced on a local machine and is not in the
> repository; what the implementation relies on is re-checked by its tests and
> by the commands recorded in T-012, not by that scratch evidence.

# Electrical domain design (final): `servo_supply_001` on ngspice

**Mode:** Architecture. This is a design. Nothing is implemented. The worktree
`wt-electrical` (`feat/domain-electrical` at `042f934`) was only read:
`git status --short` shows 0 lines (**Verified**, 2026-09-27).

**Evidence labels** follow `CLAUDE.md`. **Verified** means I ran it on this
machine on 2026-09-27: ngspice-47 at `/opt/homebrew/bin/ngspice`, macOS arm64,
CPython 3.14. Scratch evidence is under
`design-scratch/synth/final/` (the root is
a local scratch directory that is not part of the repository):

| File | What it holds |
|---|---|
| `servo_supply_001.cir` | the source netlist of §1.2, byte for byte |
| `deck.cir` | the deck of §4.2, byte for byte |
| `run1.out`, `run2.out`, `run*.err` | two ngspice-47 runs of the deck: identical stdout, empty stderr |
| `cf.py` | independent closed forms of §5 |
| `gen.py`, `sens.py` | the variant decks and the writer-error sensitivity of §5.4 |
| `rpre1_f.*`, `early_f.*` | the FAIL copies of §6.4 |
| `proto_parse.py` | a scratch prototype of the §3 grammar (not repository code) |
| `probes/` | the ngspice behaviour probes of §3.1 and §7 |

**Base design:** the *minimal* design. Its architecture is kept: one self-contained
testbench netlist, one deck, scenarios as windows of one transient, and one
protocol change.

**Grafts:**
- **From the *extensible* design:** the bypassed precharge circuit, uppercase
  designators with lowercase nodes, the declared-name `.meas` parser, the
  stand-in ngspice for the fast matrix, and exact boundary tests.
- **From the *honesty* design:** `.options noacct`, the UNSPECIFIED sheet
  facets, the facet-unit vocabulary check, and receipt-safe probe reasons on
  the ngspice path.

Every conflict is resolved in §0.3.

---

## 0. Assessment of the three designs

### 0.1 Scores (1-10)

| Criterion | minimal | honesty | extensible |
|---|---|---|---|
| Correctness against the code | 8 | 6 | 6 |
| Data honesty | 9 | 9 | 8 |
| Completeness against the plan's per-domain list | 8 | 9 | 8 |
| Testability (verdict paths reachable, killable mutants) | 8 | 7 | 8 |
| Minimal blast radius on merged code | 9 | 4 | 4 |
| Usefulness to later domains | 6 | 8 | 8 |
| **Total** | **48** | **43** | **42** |

**minimal (48).**
- Citations are accurate. It gets two things right that the others miss:
  - it places the CI job so the existing slice test stays exact;
  - it knows that a dataset mutant which breaks the build is a `HARNESS`
    result, not a kill.
- Its protocol change is the only one the domain forces, and it touches the
  fewest files.
- It loses points for:
  - a fixed 1 Ω limiter that dissipates about 20 W and drops the bus 4.5 V in
    steady state (its own open question);
  - no power metric (spec §7 lists "power");
  - one false `measured_by` claim (§0.2).

**honesty (43).**
- It has the best data discipline: UNSPECIFIED facets for what the sheet is
  silent on, a facet-unit vocabulary, and power and energy metrics.
- It loses points for:
  - five protocol changes and a runner guard;
  - a change to ngspice's verdict mapping that the plan does not name;
  - several false claims (§0.2).

**extensible (42).**
- It has the best circuit (a bypassed precharge), full closed forms including
  the charge time and i²t, a stand-in simulator, and exact boundary tests.
- It loses points for:
  - a per-sample README that breaks `check`;
  - a breaking `case_target` signature change whose results-side call site is
    not listed;
  - a CI placement that weakens an existing test;
  - letting a new adapter silently fall back to the builder as producer.

### 0.2 Claims in the designs that are false against the code or the tool

| # | Design | Claim | What is true |
|---|---|---|---|
| F1 | minimal | "REQ-EL-003 borrows `bus_peak_voltage_v` from `v3.REF-EL-002`" | It borrows from `v3.REF-EL-001`. Every case runs the same deck, so every check's `metrics` holds all five values: the case engine stores the adapter's whole metric dict (`cases.py:482`). The borrow loop takes the first check in sorted order whose case has equal arguments (`results.py:297-306`). **Observed.** |
| F2 | honesty | REQ-ELEC-004/-005/-006/-007 measured by REF-ELEC-002/-004/-005/-007 | Same loop, even with its P3. The four startup metrics are borrowed from `v3.REF-ELEC-001`, the steady one from `v3.REF-ELEC-006`. Only REQ-ELEC-008 → REF-ELEC-009 is right. |
| F3 | honesty | mutant `provenance-domain-mutated` is "killed by electrical #1" | A dataset mutant is rebuilt first (`run_mutations.py:450-458`). With domain `mechanical` the rebuild fails (the mechanical adapter needs exactly one STEP source, `mechanical.py:271-275`), so the harness reports `HARNESS`, never `KILLED`. |
| F4 | honesty | an `AI_ASSUMPTION` `value_basis` on netlist values gives `INCONCLUSIVE` | Its values carry source kind `design_annotation`. `common.schema.json:117-118` requires kind `ai` for `AI_ASSUMPTION`, so the model is schema-invalid and V1 says `DATASET_INPUT_INVALID`. |
| F5 | extensible | a per-sample `README.md` in the item | `integrity()` reports every committed file the manifest does not record (`dataset.py:640-643`), so `check` fails. |
| F6 | extensible | P2 "case documents byte-identical", with its other call sites listed | `results.py:297` calls `adapter.case_target(sample_id).arguments(...)`. The P2 signature change breaks it, and that site is not in the "Other files that change" list. |
| F7 | honesty, extensible | (implicitly) the `spice` job goes after `cad-dataset` | `test_ci_and_runner.py:59-61` slices the text from `cad-dataset:` to `release:`. A job placed between them joins that slice, so the existing test would pass on the spice job's lines. |
| F8 | extensible, honesty | the declared-`.meas` regex accepts `op` (and `sp`, `noise`) | ngspice-47 rejects `.meas op`: "unrecognized analysis type 'op'" (**Verified**, `probes/milli.cir`). |
| F9 | minimal | "written without the walrus operator … for Python 3.10 style" | `:=` is valid from Python 3.8, so this is not a constraint. Harmless. |
| F10 | extensible | "ngspice drops an invalid element line with only a warning" | Partly true. A malformed `R2 a` is ignored with a warning and exit 0, but `Q9 a` exits 1 (**Verified**, `probes/bad*.cir`). |

Minor line-number slips, none load-bearing:
- the doctest list is at `test_engineering_model.py:1210`, not 1216;
- the parts-slice is at `run_mutations.py:454`, not 452.

The following claims were checked and hold (**Verified** on ngspice-47, or
**Observed** in the code):
- `-r` disables `.meas` in batch mode, and `-o` moves the results into a log
  that `run_process` deletes.
- A failed `.meas` goes to stderr and the exit code is 0.
- A duplicated `.meas` name is printed twice.
- `1M` is milli, `1MEG` is mega, `10uF` is 10 µ, `10F` is femto (clamped with a
  warning), and `2kohm` is 2 k.
- `gnd` is ground.
- An element after `.end` is parsed, and a missing `.end` is accepted.
- `+` continuation merges lines, and a card on the title line vanishes.
- `.control`/`shell` runs under `-b`; a `.spiceinit` in the working directory
  runs, and `-n` stops it.
- `numdgt` does not change `.meas` digits.
- `noacct` makes stdout identical run to run.
- The banner's first line is `******`.
- Adapter enum, schema lines, the ENGINE-1 path, and the README/integrity rule
  are as cited.

**New finding (Verified, `probes/pa*.cir`).** `par()` in a `.meas` makes ngspice
create nodes `pa_00`, `pa_01`, …. A netlist node with that name is hijacked:
1 V across 2 Ω read as 1.0 A instead of 0.5 A. None of the three designs
refuses such names, and §3.1 does.

### 0.3 Decision log (where each decision came from, and what was rejected)

| # | Decision | From | Rejected alternatives and why |
|---|---|---|---|
| D1 | One self-contained testbench netlist. Scenarios are windows of one ngspice transient, so a scenario carries only its name. | minimal | Per-scenario decks written at build time (honesty P1/P2, extensible P1/P2). They force two or three protocol changes, and a breaking `case_target` signature in extensible's case. Nothing in this sample needs scenario parameters, and QUALITY.md says not to abstract for a second case that does not exist. They are PLANNED: a later domain that needs them adds `CaseTarget.scenario_inputs` (honesty's additive form). |
| D2 | Circuit: fuse resistance → precharge resistor ∥ ideal bypass switch → bus with C + ESR, a constant-current 200 W/48 V load, and a fault switch. All are in the netlist, sequenced by PWL sources. | extensible (circuit) + minimal (fault injector in the netlist) | minimal's fixed 1 Ω limiter: steady bus 43.4 V and about 20 W lost in the limiter. honesty's `.subckt` DUT with generated test benches: needs hierarchy in the parser and the writer, and D1 rejects its per-scenario benches. |
| D3 | The netlist is the source of truth, read by a strict allow-list parser in `ecad_model/spice.py`. ngspice only ever sees a deck regenerated from the model. | all three | A JSON circuit plus a generator: the parser's refusals would never run on the real input. `importers/spice.py`: `importers/` is the content-signature CAD layer, and SPICE has no signature (FACT-6). |
| D4 | Uppercase designators and lowercase nodes; lowercase scale suffixes only (`t g meg k m u n p`). Refused: `f`, uppercase suffixes, trailing letters, `mil`, `gnd` and `pa_N` nodes. | extensible (case rule, `f`), synthesis (`pa_N`) | minimal's lower-cased designators: its own prototype accepted `20M`. |
| D5 | Topology lives in the model: `components[].circuit` = `{designator, element, terminals{p,n[,cp,cn]}, model?}`. Nets and rails are derived, not stored. There is no extraction file. This amends plan §8.2 (ARCH-1). | minimal (placement, no extraction file) + extensible (named terminals, designator) | honesty's top-level `circuit` with `nets`, `ports` and `rails`: two sources of truth for connectivity. An extraction file (`netlist.json`): a V2 comparison of two outputs of one deterministic parse. `design.power_rails` (extensible): the network class already fixes the rail; PLANNED for a second rail. |
| D6 | A compatible addition raises the in-document minor version, and the schema enforces it: `model_version` and `annotations_version` accept `1.0.0` and `1.1.0`, and `1.1.0` is required when a circuit member, a new kind or `circuit_elements` is present. | minimal (model), extended here to annotations | Keeping `1.0.0` (honesty, and extensible's open Q-E1): a 1.0.0 reader would be handed members its closed schema refuses. |
| D7 | Protocol change: `Extraction.producer: Tuple[str, str]`, required with no default. The protocol is then declared stable. | minimal | extensible's `Optional` default, which silently falls back to the builder. honesty's `model_producer` class attribute: the producer belongs to what produced *this* model. |
| D8 | ARCH-2: `ngspice -b <deck>`. `.meas` results are read from stdout for the names the deck declares, with a strict number grammar. Truncated output → `INCONCLUSIVE`, no metrics. Exit ≠ 0 stays `FAIL TOOL_EXITED_NONZERO`. `run_process` is unchanged. | minimal + extensible (declared names, number pre-check) + honesty (truncation withholds all) | honesty's exit≠0 → `INCONCLUSIVE`: not named by ARCH-2, and inconsistent with `python_control.py:56-57`. It is left as an open question. minimal's "a duplicate withholds every metric": broader than needed, since each comparator reads only its own metric. |
| D9 | The deck carries `.options noacct`: stdout is byte-identical run to run and has no statistics lines. Numerical options stay at the defaults, with a fixed `TMAX` of 1 µs. | honesty (`noacct`) | honesty's `reltol=1e-06 abstol=1e-12 vntol=1e-09`: it changed the one measurable i²t by 1e-7 only (**Verified**), and it is a second setting to validate across ngspice versions. |
| D10 | RESULT-8: an ngspice-only `VERSION_PATTERNS` inside `probe_executable`. No match → version `None`, and the existing policy turns a PASS into `BLOCKED TOOL_VERSION_UNAVAILABLE`. RESULT-2 is fixed on the ngspice path only, in `ngspice.py`. | minimal (RESULT-8), honesty (RESULT-2 local) | honesty's `VERSION_UNRECOGNISED` (unavailable): a new policy where the spec says to follow the existing one. Fixing RESULT-2 inside `probe_executable`: it would change kicad/iverilog/mujoco error paths, which the brief forbids. Stacking on the unwritten `fix/version-probe-reason-codes` (minimal): it would block this PR on work nobody has scheduled. |
| D11 | 9 metrics, all `SIMPLIFIED`, each with a V3 closed form. Tolerances are at least 8× the measured deviation on the committed sample and on the FAIL copy. A 1% capacitance error is caught. | extensible (forms) + honesty (power metric) + synthesis (measured tolerances, TMAX) | minimal's five metrics: they cannot see a 1% error in C. |
| D12 | V4: 4 illustrative limits (`WARNING`) and 3 rating limits `BLOCKED` on `UNKNOWN` part ratings. The FAIL, boundary, AI and PASS paths come from test-built copies. | all three | Committing invalid or boundary items: left open (§13 Q-E3). |
| D13 | The runner guard (a committed case document runs only if the fresh derivation vouches for every execution in it) is **not** in this PR. It is specified as defect SEC-2 for its own PR (§13.1). | minimal (defer) | honesty R1 / extensible P5 inside this PR. It narrows the recorded decision at `MEMORY.md:66` for every domain, and it must replicate the engine's pre-execution refusals to avoid changing existing ENGINE-1 assertions. Plan R5 already names SPICE `.control` under SEC-1. |
| D14 | The CI `spice` job goes **between** `validation-evidence` and `cad-dataset`. A stand-in ngspice built from recorded ngspice-47 output lets all nine matrix legs run the sample's receipt. | minimal (placement), extensible (stand-in) | Placing it after `cad-dataset` (F7). |
| D15 | `.gitattributes`: `-text` for `datasets/cad/**`, `LICENSE` and the cited product sheet. | minimal + honesty | Only the new sample: `LICENSE` and the sheet are hash-cited, and the electrical sample is the first cited-hash check that runs on Windows legs. |
| D16 | The layout stays `datasets/cad/<id>/`. | the brief | Plan §21 says the Q8 move goes with the first non-mechanical sample. The brief overrides it (`CLAUDE.md` precedence 1), and the conflict is recorded here and in the plan. |
| D17 | LTspice and PSpice: PLANNED only, with no adapter and no stub. | the brief | — |

---

## 1. Sample

### 1.1 Identity and layout

- **Sample id / `design_id`:** `servo_supply_001`.
- **Directory:** `datasets/cad/servo_supply_001/`. The layout is kept (D16).
  The mutation harness takes the item from `Path(relative).parts[:3]`
  (`run_mutations.py:454`).

| Path | Written by | Role |
|---|---|---|
| `source/provenance.json` | hand | licence, origin, domain `electrical`, artefact `source/servo_supply_001.cir` in format `spice` |
| `source/servo_supply_001.cir` | hand | **source of truth** (§1.2) |
| `design/annotations.json` | hand | element names, kinds and ratings (`UNKNOWN`); the eServo-200 drive; one relationship |
| `requirements/requirements.json` | hand | 9 references, 7 requirements (§6) |
| `derived/engineering_model.json` | `build` | model format 1.1.0 |
| `derived/electrical/servo_supply_001.cir` | `build` | the deck ngspice runs (§4.2) |
| `validation/golden/cases.json` | `build` | 9 V3 cases |
| `validation/corners/cases.json` | `build` | 4 V4 cases; 3 are blocked at compile time (`requirements.py:151-162`) |
| `dataset-item.json` | `build` | manifest |

**Deliberately absent:**
- **`simulation/`:** `simulation_files()` returns `[]`, so `versions.simulation`
  is `sha256:e3b0c442…b855`, the digest of an empty script set (documented).
- **A per-sample README (F5):** the row lives in `datasets/cad/README.md`.
- **A `generator` key:** nothing generates the netlist.

### 1.2 The netlist, exactly (LF only, ASCII)

The scratch copy is 1300 bytes, sha256
`838cde196936a321bdca5e41eca4a91902b4ee0a8f1fe8dcc86401a7a3ef3344`
(**Verified**, `synth/final/servo_supply_001.cir`).

```spice
servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load
* Self-authored for the eCAD multi-domain validation pipeline (issue #27).
* No element is a real part: every value below is a design choice of this
* testbench, not a rating, measurement or datasheet value of any component.
* The 48 V supply and the 200 W load come from the eServo-200 product sheet
* (eRobotics_CAD_Design/robot_components/product_datasheet.md). I_LOAD is
* 200 W / 48 V written to six significant figures: a constant-current
* stand-in for the drive's input. R_F1 is a fuse's cold resistance only; it
* never opens. S_BYP is an ideal switch standing for the precharge bypass.
* S_FLT is a testbench fault injector: it shorts the bus through 100 mohm.
* Sequence: hot plug 0 -> 48 V in 100 us; bypass closes at 30 ms; the load
* steps on at 40 ms; the bus is shorted at 100 ms.
V_IN n_in 0 PWL(0 0 100u 48)
R_F1 n_in n_f 20m
R_PRE n_f n_bus 10
S_BYP n_f n_bus n_byp 0 SW_BYP
V_BYP n_byp 0 PWL(0 0 30m 0 30.001m 5)
C_BULK n_bus n_esr 470u
R_ESR n_esr 0 50m
I_LOAD n_bus 0 PWL(0 0 40m 0 40.1m 4.16667)
S_FLT n_bus 0 n_fc 0 SW_FLT
V_FLT n_fc 0 PWL(0 0 100m 0 100.001m 5)
.model SW_BYP SW(RON=10m ROFF=1g VT=2.5 VH=0)
.model SW_FLT SW(RON=100m ROFF=1g VT=2.5 VH=0)
.end
```

Run on its own, ngspice exits 1 with "no simulations run" (**Verified**,
`src.err`): the file describes the circuit and holds no analysis.

### 1.3 `source/provenance.json`

```json
{
  "$schema": "https://embeddedos.org/schemas/cad-dataset/v1/source-provenance.schema.json",
  "provenance_version": "1.0.0",
  "domain": "electrical",
  "artifacts": [{"path": "source/servo_supply_001.cir", "format": "spice"}],
  "description": "48 V servo-drive supply input testbench: hot-plug supply, fuse F1 as its cold resistance, precharge resistor with an ideal bypass switch, bulk capacitor with series resistance, a constant-current stand-in for the eServo-200 drive, and a fault switch that shorts the bus. No element is a real part. Authored for the eCAD multi-domain validation pipeline (issue #27).",
  "artifact_type": "spice_netlist",
  "artifact_version": "1.0",
  "units": "SI (V, A, ohm, F, s) with lowercase SPICE scale suffixes t g meg k m u n p",
  "coordinate_system": "none (a netlist has no geometry)",
  "created_at": "<YYYY-MM-DD: the day the netlist is written>",
  "collected_at": "<the same day>",
  "origin": {"kind": "self_authored", "author": "EmbeddedOS (EoS) Research Foundation"},
  "license": {
    "spdx": "MIT",
    "attribution": "Copyright (c) 2024-2026 EmbeddedOS (EoS) Research Foundation",
    "license_verified": true,
    "license_text": {"path": "LICENSE", "sha256": "2779b5d4987171210e3c18f461e4ee832426c3c52ca3e53a7dce23af057c4c0a"},
    "redistribution_permitted": true,
    "training_use_permitted": true,
    "basis": "hand-written in this repository as source/servo_supply_001.cir and committed under the repository's MIT LICENSE; contains no third-party model, library or part data"
  }
}
```

- `spice_netlist` is already in the `artifact_type` enum
  (`source-provenance.schema.json:50`), and `format` is an open identifier.
- The `LICENSE` digest matches (**Verified**, `shasum -a 256`).
- The two dates are the real authoring date, written at commit time. They are
  not supplied here, because a date nobody observed is invented.

### 1.4 `design/annotations.json`

```json
{
  "$schema": "https://embeddedos.org/schemas/engineering-model/v1/design-annotations.schema.json",
  "annotations_version": "1.1.0",
  "design_id": "servo_supply_001",
  "materials": {}, "parts": {}, "joints": [], "attachments": [],
  "circuit_elements": {
    "V_IN":   {"name": "hot-plug supply: 0 to 48 V in 100 us (testbench stimulus)", "kind": "voltage_source"},
    "R_F1":   {"name": "F1 input fuse, modelled by its cold resistance only (no fuse is selected; it never opens)", "kind": "fuse",
               "domains": {"electrical": {"current_rating": U_A_FUSE, "melting_i2t": U_I2T_FUSE, "breaking_capacity": U_BC_FUSE}}},
    "R_PRE":  {"name": "R1 precharge resistor (no resistor is selected)", "kind": "resistor",
               "domains": {"electrical": {"power_rating": U_W_RES, "pulse_energy_rating": U_J_RES}}},
    "S_BYP":  {"name": "Q1 precharge bypass, an ideal voltage-controlled switch (no relay or MOSFET is selected)", "kind": "switch",
               "domains": {"electrical": {"current_rating": U_A_SW}}},
    "V_BYP":  {"name": "precharge controller's bypass command, 0 to 5 V at 30 ms (testbench stimulus)", "kind": "voltage_source"},
    "C_BULK": {"name": "C1 bulk capacitor, ideal apart from R_ESR (no capacitor is selected)", "kind": "capacitor",
               "domains": {"electrical": {"voltage_rating": U_V_CAP, "ripple_current_rating": U_A_CAP}}},
    "R_ESR":  {"name": "C1 series resistance: a design value, not a datasheet ESR", "kind": "resistor"},
    "I_LOAD": {"name": "constant-current stand-in for the eServo-200 drive input, 200 W / 48 V from 40 ms (testbench stimulus)", "kind": "current_source"},
    "S_FLT":  {"name": "fault injector: shorts the bus through 100 mohm at 100 ms (testbench only)", "kind": "switch"},
    "V_FLT":  {"name": "fault injector command (testbench only)", "kind": "voltage_source"}
  },
  "components_without_cad": [ DRIVE ],
  "relationships": [{"relation": "powered_by", "from": "drive", "to": "v_in"}]
}
```

**The `UNKNOWN` facets.** Each `U_*` placeholder above is:

```json
{"value": null, "unit": "<unit>", "status": "UNKNOWN",
 "source": {"kind": "design_annotation", "ref": "datasets/cad/servo_supply_001/design/annotations.json"},
 "note": "<note>"}
```

| Placeholder | Unit | Note |
|---|---|---|
| `U_A_FUSE` | `A` | no fuse is selected, so no current rating exists to check against |
| `U_I2T_FUSE` | `A^2*s` | no fuse is selected, so no melting I2t exists to check against |
| `U_BC_FUSE` | `A` | no fuse is selected, so no breaking capacity exists to check against |
| `U_W_RES` | `W` | no resistor is selected |
| `U_J_RES` | `J` | no resistor is selected |
| `U_A_SW` | `A` | no bypass device is selected |
| `U_V_CAP` | `V` | no capacitor is selected, so no voltage rating exists to check against |
| `U_A_CAP` | `A` | no capacitor is selected |

**`DRIVE`** is the `drive` entry of `robotic_joint_001/design/annotations.json`:
- component id `drive`, name "eServo-200 EtherCAT servo drive", kind `motor_driver`;
- its `supply_voltage` 48.0 V, `rated_current` 5.0 A (with the existing note
  that the sheet does not say continuous or peak) and `rated_power` 200.0 W,
  all `SPECIFIED`, source `product_specification`, ref
  `eRobotics_CAD_Design/robot_components/product_datasheet.md`, sha256
  `f6e4502a3a93112aab7fcd91c9c9242c1227cde8d21c6614dabbab2291094f8c`
  (**Verified** current).

It gains two `UNSPECIFIED` electrical facets. Each cites the same sheet by hash,
which `common.schema.json:103-107` requires:
- `input_ripple_current` (A): note "the sheet does not state the drive's input
  ripple current".
- `switching_frequency` (Hz): note "the sheet gives a 20 kHz current-loop
  bandwidth, which is not a switching frequency".

These two record why the plan's "steady ripple" check is `BLOCKED` on data
(from honesty). The drive's `control/current_loop_bandwidth` is not copied:
nothing electrical reads it.

### 1.5 Every input value, with its status and source

Nothing below is invented.
- Netlist values are `SPECIFIED`, source
  `{"kind": "design_annotation", "ref": "datasets/cad/servo_supply_001/source/servo_supply_001.cir", "sha256": "<netlist sha256>"}`,
  with the note "<DESIGNATOR> <parameter> in the netlist: a design choice of
  this self-authored testbench, not a rating, measurement or datasheet value of
  any part".
- "sheet" means `product_specification` citing the sheet by hash.

| Model path (`components/<id>/domains/electrical/…`) | Value | Status | Source |
|---|---|---|---|
| `v_in/waveform_time`, `waveform_voltage` | [0, 1e-4] s; [0, 48] V | SPECIFIED | netlist (48 V is written in from the sheet, as the comment says) |
| `r_f1/resistance` | 0.02 Ω | SPECIFIED | netlist |
| `r_pre/resistance` | 10.0 Ω | SPECIFIED | netlist |
| `s_byp/on_resistance`, `off_resistance`, `threshold_voltage`, `hysteresis_voltage` | 0.01 Ω, 1e9 Ω, 2.5 V, 0.0 V | SPECIFIED | netlist `.model SW_BYP` |
| `v_byp/waveform_time`, `waveform_voltage` | [0, 0.03, 0.030001] s; [0, 0, 5] V | SPECIFIED | netlist |
| `c_bulk/capacitance` | 4.7e-4 F | SPECIFIED | netlist |
| `r_esr/resistance` | 0.05 Ω | SPECIFIED | netlist |
| `i_load/waveform_time`, `waveform_current` | [0, 0.04, 0.0401] s; [0, 0, 4.16667] A | SPECIFIED | netlist (the designer's 200 W / 48 V; the sheet does not say input or output power) |
| `s_flt/…` (4 switch facets) | 0.1 Ω, 1e9 Ω, 2.5 V, 0.0 V | SPECIFIED | netlist `.model SW_FLT` |
| `v_flt/waveform_time`, `waveform_voltage` | [0, 0.1, 0.100001] s; [0, 0, 5] V | SPECIFIED | netlist |
| `r_f1/current_rating`, `melting_i2t`, `breaking_capacity` | null | UNKNOWN | annotations |
| `r_pre/power_rating`, `pulse_energy_rating` | null | UNKNOWN | annotations |
| `s_byp/current_rating` | null | UNKNOWN | annotations |
| `c_bulk/voltage_rating`, `ripple_current_rating` | null | UNKNOWN | annotations |
| `drive/supply_voltage`, `rated_current`, `rated_power` | 48 V, 5 A, 200 W | SPECIFIED | sheet |
| `drive/input_ripple_current`, `switching_frequency` | null | UNSPECIFIED | sheet |
| Method constants (§4.1) | — | not quantities | `domains/electrical.py` `VERSION`, recorded in the hash-bound deck |
| Illustrative limits (§6) | — | requirement, `illustrative: true` | `requirements.json` |

The unknowns index has 10 entries (8 UNKNOWN, 2 UNSPECIFIED), each with
`needed_by: ["electrical"]` (`builder.py:393-399`). Nothing is MEASURED,
SIMULATED, ESTIMATED, DERIVED or AI_ASSUMPTION.

---

## 2. Engineering model

### 2.1 How each spec §7 concept is represented

| Spec §7 | Where |
|---|---|
| Circuit | The model of a sample whose primary domain is `electrical`. `design`: `design_id`, `name` = the netlist title, `revision` "1.0", `sources: [{path: <repo path of the .cir>, format: "spice", sha256}]`, no `gravity`. |
| Component | One `components[]` entry per netlist element, plus `drive`. `component_id` = the designator in lower case. `cad_ref`, `material`, `geometry`, `physical` and `placement` are `null` (`engineering-model.schema.json:84` requires them; they are nullable). |
| Component type | `kind` (new values `fuse resistor capacitor switch voltage_source current_source`) and `circuit.element` (`resistor capacitor voltage_source current_source voltage_controlled_switch`) |
| Node, connectivity | `circuit.terminals`: `p`, `n`, plus `cp` and `cn` for a switch → node name, with `"0"` as ground |
| Net | Derived by readers: the terminals that name one node. Not stored. |
| PowerRail, Input, Output | The roles of the supported network class (§3.3): the supply is the Input; the rail `n_bus` and the load are the Output. PLANNED as stored fields when a second rail or a PCB rule needs them. |
| resistance, capacitance | facets `resistance` [ohm], `capacitance` [F] |
| Sources and switches | `waveform_time` [s] plus `waveform_voltage` [V] or `waveform_current` [A], as vectors (`common.schema.json:60-70` allows 1-D arrays); `on_resistance`, `off_resistance` [ohm]; `threshold_voltage`, `hysteresis_voltage` [V]; `circuit.model` keeps the `.model` name |
| ComponentRating | rating facets from the annotations: `voltage_rating` [V], `current_rating` [A], `power_rating` [W], `melting_i2t` [A^2*s], `breaking_capacity` [A], `pulse_energy_rating` [J], `ripple_current_rating` [A] |
| inductance | PLANNED: `L` elements are refused |

**Example component:**

```json
{"component_id": "s_byp", "name": "Q1 precharge bypass, an ideal voltage-controlled switch (no relay or MOSFET is selected)",
 "kind": "switch", "cad_ref": null, "material": null, "geometry": null, "physical": null, "placement": null,
 "circuit": {"designator": "S_BYP", "element": "voltage_controlled_switch", "model": "SW_BYP",
             "terminals": {"p": "n_f", "n": "n_bus", "cp": "n_byp", "cn": "0"}},
 "domains": {"electrical": {
   "on_resistance": {"value": 0.01, "unit": "ohm", "status": "SPECIFIED", "source": NETLIST,
                     "note": "S_BYP on_resistance in the netlist: a design choice of this self-authored testbench, not a rating, measurement or datasheet value of any part"},
   "off_resistance": {"…": "…"}, "threshold_voltage": {"…": "…"}, "hysteresis_voltage": {"…": "…"},
   "current_rating": {"value": null, "unit": "A", "status": "UNKNOWN", "source": ANNOTATIONS, "note": "no bypass device is selected"}}}}
```

**Ordering.** Components follow netlist order, then `drive`.

**Relationships:**
- `contains`, from `design_id` to each circuit component, with the netlist as
  source (like the builder's `contains` for CAD parts);
- the annotation's `drive powered_by v_in`, with the annotations as source.

`index_unknowns`, `resolve`, `input_leaves` and lineage need no change. The
`circuit` member holds no quantities, so the walks skip it (**Observed**,
`builder.py:421-436`, `results.py:88-99`).

### 2.2 Schema changes (all compatible, all in v1)

**`schemas/engineering-model/v1/engineering-model.schema.json`:**

1. **`model_version`** changes from `{"const": "1.0.0"}` (line 21) to
   `{"enum": ["1.0.0", "1.1.0"]}`.
2. **The component `kind` enum** (lines 88-104) gains `fuse`, `resistor`,
   `capacitor`, `switch`, `voltage_source` and `current_source`.
3. **An optional `"circuit": {"$ref": "#/definitions/circuit"}`** on
   `component`. It is not added to `required` (line 84).

   ```json
   "circuit": {
     "type": "object", "additionalProperties": false, "required": ["designator", "element", "terminals"],
     "properties": {
       "designator": {"type": "string", "pattern": "^[RCVIS][A-Z0-9_]{1,31}$"},
       "element": {"enum": ["resistor", "capacitor", "voltage_source", "current_source", "voltage_controlled_switch"]},
       "model": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,31}$"},
       "terminals": {"type": "object", "propertyNames": {"enum": ["p", "n", "cp", "cn"]},
                     "additionalProperties": {"type": "string", "pattern": "^(0|(?!gnd$)(?!pa_[0-9]+$)[a-z][a-z0-9_]{0,31})$"}}},
     "allOf": [
       {"if": {"properties": {"element": {"const": "voltage_controlled_switch"}}},
        "then": {"required": ["model"], "properties": {"designator": {"pattern": "^S"}, "terminals": {"required": ["p", "n", "cp", "cn"]}}},
        "else": {"not": {"required": ["model"]}, "properties": {"terminals": {"required": ["p", "n"], "maxProperties": 2}}}},
       {"if": {"properties": {"element": {"const": "resistor"}}}, "then": {"properties": {"designator": {"pattern": "^R"}}}},
       {"if": {"properties": {"element": {"const": "capacitor"}}}, "then": {"properties": {"designator": {"pattern": "^C"}}}},
       {"if": {"properties": {"element": {"const": "voltage_source"}}}, "then": {"properties": {"designator": {"pattern": "^V"}}}},
       {"if": {"properties": {"element": {"const": "current_source"}}}, "then": {"properties": {"designator": {"pattern": "^I"}}}}]}
   ```
4. **A top-level `allOf` rule:** a component with a circuit member, or with a
   new kind, requires format 1.1.0.

   ```json
   {"if": {"properties": {"components": {"contains": {"anyOf": [{"required": ["circuit"]},
          {"required": ["kind"], "properties": {"kind": {"enum": ["fuse", "resistor", "capacitor", "switch", "voltage_source", "current_source"]}}}]}}}},
    "then": {"properties": {"model_version": {"const": "1.1.0"}}}}
   ```

**`schemas/engineering-model/v1/design-annotations.schema.json`:**

- `annotations_version` becomes `{"enum": ["1.0.0", "1.1.0"]}`.
- An optional `circuit_elements` object:
  - keys match `^[RCVIS][A-Z0-9_]{1,31}$`;
  - each value is closed: `{name, kind, note?, domains?: {electrical?: facet, thermal?: facet}}`;
  - `kind` ∈ `fuse resistor capacitor switch voltage_source current_source other`.
- An `allOf` rule: `circuit_elements` present ⇒ `annotations_version` const `"1.1.0"`.

**New `schemas/engineering-model/v1/electrical-vocabulary.schema.json`.** It
mirrors `mechanical-vocabulary.schema.json`:
- `scenarios`: items `{"name": {"enum": ["startup", "steady_state", "output_short"]}}`
  with `additionalProperties: false`;
- `derivations`: items from the enum of the nine names in §5.1.

**Unchanged:** `common.schema.json` (the source kinds, statuses and vector
values needed all exist), engineering-requirements, validation-results,
cad-dataset/v1 (dataset-item, source-provenance), and hardware-validation/v1.
The cases adapter enum already has `ngspice` (`validation-cases.schema.json:48`),
so Q9 is not triggered.

### 2.3 Versioning (plan §9.3)

**The rule (D6), written into the docs' Versioning section:** "a compatible
addition to a document format raises that document's minor version; the v1
schema accepts every minor version of v1, and requires the new one for a
document that uses the addition."

**Versions after this PR:**
- `ecad_model.MODEL_VERSION` stays "1.0.0", since the builder writes no new member.
- A new `ecad_model.CIRCUIT_MODEL_VERSION = "1.1.0"` is written by the
  electrical adapter.
- The mechanical model, annotations and manifest stay byte-identical, except
  the manifest's one domain-status entry (§8.3).

**New producers:**
- `ecad_model.spice.VERSION = "1.0.0"`: the parser and the deck serialiser.
- `ecad_model.domains.electrical.MODEL_BUILDER_VERSION = "1.0.0"`: the model.
  It is recorded as the model's producer
  `("ecad_model.domains.electrical", "1.0.0 (ecad_model.spice 1.0.0)")`.
- `ecad_model.domains.electrical.VERSION = "1.0.0"`: the deck's analysis and
  measurements, and the case target.

**Unchanged producers:** `builder`, `requirements`, `results` and
`dataset.VALIDATOR_VERSION`. Their output does not change.

### 2.4 Why topology goes into the model (amends plan §8.2 ARCH-1)

The protocol hands `write_models`, `sanity_problems`, `reference_value`,
`reference_inputs`, `dependencies` and `invariant_problems` only the model
(`base.py:103-132`). The deck has to be a function of the model, which is the
property V2 enforces for MJCF. The closed forms and the class check need
connectivity. Without terminals in the model, "netlist → engineering model →
simulator" (spec §36) would be false.

The amendment, with the rejected alternatives, goes into plan §8.2 and
`MEMORY.md`:
- (a) passing extraction files to `write_models`: a protocol change, and V1
  and V3 still would not see the topology;
- (b) re-reading the source by hash inside `write_models`: a hidden input
  outside `Item.read`;
- (c) a wrapper deck that `.include`s the source: runs unparsed text.

---

## 3. Extraction

### 3.1 The parser: `tools/ecad_model/spice.py` (format layer, no roles)

**Public API** (each function has a doctest):

```python
VERSION = "1.0.0"
MAX_NETLIST_BYTES = 1 << 20; MAX_LINE_CHARS = 1024; MAX_ELEMENTS = 1000; MAX_PWL_POINTS = 1000
@dataclass(frozen=True)
class Element: designator: str; element: str; terminals: Dict[str, str]; values: Dict[str, Any]; model: Optional[str]; line: int
@dataclass(frozen=True)
class Netlist: title: str; elements: Tuple[Element, ...]; models: Dict[str, Dict[str, float]]
class NetlistRefused(ExtractionError): ...          # kind "rejected"; message "<path>:<line>: <reason>"
def parse_value(token: str, where: str) -> float
def parse_netlist(data: bytes, path: str) -> Netlist
def write_elements(netlist_like) -> List[str]         # the element and .model lines of a deck, from values in SI
def read_deck(data: bytes, path: str) -> Tuple[Netlist, List[str]]   # the circuit block, and the adapter's own lines
```

It is pure Python, one pass, linear time, with anchored regexes and no
recursion. It runs in-process: the child process of `MEMORY.md:58` was for
native code, and this is not native code.

**File-level refusals** (each raises `NetlistRefused`):
- more than `MAX_NETLIST_BYTES`;
- empty;
- a Git LFS pointer (`version https://git-lfs`);
- any byte outside 0x09, 0x0A and 0x20–0x7E, so any CR, NUL or non-ASCII
  character is refused;
- a line over 1024 characters;
- more than 1000 elements, or more than 1000 PWL points in one source.

**Line 1 is the title.** SPICE always reads line 1 as the title
(**Verified**: a card placed there vanished). It is refused when:
- it is blank;
- it starts with `.` or `+`;
- it matches the element grammar below case-insensitively.

**Other lines:**
- Blank lines and lines starting with `*` are skipped.
- Refused anywhere else:
  - `+` continuation (**Verified**: it merges lines);
  - any of `; $ ' " { } \` ! \`;
  - `.end` missing, or any non-blank line after it (**Verified**: ngspice
    parses past `.end` and accepts no `.end`).

**Directives.** Only `.model` and `.end` are allowed. Every other dot-card is
refused with its class named:
- `.include .inc .lib .endl`: "reads another file";
- `.control .endc`: "runs commands, including shell" (**Verified** under `-b`);
- `.param .func .csparam`: "expressions";
- `.subckt .ends`: "subcircuits: PLANNED";
- `.options .option .temp .ic .nodeset .global`: "changes simulator state";
- `.tran .ac .dc .op .noise .tf .sens .pz .four .meas .measure .print .plot .save .probe`:
  "the analysis and measurements are written by the adapter";
- anything else: "unknown directive".

**Elements.** A designator matches `^[RCVIS][A-Z0-9_]{1,31}$`, so upper case
only; lowercase or unknown-letter designators are refused.

| Letter | Grammar | Terminals | Values |
|---|---|---|---|
| R | `R<id> NODE NODE VALUE`, exactly 4 tokens | p, n | `resistance` |
| C | `C<id> NODE NODE VALUE`, exactly 4 tokens (no `ic=`) | p, n | `capacitance` |
| V | `V<id> NODE NODE PWL( t0 v0 t1 v1 … )` | p, n | `waveform_time`, `waveform_voltage` |
| I | `I<id> NODE NODE PWL( … )` | p, n | `waveform_time`, `waveform_current` |
| S | `S<id> NODE NODE NODE NODE MODEL`, exactly 6 tokens (no `on`/`off`) | p, n, cp, cn | from its model: `on_resistance`, `off_resistance`, `threshold_voltage`, `hysteresis_voltage` |

The `PWL` keyword is case-insensitive. A PWL has an even count of at least 4
numbers; its times start at 0 and strictly increase.

**Refused with their type named:**
- sources other than PWL: `DC`, bare values, `PULSE`, `SIN`, `EXP`, `AC`
  (PLANNED);
- `L`: inductor, PLANNED;
- `B E F G H`: behavioural or controlled sources evaluate expressions;
- `X`: subcircuit instance;
- `A N`: code models and OSDI load libraries;
- `D Q M J K T U O W Y Z P`: not modelled by this domain.

**`.model`:** `.model <NAME> SW(RON=v ROFF=v VT=v VH=v)`.
- NAME matches `^[A-Z][A-Z0-9_]{0,31}$`; `SW` and the keys are
  case-insensitive.
- All four keys are required, each exactly once, in any order, and no others.
  No SPICE default may fill a value nobody chose.
- A model must be used by exactly one switch, and a switch must name a
  declared model.

**Numbers:** `^([+-]?(?:\d+\.?\d*|\.\d+))(?:([eE][+-]?\d+)|(meg|[tgkmunp]))?$`.
- The value is `float(f"{mantissa}e{exponent}")`: one correctly rounded
  conversion, so `470u` is exactly `float("470e-6")` = 0.00047.
- Refused (**Verified** traps in ngspice-47):
  - uppercase suffixes (`1M` is milli: 1 V across `1M` drew 1000 A);
  - `f` and `F` (femto);
  - trailing letters (`10uF`, `2kohm` are silently accepted by ngspice);
  - `mil`;
  - an exponent together with a suffix (`1e3k`);
  - non-finite results (`1e999`).

**Names:**
- Nodes match `^(0|[a-z][a-z0-9_]{0,31})$`.
- `gnd` is refused (**Verified**: ngspice treats it as ground).
- `pa_<digits>` is refused (**Verified**: ngspice's `par()` expansion creates
  those nodes and hijacks one of that name).
- Designators and model names must be unique.

**Connectivity** (after all lines):
- ground `0` is present;
- no element has both main terminals on one node;
- every other node has at least 2 terminals, counting switch control
  terminals (**Verified**: ngspice accepts a dangling node);
- every node reaches `0` through R, V or switch p–n edges. C, I and switch
  control pairs are open, so otherwise the node is refused with "no DC path to
  ground: the operating point is singular".

The scratch prototype (`synth/final/proto_parse.py`) accepts the committed
netlist with the values of §1.5. It refuses `1M`, `470uF`, `1kohm`, `1e3k`,
`.control`, `.include`, `gnd`, `pa_00`, text after `.end`, no `.end`, CRLF,
`µ`, a lowercase designator, `;`, `L`, `B`, `DC` and a missing `VH`
(**Verified**).

### 3.2 The adapter's `extract` (`tools/ecad_model/domains/electrical.py`)

1. Require exactly one source of format `spice`, following
   `mechanical.py:271-275`.
2. Run `regular_file(path, spice.MAX_NETLIST_BYTES)`. Its `UnsupportedFormat` is
   re-raised as `ExtractionError("rejected", …)`, because `regular_file` raises
   `UnsupportedFormat`, not an `ExtractionError`. A FIFO or symlink never
   reaches here: `Item` refuses declared sources that are not regular files
   before any gate (`dataset.py:119-123`).
3. `spice.parse_netlist(data, path)`.
4. Merge the annotations:
   - `circuit_elements` keys must be netlist designators;
   - a facet the netlist already sets is refused as "declared twice";
   - an unannotated element gets name = designator and kind from its letter
     (R `resistor`, C `capacitor`, V `voltage_source`, I `current_source`,
     S `switch`);
   - `components_without_cad` entries become components with no `circuit`,
     and their ids must not collide with a designator's;
   - relationship endpoints must exist.

   Each inconsistency is a `ValueError`, which V1 reports as
   `FAIL DATASET_INPUT_INVALID` (`dataset.py:998-1003`).
5. Build the model (§2.1), with `unknowns = index_unknowns(model)`.
6. Apply the network class (§3.3). A violation raises
   `ExtractionError("rejected", "<path>: not the series-precharge supply-input network the electrical domain validates: rule Cn: …")`,
   so V1 gives `FAIL SOURCE_REJECTED` (`dataset.py:986-987`) and V2–V4 give
   `BLOCKED DERIVATION_NOT_AVAILABLE` (`dataset.py:1050-1057, 1086-1092`). A
   refused netlist never reaches ngspice.
7. Return `Extraction(model=model, producer=("ecad_model.domains.electrical", f"{MODEL_BUILDER_VERSION} (ecad_model.spice {spice.VERSION})"))`
   with `files=[]` and `tools=[]`.

### 3.3 The supported network class: `supply_input_roles(model) -> Roles`

This is the only topology the adapter validates. It is stated in the
`description` the manifest shows for `AVAILABLE`, and in the documentation, as
honestly as mechanical's "one revolute joint".

| Rule | Requirement |
|---|---|
| C1 | Exactly one voltage source whose `n` is `0` and whose waveform has exactly two points (0, 0), (t_r, V), with t_r > 0 and V > 0. It is the **supply**; its `p` node is the input node. |
| C2 | Exactly one resistor between the input node and a node X (the **fuse**). Nothing else connects to the input node. |
| C3 | Between X and a node B ≠ 0, exactly one resistor (the **limiter**) and one switch on p/n (the **bypass**). Nothing else connects to X. B is the **rail**. |
| C4 | The bypass has `cn` = `0`. Its `cp` node connects only to it and to one voltage source (the **bypass command**) with `n` = `0`, whose waveform has exactly three points (0, 0), (t_b, 0), (t_b + e_b, h_b), with t_b > 0, e_b > 0 and h_b > 0. |
| C5 | At B, exactly one capacitor. It goes either to a node E ≠ 0 that has exactly one other element, a resistor to `0` (the **ESR**), or straight to `0` (R_E = 0). |
| C6 | Exactly one current source with p = B and n = `0` (the **load**). Its waveform has exactly three points (0, 0), (t_l0, 0), (t_l1, I_L), with 0 < t_l0 < t_l1 and I_L > 0. |
| C7 | Exactly one switch with p = B, n = `0` and `cn` = `0` (the **fault**). Its command source is shaped as in C4: (0, 0), (t_f, 0), (t_f + e_f, h_f). |
| C8 | No other element. |

### 3.4 V1: `sanity_problems(model)` → `DOMAIN_SANITY_FAILED`

1. Every electrical facet name is in the vocabulary, with that vocabulary's
   unit (from honesty; it catches unit mutations and typos):

   | Facet | Unit |
   |---|---|
   | `resistance`, `on_resistance`, `off_resistance` | `ohm` |
   | `capacitance` | `F` |
   | `waveform_time` | `s` |
   | `waveform_voltage`, `threshold_voltage`, `hysteresis_voltage`, `voltage_rating`, `supply_voltage` | `V` |
   | `waveform_current`, `current_rating`, `breaking_capacity`, `ripple_current_rating`, `rated_current`, `input_ripple_current` | `A` |
   | `power_rating`, `rated_power` | `W` |
   | `melting_i2t` | `A^2*s` |
   | `pulse_energy_rating` | `J` |
   | `switching_frequency` | `Hz` |

2. Values:
   - resistance and capacitance > 0;
   - `on_resistance` > 0, `off_resistance` > `on_resistance`;
   - `hysteresis_voltage` ≥ 0, `threshold_voltage` > `hysteresis_voltage`, so
     each switch starts open at 0 V command;
   - each command's high level h > VT + VH, so the switch does close;
   - every known rating > 0.
3. The sequence the measurement windows assume:
   - t_r < t_b (the ramp ends before the bypass command);
   - t_sw,b := t_b + e_b·(VT+VH)/h_b < t_l0 (the load starts after the bypass
     closes);
   - t_l1 < t_f (the load is on before the fault).
4. Resource guard (spec §26): T_END / TMAX ≤ 1 000 000. The committed sample
   needs 110 000 steps.

For the committed model this gives `[]`. The arithmetic was **Verified** in
`cf.py`: t_sw,b = 30.0005 ms, t_l0 = 40 ms, t_l1 = 40.1 ms, t_f = 100 ms.

### 3.5 V2: `invariant_problems(model, {}, {deck_path: bytes})` → `DOMAIN_MODEL_INCONSISTENT`

1. `spice.read_deck` splits the deck at `.options noacct` and re-parses the
   circuit block with the §3.1 grammar. Its elements (designator, element,
   terminals, model) and values must equal the model's circuit components, in
   order, with floats compared exactly (`float(repr(x)) == x`).
2. The adapter's own lines must equal, character for character, what §4.1
   writes for this model: `.options noacct`, one `.tran`, and the nine `.meas`
   lines in vocabulary order. Then comes `.end`, and nothing follows it.
3. Every netlist-derived facet's `source.sha256` equals
   `design.sources[0].sha256`.
4. **Supply matches the sheet** (from extensible). For every `powered_by`
   relationship from a component with a non-null electrical `supply_voltage`
   to a circuit voltage source, that source's final waveform value equals it.
   Here V_IN's 48.0 = the drive's 48.0.

The domain-neutral `v2.dataset-reproduction` also compares the deck
byte-exactly (comparator `exact`, `dataset.py:696-709`), along with the source
hash, requirement components and a fresh unknowns index (`dataset.py:836-862`).

---

## 4. Domain model and case target

### 4.1 `write_models(model, sample_id)`

It returns one file:

```python
[DerivedFile(path=f"derived/electrical/{sample_id}.cir", data=deck, role="domain_model", media_type="text/x-spice",
             producer="ecad_model.domains.electrical", version=VERSION,
             derived_from=("derived/engineering_model.json",), comparator="exact")]
```

`.cir` is already mapped to `text/x-spice` (`base.py:31`). The comparator is
`exact`: every number is a netlist value, or a sum or product of netlist values
and method constants. All of them are correctly rounded IEEE operations printed
with `repr`, and no kernel is involved.

**Method constants** (in `domains/electrical.py`, versioned by `VERSION`):
- `TSTEP = TMAX = 1e-06` s;
- `FAULT_WINDOW_S = 0.01`;
- `CHARGED_FRACTION = 0.9`;
- `SETTLE_TIME_CONSTANTS = 30`;
- `MAX_STEPS = 1_000_000`.

**Windows, from the roles:**
- T_BYP = t_b (the bypass command's second time point);
- T_FLT = t_f;
- T_END = T_FLT + FAULT_WINDOW_S;
- the charge level is LEVEL = CHARGED_FRACTION · V.

**Line templates, in order:**
- `* <design.name>`;
- `* written by ecad_model.domains.electrical <VERSION> from derived/engineering_model.json; regenerate with build, never edit`;
- one line per circuit component, in model order:
  - R/C: `D p n v`;
  - V/I: `D p n PWL(t0 v0 t1 v1 …)`;
  - S: `D p n cp cn MODEL`;
- one `.model NAME SW(RON=… ROFF=… VT=… VH=…)` per switch, in element order;
- `.options noacct`;
- `.tran TSTEP T_END 0.0 TMAX`;
- nine `.meas` lines (§5.1);
- `.end` and a final LF.

### 4.2 The committed deck, exactly

The scratch copy is 1300 bytes, sha256
`2840fc040b30a626891a347bb447a242f81ce97cd23aa415a6e32c7ef4451d30`.
ngspice-47 ran it twice (**Verified**, `synth/final/run1.out`, `run2.out`):
- exit 0 both times, with empty stderr;
- identical stdout both times;
- no `/` anywhere in stdout, so no host path.

```spice
* servo_supply_001: 48 V servo-drive supply input -- fuse, precharge limiter with bypass, bulk capacitor, drive load
* written by ecad_model.domains.electrical 1.0.0 from derived/engineering_model.json; regenerate with build, never edit
V_IN n_in 0 PWL(0.0 0.0 0.0001 48.0)
R_F1 n_in n_f 0.02
R_PRE n_f n_bus 10.0
S_BYP n_f n_bus n_byp 0 SW_BYP
V_BYP n_byp 0 PWL(0.0 0.0 0.03 0.0 0.030001 5.0)
C_BULK n_bus n_esr 0.00047
R_ESR n_esr 0 0.05
I_LOAD n_bus 0 PWL(0.0 0.0 0.04 0.0 0.0401 4.16667)
S_FLT n_bus 0 n_fc 0 SW_FLT
V_FLT n_fc 0 PWL(0.0 0.0 0.1 0.0 0.100001 5.0)
.model SW_BYP SW(RON=0.01 ROFF=1000000000.0 VT=2.5 VH=0.0)
.model SW_FLT SW(RON=0.1 ROFF=1000000000.0 VT=2.5 VH=0.0)
.options noacct
.tran 1e-06 0.11 0.0 1e-06
.meas tran inrush_peak_current_a MAX par('-i(V_IN)') FROM=0.0 TO=0.03
.meas tran inrush_i2t_a2s INTEG par('i(V_IN)*i(V_IN)') FROM=0.0 TO=0.03
.meas tran bus_charge_time_s WHEN v(n_bus)=43.2 RISE=1
.meas tran bus_voltage_at_bypass_v FIND v(n_bus) AT=0.03
.meas tran bus_peak_voltage_v MAX v(n_bus) FROM=0.0 TO=0.1
.meas tran steady_bus_voltage_v FIND v(n_bus) AT=0.1
.meas tran steady_input_current_a FIND par('-i(V_IN)') AT=0.1
.meas tran steady_fuse_power_w FIND par('(v(n_in)-v(n_f))*(-i(V_IN))') AT=0.1
.meas tran fault_input_current_a FIND par('-i(V_IN)') AT=0.11
.end
```

**Notes on the deck:**
- The current through a voltage source is negative when it sources, hence
  `-i(V_IN)`.
- Steady-state values are sampled at T_FLT = 0.1 s, which is a PWL
  breakpoint. The fault switch closes at 0.1000005 s, after the sample.

### 4.3 Case target

```python
CaseTarget(adapter="ngspice", inputs=(f"derived/electrical/{sample_id}.cir",), arguments=lambda scenario: [])
```

- It uses the default timeout of 300 s (`base.py:95`). One run took 0.2 s
  (**Verified**).
- `_case` (`requirements.py:55-65`) compiles it unchanged.
- Every case runs the identical deck, so borrowing a measured value for a
  limit-blocked requirement is correct for any case with equal arguments
  (`results.py:296-306`). It picks `v3.REF-EL-001` (F1).

**Scenarios.** Each metric belongs to exactly one scenario:
- `startup`: the power-up sequence before the fault, [0, T_FLT];
- `steady_state`: at T_FLT;
- `output_short`: at T_END.

A scenario carries only its name. The stimulus, bypass and fault timing, and
the fault resistance are design data in the hashed netlist. Scenario
parameters are PLANNED: they need scenario-dependent inputs (D1).

---

## 5. Metrics and references

### 5.1 The nine metrics

Every metric is `SIMPLIFIED`: an ideal source; the fuse as a fixed
resistance; an ideal switch; C with a series resistance only; a
constant-current load; no temperature and no parasitics.

| Metric | Unit | Scenario | `.meas` (window) | Derivation | Tolerance |
|---|---|---|---|---|---|
| `inrush_peak_current_a` | A | startup | `MAX par('-i(V_IN)') FROM=0.0 TO=T_BYP` | `precharge_peak_current` | 1e-4 |
| `inrush_i2t_a2s` | A^2*s | startup | `INTEG par('i(V_IN)*i(V_IN)') FROM=0.0 TO=T_BYP` | `precharge_i2t` | 1e-4 |
| `bus_charge_time_s` | s | startup | `WHEN v(RAIL)=LEVEL RISE=1` | `precharge_charge_time` | 1e-6 |
| `bus_voltage_at_bypass_v` | V | startup | `FIND v(RAIL) AT=T_BYP` | `precharge_bus_voltage` | 1e-3 |
| `bus_peak_voltage_v` | V | startup | `MAX v(RAIL) FROM=0.0 TO=T_FLT` | `settled_no_load_bus_voltage` | 1e-3 |
| `steady_bus_voltage_v` | V | steady_state | `FIND v(RAIL) AT=T_FLT` | `steady_bus_voltage` | 1e-3 |
| `steady_input_current_a` | A | steady_state | `FIND par('-i(SUPPLY)') AT=T_FLT` | `steady_input_current` | 1e-4 |
| `steady_fuse_power_w` | W | steady_state | `FIND par('(v(FUSE.p)-v(FUSE.n))*(-i(SUPPLY))') AT=T_FLT` | `steady_fuse_power` | 1e-5 |
| `fault_input_current_a` | A | output_short | `FIND par('-i(SUPPLY)') AT=T_END` | `settled_fault_input_current` | 1e-2 |

`SUPPLY` is the supply's designator, `RAIL` the rail node, and `FUSE.p/n` the
fuse's terminals. In the first two rows `V_IN` stands for SUPPLY. §4.2 shows
the lines as written for the committed model.

### 5.2 Closed forms (`electrical.reference_value`)

They are computed from the roles and facets only, never from the deck or the
simulator.

**Definitions:**
- par(a, b) = ab/(a+b);
- R1 = R_F + par(R_P, R_off,B) + R_E; τ1 = R1·C; k = V/t_r;
- R_c = R_F + par(R_P, R_on,B).

**Forms:**
- `precharge_peak_current` = C·k·(1 − e^(−t_r/τ1)).
  - During the ramp the current rises; after it, it decays.
- v_C(t_r) = k(t_r − τ1(1 − e^(−t_r/τ1))); A = V − v_C(t_r).
- `precharge_i2t` = (Ck)²[t_r − 2τ1(1 − e^(−t_r/τ1)) + (τ1/2)(1 − e^(−2t_r/τ1))] + (A/R1)²(τ1/2)(1 − e^(−2(T_BYP − t_r)/τ1)).
- `precharge_charge_time` = t_r + τ1·ln(A(1 − R_E/R1)/((1 − f)V)), with f = `CHARGED_FRACTION`.
  - After the ramp the rail follows v_B = V − A(1 − R_E/R1)e^(−(t−t_r)/τ1), rising.
- `precharge_bus_voltage` = V − A(1 − R_E/R1)e^(−(T_BYP − t_r)/τ1).
- `settled_no_load_bus_voltage` = V·R_off,F/(R_off,F + R_c).
  - After the bypass closes and before the load, v_B = V − R_c·i_in ≤ this
    level, and it rises monotonically to it.
- `steady_bus_voltage` v_ss = (V − I_L·R_c)/(1 + R_c/R_off,F).
- `steady_input_current` = (V − v_ss)/R_c.
- `steady_fuse_power` = i_ss²·R_F.
- `settled_fault_input_current`: v∞ = (V/R_c − I_L)/(1/R_c + 1/R_on,F); i = (V − v∞)/R_c.

**Neglected, with a bound.** The fault switch's R_off,F across the rail during
precharge draws at most V/R_off,F = 4.8e-8 A. That is below the tightest
current tolerance by 2000×.

**Applicability.** A form that does not apply raises `ReferenceBlocked(msg, [])`,
which gives V3 `REFERENCE_NOT_APPLICABLE`.

| Form | Applies when |
|---|---|
| `precharge_charge_time` | the crossing lies after the ramp, A(1 − R_E/R1) > (1 − f)V, and at or before T_BYP |
| `settled_no_load_bus_voltage` | t_l0 − t_sw,b ≥ 30·τ2, with τ2 = C·(R_E + par(R_c, R_off,F)) |
| steady forms | T_FLT − t_l1 ≥ 30·τ2 |
| fault form | T_END − t_sw,f ≥ 30·τ_f, with τ_f = C·(R_E + par(R_c, R_on,F)) and t_sw,f = t_f + e_f·(VT+VH)/h_f |

For the committed sample:
- τ1 = 4.7329 ms;
- τ2 = 37.6 µs, so 30τ2 = 1.13 ms ≤ 9.9995 ms and ≤ 59.9 ms;
- τ_f = 34.3 µs, so 30τ_f = 1.03 ms ≤ 9.9995 ms.

**Verified**, `cf.py`. A null input raises `ReferenceBlocked(msg, missing)`,
which gives `MISSING_REQUIRED_INPUT`.

**`reference_inputs`** returns exactly the facet paths each form reads:
- the supply waveform and every resistance on the series path;
- the bypass `on_resistance` or `off_resistance`;
- the bypass command waveform and switch thresholds, for the forms that use t_sw;
- `c_bulk/capacitance`;
- the load waveform;
- the fault switch's `on_resistance` or `off_resistance`, and its command waveform.

**`dependencies(model, metric, scenario)`** is coarse on purpose (mechanical
style, `mechanical.py:357-383`): every facet of every circuit component except
ratings. The runner adds a requirement's limit quantity
(`dataset.py:1313-1315`).

**`components_for`** returns every circuit component as `"<id> (<DESIGNATOR>)"`.

### 5.3 Values: ngspice-47 against the closed forms

**Verified**: `run1.out`, `cf.py`. The compiled golden stores the value to 12
significant figures (`requirements.py:143`).

| Metric | ngspice-47 | closed form (12 s.f.) | abs(difference) | Tolerance / difference |
|---|---|---|---|---|
| `inrush_peak_current_a` | 4.71663 | 4.71663002764 | 2.8e-8 | 3600× |
| `inrush_i2t_a2s` | 0.0533906 | 0.0533907676223 | 1.7e-7 | 600× |
| `bus_charge_time_s` | 0.0109244 | 0.0109244343789 | 3.4e-8 | 29× |
| `bus_voltage_at_bypass_v` | 47.9147 | 47.9147188794 | 1.9e-5 | 53× |
| `bus_peak_voltage_v` | 48.0000 | 47.9999999986 | 1.4e-9 | ≫ |
| `steady_bus_voltage_v` | 47.8750 | 47.8750415236 | 4.2e-5 | 24× |
| `steady_input_current_a` | 4.16667 | 4.16667004787 | 4.8e-8 | 2000× |
| `steady_fuse_power_w` | 0.347223 | 0.347222785757 | 2.1e-7 | 47× |
| `fault_input_current_a` | 372.465 | 372.464522495 | 4.8e-4 | 21× |

**Precision limits:**
- ngspice prints 6 significant digits, and `numdgt=12` does not change that
  (**Verified**).
- The i²t integration error scales with TMAX: 4.3e-7 at TMAX 1e-5 and 1.7e-7
  at 1e-6 on the committed sample. On the FAIL copy it is 1.2e-5 at 1e-6
  (**Verified**). That is why TMAX is 1 µs and the i²t tolerance 1e-4.

### 5.4 What the goldens catch (writer and data errors)

**Verified**, `sens.py`: decks with one error against the unchanged model's
closed forms, at the §5.1 tolerances.

| Error in the deck | Goldens that FAIL |
|---|---|
| ESR dropped | peak, i²t, charge time, bus at bypass |
| C +10% | the same four |
| **C +1%** | the same four (minimal's design could not catch a 1% error) |
| fuse `m` read as `µ` | 7 of 9 |
| bypass R_off 1 kΩ | 4 |
| fault R_on ×10 | fault current |
| load ×1.001 | steady current, fuse power |
| supply 47 V | 6 |
| current sign flipped (`par('i(V_IN)')`) | peak reads 0 and steady −4.16667: peak, steady current and fault fail. V4 alone would be trivially met, which is why the goldens matter. |

The goldens compare two computations on the same values. They catch deck
writing and simulator errors, not parser scaling errors, so the parser tests
(§9, N1–N3) and the differential test S6 cover those.

---

## 6. Requirements (`requirements/requirements.json`)

The document header is `$schema` = the engineering-requirements schema,
`requirements_version` "1.0.0" and `design_id` "servo_supply_001". Every entry
has `"domain": "electrical"`. Three shared sources:

```json
COMPUTATION = {"kind": "computation", "ref": "model verification: an independent closed-form derivation, not a design requirement"}
EXAMPLE     = {"kind": "requirement", "ref": "example requirement for the servo_supply_001 MVP, chosen to exercise the pipeline; not a customer, safety or certification requirement"}
RATING      = {"kind": "requirement", "ref": "example rule for the servo_supply_001 MVP: a part stays within its own rating, with no derating; no standard was consulted"}
```

### 6.1 References (V3)

Every scenario below is `{"name": <scenario>}`.

| `reference_id` | `title` | metric | scenario | unit | `absolute_tolerance` | derivation | source |
|---|---|---|---|---|---|---|---|
| REF-EL-001 | Inrush peak equals the RC-ramp closed form | inrush_peak_current_a | startup | A | 0.0001 | precharge_peak_current | COMPUTATION |
| REF-EL-002 | Inrush I2t over the precharge equals its closed form | inrush_i2t_a2s | startup | A^2*s | 0.0001 | precharge_i2t | COMPUTATION |
| REF-EL-003 | The bus reaches 90 % of the supply when the RC charge says | bus_charge_time_s | startup | s | 1e-06 | precharge_charge_time | COMPUTATION |
| REF-EL-004 | Bus voltage when the bypass is commanded equals its closed form | bus_voltage_at_bypass_v | startup | V | 0.001 | precharge_bus_voltage | COMPUTATION |
| REF-EL-005 | The bus never exceeds its settled no-load voltage | bus_peak_voltage_v | startup | V | 0.001 | settled_no_load_bus_voltage | COMPUTATION |
| REF-EL-006 | Steady bus voltage under the load equals the DC divider | steady_bus_voltage_v | steady_state | V | 0.001 | steady_bus_voltage | COMPUTATION |
| REF-EL-007 | Steady input current equals the DC divider | steady_input_current_a | steady_state | A | 0.0001 | steady_input_current | COMPUTATION |
| REF-EL-008 | Steady fuse dissipation equals I^2 R | steady_fuse_power_w | steady_state | W | 1e-05 | steady_fuse_power | COMPUTATION |
| REF-EL-009 | Settled short-circuit input current equals the DC divider | fault_input_current_a | output_short | A | 0.01 | settled_fault_input_current | COMPUTATION |

All nine are expected to PASS.

### 6.2 Requirements (V4)

Every requirement has `"illustrative": true` and no tolerance (0).

| `requirement_id` | `title` | component | metric / scenario | operator, `limit` | unit | source | Expected |
|---|---|---|---|---|---|---|---|
| REQ-EL-001 | Precharge keeps the inrush peak at or below 10 A | r_pre | inrush_peak_current_a / startup | `<=` `{"value": 10.0}` | A | EXAMPLE | `WARNING WITHIN_ILLUSTRATIVE_LIMIT` (4.71663) |
| REQ-EL-002 | The bypass closes only once the bus is within 5 % of the supply | s_byp | bus_voltage_at_bypass_v / startup | `>=` `{"value": 45.6}` | V | EXAMPLE | `WARNING` (47.9147) |
| REQ-EL-003 | Steady input current within the eServo-200 sheet's 5 A (continuous or peak is not stated) | drive | steady_input_current_a / steady_state | `<=` `{"quantity": "components/drive/domains/electrical/rated_current"}` | A | EXAMPLE | `WARNING` (4.16667) |
| REQ-EL-004 | Steady bus at or above 47 V under the drive load | drive | steady_bus_voltage_v / steady_state | `>=` `{"value": 47.0}` | V | EXAMPLE | `WARNING` (47.875) |
| REQ-EL-005 | Bus peak within C1's voltage rating | c_bulk | bus_peak_voltage_v / startup | `<=` `{"quantity": "components/c_bulk/domains/electrical/voltage_rating"}` | V | RATING | **`BLOCKED MISSING_REQUIRED_INPUT`**, finding `UNKNOWN: components/c_bulk/domains/electrical/voltage_rating`; results show 48.0 measured by `v3.REF-EL-001` |
| REQ-EL-006 | Precharge I2t within F1's melting I2t | r_f1 | inrush_i2t_a2s / startup | `<=` `{"quantity": "components/r_f1/domains/electrical/melting_i2t"}` | A^2*s | RATING | `BLOCKED`; 0.0533906 measured by `v3.REF-EL-001` |
| REQ-EL-007 | Prospective short-circuit current within F1's breaking capacity | r_f1 | fault_input_current_a / output_short | `<=` `{"quantity": "components/r_f1/domains/electrical/breaking_capacity"}` | A | RATING | `BLOCKED`; 372.465 measured by `v3.REF-EL-001` |

### 6.3 Expected receipt

This is a target. It is **Inferred** from the Verified numbers and the compile
and propagation rules (`requirements.py:148-182`, `dataset.py:1297-1350`):
- V0–V3 PASS;
- V4 `BLOCKED` (4 WARNING, 3 BLOCKED);
- overall `BLOCKED`, `eligible_for_ebuild` false;
- 16 results.

No part-rating check can `PASS`: every rating is `UNKNOWN`, and every limit is
illustrative. Without ngspice, the 13 compiled cases are
`BLOCKED TOOL_NOT_INSTALLED`, attributed to `ecad-validator`
(`cases.py:444-454`).

### 6.4 Test-built copies (not committed)

**FAIL from a mutated input: `R_PRE … 10` → `1`.**
- REQ-EL-001 is `FAIL CORNER_LIMITS_FAILED` at 40.6812 A (closed form
  40.6811962).
- Every V3 reference still passes: the differences are
  - inrush 3.8e-6;
  - i²t 1.2e-5;
  - charge time 1.5e-9;
  - bus at bypass 0;
  - steady bus 1.2e-5;
  - fault 2.3e-4.

  All are within tolerance (**Verified**, `rpre1_f.*`). The FAIL is the
  design's, not the simulator's.

**FAIL of a sequence: bypass command at 5 ms.**
- REQ-EL-002 is `FAIL` at 31.2169 V (**Verified**, `early_f.out`).
- REF-EL-003 is `REFERENCE_NOT_APPLICABLE`: its crossing, 10.92 ms, is after
  T_BYP.

**Boundary:**
- with a stand-in returning the recorded 4.71663:
  - limit 4.71663 → WARNING;
  - `math.nextafter(4.71663, 0)` → FAIL;
  - the same limit with tolerance 1e-9 → WARNING;
  - `>=` 47.9147 → WARNING, and `nextafter(47.9147, inf)` → FAIL;
- with real ngspice, at margins ≥ 3.4e-3 over the numerical error:
  - 4.72 → WARNING;
  - 4.71 → FAIL;
  - 4.71 with tolerance 0.01 → WARNING.

**BLOCKED from each null status:** C1's `voltage_rating` as UNKNOWN,
UNSPECIFIED (citing the netlist by hash as the silent document) and
NOT_AVAILABLE → `BLOCKED MISSING_REQUIRED_INPUT <STATUS>: <path>`.

**AI and PASS paths:** a non-illustrative copy of REQ-EL-005 with C1's rating:
- `SPECIFIED` 63 V → `PASS` (test data labelled as a fixture);
- `AI_ASSUMPTION` (source kind `ai`) at 63 V and at 40 V →
  `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` both times;
- the illustrative original with `SPECIFIED` 63 V → `WARNING`.

**Invalid inputs:** §3.1 refusals and §3.3 class violations, each as a copy
(§9).

---

## 7. Tool-adapter changes (engine: ARCH-2, RESULT-8, RESULT-2 on the ngspice path only)

### 7.1 ARCH-2: `tools/ecad_validation/adapters/ngspice.py`

**Today (Observed):**
- The argv is `[exe, "-b", "-o", "ngspice.log", "-r", "ngspice.raw", deck]`
  (lines 38-53).
- With `-r`, ngspice logs "No .measure possible in batch mode (-b) with -r
  rawfile set!".
- With only `-o`, results go to a log inside the workspace that `run_process`
  deletes (`process.py:91`).
- No metrics are returned (lines 63-74).

**New module-level constants:**

```python
MAX_DECK_BYTES = 1 << 20
DECLARED = re.compile(r"^[ \t]*\.meas(?:ure)?[ \t]+(?:tran|dc|ac)[ \t]+([A-Za-z][A-Za-z0-9_]*)[ \t]", re.IGNORECASE | re.MULTILINE)
REPORTED = re.compile(r"^([a-z][a-z0-9_]*)[ \t]*=[ \t]*(\S+)(?:[ \t]+(?:at|from|to)=[ \t]*\S+)*[ \t]*$")
NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
FAILED = re.compile(r"^[ \t]*\.meas(?:ure)?[ \t]+\S+[ \t]+([a-z][a-z0-9_]*)\b.*\bfailed!\s*$", re.IGNORECASE | re.MULTILINE)
TRUNCATED = "[output truncated]"   # what process._limited appends (process.py:55-59)
RECEIPT_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
```

**New public functions** (each with a doctest):

```python
def declared_measurements(deck: str) -> Tuple[List[str], List[str]]:
    """(names declared once, lower-cased, in deck order; names declared more than once)."""

def parse_measurements(stdout: str, stderr: str, declared: Sequence[str]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """(metrics, problems): a declared name becomes a metric only if exactly one stdout line reports it, and
    its value matches NUMBER and is finite. Every other declared name is in problems: "failed: <stderr line>",
    "not reported", "reported more than once", "not a number: <token>", "not finite". Undeclared names are ignored."""
```

**`run()` flow.** The existing mapping at lines 54-62 is unchanged.

1. The capability is unavailable → `BLOCKED` with reason
   `_receipt_reason(capability.reason)` (§7.3) and the raw reason in the summary.
2. There are no inputs → `BLOCKED NETLIST_INPUT_MISSING` (existing).
3. `input_files[0].stat().st_size > MAX_DECK_BYTES` →
   `BLOCKED NETLIST_INPUT_TOO_LARGE`, and nothing is run. Otherwise read it as
   UTF-8 with `errors="replace"`. The case engine has already refused
   non-regular inputs (`cases.py:331`).
4. Call `run_process(argv=[capability.executable or "ngspice", "-b", relative], …)`.
   `request.arguments` never reach argv.
5. The verdict comes from the process as today:
   - UNAVAILABLE → `BLOCKED`;
   - not completed → `INCONCLUSIVE`;
   - rc 0 → `PASS`;
   - rc ≠ 0 → `FAIL TOOL_EXITED_NONZERO`, with no metrics.
6. If the verdict is `PASS`:
   - stdout ends with `TRUNCATED` → `INCONCLUSIVE`, reason `OUTPUT_TRUNCATED`,
     metrics `{}`. A cut line such as `3.72465e+0` would otherwise parse as
     the wrong number.
   - Otherwise `metrics` = the parsed values, and the summary reads
     "`<n>` of `<m>` declared measurements read" plus up to 10 problems. A
     missing metric gives its case `GOLDEN/CORNER_METRICS_INCONCLUSIVE` from
     the comparator (`cases.py:99-101, 124-127`), so no adapter decides a
     verdict.
7. `metrics` holds only finite floats, so `canonical_json_bytes` cannot raise
   for ngspice (ENGINE-1 path, `cases.py:410`).
8. `stdout` and `stderr` go verbatim into the hash-bound execution record
   (`cases.py:398-418`). With `noacct` the committed deck's stdout is
   byte-identical run to run and contains no host path (**Verified**). The
   record's `command[0]` is the absolute executable path, which is STATE-2
   (still open).

**The stdout formats the parser must handle** (**Verified**, `run1.out`):
- `inrush_peak_current_a=  4.71663e+00 at=  1.00000e-04`: a name of 20 or more
  characters has no space before `=`;
- `inrush_i2t_a2s      =   5.33906e-02 from=  0.00000e+00 to=  3.00000e-02`;
- `bus_charge_time_s   =   1.09244e-02`.

A failed measurement is absent from stdout. stderr carries
`Error: measure  late  find(AT) : out of interval` and
` .meas tran late find v(a) at=50u failed!`, with exit 0 (**Verified**). A
duplicated name is printed twice (**Verified**).

### 7.2 RESULT-8: `tools/ecad_validation/adapters/capabilities.py`

```python
VERSION_PATTERNS = {"ngspice": re.compile(r"\bngspice-([0-9][0-9A-Za-z.+~-]*)")}   # its first line is "******" (verified)
# in probe_executable, replacing line 48:
pattern = VERSION_PATTERNS.get(adapter)
if pattern is None:
    version_line = output.splitlines()[0].strip() if output else None
else:
    match = pattern.search(output)
    version_line = match.group(1) if match else None
```

- ngspice-47's `--version` prints `******` and then
  `** ngspice-47 : Circuit level simulation program`, with exit 0. The probe
  gives "47" (**Verified**).
- No match gives `None`, and the tool stays available. A PASS then becomes
  `BLOCKED TOOL_VERSION_UNAVAILABLE` (`cases.py:444-454`), the existing policy.
- `NgspiceAdapter.capability()` and `detect_capabilities()` both call
  `probe_executable("ngspice", …)`, so both are fixed.
- kicad, iverilog, verilator and openscad have no pattern, so they are
  byte-identical.

### 7.3 RESULT-2, ngspice path only (`ngspice.py`)

```python
def _receipt_reason(reason: Optional[str]) -> str:
    """A capability reason the receipt schema accepts (^[A-Z][A-Z0-9_]*$)."""
    if reason and RECEIPT_CODE.match(reason): return reason
    if reason and reason.startswith("VERSION_PROBE_ERROR:"): return "VERSION_PROBE_ERROR"
    if reason and reason.startswith("VERSION_PROBE_EXIT_"): return "VERSION_PROBE_EXIT_NONZERO"
    return "TOOL_UNAVAILABLE"
```

`capabilities.py:45` and `:54` emit `VERSION_PROBE_ERROR:{exc}` and
`VERSION_PROBE_EXIT_-9`. Passed through `ngspice.py:24`, these fail the receipt
schema, and then no receipt is written.

The general fix stays on `fix/version-probe-reason-codes` (plan §21 item 1).
When that lands, `_receipt_reason` is deleted in the same change.

### 7.4 Why no other adapter changes

- `python_control`, `mujoco`, `kicad` and `hdl` are untouched, and so is
  `run_process`.
- The other half of ARCH-2, copying declared outputs out of the workspace, is
  not needed by ngspice. It stays open for the KiCad and HDL PRs.
- `cases.ADAPTERS` is unchanged.
- No committed case uses ngspice today (**Verified**: `git ls-files` shows only
  the two mechanical case documents).
- `-n` (skip `.spiceinit`) and a deck screen in the adapter are SEC-1 changes
  to engine code that no named defect covers. They are open questions (§13).

---

## 8. Protocol: `DomainAdapter` becomes stable

### 8.1 The one change the domain forced (SCOPE-15 list)

| Change | Why electrical forces it | Matching mechanical change | Other call sites |
|---|---|---|---|
| `Extraction.producer: Tuple[str, str]`, required with no default. `base.py:79-85` becomes `model, producer, files=[], tools=[]`. | The runner hard-codes `producer="ecad_model.builder", version=BUILDER_VERSION` for every model (`dataset.py:279-281`) and `versions.engineering_model: BUILDER_VERSION` (`dataset.py:363`). The electrical manifest would claim the mechanical builder wrote its model. | `mechanical.py:298` passes `producer=("ecad_model.builder", BUILDER_VERSION)`, importing `VERSION as BUILDER_VERSION` from `..builder`. The mechanical manifest stays byte-identical in both fields. | `dataset.py` uses `extraction.producer[0]` and `[1]` at 281, and `[1]` at 363. It drops the now-unused import at line 50. The test fixture `test_domain_adapter.py:98` passes `producer=("tests.unit.test_domain_adapter", "0")`. |

**Considered and not changed:**
- `write_models` and `case_target` signatures: D1 and D5 make them sufficient;
- scenario-dependent inputs: PLANNED as honesty's additive `scenario_inputs`
  when a domain needs them;
- `publish` and `depends_on`: they still wait for cross-domain rules.

### 8.2 The non-provisional statement

`base.py:17-19` becomes:

"Stable since the electrical domain: two production domains use it, one
CAD-first (mechanical) and one artefact-first (electrical). Changes since the
foundation: `Extraction.producer`. A further change lists its reason and the
matching change to every registered adapter and to the test fixture."

Plan §11 and the docs' Limitations section change to match.

### 8.3 Registry side effects (not protocol changes)

- `domains/__init__.py:28` becomes
  `REGISTRY = {"mechanical": MechanicalAdapter(), "electrical": ElectricalAdapter()}`.
- The doctest at lines 72-74 becomes `[:2]` → `['AVAILABLE', 'NOT_APPLICABLE']`.
- `robotic_joint_001/dataset-item.json` has one entry regenerated. It is the
  only diff in that item:
  - it was `NOT_IMPLEMENTED` (lines 105-107);
  - it becomes `NOT_APPLICABLE`, "the electrical adapter reads spice, which
    this sample does not have; this sample also lacks
    components/actuator/domains/electrical/torque_constant (UNKNOWN),
    components/actuator/domains/electrical/winding_resistance (UNKNOWN)".
- `test_domain_adapter.py:289-291` gains
  `self.assertEqual(status.pop("electrical"), "NOT_APPLICABLE")` before the
  `NOT_IMPLEMENTED` set check. This strengthens the test, and its docstring
  (lines 12-15) is updated. It is the only existing assertion edited, and it
  is not weakened.

---

## 9. Tests

**Conventions:**
- New test files import `ecad_model` inside tests or after a `sys.path` setup
  that needs no `noqa`, the pattern of `test_cad_dataset.py:26-27`.
- Expected values are typed by hand from the netlist text and the formulas,
  never obtained by calling the code under test.

**`require_ngspice()`** lives in `test_electrical_spice.py`. It needs
`NgspiceAdapter().capability()` to be available **and** to have a version.
Otherwise it raises `unittest.SkipTest(reason)`, or `AssertionError` when
`ECAD_REQUIRE_SPICE_TOOLS=1`, as `test_cad_dataset.py:34-41` does.

**The stand-in ngspice** (fast tests) follows the `_passing_icarus` pattern of
`test_domain_adapter.py:203-221`:
- it uses `mock.patch.dict("ecad_validation.cases.ADAPTERS", {"ngspice": StandIn})`;
- `StandIn.run` returns
  `parse_measurements(RECORDED_STDOUT, "", declared_measurements(deck)[0])[0]`;
- `RECORDED_STDOUT` is `synth/final/run1.out`, labelled "ngspice-47, macOS
  arm64, 2026-09-27", with tool version "stand-in 0".

### `tests/unit/test_spice_netlist.py` (fast: parser)

| # | Test | Asserts |
|---|---|---|
| N1 | `test_the_committed_netlist_parses_to_its_hand_read_elements` | the §1.5 table: 10 elements, their terminals, SI values, 2 models, title |
| N2 | `test_scale_suffixes_are_read_exactly` | `t g meg k m u n p`, exponents, `.5`, `5.`; `470u == float("470e-6")`; `30.001m == float("30.001e-3")` |
| N3 | `test_values_spice_would_misread_are_refused` | `1M 1MEG 1F 1f 10uF 470uF 2kohm 1ms 1mil 1e3k 1e999 nan inf 1_0 470µ` |
| N4 | `test_directives_that_read_files_run_commands_or_belong_to_the_adapter_are_refused` | one subTest per §3.1 directive; the message names the directive, its class and the line |
| N5 | `test_continuations_and_characters_spice_would_reinterpret_are_refused` | `+` after a complete line; ``; $ ' " { } ` ! \`` |
| N6 | `test_element_letters_outside_r_c_v_i_s_are_refused` | each refused letter named with its reason; lowercase designators |
| N7 | `test_sources_are_piecewise_linear_with_increasing_times` | DC, PULSE, SIN, EXP, AC; odd count; fewer than 4 numbers; first time ≠ 0; non-increasing times |
| N8 | `test_switch_models_state_every_parameter_once` | missing VH; unknown key; repeated key; type not SW; undefined model; model used twice; unused model |
| N9 | `test_names_are_canonical_unique_and_never_ground_aliases_or_par_nodes` | duplicate designator or model; uppercase node; `gnd`; `pa_0`, `pa_12`; `00`; 33-character name |
| N10 | `test_every_node_is_connected_twice_and_reaches_ground` | dangling node; node reached only through C/I; no ground; both terminals on one node |
| N11 | `test_the_title_line_is_never_a_card` | card-like title (case-insensitive), `.` title, blank title refused; prose title accepted |
| N12 | `test_the_file_ends_at_dot_end` | missing `.end`; text after `.end`; blank lines after it accepted |
| N13 | `test_input_bounds_and_encoding_are_exact` | at the limit accepted and one over refused, for bytes, line length, elements and PWL points; empty; NUL; CR; non-ASCII; LFS pointer |
| N14 | `test_the_deck_reader_accepts_only_the_adapters_own_lines` | the §4.2 deck is read; an inserted `.control`, an extra `.meas` or a second `.tran` is refused |
| N15 | `test_examples_in_the_spice_module` | doctests |

### `tests/unit/test_ngspice_adapter.py` (fast: `run_process` or `subprocess.run` mocked)

| # | Test | Asserts |
|---|---|---|
| G1 | `test_ngspice_runs_in_batch_mode_with_no_log_rawfile_or_case_arguments` | argv is exactly `[exe, "-b", "derived/electrical/x.cir"]`, even with `request.arguments` set |
| G2 | `test_measurements_are_read_as_ngspice_47_prints_them` | the recorded stdout gives the nine exact floats; the `at=` and `from= to=` suffixes; padded and unpadded names; TEMP and other lines are not taken |
| G3 | `test_a_declared_measurement_that_failed_is_absent_and_named` | recorded stderr; the summary names it; `execute_cases` gives `GOLDEN_METRICS_INCONCLUSIVE` for a case needing it |
| G4 | `test_duplicated_non_numeric_or_non_finite_values_are_not_metrics` | reported twice; `failed`; `nan`; `inf`; `1e999`; `1_0`. `execute_cases` writes an execution record without raising |
| G5 | `test_names_the_deck_does_not_declare_are_ignored` | an extra `foo = 1.0` stdout line; a name declared twice in the deck is excluded |
| G6 | `test_truncated_output_yields_no_metrics` | output built with `process._limited` → `INCONCLUSIVE OUTPUT_TRUNCATED`, `{}` |
| G7 | `test_a_nonzero_exit_fails_with_no_metrics` | rc 1 with measurement lines → `FAIL TOOL_EXITED_NONZERO`, `{}` |
| G8 | `test_other_process_outcomes_keep_their_verdicts` | UNAVAILABLE → `BLOCKED TOOL_NOT_INSTALLED`; TIMED_OUT → `INCONCLUSIVE` |
| G9 | `test_an_oversized_deck_is_neither_read_nor_run` | → `BLOCKED NETLIST_INPUT_TOO_LARGE`; `run_process` not called |
| G10 | `test_the_ngspice_version_comes_from_its_banner` | recorded banner → "47"; `** ngspice-36 : …` → "36"; no banner → `None` and available, then a PASS becomes `BLOCKED TOOL_VERSION_UNAVAILABLE` via `execute_cases` |
| G11 | `test_probes_of_other_tools_still_take_their_first_line` | kicad `8.0.1` and iverilog `Icarus Verilog version 12.0 (stable)` unchanged; `detect_capabilities()["ngspice"].version == "47"` |
| G12 | `test_a_version_probe_failure_gives_a_reason_the_receipt_accepts` | `VERSION_PROBE_ERROR:[Errno 13] …` → `VERSION_PROBE_ERROR`; `VERSION_PROBE_EXIT_-9` → `VERSION_PROBE_EXIT_NONZERO`; every code matches `^[A-Z][A-Z0-9_]*$`; the raw text is in the summary |
| G13 | `test_examples_in_the_ngspice_and_capabilities_modules` | doctests |

### `tests/unit/test_electrical_domain.py` (fast)

| # | Test | Asserts |
|---|---|---|
| M1 | `test_every_netlist_value_is_specified_by_the_netlist_and_names_no_part` | status, kind, ref, sha256 = the netlist's, and note, for each §1.5 facet |
| M2 | `test_no_rating_of_an_unselected_part_has_a_value` | the 8 UNKNOWN and 2 UNSPECIFIED facets, indexed `needed_by` electrical; no MEASURED, SIMULATED, ESTIMATED, DERIVED or AI_ASSUMPTION status anywhere |
| M3 | `test_the_supply_traces_to_the_product_sheet` | the drive facets cite the sheet by hash; V2 invariant 4 holds; a 60 V copy → `DOMAIN_MODEL_INCONSISTENT` |
| M4 | `test_a_circuit_member_needs_format_1_1_0` | 1.0.0 with `circuit` is invalid; a new kind in 1.0.0 is invalid; designator letter and element must match; a switch needs `cp`/`cn` and a model; the mechanical model is still valid; annotations 1.0.0 with `circuit_elements` are invalid |
| M5 | `test_annotations_add_names_kinds_and_ratings_but_never_netlist_values` | a restated `resistance` → `DATASET_INPUT_INVALID`; an unknown designator → invalid; an unannotated element gets kind from its letter |
| M6 | `test_only_the_series_precharge_supply_network_is_accepted` | each of C1–C8 violated once: V1 `SOURCE_REJECTED` naming the rule. One case is the connectivity mutation "C_BULK moved to n_f" |
| M7 | `test_v1_refuses_impossible_values_units_and_sequences` | each §3.4 rule, including a rating in `mV`; the committed model gives `[]` |
| M8 | `test_the_deck_is_the_model_with_the_adapters_analysis_and_measurements` | the §4.2 bytes, typed in the test |
| M9 | `test_v2_names_every_way_a_deck_can_disagree_with_its_model` | changed value; swapped terminal; dropped element; missing, extra or duplicated `.meas`; changed `.tran`; a facet sha that is not the netlist's |
| M10 | `test_references_are_the_closed_forms_written_out_here` | the 9 derivations against formulas in the test (relative 1e-12) for the committed model and the R_PRE = 1 Ω copy; `reference_inputs` exact sets |
| M11 | `test_a_reference_does_not_apply_where_its_assumptions_fail` | crossing after the bypass; unsettled before the load; unsettled fault window → `REFERENCE_NOT_APPLICABLE` |
| M12 | `test_each_metric_has_one_scenario_and_each_derivation_its_metric` | unknown scenario; scenario with parameters; wrong metric for a derivation; metric under a wrong scenario; unknown derivation → V1 `DATASET_INPUT_INVALID`; unit `mA` → compile refuses |
| M13 | `test_the_model_names_the_adapter_that_built_it` | the electrical manifest's model producer and `versions.engineering_model`; the mechanical manifest still `ecad_model.builder` / `1.0.0` |
| M14 | `test_the_committed_sample_checks_and_rebuilds_to_the_same_bytes` | `check == []`; a build on a copy is byte-identical; electrical `AVAILABLE` (the reason names the network class), mechanical `NOT_APPLICABLE`, seven `NOT_IMPLEMENTED`; model `derived_from` = [`source/servo_supply_001.cir`, `design/annotations.json`]; `versions.extraction == "none"`; `artifact_type == "spice_netlist"` |
| M15 | `test_the_committed_sample_validates_as_designed_with_recorded_ngspice_output` | with the stand-in: §6.3 in full; 16 schema-valid results; the three BLOCKED results measured by `v3.REF-EL-001` with 48.0, 0.0533906 and 372.465 |
| M16 | `test_a_tightened_limit_fails_and_only_a_real_requirement_can_pass` | REQ-EL-001 limit 4.0 → `FAIL`; `illustrative: false` → `PASS` |
| M17 | `test_the_limit_boundaries_are_exact` | the §6.4 stand-in boundaries on both operators, with tolerance folding |
| M18 | `test_each_null_status_of_a_rating_blocks_with_its_status_and_path` | ×3 statuses; schema-valid receipt |
| M19 | `test_a_rating_passes_only_when_specified_and_real_and_never_when_ai_assumed` | §6.4 AI and PASS paths |
| M20 | `test_without_ngspice_every_case_is_blocked_and_the_receipt_holds` | 13 cases `BLOCKED TOOL_NOT_INSTALLED` for `ecad-validator`; 3 `MISSING_REQUIRED_INPUT`; no `simulator_version` |
| M21 | `test_a_refused_netlist_gives_a_receipt_and_never_reaches_ngspice` | a `.control` copy: V1 `SOURCE_REJECTED`, V2–V4 `DERIVATION_NOT_AVAILABLE`; a stand-in that fails the test if called |
| M22 | `test_a_deck_edited_without_a_rebuild_is_divergent_and_not_counted` | V2 `DERIVATION_DIVERGED`; every entry `COMMITTED_CASE_STALE` with "its input derived/electrical/servo_supply_001.cir no longer reproduces" (`dataset.py:1253-1263`) |
| M23 | `test_the_cited_product_sheet_and_licence_are_rehashed` | a changed digest is reported by `check` |
| M24 | `test_results_trace_source_to_evidence_and_regenerate_identically` | netlist sha = model source = manifest artefact; each result's inputs SPECIFIED; the deck digest is in each execution's evidence; `regenerate_results` byte-identical |
| M25 | `test_dataset_bytes_are_never_converted_on_checkout` | `git check-attr text` is `unset` for every sample file, `LICENSE` and the sheet |
| M26 | `test_the_ngspice_requirement_turns_a_skip_into_a_failure` | `require_ngspice` with the capability mocked, with and without the environment variable |

### `tests/unit/test_electrical_spice.py` (needs ngspice; mandatory in the `spice` job)

| # | Test | Asserts |
|---|---|---|
| S1 | `test_ngspice_reproduces_the_closed_forms` | the committed deck through `NgspiceAdapter`: the nine metrics within tolerance of the hand values; stdout identical over two runs; stderr empty; no `/` in stdout |
| S2 | `test_the_committed_sample_validates_as_designed` | §6.3 with real ngspice; the tool version equals the probe's and matches `^\d`; all fidelities `SIMPLIFIED`; evidence re-hashes; regeneration identical |
| S3 | `test_an_undersized_precharge_resistor_fails_the_inrush_requirement` | REQ-EL-001 `FAIL` at 40.6812 ± 1e-3; every V3 `PASS` |
| S4 | `test_a_bypass_that_closes_before_the_bus_is_charged_fails` | REQ-EL-002 `FAIL` at 31.2169 ± 1e-3; REF-EL-003 `REFERENCE_NOT_APPLICABLE` |
| S5 | `test_the_inrush_limit_at_its_boundary_with_real_ngspice` | 4.72 → WARNING; 4.71 → FAIL; 4.71 with tolerance 0.01 → WARNING |
| S6 | `test_the_parser_reads_every_value_form_as_ngspice_does` | differential (from honesty): a deck of resistors, one per accepted value form; the ngspice current equals 1/parsed value |
| S7 | `test_a_measurement_ngspice_cannot_make_is_named` | a crossing that never happens: metric absent, summary names it, case `INCONCLUSIVE` |

### Changes to existing tests (none weakened)

- **`test_ci_and_runner.py`:** add `test_spice_job_cannot_skip_silently`.
  - It slices from `"\n  spice:\n"` to `"\n  cad-dataset:\n"`.
  - It asserts `ECAD_REQUIRE_SPICE_TOOLS: "1"`, `apt-get install -y ngspice`,
    `run: python run_all_tests.py --tb=short`,
    `python tools/cad_dataset.py check datasets/cad/servo_supply_001`, and
    `validate`.
  - It asserts no `continue-on-error`.
- **`test_domain_adapter.py`:**
  - the fixture's `producer` (line 98);
  - the electrical pop (lines 289-291) and its docstring;
  - a new `test_the_manifest_names_the_fixture_as_its_model_producer`.
- **`test_engineering_model.py:1210`:** the doctest list adds `"spice"` and
  `"domains.electrical"`.

---

## 10. Mutants (`tests/mutation/run_mutations.py`)

**Harness changes:**
- Constants:
  - `SP`: `tools/ecad_model/spice.py`;
  - `EL`: `domains/electrical.py`;
  - `NG`: `adapters/ngspice.py`;
  - `CP`: `adapters/capabilities.py`;
  - `EN`, `EA`, `ER`, `EP`: the sample's netlist, annotations, requirements
    and provenance;
  - `MS`: `schemas/engineering-model/v1/engineering-model.schema.json`;
  - `NETLIST`, `NGSPICE`, `ELECTRICAL`, `SPICE`: the four new test files.
- `environment` (line 462) adds `ECAD_REQUIRE_SPICE_TOOLS="1"`.
- The suites (line 463) become
  `(FAST, ADAPTER, NETLIST, NGSPICE, ELECTRICAL, SPICE, SLOW)`.
- The module docstring says ngspice is needed.

**Rules:**
- A dataset mutant must leave the item buildable. The harness rebuilds it
  (lines 450-458), and a failed rebuild is `HARNESS`, not a kill (F3). So
  topology and format mutations are code mutants or test-built copies.
- Anchors are written with the code; each must occur exactly once (line 47).

| # | Name | File | Change | Killed by |
|---|---|---|---|---|
| 1 | spice-control-accepted | SP | `.control`/`.endc` skipped instead of refused | N4 |
| 2 | spice-include-accepted | SP | `.include`/`.lib` skipped | N4 |
| 3 | spice-milli-read-as-micro | SP | suffix `m` → exponent −6 | N1, N2 |
| 4 | spice-number-case-folded | SP | the number is matched on `token.lower()` | N3 (`1M`) |
| 5 | spice-unit-letters-ignored | SP | the number regex tail allows `[A-Za-z]*` | N3 (`470uF`) |
| 6 | spice-femto-accepted | SP | `f` added to the suffixes | N3 |
| 7 | spice-gnd-accepted | SP | `gnd` exclusion dropped | N9 |
| 8 | spice-par-node-accepted | SP | `pa_N` exclusion dropped | N9 |
| 9 | spice-after-end-ignored | SP | lines after `.end` skipped | N12 |
| 10 | spice-end-optional | SP | `.end` requirement dropped | N12 |
| 11 | spice-title-card-accepted | SP | title check dropped | N11 |
| 12 | spice-continuation-accepted | SP | `+` lines appended to the previous line | N5 |
| 13 | spice-dangling-node-allowed | SP | the "≥ 2 terminals" check dropped | N10 |
| 14 | spice-dc-path-unchecked | SP | ground reachability dropped | N10 |
| 15 | spice-duplicate-designator-accepted | SP | uniqueness check dropped | N9 |
| 16 | spice-switch-defaults-allowed | SP | required keys → {RON, ROFF} | N8 |
| 17 | spice-pwl-order-unchecked | SP | increasing-time check dropped | N7 |
| 18 | spice-writer-rounds-values | SP | `repr(v)` → `f"{v:.6g}"` | M8, M9 |
| 19 | el-extra-element-accepted | EL | rule C8 dropped | M6 |
| 20 | el-capacitor-anywhere | EL | rule C5 dropped | M6 (capacitor moved) |
| 21 | el-esr-left-out-of-references | EL | `+ R_E` dropped from R1 | M10, M15 (V3 FAIL) |
| 22 | el-ramp-read-as-step | EL | peak = V/R1 | M10, M15 |
| 23 | el-charge-level-changed | EL | `CHARGED_FRACTION = 0.9` → `1 - 1/math.e` | M8 (the deck text changes; references change consistently) |
| 24 | el-supply-current-sign-flipped | EL | `par('-i(` → `par('i(` | M8, S1, S2 |
| 25 | el-fault-measured-at-the-fault | EL | the fault `AT=` uses T_FLT | M8, S1 |
| 26 | el-steady-sampled-after-the-fault | EL | the steady `AT=` uses T_END | M8, S1 |
| 27 | el-settling-unchecked | EL | the applicability test returns true | M11 |
| 28 | el-scenario-pairing-unchecked | EL | the `METRIC_SCENARIO` check dropped | M12 |
| 29 | el-derivation-pairing-unchecked | EL | the `DERIVATION_METRIC` check dropped | M12 |
| 30 | el-metric-unit-wrong | EL | inrush `Metric("A", …)` → `"mA"` | M14 (build raises) |
| 31 | el-facet-unit-unchecked | EL | vocabulary unit check dropped | M7 (`mV` rating) |
| 32 | el-supply-sheet-invariant-off | EL | V2 invariant 4 dropped | M3 |
| 33 | el-netlist-hash-not-bound | EL | the netlist sha256 dropped from facet sources | M1, M9 |
| 34 | el-annotation-overrides-netlist | EL | a facet collision is allowed (annotation wins) | M5 |
| 35 | el-ratings-dropped | EL | annotation rating facets not merged | M2, M15 |
| 36 | el-precharge-resistor-changed | EN | `R_PRE n_f n_bus 10` → `1` | N1, M15 (recorded metrics against new references: V3 FAIL) |
| 37 | el-capacitance-plus-one-percent | EN | `470u` → `474.7u` | N1, M15 (REF-EL-003 FAIL) |
| 38 | el-inrush-limit-changed | ER | REQ-EL-001 `10.0` → `4.0` | M15 |
| 39 | el-illustrative-flag-cleared | ER | REQ-EL-001 `true` → `false` | M15 (PASS, expected WARNING) |
| 40 | el-operator-flipped | ER | REQ-EL-004 `">="` → `"<="` | M15 |
| 41 | el-rating-invented | EA | c_bulk `voltage_rating` null/UNKNOWN → 63.0/SPECIFIED | M2, M15 |
| 42 | el-sheet-digest-changed | EA | drive `rated_current` sha256 → another digest | M23, M14 |
| 43 | el-artifact-type-changed | EP | `spice_netlist` → `other` | M14 |
| 44 | ngspice-rawfile-requested | NG | argv adds `-r ngspice.raw` | G1, S1 |
| 45 | ngspice-log-requested | NG | argv adds `-o ngspice.log` | G1, S1 |
| 46 | ngspice-arguments-passed | NG | argv extends `request.arguments` | G1 |
| 47 | ngspice-suffix-refused | NG | the `(?:at\|from\|to)=` group removed | G2 |
| 48 | ngspice-duplicate-kept | NG | a duplicate is kept (last wins) | G4 |
| 49 | ngspice-non-finite-kept | NG | `math.isfinite` check dropped | G4 (`1e999`) |
| 50 | ngspice-python-number-spellings | NG | `NUMBER` pre-check dropped | G4 (`1_0`) |
| 51 | ngspice-failed-read-as-zero | NG | `failed` → 0.0 | G4 |
| 52 | ngspice-undeclared-names-read | NG | every `REPORTED` line is a metric | G5 |
| 53 | ngspice-truncation-ignored | NG | truncation check dropped | G6 |
| 54 | ngspice-parsed-on-failure | NG | metrics parsed when rc ≠ 0 | G7 |
| 55 | ngspice-oversize-deck-read | NG | size check dropped | G9 |
| 56 | ngspice-reason-unsanitised | NG | `_receipt_reason` returns its input | G12 |
| 57 | ngspice-version-first-line | CP | `VERSION_PATTERNS` entry removed | G10 |
| 58 | ngspice-version-invented | CP | no match → `"unknown"` | G10 |
| 59 | probe-pattern-for-every-tool | CP | `.get(adapter)` → `.get("ngspice")` | G11 |
| 60 | model-producer-hard-coded | D | `extraction.producer` → `("ecad_model.builder", BUILDER_VERSION)` | M13 |
| 61 | circuit-format-rule-dropped | MS | the top-level `allOf` removed | M4 |
| 62 | electrical-unregistered | DR | the REGISTRY entry removed | M14, `test_domain_adapter` status test |

The categories spec §23 names are all covered:
- requirements: 38–40;
- units: 3–6, 30, 31;
- component values: 36, 37;
- connectivity: 13, 14, 19, 20, and M6's copy;
- metadata: 42, 43, 60, 61;
- simulator outputs: 44–59;
- invalid input: 1–17.

**Acceptance:** zero survivors after a green baseline, with each kill naming
its test.

---

## 11. CI job and documentation

### 11.1 `.github/workflows/ci.yml`

The job is inserted **between** `validation-evidence` (lines 51-85) and
`cad-dataset` (line 87), so the existing slice test stays exact (F7). It is not
added to `release.needs` (line 139), and neither is `cad-dataset`.

```yaml
  spice:
    name: Electrical dataset (ngspice) and V0-V4
    runs-on: ubuntu-22.04
    env:
      # The electrical simulation tests skip without ngspice; here a skip is a failure.
      ECAD_REQUIRE_SPICE_TOOLS: "1"
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: tools/requirements.txt

      - name: Install ngspice
        # A system package, installed rather than assumed; the version each
        # receipt records is printed here too.
        run: sudo apt-get update && sudo apt-get install -y ngspice && ngspice --version

      - name: Install validation dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r tools/requirements.txt pytest

      - name: Complete test suite, electrical simulation tests mandatory
        run: python run_all_tests.py --tb=short

      - name: Committed derivation reproduces from the netlist
        run: python tools/cad_dataset.py check datasets/cad/servo_supply_001

      - name: V0-V4 receipt
        run: >-
          python tools/cad_dataset.py validate datasets/cad/servo_supply_001
          --output electrical-validation

      - name: Upload electrical evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: electrical-dataset-${{ github.sha }}
          path: electrical-validation/
          if-no-files-found: error
```

**Where each test runs:**
- In this job the CAD tests skip with a reason, since `ECAD_REQUIRE_CAD_TOOLS`
  is unset; `cad-dataset` covers them.
- The fast electrical tests (parser, adapter, stand-in receipt) run on all nine
  matrix legs.
- The apt ngspice version on ubuntu-22.04 is **Unknown**. It is not pinned
  (§13).

### 11.2 `.gitattributes`

```
datasets/cad/** -text
LICENSE -text
eRobotics_CAD_Design/robot_components/product_datasheet.md -text
```

All three are hash-bound or hash-cited, and M14 and M23 run on `windows-2022`.
Whether GitHub's Windows images enable `core.autocrlf` is **Unknown**; these
rules make it irrelevant. M25 asserts them.

### 11.3 Documentation

**New `docs/electrical-domain-v1.md`,** with the spec §28 headings:

| Heading | Content |
|---|---|
| What the domain is | |
| Supported inputs | the §3.1 grammar, and the accepted and refused tables |
| Engineering model | the §2.1 mapping |
| Supported simulators | ngspice batch, the version from the banner; LTspice and PSpice PLANNED, licensed, no adapter |
| Validation capabilities | the network class, windows, metrics, V1/V2 |
| Known limitations | 6-digit `.meas`; ideal elements; the fuse does not open and fault currents are prospective; one network class; steady ripple BLOCKED on data; SEC-1/SEC-2 residual; STATE-2 |
| Example | the three commands and the receipt table, run for real before this doc is committed |
| Dataset samples | |
| Requirements | |
| Expected outputs | |
| Evidence | the deck, execution records with raw stdout, what `noacct` removes |
| Training data | none (plan §15) |
| Future work | |

**`docs/cad-dataset-engineering-model-v1.md`:**
- Engineering model: `circuit`, the new kinds, format 1.1.0.
- Requirements: a pointer to the electrical vocabulary.
- Security:
  - the netlist refusals;
  - the Verified `.control` and `.spiceinit` facts, and `pa_N`;
  - the SEC-2 residual.
- Versioning: the D6 minor-version rule; the new producers; `results_version`
  doubles as a schema const.
- Limitations: the protocol is stable; two production domains.
- Adding a domain: `Extraction.producer`; the robotic joint paragraph (lines
  501-505) now says electrical is `NOT_APPLICABLE`.

**`datasets/cad/README.md`:**
- a `servo_supply_001` row;
- the corrected `robotic_joint_001` row;
- ngspice in Commands.

**`tools/requirements.txt`:** an ngspice note under "Not installable from PyPI"
(`sudo apt install ngspice`; `brew install ngspice`).

**`ECAD_MULTI_DOMAIN_DATASET_PLAN.md`:**
- §7.2:
  - RESULT-8 Verified and fixed;
  - ARCH-2 ngspice half fixed;
  - RESULT-2 ngspice path;
  - new SEC-2;
- §8.2: the ARCH-1 amendment;
- §9.3: the minor-version rule;
- §10 row 2: "ngspice not installed here" is stale;
- §11: non-provisional, with the change list;
- §16 and §17 counts;
- §21 item 4 markers;
- the Q8 note: the brief kept the layout.

**`MEMORY.md`:**
- Decisions, each with its rejected alternatives: D1, D2, D5, D6, D7, D8, D13.
- Traps:
  - `-r` disables `.meas`;
  - `.meas` prints 6 digits whatever `numdgt` says;
  - a failed `.meas` goes to stderr with exit 0;
  - `1M` is milli, `10uF` is 10 µ, `F` is femto;
  - `gnd` is ground;
  - ngspice reads past `.end` and accepts no `.end`;
  - the title line swallows a card;
  - `par()` owns the `pa_N` node names;
  - `.control shell` and a working-directory `.spiceinit` run under `-b`;
  - `noacct` makes stdout reproducible.

**`TASKS.md`:** T-012, carrying plan §21 item 4 and the §10 per-domain list
verbatim, every verification row `NOT RUN`.

**`CHANGELOG.md`:** an entry.

### 11.4 Commit order

All commits are local only, authored by kartikey1306, with no AI attribution
lines. Nothing is pushed.

1. `fix(ngspice)`: batch `.meas` capture from stdout, version from the banner,
   receipt-safe probe reasons. Files: `ngspice.py`, `capabilities.py`, tests
   G1–G13, mutants 44–59.
2. `refactor(domains)`: the adapter names its model's producer. Files:
   `base.py`, `dataset.py`, `mechanical.py`, the fixture, mutant 60. The
   mechanical manifest must be byte-identical.
3. `feat(electrical)`: schemas, `spice.py`, `domains/electrical.py`, the
   registry, the sample, the regenerated robotic-joint manifest,
   `.gitattributes`, tests N/M/S, mutants 1–43, 61–62.
4. `ci`: the `spice` job and its test.
5. `docs`: §11.3.

---

## 12. Status after this PR, if its verification passes

Every row is a target. Nothing is implemented, and the suite, the mutation run
and CI are all **NOT RUN**.

| Deliverable | Label | Evidence required, or reason |
|---|---|---|
| Sample `servo_supply_001` | IMPLEMENTED | M14, M15, S2; the deck Verified in scratch |
| Restricted SPICE parser (R, C, PWL V/I, S + `.model SW`) and its refusals | IMPLEMENTED | N1–N15, S6; mutants 1–18 |
| Model `circuit` member, format 1.1.0 | IMPLEMENTED | M4; mutant 61 |
| Deck writer, V1 sanity, V2 invariants | IMPLEMENTED | M7–M9 |
| Scenarios startup, steady_state, output_short (windows of one run) | IMPLEMENTED | S1, S2 |
| Scenario parameters, per-scenario decks | PLANNED | needs scenario-dependent inputs (D1) |
| 9 metrics (SIMPLIFIED), 9 V3 closed forms | IMPLEMENTED for the series-precharge class only | §5.3 Verified on ngspice-47 macOS; Linux apt ngspice NOT RUN |
| V4: WARNING ×4, BLOCKED ×3; FAIL, boundary, AI and PASS copies | IMPLEMENTED | M15–M19, S3–S5 |
| Invalid and boundary samples | PARTIAL | test-built, not committed items (spec §21) |
| Part-rating checks passing | BLOCKED | data: no real part is selected |
| Steady ripple; fuse I²t against a real part; NTC or thermal behaviour | BLOCKED | data: the drive's ripple is UNSPECIFIED; no parts |
| L, D, M, Q, X, B elements; DC/PULSE/SIN sources; AC analysis; subcircuits; other topologies; KiCad schematic → netlist | PLANNED | refused today |
| ARCH-2, ngspice half | IMPLEMENTED | G1–G9 |
| ARCH-2, `run_process` output copy; iverilog/kicad parsers | PLANNED | the digital and PCB PRs |
| RESULT-8 | IMPLEMENTED | G10, G11 |
| RESULT-2 | PARTIAL | the ngspice path only (G12); the general fix branch is not written |
| DomainAdapter non-provisional; SCOPE-15 list | IMPLEMENTED | one change (§8.1); M13; mechanical byte-identical except one domain-status entry |
| SEC-1 for SPICE | PARTIAL | parser plus canonical deck; `run_process` is no sandbox; SEC-2 open |
| SEC-2 runner guard | PLANNED | its own PR (§13.1) |
| STATE-2 | open (existing) | absolute executable path in execution records |
| CI `spice` job | PARTIAL | written and tested by the slice test; execution NOT RUN (read-only push access; local only) |
| ngspice version pinned in CI | BLOCKED | the runner's version is Unknown |
| Linux reproduction | PLANNED | a `python:3.12-slim` container with apt ngspice and the job's steps |
| Documentation (spec §28) | IMPLEMENTED | examples run before the claim |
| Mutation run, zero survivors (222 existing + 62 new) | NOT RUN | needs ngspice, OCP and MuJoCo together |
| LTspice, PSpice | PLANNED | licensed; open tools only; no adapter, no stub |
| Training records | PLANNED | plan §15 |
| Dataset move (Q8) | BLOCKED | maintainer decision |
| Independent review | NOT RUN | CLAUDE.md rule 4 |

---

## 13. Risks and open questions

### 13.1 Risks

1. **SEC-1 and a proposed SEC-2 (Verified facts).**
   - **The facts:** a `.control … shell` block runs under `-b`, and a
     `.spiceinit` in the working directory runs.
   - **The problem:** the runner executes the whole committed case document
     before it decides what counts (`dataset.py:1267`, filtering at 1277). A
     hand-edited committed deck, or a forged committed case whose inputs
     include a `.spiceinit`, would therefore run shell before being marked
     stale.
   - **What this PR does:** the parser and deck regeneration close the source
     path. V2 and `check` flag any edited deck. Plan R5 governs the rest
     (reviewed repository content only).
   - **The proposed SEC-2 rule, for its own PR on the foundation branch:**
     before `execute_cases`:
     - parse the committed document exactly as the engine does
       (`json.loads(bytes.decode("utf-8"))`);
     - if it would pass the engine's pre-execution checks (schema, gate,
       non-empty, unique ids), run it only if:
       - every case's `(adapter, inputs, arguments, settings)` equals some
         fresh case's, and
       - every derived input reproduces;
     - otherwise run nothing. Compiled entries become `COMMITTED_CASE_STALE`
       where their own case differs, or else a new `CASE_DOCUMENT_NOT_RUN`,
       which is added to `results.NOT_RUN_REASONS`;
     - hand documents the engine refuses anyway to it unchanged, so the
       ENGINE-1 tests keep their assertions;
     - bump `VALIDATOR_VERSION` to 1.1.0.
   - It narrows `MEMORY.md:66`, so it needs the maintainer's acceptance.
2. **ngspice version drift.**
   - The CI apt version is **Unknown** (Inferred: 36).
   - Its banner, `par()` in `.meas`, `noacct` and the stdout format are
     unverified there.
   - If the banner does not match, cases become `BLOCKED` loudly. If the
     numbers drift beyond tolerance, pin ngspice (a container, or a source
     tarball with a hash measured then). Tolerances are not widened without
     evidence.
3. **Numerical limits.** ngspice prints 6 digits. The tolerances rest on one
   platform. R_off terms under 1e-7 relative are invisible.
4. **"Electrical AVAILABLE" covers one network class.** The manifest reason and
   the docs name it.
5. **Windows line endings** are **Unknown** without `.gitattributes`. The rules
   make them irrelevant.
6. **Awkward names:**
   - `cad_components` lists circuit elements;
   - `tools/cad_dataset.py` and `datasets/cad/` hold a netlist sample;
   - `versions.extraction` reads "none";
   - `versions.simulation` is the empty-set digest;
   - the run environment records `constraints-cad.txt` (`dataset.py:1123`),
     which says nothing about ngspice.
7. **Mutation cost.** The harness now needs ngspice, OCP and MuJoCo on one
   machine.
8. **The committed mechanical manifest changes in one entry.** No derived
   number changes.

### 13.2 Open questions (maintainer)

| # | Question |
|---|---|
| Q8 | The layout stays `datasets/cad/`, against plan §21's move-with-the-first-non-mechanical-sample rule. The brief decided it for this PR. |
| ARCH-1 | Accept `components[].circuit` (§2.4)? |
| D6 | Accept the minor-version rule for in-document versions? |
| SEC-2 | Land the guard of §13.1 as its own foundation PR, before this PR's `validate` runs on anything unreviewed? |
| Exit code | Should ngspice exit ≠ 0 become `INCONCLUSIVE` (honesty's proposal)? It changes the adapter's contract, and `python_control` maps it to `FAIL` too. |
| SEC-1 | Add ngspice `-n` and a `.control`/`.include` deck screen in `NgspiceAdapter` (engine code, not a named defect)? |
| RESULT-2 | Order against `fix/version-probe-reason-codes`. The ngspice-local mapping is removed when it lands. |
| Q-E3 | Commit invalid and boundary samples as dataset items with expected receipts? |
| Pinning | Pin ngspice after the first CI run, or pin the runner image or a container? |
| Q6 | Coordinate with PR #31's eServo-200 `python_control` bus-current cases, so the two current figures are not read as contradicting each other. |
| Q4 | Every limit is illustrative; real requirements need a product owner. The sheet does not say whether 5 A is continuous or peak, or whether 200 W is input or output power. |

---

**Report (VERIFY.md format)**

- **Status:** design complete, nothing implemented.
- **Mode:** Architecture.
- **Files changed in the worktree:** none (`git status` empty at `042f934`).
- **Written:**
  - this file;
  - scratch evidence under `design-scratch/synth/`.

**Verification:**

| Check | Result |
|---|---|
| ngspice behaviours cited in §0.2, §3.1 and §7 | PASS (Verified) |
| Deck runs, determinism, no host path | PASS (Verified) |
| Closed forms against ngspice for the committed sample, the FAIL copy and two value variants | PASS (Verified) |
| Writer-error sensitivity | PASS (Verified) |
| Grammar prototype | PASS (Verified, scratch only) |
| Repository tests, mutation run, CI, Linux reproduction | NOT RUN |

**Assumptions:** the CI apt ngspice supports `noacct` and `par()` in `.meas`,
and prints an `ngspice-<n>` banner. All three are unverified there.

**Next step:** an independent review of D1, D5, D6 and SEC-2; then implement
the commits of §11.4 in order.
