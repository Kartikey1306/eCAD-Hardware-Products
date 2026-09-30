# Electrical domain v1

The electrical domain is the second production domain of issue #27, and the
first whose source artefact is not CAD. Its source of truth is a SPICE
netlist. A strict parser reads the netlist into the engineering model; the
adapter writes an ngspice deck from that model; ngspice runs the deck; and
the V0–V4 contract compares what it measured with closed-form references and
requirements:

```
source/<id>.cir ── ecad_model.spice (allow-list grammar) ──► derived/engineering_model.json
design/annotations.json (names, kinds, ratings) ───────────┘            │
                                         domains/electrical.write_deck  ▼
                                   derived/electrical/<id>.cir  (the deck ngspice runs)
requirements/requirements.json ──► validation/{golden,corners}/cases.json
                                                 │
                        case engine + NgspiceAdapter (`ngspice -b <deck>`)
                                                 │
                        receipt.json · evidence/ · results.json · report.md
```

ngspice never sees the netlist. It runs the committed deck, which `build`
wrote from the model, so every value it simulates is one the model records
with its source and status -- as long as the committed deck is still the
one the model regenerates, which `v2.dataset-reproduction` and `check`
compare byte for byte. A committed deck edited by hand still runs (plan
§7.2 SEC-2, Known limitations).
The dataset layout, gates and results are those of
[cad-dataset-engineering-model-v1.md](cad-dataset-engineering-model-v1.md);
this page covers what is specific to the electrical domain. The code is
`tools/ecad_model/spice.py` (the format layer),
`tools/ecad_model/domains/electrical.py` (the adapter) and
`tools/ecad_validation/adapters/ngspice.py` (the tool adapter). The design
it was built from, with the alternatives each decision rejected, is
[design/electrical-domain-design.md](design/electrical-domain-design.md).

Every statement marked **Verified** below was run on 2026-09-27, or for
what the review of the branch changed on 2026-09-28, on macOS arm64 with
Python 3.14.4 and ngspice-47 (`/opt/homebrew/bin/ngspice`).

## What the domain is

One network class, and nothing else: the supply input of a DC-powered drive.
A supply ramps once from 0 V, feeds a fuse (its cold resistance only), then a
precharge resistor with a voltage-controlled bypass switch across it, into a
rail with a bulk capacitor (and an optional series resistance), a
constant-current load that steps on, and a fault switch that shorts the rail.
Every stimulus is a piecewise-linear source in the netlist, so one transient
covers the whole sequence: hot plug, precharge, bypass, load step, short.

The adapter's `AVAILABLE` reason in the manifest names this class. A netlist
outside it is refused at extraction (V1 `FAIL SOURCE_REJECTED`) and never
reaches ngspice. "Electrical `AVAILABLE`" therefore means this class, not
circuits in general.

## Supported inputs

**One SPICE netlist per sample**, declared in `source/provenance.json` with
format `spice` (artefact type `spice_netlist`). It is read by
`ecad_model.spice.parse_netlist`, an allow-list, not a SPICE parser: anything
outside it is refused with the line and the reason (`NetlistRefused`, kind
`rejected`). Each refusal exists because ngspice reads the refused text as
something other than what it looks like; the Security section of
[cad-dataset-engineering-model-v1.md](cad-dataset-engineering-model-v1.md#security)
lists what was verified.

| Accepted | Form |
|---|---|
| Title | Line 1, always. Not blank, not starting with `.`, `+` or `*ng_script`, and not shaped like an element card |
| Comments, blank lines | `*` lines below the title, except `*#` |
| Resistor, capacitor | `R<id> NODE NODE VALUE`, `C<id> NODE NODE VALUE`, exactly four tokens (no `ic=`) |
| Voltage and current sources | `V<id> NODE NODE PWL(t0 v0 t1 v1 ...)`, `I<id> ...`: at least two points, at most `MAX_PWL_POINTS` (16), the first at time 0, times strictly increasing |
| Voltage-controlled switch | `S<id> NODE NODE NODE NODE MODEL`, exactly six tokens (no `on`/`off`), with its own `.model NAME SW(RON=v ROFF=v VT=v VH=v)`: all four keys, each once, no other; one switch per model, and every model used |
| End | `.end` alone on its line; only blank lines after it |
| Names | Designators `^[RCVIS][A-Z0-9_]{1,31}$`, unique; model names `^SW_[A-Z0-9_]{1,29}$`; nodes `0` or `^n_[a-z0-9_]{1,30}$` |
| Numbers | Digits with an optional fraction, then either an exponent or one lower-case scale suffix: `t g meg k m u n p`. `470u` is read as the one decimal literal `470e-6` |
| Connectivity | Node `0` present; no element with both main terminals on one node; every other node on at least two terminals; every node reaches `0` through resistors, voltage sources or switch main terminals |

| Refused | Why |
|---|---|
| `.include .inc .lib .endl` | reads another file |
| `.control .endc`, and any `*#` comment line | runs front-end commands, including `shell` |
| `.param .func .csparam` | expressions |
| `.subckt .ends`, `X` elements | subcircuits: PLANNED |
| `.options .option .temp .ic .nodeset .global` | changes simulator state |
| `.tran .ac .dc .op .noise .tf .sens .pz .four .meas .measure .print .plot .save .probe` | the analysis and measurements are written by the adapter |
| any other directive | unknown |
| `L` | an inductor: PLANNED |
| `B E F G H` | behavioural or controlled sources evaluate expressions |
| `A N` | code models and OSDI devices load a library |
| `D Q M J K T U O W Y Z P` | a device this domain does not model |
| DC, bare-value, `PULSE`, `SIN`, `EXP`, `AC` sources | PLANNED |
| `+` continuation lines | they join the line before |
| `;` `$` `'` `"` `{` `}` `` ` `` `!` `\` | inline comments, expressions, quoting or escapes |
| upper-case suffixes, `f`/`F`, trailing unit letters, `mil`, an exponent with a suffix, a non-finite value | ngspice misreads them (`1M` is milli, `10uF` is 10 µ) |
| node `gnd`, nodes `pa_<digits>` | `gnd` is ground to ngspice; `par()` in a `.meas` creates nodes `pa_00`, `pa_01`, … and takes over a netlist node of that name |
| any other node name without the `n_` prefix, any model name without `SW_` | in a `.meas` ngspice-47 reads `v(time)` as the time axis, `v(all)` and `v(allv)` as another vector and `v(alli)` as none, crashes on a node `temper`, and stops on `limit`, `gauss`, `agauss`, `unif` and `aunif` inside `par()`; a model `TEMPER` crashes it and a model `GND` is never found (**Verified**, 2026-09-28: 12 of 174 probed names misread as nodes and 2 as models, none with the prefixes). With the rail named `time`, a real limit "bus peak ≤ 45 V" passed at 0.1 |
| a title card, a missing `.end`, text after `.end`, a dangling node, a node with no DC path to ground | ngspice would drop, read on, or accept them |
| CR, NUL or any byte outside printable ASCII, tab and LF; a Git LFS pointer; more than 1 MiB, 1024 characters on a line or 1000 elements; an empty file | the file-level limits |

**`design/annotations.json`** (format 1.1.0) adds what a netlist cannot
carry, under `circuit_elements` keyed by designator: a name, a kind (`fuse
resistor capacitor switch voltage_source current_source other`) and the
ratings of the part the element stands for. It may not restate or add a
value the netlist states (`resistance`, `capacitance`, the waveforms and the
switch parameters): the deck is written from the netlist's values alone.
`components_without_cad` adds components with no element (here the drive the
supply powers), and `relationships` relates them. Annotations with
`materials`, `parts`, `joints` or `attachments` are refused. An inconsistent
annotation is V1 `FAIL DATASET_INPUT_INVALID`; a netlist title longer than
the deck's `* <title>` line can carry (`MAX_LINE_CHARS - 2`, 1022
characters) is `FAIL SOURCE_REJECTED`, like any other refused netlist.

## Engineering model

The model is format 1.1.0 (`ecad_model.CIRCUIT_MODEL_VERSION`), written by
`ecad_model.domains.electrical` `1.0.0 (ecad_model.spice 1.0.0)`, which the
manifest records as the model's producer and as `versions.engineering_model`.

| Spec §7 concept | Where it is |
|---|---|
| Circuit | The model of a sample whose primary domain is `electrical`: `design.name` is the netlist title, `design.sources` the netlist by path, format `spice` and SHA-256 |
| Component | One per netlist element, in netlist order, `component_id` = the designator in lower case, then the annotations' components without an element. `cad_ref`, `material`, `geometry`, `physical` and `placement` are `null` |
| Component type | `kind` (`fuse resistor capacitor switch voltage_source current_source`, new in 1.1.0) and `circuit.element` (`resistor capacitor voltage_source current_source voltage_controlled_switch`) |
| Node, connectivity | `circuit.terminals`: `p` and `n`, plus `cp` and `cn` for a switch, each a node name, `"0"` being ground; `circuit.model` is a switch's `.model` name |
| Net | Derived: the terminals that name one node. Not stored |
| PowerRail, Input, Output | The roles of the network class (below): the supply is the input, the rail and the load are the output. Not stored fields |
| resistance, capacitance | Facets `resistance` [ohm] and `capacitance` [F] |
| Sources and switches | `waveform_time` [s] with `waveform_voltage` [V] or `waveform_current` [A], as vectors; `on_resistance`, `off_resistance` [ohm]; `threshold_voltage`, `hysteresis_voltage` [V] |
| ComponentRating | Facets from the annotations: `voltage_rating` [V], `current_rating` [A], `power_rating` [W], `melting_i2t` [A^2*s], `breaking_capacity` [A], `pulse_energy_rating` [J], `ripple_current_rating` [A] |
| inductance | PLANNED: `L` elements are refused |

Every netlist value is `SPECIFIED`, with source kind `design_annotation`
citing the netlist by path and hash, and the note "`<DESIGNATOR> <facet>` as
the netlist states it, not a rating of any part". Every rating of a part
nobody has selected is `UNKNOWN`; a value the cited product sheet is silent
on is `UNSPECIFIED`. There is no extraction file: the model is built from
the parsed netlist directly, so `versions.extraction` is `none`. The
relationships are `contains` from the design to each circuit component, with
the netlist as source, and the annotations' own.

Why topology is in the model (ARCH-1, amended in the plan §8.2): the
protocol hands the deck writer, V1, V2 and the closed forms only the model,
so without terminals the deck could not be a function of the model.

## Supported simulators

| Simulator | State |
|---|---|
| ngspice, batch mode | IMPLEMENTED. `ngspice -b <deck>` and nothing else: case arguments never reach the command line. The version is read from the `--version` banner (`** ngspice-47 : Circuit level simulation program` gives `47`); a banner the pattern does not match gives no version, and the case engine then turns a `PASS` into `BLOCKED TOOL_VERSION_UNAVAILABLE`. The adapter's tests replay the recorded output of ngspice-36 and 44.2 as well as 47 |
| LTspice, PSpice | PLANNED. Licensed tools; the core MVP uses open tools only. No adapter and no stub exist |

**How metrics are read.** The metrics are the `.meas` results the deck
declares, taken from stdout: a declared name becomes a metric only when
exactly one stdout line reports it and its value is a finite number in plain
SPICE decimal notation. A measurement ngspice could not make is absent from
stdout and named on stderr, with exit status 0; a name printed twice has no
single value; neither becomes a metric, and the summary names each. The
case's comparator, not the adapter, then decides what a missing metric means
(`INCONCLUSIVE`). Other outcomes:

| ngspice run | Verdict | Reason |
|---|---|---|
| Not installed | `BLOCKED` | `TOOL_NOT_INSTALLED` |
| Deck over 1 MiB | `BLOCKED`, not run | `NETLIST_INPUT_TOO_LARGE` |
| Timed out (300 s) | `INCONCLUSIVE` | `TOOL_TIMED_OUT` |
| Exit status not 0 | `FAIL`, no metrics | `TOOL_EXITED_NONZERO` |
| Output cut by the capture limit | `INCONCLUSIVE`, no metrics | `OUTPUT_TRUNCATED` |
| A version probe error such as `VERSION_PROBE_ERROR:<message>` | `BLOCKED` | a reason code the receipt accepts (`VERSION_PROBE_ERROR`, `VERSION_PROBE_EXIT_NONZERO`), the raw text in the summary |

## Validation capabilities

**The network class** (`supply_input_roles`): each rule is named when a
netlist breaks it.

| Rule | Requirement |
|---|---|
| C1 | Exactly one voltage source from ground ramps once, (0, 0) to (t_r, V) with t_r, V > 0: the supply |
| C2 | The supply's node connects only the supply and one resistor to a node other than ground: the fuse |
| C3 | The fuse's other node connects only the fuse, one resistor (the precharge limiter) and one switch (its bypass), both ending on one rail node other than ground |
| C4 | The bypass's `cn` is ground, and its `cp` is driven only by one voltage source from ground stepping (0, 0), (t_b, 0), (t_b + e_b, h_b) |
| C5 | Exactly one capacitor on the rail, to ground or through one resistor to ground (its series resistance) |
| C6 | Exactly one current source from the rail to ground, stepping (0, 0), (t_l0, 0), (t_l1, I_L): the load |
| C7 | Exactly one other switch from the rail to ground, commanded like the bypass: the fault |
| C8 | No other element |

The transient must also fit the resource guard: T_END / TMAX may not exceed
1 000 000 steps, or extraction refuses it (the committed sample needs
110 000). Extraction also refuses a circuit the deck's windows cannot
measure (`_unmeasurable`): a resistance, capacitance or switch resistance
that is not positive (the closed forms divide by them); a supply ramp still
rising at the bypass command, where the precharge windows end; and a fault
switch whose command never exceeds VT + VH, or that closes too late for the
rail to settle, 30 time constants of C·(R_E + R_c ‖ R_on,F), before T_END,
so that `fault_input_current_a` would read the current before (or during)
the short. Each is V1 `FAIL SOURCE_REJECTED`, not a V1 sanity finding,
because V1's findings do not stop the cases: with V_FLT rising over 100 ms
the switch closed at 150 ms, after T_END, V1 passed and a real limit of
10 A on the fault current passed at the pre-fault 4.17 A (review finding
CS-2). The bypass's timing is a V1 finding (it must close before the load
steps on), and the forms that need the rail settled after it say they do
not apply.

**Scenarios are windows of the one transient.** With T_BYP the bypass
command time, T_FLT the fault command time and T_END = T_FLT + 10 ms:
`startup` covers [0, T_FLT], `steady_state` is the instant T_FLT (a PWL
breakpoint, before the fault switch closes), and `output_short` is T_END. A
scenario carries only its name
(`schemas/engineering-model/v1/electrical-vocabulary.schema.json`), and every
case runs the same deck.

**Ten metrics**, all `SIMPLIFIED` (ideal sources, the fuse as a fixed
resistance, ideal switches, a capacitor with a series resistance only, a
constant-current load, no temperature, no parasitics):

| Metric | Unit | Scenario | Measured as | Closed form (V3) |
|---|---|---|---|---|
| `inrush_peak_current_a` | A | startup | `MAX` of the supply current over [0, T_BYP] | `precharge_peak_current` |
| `inrush_i2t_a2s` | A^2*s | startup | `INTEG` of the squared supply current over [0, T_BYP] | `precharge_i2t` |
| `bus_charge_time_s` | s | startup | `WHEN` the rail first reaches 0.9 × V | `precharge_charge_time` |
| `bus_voltage_at_bypass_v` | V | startup | rail voltage at T_BYP | `precharge_bus_voltage` |
| `bus_peak_voltage_v` | V | startup | `MAX` of the rail voltage over [0, T_FLT] | `settled_no_load_bus_voltage` |
| `steady_bus_voltage_v` | V | steady_state | rail voltage at T_FLT | `steady_bus_voltage` |
| `steady_input_current_a` | A | steady_state | supply current at T_FLT | `steady_input_current` |
| `steady_fuse_power_w` | W | steady_state | fuse voltage × supply current at T_FLT | `steady_fuse_power` |
| `fault_input_current_a` | A | output_short | supply current at T_END | `settled_fault_input_current` |
| `startup_peak_current_a` | A | startup | `MAX` of the supply current over [0, T_FLT], the surge when the bypass closes included | `startup_peak_current` |

The closed forms (`electrical.reference_value`, written out in its
docstring) are computed from the model's values alone, on a code path
separate from the deck writer and the simulator, so a deck-writing or
simulator error shows up as a golden mismatch. Until the bypass closes,
the four precharge forms see the open fault switch's off resistance across
the rail as a Thevenin source (review finding CS-4: with a valid ROFF of
1 kΩ they had failed REF-EL-002 to 004; with it folded in they agree with
ngspice-47 at 1 kΩ, 100 Ω and the committed 1 GΩ, **Verified**
2026-09-28). The inrush metrics stop at T_BYP; `startup_peak_current_a`
runs to T_FLT, so the surge when an early bypass closes is seen (CS-5: a
bypass at 14.5 ms drew 28.3 A that no metric measured, and REQ-EL-001
passed). Its form is the larger of the precharge peak and the settled load
current, when the surge as the bypass closes is smaller than both.

A form that does not apply raises `ReferenceBlocked`, and V3 reports
`REFERENCE_NOT_APPLICABLE`: the charge-time form when the rail crosses
0.9 × V during the ramp or after T_BYP, or never; the settled forms, and
the startup peak, when their window is shorter than 30 time constants;
the startup peak when the bypass surge is the largest current, because
ngspice samples that step at its first time point after the switch
closes (28.3205 A against the form's 28.3286 A at 14.5 ms, 3e-4 to 8e-4
low on the variants tried); and any form that cannot be evaluated on the
model's values (a division by zero, an overflow) or gives a value that is
not finite -- values extraction refuses, reached only by a model built
some other way. A null-status input gives `MISSING_REQUIRED_INPUT`.

**V1** (`sanity_problems`, `DOMAIN_SANITY_FAILED`): every electrical facet is
in the domain's vocabulary with that vocabulary's unit; resistances,
capacitances and switch on-resistances are positive (extraction already
refuses a netlist whose values are not, so through `validate` this reports
only a model built some other way); a switch's off
resistance exceeds its on resistance, its hysteresis is not negative and its
threshold exceeds its hysteresis, so it starts open; each command's high
level exceeds VT + VH, so the switch closes; every known rating is positive;
and the sequence the windows assume holds: the ramp ends before the bypass
command, the bypass closes before the load steps on, and the load is fully on
before the fault command.

**V2** (`invariant_problems`, `DOMAIN_MODEL_INCONSISTENT`): the deck the runner
regenerates from the fresh model -- not the committed deck -- is read back
with the netlist grammar (`spice.read_deck`); its title, its elements
(designator, element, terminals, model, values compared as exact floats)
and every line of the adapter's own section must equal what the model
calls for; every netlist value cites the netlist by path and hash; and a
supply that powers a component with a stated `supply_voltage` settles at
that voltage (here V_IN's 48 V against the eServo-200 sheet's 48 V). These
invariants check the deck writer against the reader and the model. Only
the domain-neutral `v2.dataset-reproduction` reads the committed deck: it
compares it byte for byte (comparator `exact`), so a committed deck edited
without a rebuild fails reproduction while the model invariants still pass
(`test_a_deck_edited_without_a_rebuild_is_divergent_and_not_counted`).

## Known limitations

- **One network class** (C1–C8). Other topologies, `L`, diodes and
  transistors, subcircuits, DC/PULSE/SIN sources and AC analysis are refused.
- **Ideal elements.** The fuse is a fixed resistance and never opens, so the
  fault current is prospective; the switches are ideal; the capacitor has a
  series resistance only; the load is a constant current; there is no
  temperature and no parasitic.
- **`.meas` precision.** ngspice-47 prints six significant digits, and
  `.options numdgt=12` does not change that (**Verified**: a 1 V / 3 Ω probe
  printed `3.33333e-01`). The recorded outputs of ngspice-36 and 44.2 in
  `tests/unit/test_ngspice_adapter.py`, of the nine-measurement deck
  committed on 2026-09-27, print seven of the nine values to seven digits.
  The tolerances are at least 20 times the deviation measured on ngspice-47
  (20.94 for the fault current; Example, below) and were set on that one
  platform. The nine references of 2026-09-27 also passed on real
  ngspice-36 and 44.2 in arm64 Linux containers (**Verified** at `f6dee36`,
  `TASKS.md`); the tenth, and the precharge goldens as the fault switch's
  off resistance moved them (by 2e-12 to 3e-8 relative), have been run on
  ngspice-47 only, and nothing on the x86_64 CI runner.
- **No part rating can pass.** Every rating is `UNKNOWN` because no part is
  selected, and every limit is illustrative, so the sample's receipt is at
  best `BLOCKED` and never eligible for ebuild.
- **Steady ripple is `BLOCKED` on data.** The drive's input ripple current
  and switching frequency are `UNSPECIFIED`: the eServo-200 sheet states
  neither. No ripple metric exists.
- **ngspice's stdout is not identical run to run.** A run can write a
  progress report, ` Reference value : <time>`, whose value differs between
  runs; `.options noacct` does not remove it (**Verified**: two sequential
  runs of the committed deck printed `7.83155e-02` and `8.02525e-02`, their
  measurement lines identical). ngspice-36 writes the report to stderr
  instead, and the case engine keeps a run's stderr among its check's
  findings (**Observed** in an ubuntu:22.04 arm64 container under load:
  two or three lines on every run). The execution records of two runs, and
  on 36 their findings, can therefore differ in that line. Whether to add
  `norefvalue`, which removed the report on 36, 44.2 and 47 alike, is plan
  §20 Q11.
- **SEC-1 and SEC-2 residual.** `run_process` is process hardening, not a
  sandbox. The parser keeps what a netlist can carry out of the deck
  `build` writes, but ngspice runs the committed deck, which equals that
  deck only while `v2.dataset-reproduction` passes. The runner executes a
  committed case document, and the committed deck it names, before it
  decides which cases count: a hand-edited deck with a `.control` `shell`
  block ran during `validate` (**Verified** by the review, 2026-09-28), and
  a forged case document could name other inputs, before either is marked
  stale. The same holds for the Python case scripts of the mechanical
  domain. The guard that would close it (plan §7.2 SEC-2, §20 Q14) is a
  maintainer's decision and is not implemented; until then only reviewed
  repository content may be validated (plan §20 R5).
- **STATE-2.** Execution records and the receipt's `tools[]` carry the
  absolute path of the ngspice executable (plan §7.2, open).
- **The CI ngspice is unpinned and its version Unknown** until the `spice` job
  runs (plan §20).
- **Awkward names.** `tools/cad_dataset.py` and `datasets/cad/` hold a
  netlist sample; results call circuit elements `cad_components`;
  `versions.simulation` is the digest of an empty set of scripts; the run
  environment records the digest of `tools/constraints-cad.txt`, which says
  nothing about ngspice.

## Example

Run on a clean clone of `ec37115` (macOS arm64, Python 3.14.4, ngspice-47,
2026-09-28). The output directory is shown as `<dir>`; nothing else is
edited. The `build` shown is the one run on 2026-09-27; `check` now says
the same, and `build` writes the same five files.

```console
$ python3 tools/cad_dataset.py check datasets/cad/servo_supply_001
datasets/cad/servo_supply_001: every hash matches and every derived file reproduces from the sources
$ python3 tools/cad_dataset.py build datasets/cad/servo_supply_001
wrote datasets/cad/servo_supply_001/derived/engineering_model.json
wrote datasets/cad/servo_supply_001/derived/electrical/servo_supply_001.cir
wrote datasets/cad/servo_supply_001/validation/golden/cases.json
wrote datasets/cad/servo_supply_001/validation/corners/cases.json
wrote datasets/cad/servo_supply_001/dataset-item.json
$ git status --short
$ python3 tools/cad_dataset.py validate datasets/cad/servo_supply_001 --output <dir>
{
  "execution_complete": false,
  "gates": {
    "V0": "PASS",
    "V1": "PASS",
    "V2": "PASS",
    "V3": "PASS",
    "V4": "BLOCKED"
  },
  "overall_verdict": "BLOCKED",
  "product": "datasets:servo_supply_001"
}
report: <dir>/report.md
```

All three exited 0; the rebuild left the tree unchanged. The receipt is not
eligible for ebuild; `results.json` holds 18 results bound to the receipt's
digest, and all 90 evidence entries (47 distinct digests) re-hash. The
requirements table of `report.md`:

| Requirement | Kind | Metric | Measured | Verdict | Why |
|---|---|---|---|---|---|
| REF-EL-001 | reference | `inrush_peak_current_a` | 4.71663 A | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-002 | reference | `inrush_i2t_a2s` | 0.0533906 A^2*s | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-003 | reference | `bus_charge_time_s` | 0.0109244 s | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-004 | reference | `bus_voltage_at_bypass_v` | 47.9147 V | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-005 | reference | `bus_peak_voltage_v` | 48 V | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-006 | reference | `steady_bus_voltage_v` | 47.875 V | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-007 | reference | `steady_input_current_a` | 4.16667 A | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-008 | reference | `steady_fuse_power_w` | 0.347223 W | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-009 | reference | `fault_input_current_a` | 372.465 A | PASS | GOLDEN_COMPARISON_PASSED |
| REF-EL-010 | reference | `startup_peak_current_a` | 4.71663 A | PASS | GOLDEN_COMPARISON_PASSED |
| REQ-EL-001 | illustrative requirement | `inrush_peak_current_a` | 4.71663 A | WARNING | REQ-EL-001 is illustrative: not a customer, safety or certification requirement |
| REQ-EL-002 | illustrative requirement | `bus_voltage_at_bypass_v` | 47.9147 V | WARNING | REQ-EL-002 is illustrative: not a customer, safety or certification requirement |
| REQ-EL-003 | illustrative requirement | `steady_input_current_a` | 4.16667 A | WARNING | REQ-EL-003 is illustrative: not a customer, safety or certification requirement |
| REQ-EL-004 | illustrative requirement | `steady_bus_voltage_v` | 47.875 V | WARNING | REQ-EL-004 is illustrative: not a customer, safety or certification requirement |
| REQ-EL-005 | illustrative requirement | `bus_peak_voltage_v` | 48 V (measured by v3.REF-EL-001) | BLOCKED | UNKNOWN: components/c_bulk/domains/electrical/voltage_rating |
| REQ-EL-006 | illustrative requirement | `inrush_i2t_a2s` | 0.0533906 A^2*s (measured by v3.REF-EL-001) | BLOCKED | UNKNOWN: components/r_f1/domains/electrical/melting_i2t |
| REQ-EL-007 | illustrative requirement | `fault_input_current_a` | 372.465 A (measured by v3.REF-EL-001) | BLOCKED | UNKNOWN: components/r_f1/domains/electrical/breaking_capacity |
| REQ-EL-008 | illustrative requirement | `startup_peak_current_a` | 4.71663 A | WARNING | REQ-EL-008 is illustrative: not a customer, safety or certification requirement |

Every case runs the same deck, so a requirement blocked only by its limit
still reports the value another check measured for the same metric, and
names that check.

**ngspice-47 against the closed forms**, the golden stored to 12 significant
figures (**Verified**, 2026-09-28: the committed deck run with ngspice-47,
twice, identical stdout and empty stderr; the goldens of
`validation/golden/cases.json`; each difference and ratio computed in
decimal from the printed value and the stored golden):

| Metric | ngspice-47 | Closed form | \|difference\| | Tolerance | Tolerance / difference |
|---|---|---|---|---|---|
| `inrush_peak_current_a` | 4.71663 | 4.71663002765 | 2.8e-8 | 1e-4 | 3617 |
| `inrush_i2t_a2s` | 0.0533906 | 0.0533907681653 | 1.7e-7 | 1e-4 | 595 |
| `bus_charge_time_s` | 0.0109244 | 0.010924434697 | 3.5e-8 | 1e-6 | 28.8 |
| `bus_voltage_at_bypass_v` | 47.9147 | 47.9147184047 | 1.8e-5 | 1e-3 | 54.3 |
| `bus_peak_voltage_v` | 48.0000 | 47.9999999986 | 1.4e-9 | 1e-3 | 714286 |
| `steady_bus_voltage_v` | 47.8750 | 47.8750415236 | 4.2e-5 | 1e-3 | 24.1 |
| `steady_input_current_a` | 4.16667 | 4.16667004787 | 4.8e-8 | 1e-4 | 2089 |
| `steady_fuse_power_w` | 0.347223 | 0.347222785757 | 2.1e-7 | 1e-5 | 46.7 |
| `fault_input_current_a` | 372.465 | 372.464522495 | 4.8e-4 | 1e-2 | 20.9 |
| `startup_peak_current_a` | 4.71663 | 4.71663002765 | 2.8e-8 | 1e-4 | 3617 |

The first four closed forms are those of the design with the open fault
switch's 1 GΩ folded in, which moves them in the eighth to twelfth figure
(the design's 4.71663002764, 0.0533907676223, 0.0109244343789 and
47.9147188794). A scratch computation written apart from the adapter
(`_closed_forms` in `test_electrical_domain.py` follows it) agrees to the
digits printed.

## Dataset samples

One sample, [`datasets/cad/servo_supply_001`](../datasets/cad/servo_supply_001):
the 48 V supply input of the eServo-200 servo drive, a self-authored MIT
testbench in which no element is a real part.

| File | Written by | Holds |
|---|---|---|
| `source/provenance.json` | hand | domain `electrical`, the netlist as format `spice`, the MIT licence cited by the `LICENSE` digest, created and collected 2026-09-27 |
| `source/servo_supply_001.cir` | hand | the source of truth: V_IN 0 → 48 V in 100 µs; R_F1 20 mΩ; R_PRE 10 Ω with S_BYP across it (commanded at 30 ms); C_BULK 470 µF with R_ESR 50 mΩ; I_LOAD 4.16667 A from 40 ms (200 W / 48 V); S_FLT shorting the rail through 100 mΩ at 100 ms. Its comments say which values come from the eServo-200 sheet, that none is a part's rating, and that taking the sheet's 200 W as the drive's input power is an assumption: the sheet does not say input or output |
| `design/annotations.json` | hand | element names and kinds; eight `UNKNOWN` ratings of the unselected fuse, resistor, bypass device and capacitor; the eServo-200 drive with its 48 V, 5 A and 200 W from the product sheet (cited by hash), whose notes say what the sheet leaves open and what is assumed: whether 5 A is continuous or peak and bounds the input current (the sheet gives it for the power stage), and whether 200 W is input or output power; two `UNSPECIFIED` facets the sheet is silent on; `drive powered_by v_in` |
| `requirements/requirements.json` | hand | 10 references and 8 illustrative requirements (below) |
| `derived/engineering_model.json` | `build` | 11 components, 10 null-status values indexed as needed by electrical |
| `derived/electrical/servo_supply_001.cir` | `build` | the deck ngspice runs |
| `validation/golden/cases.json`, `validation/corners/cases.json` | `build` | 10 V3 cases; 5 V4 cases (the 3 rating limits are blocked when compiled) |
| `dataset-item.json` | `build` | the manifest: electrical `AVAILABLE`, mechanical `NOT_APPLICABLE`, the other seven `NOT_IMPLEMENTED` |

There is no `simulation/` directory (no script runs) and no per-sample README
(`check` reports any file the manifest does not record). Invalid and boundary
inputs are built by the tests as copies, not committed.

## Requirements

`requirements/requirements.json` follows
`engineering-model/v1/engineering-requirements`; every entry has domain
`electrical` and a scenario the vocabulary names, and the adapter also
refuses a metric under another scenario than the one it is measured in and a
derivation paired with another metric.

- **References** REF-EL-001 to 010: one per metric, each comparing ngspice
  with its closed form within the absolute tolerance above. Their source is
  model verification, not a design requirement.
- **Requirements**, all `illustrative: true` and chosen to exercise the
  pipeline, not customer, safety or certification requirements:

| Id | Component | Limit | Source of the limit |
|---|---|---|---|
| REQ-EL-001 | r_pre | inrush peak ≤ 10 A | example |
| REQ-EL-002 | s_byp | rail at the bypass command ≥ 45.6 V (within 5 % of the supply) | example |
| REQ-EL-003 | drive | steady input current ≤ the sheet's 5 A, **assumed** to bound the drive's input (the sheet gives 5 A for the power stage and says neither continuous nor peak) | `components/drive/domains/electrical/rated_current` |
| REQ-EL-004 | drive | steady rail ≥ 47 V | example |
| REQ-EL-005 | c_bulk | rail peak ≤ the capacitor's voltage rating | `UNKNOWN`: `BLOCKED` |
| REQ-EL-006 | r_f1 | precharge I²t ≤ the fuse's melting I²t | `UNKNOWN`: `BLOCKED` |
| REQ-EL-007 | r_f1 | prospective short-circuit current ≤ the fuse's breaking capacity | `UNKNOWN`: `BLOCKED` |
| REQ-EL-008 | s_byp | supply current up to the fault command, the bypass surge included, ≤ 10 A | example (the same as REQ-EL-001's) |

## Expected outputs

| Input | Receipt | Where it is shown |
|---|---|---|
| The committed sample | V0–V3 `PASS`; V4 `BLOCKED`: five `WARNING WITHIN_ILLUSTRATIVE_LIMIT`, three `BLOCKED MISSING_REQUIRED_INPUT`; overall `BLOCKED`, not eligible; 18 results | Example above; `test_the_committed_sample_validates_as_designed` (real ngspice), `test_the_committed_sample_validates_as_designed_with_recorded_ngspice_output` (stand-in) |
| R_PRE 10 Ω → 1 Ω, rebuilt | REQ-EL-001 `FAIL CORNER_LIMITS_FAILED` at 40.6812 A ("actual 40.6812 is above maximum 10.0"); every reference still `PASS`; overall `FAIL` (**Verified**) | `test_an_undersized_precharge_resistor_fails_the_inrush_requirement` |
| Bypass commanded at 5 ms instead of 30 ms, rebuilt | REQ-EL-002 `FAIL` at 31.2169 V; REF-EL-003 `BLOCKED REFERENCE_NOT_APPLICABLE`: "the precharge would reach the charge level at 0.010924434378860507 s, after the bypass is commanded at 0.005 s"; overall `FAIL` (**Verified**) | `test_a_bypass_that_closes_before_the_bus_is_charged_fails` |
| ngspice not on `PATH` | the 15 compiled cases `BLOCKED TOOL_NOT_INSTALLED`, the 3 rating limits `BLOCKED MISSING_REQUIRED_INPUT`; no simulator version in any result | `test_without_ngspice_every_case_is_blocked_and_the_receipt_holds` |
| A limit on the boundary, one float beyond, and with a tolerance | `WARNING`, `FAIL`, `WARNING` on both operators | `test_the_limit_boundaries_are_exact`, `test_the_inrush_limit_at_its_boundary_with_real_ngspice` |
| A rating as `UNKNOWN`, `UNSPECIFIED`, `NOT_AVAILABLE` | `BLOCKED MISSING_REQUIRED_INPUT` naming the status and path | `test_each_null_status_of_a_rating_blocks_with_its_status_and_path` |
| A real (non-illustrative) limit on a `SPECIFIED` fixture rating; the same as `AI_ASSUMPTION` | `PASS`; `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` whether met or violated | `test_a_rating_passes_only_when_specified_and_real_and_never_when_ai_assumed` |
| A refused netlist (`.control`) | V1 `FAIL SOURCE_REJECTED`, V2–V4 `BLOCKED DERIVATION_NOT_AVAILABLE`; ngspice never called | `test_a_refused_netlist_gives_a_receipt_and_never_reaches_ngspice` |
| A deck edited without a rebuild | `v2.dataset-reproduction` `FAIL DERIVATION_DIVERGED`; `v2.electrical.model-invariants` `PASS` (it reads the regenerated deck); every case `COMMITTED_CASE_STALE` | `test_a_deck_edited_without_a_rebuild_is_divergent_and_not_counted` |
| A node named `time` or `all`, a switch model named `TEMPER` | V1 `FAIL SOURCE_REJECTED`; ngspice never called | `test_a_name_ngspice_reads_as_its_own_is_refused_before_ngspice_runs` |
| V_FLT rising over 100 ms (the switch closes at 150 ms, after T_END), or too late to settle, or never above VT + VH | V1 `FAIL SOURCE_REJECTED`; every case `BLOCKED DERIVATION_NOT_AVAILABLE` (**Verified** with the review's script) | `test_a_fault_the_transient_cannot_measure_is_refused` |
| A zero or negative capacitance, a zero resistance, RON or ROFF; a bypass commanded during the ramp | V1 `FAIL SOURCE_REJECTED`, with a receipt, `validate` exit 0 (**Verified** with the review's script) | `test_values_the_closed_forms_divide_by_are_refused_and_never_cost_a_receipt` |
| SW_FLT's ROFF 1 kΩ, rebuilt | every reference `PASS` but REF-EL-010, `BLOCKED REFERENCE_NOT_APPLICABLE` (its surge, 6.98 A, is the peak) (**Verified**) | `test_the_precharge_forms_hold_with_a_leaky_fault_switch` |
| Bypass commanded at 14.5 ms, rebuilt | REQ-EL-001 `WARNING` at 4.71663 A; REQ-EL-008 `FAIL CORNER_LIMITS_FAILED` at 28.3205 A; REF-EL-010 `BLOCKED REFERENCE_NOT_APPLICABLE` (**Verified**) | `test_a_surge_after_an_early_bypass_fails_the_startup_requirement` |

## Evidence

- **The deck** (`derived/electrical/servo_supply_001.cir`, 1370 bytes, SHA-256
  `effee835…66c0`) is hash-bound in the manifest and cited, with its case
  document, by every check whose case ran. Its last lines are the adapter's
  own: `.options noacct`, `.tran 1e-06 0.11 0.0 1e-06`, the ten `.meas tran`
  lines, `.end`.
- **Each check's execution record** holds the command
  (`[<ngspice>, "-b", "derived/electrical/servo_supply_001.cir"]`), the tool
  version from the banner, the metrics, and ngspice's raw stdout and stderr,
  verbatim. Stdout names no host path (**Verified**: no `/` in it). The
  command's first element is the absolute executable path (STATE-2).
- **What `.options noacct` removes** (**Verified**, the committed deck with
  and without it): the "Initial Transient Solution" table, which lists every
  node and branch, including the `pa_00` … `pa_04` nodes and `bpa_00#branch`
  … that `par()` creates; and the timing and memory statistics (total
  analysis and elapsed time, DRAM available, program size), which differ on
  every run. It does not remove the progress report (Known limitations).
- **Results** (`results.json`) record, for each requirement and reference,
  the inputs it rests on with their statuses, the simulator and version, the
  configuration (command, scenario, seed 0), the fidelity `SIMPLIFIED`, and
  the run's environment (OS, machine, Python, the tool versions).

## Training data

None. Training records are specified in the plan (§15) and not produced by
any domain yet. The electrical results carry what a record would need
(inputs with statuses, simulator version, evidence, fidelity); the spec's
electrical tasks (schematic → circuit graph, circuit → component
identification, simulation → fault explanation) are PLANNED.

## Future work

PLANNED, none started:

- scenario parameters and per-scenario decks, through an additive
  `CaseTarget.scenario_inputs`, when a sample needs scenario-dependent inputs;
- `L`, `D`, `M`, `Q`, `X`, `B` elements, DC/PULSE/SIN sources, AC analysis,
  subcircuits and other topologies, each with its closed forms;
- a KiCad schematic → netlist importer (plan §11.1);
- part-rating checks once real parts are selected; steady ripple once the
  drive's input ripple is stated; a fuse model that opens;
- the SEC-2 runner guard and an ngspice `-n` / deck screen in the tool
  adapter (SEC-1), both open questions in the plan;
- pinning ngspice in CI after its first run, and a reproduction on the x86_64
  runner (arm64 Linux containers reproduce the `spice` job's steps);
- LTspice and PSpice as optional adapters that report `BLOCKED` when absent.
