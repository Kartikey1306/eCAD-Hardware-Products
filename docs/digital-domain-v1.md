# Digital domain v1

The digital domain is the third production domain of issue #27, and the
second whose source artefact is not CAD. Its source of truth is Verilog: the
transmitter and receiver RTL of `rtl/`, copied into the sample unmodified,
and a declarative top that says how they are wired and what they are told. A
strict grammar reads the sources into the engineering model; the adapter
writes one simulation file from that model; Icarus Verilog compiles and runs
it; and the V0–V4 contract compares what the harness measured with
closed-form references and requirements:

```
source/tb_uart_loopback.v ─┐
source/uart_tx.v (= rtl/uart_tx.v) ─┼─ ecad_model.verilog (allow-list grammar) ─► derived/engineering_model.json
source/uart_rx.v (= rtl/uart_rx.v) ─┘                                                  │  (each leaf's text verbatim)
design/annotations.json (the unselected target device) ────────────────────────────────┘
                                          domains/digital.write_simulation ▼
                  derived/digital/<id>.v  (the RTL as the model carries it, then a harness written from the model)
requirements/requirements.json ──► validation/{golden,corners}/cases.json
                                                 │
       case engine + HDLAdapter (`iverilog -g2012 -o simulation.vvp <file>`, then `vvp simulation.vvp`)
                                                 │
                        receipt.json · evidence/ · results.json · report.md
```

In a validation Icarus never compiles the sources. It compiles the committed
simulation file, which `build` wrote from the model, so every value it simulates is one
the model records with its source and status, and the RTL it compiles is the
model's copy of the sources, bound to them by hash -- as long as the
committed file is still the one the model regenerates, which
`v2.dataset-reproduction` and `check` compare byte for byte. A committed
simulation file edited by hand still runs (plan §7.2 SEC-2; Known
limitations). The dataset layout, gates and results are those of
[cad-dataset-engineering-model-v1.md](cad-dataset-engineering-model-v1.md);
this page covers what is specific to the digital domain. The code is
`tools/ecad_model/verilog.py` (the format layer),
`tools/ecad_model/domains/digital.py` (the adapter),
`tools/ecad_validation/adapters/hdl.py` (the tool adapter) and the output
copy of `tools/ecad_validation/adapters/process.py`. The design it was built
from, with the alternatives each decision rejected, is
[design/digital-domain-design.md](design/digital-domain-design.md); where the
code departs from it, `MEMORY.md` says how and why.

**Evidence.** A statement marked **Verified** below names the run behind it.
Unless it names another, that run was made for this page on 2026-09-29 on
macOS 26.6.2 arm64 with Python 3.14.4 and Icarus Verilog 13.0 (Homebrew,
`/opt/homebrew/bin`; `iverilog -V` prints `Icarus Verilog version 13.0
(stable) (v13_0)`), on the code of `0a5ff00`: either a command shown here, or
a test of the complete suite, which passed on that code (`TASKS.md` T-013).
The other runs quoted are the design's scratch runs of 2026-09-27 (Icarus 13.0
on macOS; Icarus 11.0 and Verilator 4.038 in an ubuntu:22.04 arm64
container), the digital review's fixes of 2026-09-28/29, and the hdl job's
steps run by the coordinator in an ubuntu:22.04 arm64 container (Icarus 11.0);
each is named where it is used.

## What the domain is

One design class, and nothing else: the UART 8N1 loopback. A transmitter and
a receiver with the port and parameter interfaces of `rtl/uart_tx.v` and
`rtl/uart_rx.v` are wired transmitter to receiver by a declarative top that
states the clock half-period, the reset length, the clock frequency and baud
rate each instance is told, and the bytes to send (one to sixteen). The top
holds no behaviour. The harness the adapter writes drives the clock, the
reset and the stimulus, and makes every measurement, sampling each signal on
the falling clock edge, half a cycle after the rising edge the design acts
on. The run has a fixed length, END = RESET_CYCLES + (N + 2) · 12 ·
max(T_tx, T_rx, 16) cycles, T = CLK_FREQ // BAUD_RATE of each instance and N
the bytes sent, so a spurious byte in the two idle frames after the last one
is still counted; for the committed sample END is 20 836 cycles
(**Verified**: the `end_cycle` doctest, and the harness line
`if (ecad_cycle == 20836) begin`).

The adapter's `AVAILABLE` reason in the manifest names this class ("the UART
8N1 loopback only ..."). Sources outside it are refused at extraction (V1
`FAIL SOURCE_REJECTED`) and never reach Icarus. "Digital `AVAILABLE`"
therefore means this class, not HDL in general: only the UART 8N1 loopback
class is validated.

## Supported inputs

**Verilog sources**, declared in `source/provenance.json` with format
`verilog` (artefact type `hdl_source`): at most `verilog.MAX_MODULES` (16),
refused before any is read when there are more, each a regular file of at
most 1 MiB. Each is read by `ecad_model.verilog.parse_source`, an allow-list,
not a Verilog parser: anything outside it is refused with the file, the line
and the reason (`HdlRefused`, kind `rejected`). Much of Verilog reaches
outside the simulation, and on Icarus Verilog 13.0 `` `include `` read a file
that is not a source, `$fopen` wrote a file and `$readmemh` read one
(**Verified**: `test_the_grammar_refuses_what_icarus_would_run` runs each on
raw Icarus, then shows the grammar refuses it).

| Accepted | Form |
|---|---|
| A file | UTF-8, LF line ends and a final LF, lines of at most 1024 characters, no control character but TAB and LF (C0, DEL and C1 refused), no Unicode bidirectional control; non-ASCII only inside comments; exactly one `` `timescale 1ns / 1ps `` line, before which only comments stand; one module |
| A leaf (synchronous RTL) | `module NAME [#(parameter P = <decimal>, ...)] (input [wire] [range] NAME, ..., output reg [range] NAME, ...);` then localparams (decimals, sized literals, parameters and earlier localparams under `+ - * /` and parentheses), regs, and `always @(posedge <input>)` blocks of `begin`/`end`, `if`/`else`, `case`/`endcase`/`default` and nonblocking assignments `<=`; every block of a leaf on the same clock input |
| Expressions | `? :`, `\|\| && \| ^ & == != < <= > >= << >> + - * / %`, one unary `! ~ -` (not one applied to another: Icarus refuses `~~y`), parentheses, names, bit selects `name[expr]`, decimals (unsized at most 2^31 - 1), sized literals `W'b`, `W'd`, `W'h` of at most 64 bits whose value fits |
| A declarative top | `module NAME;` then localparams, each one decimal or sized literal (`[7:0]` is the only range), one `reg` or `wire` per declaration with an optional `[N:0]` and no initial value, and instances `M #(.P(<top localparam or decimal>), ...) name (.port(signal), ...);`, every parameter and port by name |
| Names | At most 64 characters, no `$`, not starting `ecad_`; a module or instance name starting `_` cannot be a component id and is refused by the adapter; the text `ECAD_METRIC` nowhere, comments included (it is the harness's metric marker) |
| Nesting | At most `MAX_DEPTH` = 32 levels of statements or expressions, read with explicit stacks, so a deeper file is a refusal, never a `RecursionError`; an `else if` chain does not deepen |

| Refused | Why |
|---|---|
| `` `include `` | reads another file |
| `` `define ``, `` `undef ``, a macro use | text substitution |
| `` `ifdef `` `` `ifndef `` `` `elsif `` `` `else `` `` `endif `` | conditional compilation |
| every other directive, and a second or different `` `timescale `` | compiler directive |
| `$fopen`, `$readmem*`, `$dump*`, the other file tasks | open, read or write files |
| `$system` | runs a shell command |
| `$test$plusargs`, `$value$plusargs` | read the simulator's command line |
| `$random`, `$urandom`, `$dist_*` | randomness |
| `$display`, `$write`, `$strobe`, `$monitor` | only the harness prints |
| `$finish`, `$stop`, `$fatal`, `$error`, ... | only the harness ends a run (`$stop` waits for commands on stdin) |
| any other `$name` | outside the subset; a VPI module can define any `$name` |
| a string | file names and `import "DPI-C"` are strings |
| `import export chandle bind` | call C code |
| `assign initial negedge function task generate for while repeat integer real signed inout casex casez wait fork` ... | outside the synchronous RTL subset (PLANNED) |
| `defparam force release specify primitive table config library` ... | change another scope or the simulator (`defparam u.P = 7` took effect on Icarus, the design's run) |
| SystemVerilog words (`logic always_ff interface package class` ...) | SystemVerilog (PLANNED) |
| gate-level primitives and strengths (`and nand tri wand supply0` ..., `wone`) | gate-level primitive (PLANNED) |
| `bool`, `wreal` | Icarus Verilog extended types (review CS-2) |
| `=== !== <<< >>> ** -> :: ++ -- +: -:`, compound assignments, `{ }` | an operator outside the subset (PLANNED) |
| an escaped identifier, an attribute `(*`, an unsized based literal `'b1`, `x` `z` `?` digits, a real literal, a part select `name[a:b]`, a delay `#` in RTL | outside the lexical subset |
| a blocking `=`; an assignment to anything but a reg; a reg assigned in two `always` blocks; a block clocked on anything but an input; a second clock; an `output reg` no statement assigns; a name declared twice or used before its declaration; a hierarchical reference; an instance, a wire or a second module in a leaf | outside the synchronous RTL subset |
| a top with ports, an initial value, a positional or `.*` connection, an expression as an override or a connection | outside the declarative form |
| a module defined twice; no top or two; an instance of a module no source defines; a leaf instantiated twice or never; an unknown, doubly connected or unconnected port; a width mismatch; an output onto a reg; a wire two outputs drive; an input on a wire no output drives; an override of an undeclared parameter | the design does not elaborate |
| more than 1 MiB, an empty file, a Git LFS pointer, invalid UTF-8, CR, NUL, a C1 or bidirectional control, no final LF, an unterminated `/* */` | the file-level limits |

A comment is skipped as Icarus skips it: `` // `include "<file>" `` and
`// $fopen(...)` compile to nothing (the grammar's trap in `MEMORY.md`).

**The class rules** (`_classify` on the sources, `loopback_roles` on a
model), each named when a design breaks it:

| Rule | Requirement |
|---|---|
| C1 | One top with no ports and exactly two instances, of two different modules, each instantiated once |
| C2 | One instance's module declares exactly inputs `clk:1`, `rst_n:1`, `tx_data:8`, `tx_valid:1`, outputs `tx_ready:1`, `tx:1`, parameters `CLK_FREQ` and `BAUD_RATE`: the transmitter |
| C3 | The other declares exactly inputs `clk:1`, `rst_n:1`, `rx:1`, outputs `rx_data:8`, `rx_valid:1`, `rx_error:1`, the same parameters, and a localparam `OVERSAMPLE` that is one decimal literal: the receiver |
| C4 | Each instance overrides both parameters by name, with a top localparam or a decimal literal, of at most `verilog.MAX_DECIMAL` (2^31 - 1), since the harness writes each as an unsized decimal (review CS-4) |
| C5 | One reg drives both `clk` ports, one reg both `rst_n` ports; regs drive `tx_data` and `tx_valid` alone; the transmitter's `tx` and the receiver's `rx` share one wire, the line, and nothing else; `tx_ready`, `rx_data`, `rx_valid` and `rx_error` each drive a wire of their own; every declared signal is connected |
| C6 | The top's localparams are exactly `CLK_HALF_PERIOD_NS` and `RESET_CYCLES` (decimals of at least 1), `TX_BYTE_0` .. `TX_BYTE_{N-1}` (consecutive, `[7:0]`, 8-bit sized literals, 1 ≤ N ≤ 16) and those an override names; no inert data; `TX_BYTE_0` odd |
| C7 | END ≤ 2 000 000 cycles (the resource guard; the committed sample needs 20 836) |

C7 is an extraction refusal, not a V1 finding, because V1's findings do not
stop the cases. An even first byte is refused because the harness times a
bit as the line's first low run, which is the start bit alone only when bit
0 is 1: on the `0x34` copy the design's run measured 1302 cycles and
38 402.46 Bd, and REQ-DIG-001 would then fail a line that runs at 115 207 Bd
(`MEMORY.md`).

**`design/annotations.json`** (format 1.2.0) adds what the HDL cannot carry:
`components_without_cad` may give a component a `digital` facet, here the
target device with its `min_clock_period` `UNKNOWN`, and `relationships`
relates it (`tb_uart_loopback constrained_by target_device`). Annotations
with `materials`, `parts`, `joints`, `attachments` or `circuit_elements`, a
component id an HDL component already has, or a relationship to an unknown
component are refused (V1 `FAIL DATASET_INPUT_INVALID`).

**Copied sources (REUSE-1).** `source/uart_tx.v` and `source/uart_rx.v` are
byte-identical copies of `rtl/uart_tx.v` and `rtl/uart_rx.v`, and the
provenance (format 1.1.0) says so for each with `copied_from {path, sha256}`.
`check` and V0 re-hash the origin like any cited file, require the copy's
bytes to have the origin's digest, and refuse an origin that lies inside the
item, compared by file identity (`os.path.samefile`), not by spelling (review
CS-3). Both pairs have one digest each (**Verified**, `shasum -a 256`):
`5be9e1bd…f01a` (3367 bytes) and `c1bebcc6…ab81` (4195 bytes). The copies
must stay byte-identical to their origins: an edit to either fails `check`
and V0 until the copy is refreshed and the item rebuilt.
`.gitattributes` keeps both origins, and every file of the item, byte-exact
on checkout.

## Engineering model

The model is format 1.2.0 (`ecad_model.HDL_MODEL_VERSION`), written by
`ecad_model.domains.digital` `1.0.0 (ecad_model.verilog 1.0.0)`, which the
manifest records as the model's producer and as `versions.engineering_model`.

| Spec §8 concept | Where it is |
|---|---|
| DigitalSystem | The model of a sample whose primary domain is `digital`: `design.name` is the top's module name, `design.sources` the three files by path, format `verilog` and SHA-256 |
| Module | One component per module instance, and one for the top, each with an `hdl` member (new in 1.2.0): `module`, `source` and `ports`. The top lists its `signals`; an instance names its hierarchical path (`instance`), the facet holding each parameter the top passes (`parameters`), the top signal each port connects to, and its module's source text verbatim (`text`). Kind `other`; `cad_ref`, `material`, `geometry`, `physical` and `placement` are `null` |
| Signal, net | The top's `hdl.signals` (reg or wire, width) and each port's `signal`; a net is the signal a port names, never stored twice. A leaf's internal registers are not extracted |
| Clock, reset | `clock_half_period` [s] and `reset_cycles` [cycles] on the top; the clock and reset signals are those of rule C5. Active-low synchronous reset is the class's interface, not extracted |
| Interface | `hdl.ports` (direction, width, signal) and `hdl.parameters` |
| Protocol | UART 8N1, LSB first, a 16× oversampling receiver: the class, named in the `AVAILABLE` reason; not a stored field |
| Stimulus | `tx_bytes` [1] (the bytes, in order) and `byte_count` [1], `DERIVED` from them |
| Instance values | `clk_freq` [Hz] and `baud_rate` [Bd] of each instance; `oversample` [1] of the receiver, from its `OVERSAMPLE` |
| Constraint | `target_device/min_clock_period` [s], `UNKNOWN`: no device is selected |
| StateMachine, timing, constraints files | PLANNED: not extracted |

Every value a source states is `SPECIFIED`, with source kind
`design_annotation` citing the file that states it by path and hash: the
top's values and the instances' `clk_freq` and `baud_rate` cite the top,
`oversample` cites `source/uart_rx.v`. Each carries the note "`<NAME> =
<literal>` as `<file>:<line>` states it; not a rating or measurement of any
part". The RTL's parameter defaults are overridden and never read, and its
localparam expressions (`BAUD_DIV`, `SAMPLE_POINT`) are parsed, not
evaluated. There is no extraction file, so `versions.extraction` is `none`.
The relationships are `contains` from the design to the top and from the top
to each instance, and the annotations' own. The index of unknowns has one
entry, `components/target_device/domains/digital/min_clock_period`, needed
by digital (**Verified**: the committed model).

Why the RTL text is in the model (the HDL amendment of ARCH-1, plan §8.2):
the protocol hands `write_models`, V1, V2 and the closed forms only the
model, and re-reading the sources there would be a hidden input. Carried
verbatim, the bytes Icarus compiles are the committed RTL, V2 binds them to
`design.sources` by hash, and the reproduction check compares the file
exactly. The price is size: the committed model is 19 730 bytes, and it
carries the two leaves' 7 562 bytes of text.

## Supported simulators

| Simulator | State |
|---|---|
| Icarus Verilog | IMPLEMENTED, the only simulator. Both steps run through `run_process`: `iverilog -g2012 -o simulation.vvp <inputs>` in one workspace, whose program is collected out of it (`ProcessRequest.collect`), then `vvp simulation.vvp` in a second workspace holding only that program; each with the scrubbed environment, an empty stdin, the 4 MiB output cap and the case's 60 s timeout. The version probe, `iverilog -V`, runs through `run_process` too (review CS-6), and the version is its first line. Case arguments are refused (`BLOCKED RTL_ARGUMENTS_REFUSED`) and never reach either command line |
| Verilator | PLANNED, not a second adapter. The merged cases contract's adapter enum has no `verilator` (**Verified**: `validation-cases.schema.json` line 48 lists `python_control mujoco kicad ngspice iverilog`), so a Verilator case needs that contract amended (plan §20 Q9). CI's apt Verilator on ubuntu:22.04 is 4.038, which rejects `--binary` and `--timing` and refuses the harness's timing controls; Verilator's report lines carry wall time, so its execution records would differ run to run; and it is 2-state, so `outputs_unknown_after_reset` would be vacuous (the design's runs of 2026-09-27, not re-run here) |
| ModelSim / Questa | PLANNED only. Licensed; there is no adapter and no stub |

Icarus 13.0 is what ran every local run, and what printed the recorded
outputs the stand-in tests replay (those of `tests/unit/test_hdl_adapter.py`
are of the simulation file as it stood before the review, sha256
`191bd8f1…3e84`; they test the adapter's parser, not the sample). The CI
`hdl` job installs Icarus from the
ubuntu-22.04 apt archive, unpinned: in an ubuntu:22.04 arm64 container that
was Icarus 11.0 (`Icarus Verilog version 11.0 (stable) ()`), on which the
review's fixer found the harness printing the same `ECAD_METRIC` lines as on
13.0 for the committed sample and five copies (2026-09-29), and on which the
coordinator ran the job's steps (T-013). Only Icarus 13 prints
`<file>:<line>: $finish called at <t> (1ps)`: stdout differs between the two
versions in that line (**Verified** for 13.0 in the execution record below;
11.0 prints none, the design's container log).

**How metrics are read.** The metrics are the `ECAD_METRIC <name> <value>`
lines the inputs declare with `$display("ECAD_METRIC <name> %0d", ...)` or
`"%.17g"`, read from vvp's stdout. A name becomes a metric only when it is
declared once and exactly one stdout line reports it with a finite
plain-decimal value; a name declared twice, not printed, printed twice or
with a value such as `x` or `nan` is named in the summary (at most ten
problems) and left out, and the case's comparator decides what a missing
metric means (`INCONCLUSIVE`). Other outcomes:

| Icarus run | Verdict | Reason |
|---|---|---|
| `iverilog` or `vvp` not installed | `BLOCKED` | `TOOL_NOT_INSTALLED`, `VVP_NOT_INSTALLED` |
| No input; case arguments given; an input over 1 MiB | `BLOCKED`, nothing run | `RTL_INPUT_MISSING`, `RTL_ARGUMENTS_REFUSED`, `RTL_INPUT_TOO_LARGE`; no tool version, so the receipt attributes it to `ecad-validator` |
| A step timed out (60 s each) | `INCONCLUSIVE` | `RTL_EXECUTION_TIMED_OUT`, naming the step |
| A step could not execute | `INCONCLUSIVE` | `RTL_EXECUTION_ERROR` |
| Compile exit status not 0 | `FAIL` | `RTL_COMPILE_FAILED` |
| Compile exit 0, program not collected | `INCONCLUSIVE`, vvp not run | `RTL_PROGRAM_MISSING` |
| vvp exit status not 0 | `FAIL`, no metrics | `RTL_TESTBENCH_FAILED` |
| Output cut by the capture limit | `INCONCLUSIVE`, no metrics | `OUTPUT_TRUNCATED` |
| A version probe error | `BLOCKED` | a reason code the receipt accepts (`VERSION_PROBE_ERROR`, `VERSION_PROBE_EXIT_NONZERO`), the raw text in the summary |

## Validation capabilities

**Compilation** of the committed RTL, the first step of every case.

**V1** (`sanity_problems`, `DOMAIN_SANITY_FAILED`): every digital facet is
in the domain's vocabulary with its unit (`clock_half_period`,
`min_clock_period` s; `reset_cycles` cycles; `tx_bytes`, `byte_count`,
`oversample` 1; `clk_freq` Hz; `baud_rate` Bd); the half period is positive,
the reset length an integer of at least 1, the bytes 1 to 16 integers from 0
to 255 and `byte_count` their number; each instance's `clk_freq` and
`baud_rate` are positive integers with the baud rate no higher than the
clock; each instance's `CLK_FREQ` is the frequency the harness drives, within
1 Hz, compared in integers, |2 N · CLK_FREQ − 10^9| < 2 N for `always #N`
(review HT-1: a floating-point comparison refused every half period that does
not divide one second into whole Hz); `oversample` is even and at least 2;
the receiver's divider CLK_FREQ // (BAUD_RATE · OVERSAMPLE) is at least 1, or
it never samples; and a known `min_clock_period` is positive.

**V2** (`invariant_problems`, `DOMAIN_MODEL_INCONSISTENT`), on the
simulation file the runner regenerates from the fresh model -- not the
committed one:

1. it begins with the two header lines and, for each leaf in model order,
   the separator `// ---- <hdl.source> sha256 <sha256(hdl.text)> ----` and
   `hdl.text` verbatim, and the next line is `// ---- harness ----`;
2. each leaf's `hdl.text` hashes to the `design.sources` entry its
   `hdl.source` names, and every `hdl.source` is one of them;
3. `verilog.read_harness` reads the harness back by form -- its declarations
   and instances, the half period, the reset cycles, the stimulus, the
   expected bytes and their count, the count a missing byte is taken
   against, and END -- and each is compared with the model; the harness uses
   no `$name` but `$display`, `$finish` and `$realtime`;
4. the harness equals `write_harness(model)` character for character;
5. it declares exactly the nine metrics, once each, in order;
6. every `SPECIFIED` digital value cites the file that states it by path and
   hash.

These invariants check the writer against the reader and the model. Only the
domain-neutral `v2.dataset-reproduction` (and `check`) reads the committed
file, byte for byte (comparator `exact`): a committed file edited without a
rebuild fails reproduction while the invariants still pass (review CS-5 =
HT-2; `test_a_simulation_file_edited_without_a_rebuild_is_divergent_and_not_counted`).

**Nine metrics**, all `SIMPLIFIED`: the simulation is exact at the logic
level of the RTL as written and idealises the hardware -- an RTL simulation
of one clock domain with a jitter-free clock; no gate or wire delay, no setup
or hold, no metastability (the receiver's two-flop synchroniser acts
logically), no analog effect, an ideal line; and one fixed stimulus, the
bytes the top states, each sent once as soon as the transmitter is ready.

| Metric | Unit | What the harness measures | Closed form (V3) |
|---|---|---|---|
| `clock_period_s` | s | time between the harness clock's first two rising edges | `clock_period`: 2h |
| `tx_idle_after_reset` | 1 | 1 if the line and `tx_ready` are high at the first falling edge after reset is released, else 0 | `idle_high_after_reset`: 1 |
| `tx_bit_cycles` | cycles | clock cycles of the line's first low run: the start bit, when the first byte is odd | `bit_period_cycles`: D_t |
| `tx_bit_rate_bd` | Bd | 1 / the simulated duration of that run | `bit_rate`: 1 / (2h · D_t) |
| `tx_frame_cycles` | cycles | cycles `tx_ready` stays low for the first byte | `frame_cycles`: 10 · D_t |
| `rx_bytes_received` | 1 | `rx_valid` pulses before END | `bytes_sent`: N, if W holds |
| `rx_bit_errors` | bits | each bit that differs between a byte sent and the byte received in its place, and all 8 of each byte sent that never arrived | `lossless_loopback`: 0, if W holds |
| `rx_framing_errors` | 1 | `rx_error` pulses before END; not reported when there are none and a byte sent never arrived | `no_framing_errors`: 0, if W holds |
| `outputs_unknown_after_reset` | 1 | outputs (`tx_ready`, the line, `rx_data`, `rx_valid`, `rx_error`) with an X or Z bit at the first falling edge after reset is released (4-state simulation only) | none (V4 only) |

With h the clock half-period, D_t = CLK_FREQ // BAUD_RATE of the
transmitter, D_r = CLK_FREQ // (BAUD_RATE · OVERSAMPLE) of the receiver and N
the bytes sent. The closed forms (`digital.reference_value`) use the class's
interface contract and the model's facets, never the RTL's own localparam
expressions, so the RTL is not checked against itself; they run on a code
path separate from the harness writer and the simulator. The bit-period and
bit-rate forms apply only for an odd first byte.

**Condition W** (`sampling_holds`), under which the receiver's three forms
apply: the receiver detects a start at the first of its ticks (every D_r
cycles) at which its synchronised line is low, at a phase φ in [0, D_r − 1],
and samples bit b (0 confirms the start, 1–8 are data, 9 the stop) at
(SP + OS·b)·D_r cycles after that, SP = OS // 2. W holds when, for every b
in 0–9, b·D_t ≤ (SP + OS·b)·D_r and (SP + OS·b)·D_r + D_r − 1 < (b + 1)·D_t.
For the committed sample D_t = 434, D_r = 27 and W holds. **W is sufficient,
not necessary**: with the transmitter at 121 000 Bd (D_t 413, W's equality
point with D_r 27) both bytes still arrive with no error, yet W refuses it
and REF-DIG-006 to 008 are `BLOCKED REFERENCE_NOT_APPLICABLE`; at 120 500 Bd
(D_t 414) they apply and pass (**Verified**:
`test_the_sampling_condition_is_conservative_at_its_edge`, real Icarus). A
borderline design therefore gets not-applicable, never a false `PASS` or a
false V3 `FAIL`. A form that does not apply raises `ReferenceBlocked`, which
V3 reports as `REFERENCE_NOT_APPLICABLE`; a null-status input gives
`MISSING_REQUIRED_INPUT`.

**What the checks catch**, each an RTL defect in a test-built copy (the copy
loses its `copied_from`, since a modified file is no copy), rebuilt and
validated with real Icarus (**Verified**: `test_rtl_defects_fail_their_references`):

| Defect | Metrics that change | Checks that change |
|---|---|---|
| The receiver's bit order reversed | `rx_bit_errors` 8 | REF-DIG-007 and REQ-DIG-004 `FAIL` |
| The same, sending the one byte `0xA5` | nothing: `0xA5` reads the same in either bit order | none |
| The receiver never sets `rx_valid` | 0 bytes, 16 bit errors, no framing count | REF-DIG-006, 007 and REQ-DIG-003, 004 `FAIL`; REF-DIG-008 and REQ-DIG-005 `INCONCLUSIVE` |
| The receiver's bit 0 stuck at 1 | `rx_bit_errors` 1 | REF-DIG-007 and REQ-DIG-004 `FAIL` |
| The transmitter's divider off by one | 435 cycles, 114 942.53 Bd, 4350 cycles | REF-DIG-003, 004, 005 `FAIL` |
| The transmitter's line not reset | `tx_idle_after_reset` 0, `outputs_unknown_after_reset` 1 | REF-DIG-002 and REQ-DIG-006 `FAIL` |
| The receiver's stop-bit check removed | nothing | none: framing-error detection is never exercised |

That is why the sample sends `0x35` then `0xCA`: they are complements,
neither is its own bit reversal (`0x35` reversed is `0xAC`, `0xCA` is
`0x53`), `0x35` is odd so the start bit is the line's first low interval,
and `0xCA`'s bit 0 is 0, which is what shows a bit 0 stuck at 1. A change of
the bytes must keep those properties.

## Known limitations

- **One design class** (C1–C7): a transmitter and a receiver of those exact
  interfaces, one level of hierarchy, 1 to 16 bytes. Only the UART 8N1
  loopback class is validated.
- **Synchronous posedge RTL only.** No `negedge`, asynchronous reset,
  `assign`, `initial`, `generate`, functions, tasks, part selects,
  concatenation, SystemVerilog or VHDL. `rtl/spi_master.v` is refused at its
  `$clog2` (**Verified**: `parse_source` names `rtl/spi_master.v:36`).
- **Every metric is `SIMPLIFIED`**, with the idealisations listed above: one
  clock domain, no timing or analog effect, one fixed stimulus. No reset in
  operation, no clock-domain crossing.
- **W is conservative**: sufficient, not necessary (above).
- **Framing-error detection is never exercised by the committed sample**: a
  correct loopback always delivers a good stop bit, so a receiver without its
  stop-bit check gives the same metrics (above). A framing-fault scenario is
  open (design Q-D7).
- **`outputs_unknown_after_reset` needs a 4-state simulator** and is sampled
  at one instant, the first falling clock edge after reset is released;
  REQ-DIG-006 says so in its title (review HT-6). An output that goes unknown
  later is not seen.
- **The bit metrics need an odd first byte**; C6 refuses an even one.
- **No part, no device, no timing.** No FSM extraction, no static timing
  analysis, no SDC/XDC/PCF constraints, no board or pin data. REQ-DIG-007 is
  `BLOCKED` because no target device is selected, so its `min_clock_period`
  is `UNKNOWN`. Every limit is illustrative, so the receipt is at best
  `BLOCKED` and never eligible for ebuild.
- **The receipt records only the `vvp` command.** A check's execution record
  holds `[<vvp>, "simulation.vvp"]`, and so does the receipt's `iverilog`
  tool entry; neither records the `iverilog -g2012` compile step, whose
  output is dropped when it succeeds (**Verified**: the receipt of the
  Example). A warning a future Icarus printed while compiling would not reach
  the record.
- **V2's digital invariants read the regenerated simulation file**; only
  `v2.dataset-reproduction` and `check` read the committed one (review CS-5 =
  HT-2).
- **SEC-1, SEC-2.** `run_process` is process hardening, not a sandbox: no
  filesystem, network, CPU or memory confinement. The grammar keeps file,
  shell and native-code constructs out of the sources, and case arguments are
  refused, so the file `build` writes from the model carries none. But Icarus
  runs the committed simulation file, which equals the regenerated one only
  while `v2.dataset-reproduction` passes, and the runner executes the
  committed case documents, and the files they name, before it decides which
  cases count. A hand-edited committed simulation file therefore runs before
  it is flagged stale: with a `$fopen` of a file outside the item added to
  its harness, that file was written 14 times during `validate`, once per
  compiled case, and only then did V0 and `v2.dataset-reproduction` fail and
  every case become `BLOCKED COMMITTED_CASE_STALE` (**Verified** at
  `0a5ff00`, a scratch clone). The guard that would close this (plan §7.2
  SEC-2, §20 Q14) is not implemented; until then only reviewed repository
  content may be validated (plan §20 R5). A screen of the compiled program
  and `vvp -N` (SEC-3 in the design) are PLANNED.
- **STATE-2.** Execution records and the receipt's `tools[]` carry the
  absolute path of `vvp` (here `/opt/homebrew/bin/vvp`).
- **The CI Icarus is unpinned** (apt, 11.0 in the ubuntu:22.04 arm64
  container), no local run used it, and nothing has run on the x86_64 CI
  runner. The version recorded is the first line of `iverilog -V`; `vvp`'s
  own version is not compared with it (design Q-D3).
- **`capabilities.detect_capabilities`** (the `ecad_validation` CLI's
  capability listing) still probes `iverilog -V` with the caller's
  environment, and so still writes the file `IVERILOG_ICONFIG` names; the
  adapter's own probe no longer does (review CS-6; `MEMORY.md`).
- **One regression test runs only where the filesystem folds letter case**:
  the test that an origin spelled in capitals is still inside the item (review
  CS-3) is added on macOS, not on Linux.
- **Awkward names.** `tools/cad_dataset.py` and `datasets/cad/` hold an HDL
  sample; results call the instances `cad_components`;
  `versions.simulation` is the digest of an empty set of scripts; the run
  environment records the digest of `tools/constraints-cad.txt`, which says
  nothing about Icarus. The RTL headers name "EmbeddedOS Foundation" and
  `LICENSE` "EmbeddedOS (EoS) Research Foundation"; whether they are one
  licensor is Unknown (design Q-D8), and the provenance quotes both.

## Example

Run on a clean clone of `0a5ff00`, whose code the documentation commit does
not change (macOS arm64, Python 3.14.4, Icarus Verilog 13.0, 2026-09-29).
The output directory `<dir>` is a scratch directory outside the repository;
nothing else is edited. `check` and `validate` gave the same output, and the
same requirements table, in the branch's worktree at `0a5ff00` with its tree
clean.

```console
$ python3 tools/cad_dataset.py build datasets/cad/uart_loopback_001
wrote datasets/cad/uart_loopback_001/derived/engineering_model.json
wrote datasets/cad/uart_loopback_001/derived/digital/uart_loopback_001.v
wrote datasets/cad/uart_loopback_001/validation/golden/cases.json
wrote datasets/cad/uart_loopback_001/validation/corners/cases.json
wrote datasets/cad/uart_loopback_001/dataset-item.json
$ git status --short
$ python3 tools/cad_dataset.py check datasets/cad/uart_loopback_001
datasets/cad/uart_loopback_001: every hash matches and every derived file reproduces from the sources
$ python3 tools/cad_dataset.py validate datasets/cad/uart_loopback_001 --output <dir>
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
  "product": "datasets:uart_loopback_001"
}
report: <dir>/report.md
```

All three exited 0; the rebuild left the tree unchanged. The receipt names
source commit `0a5ff00` (dirty: false), the tools `ecad-validator` 1.1.0 and
`iverilog` `Icarus Verilog version 13.0 (stable) (v13_0)`, and is not
eligible for ebuild; `results.json` holds 15 results bound to the receipt's
digest, each with fidelity `SIMPLIFIED`, and all 86 evidence entries (45
distinct digests) re-hash. The requirements table of `report.md`, as written:

| Requirement | Kind | Metric | Measured | Verdict | Why |
|---|---|---|---|---|---|
| REF-DIG-001 | reference | `clock_period_s` | 2e-08 s | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-002 | reference | `tx_idle_after_reset` | 1 1 | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-003 | reference | `tx_bit_cycles` | 434 cycles | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-004 | reference | `tx_bit_rate_bd` | 115207 Bd | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-005 | reference | `tx_frame_cycles` | 4340 cycles | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-006 | reference | `rx_bytes_received` | 2 1 | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-007 | reference | `rx_bit_errors` | 0 bits | PASS | GOLDEN_COMPARISON_PASSED |
| REF-DIG-008 | reference | `rx_framing_errors` | 0 1 | PASS | GOLDEN_COMPARISON_PASSED |
| REQ-DIG-001 | illustrative requirement | `tx_bit_rate_bd` | 115207 Bd | WARNING | REQ-DIG-001 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-002 | illustrative requirement | `tx_bit_rate_bd` | 115207 Bd | WARNING | REQ-DIG-002 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-003 | illustrative requirement | `rx_bytes_received` | 2 1 | WARNING | REQ-DIG-003 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-004 | illustrative requirement | `rx_bit_errors` | 0 bits | WARNING | REQ-DIG-004 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-005 | illustrative requirement | `rx_framing_errors` | 0 1 | WARNING | REQ-DIG-005 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-006 | illustrative requirement | `outputs_unknown_after_reset` | 0 1 | WARNING | REQ-DIG-006 is illustrative: not a customer, safety or certification requirement |
| REQ-DIG-007 | illustrative requirement | `clock_period_s` | 2e-08 s (measured by v3.REF-DIG-001) | BLOCKED | UNKNOWN: components/target_device/domains/digital/min_clock_period |

(The report prints a count's unit `1` after its value.) Every case runs the
same file, so REQ-DIG-007, blocked only by its limit, still reports the value
another check measured for the same metric, and names that check.

**vvp's stdout** in the execution record of `v3.REF-DIG-004`, verbatim
(Icarus 13.0):

```
ECAD_METRIC clock_period_s 2e-08
ECAD_METRIC tx_idle_after_reset 1
ECAD_METRIC tx_bit_cycles 434
ECAD_METRIC tx_bit_rate_bd 115207.3732718894
ECAD_METRIC tx_frame_cycles 4340
ECAD_METRIC rx_bytes_received 2
ECAD_METRIC rx_bit_errors 0
ECAD_METRIC rx_framing_errors 0
ECAD_METRIC outputs_unknown_after_reset 0
derived/digital/uart_loopback_001.v:353: $finish called at 416720000 (1ps)
```

stderr is empty, and the last line is the run's END, 20 836 cycles of 20 ns
(416.72 µs). Each closed form equals the value Icarus printed; the golden
stores 12 significant figures, so REF-DIG-004's golden is 115207.373272,
1.106e-7 Bd from the printed 115207.3732718894, against a tolerance of
1e-3 Bd. The other seven references compare integers or 2e-08 exactly
(tolerance 0; 1e-15 s for the clock period).

## Dataset samples

One sample, [`datasets/cad/uart_loopback_001`](../datasets/cad/uart_loopback_001):
the UART pair of `rtl/`, copied unmodified, in a self-authored MIT loopback
testbench; no board, oscillator or peer device is modelled, and no value is a
property of a real part.

| File | Written by | Holds |
|---|---|---|
| `source/provenance.json` | hand | format 1.1.0: domain `digital`, the three files as format `verilog`, the two copies with `copied_from`, the MIT licence cited by the `LICENSE` digest, created and collected 2026-09-27 |
| `source/tb_uart_loopback.v` | hand | the declarative top (2152 bytes): `CLK_HALF_PERIOD_NS = 10` (the 20 ns clock), `CLK_FREQ = 50_000_000`, `BAUD_RATE = 115_200`, `RESET_CYCLES = 4`, `TX_BYTE_0 = 8'h35`, `TX_BYTE_1 = 8'hCA`, nine signals and the two instances. Its comment says the values are design choices of the testbench, not a rating, measurement or datasheet value of any part |
| `source/uart_tx.v`, `source/uart_rx.v` | copies of `rtl/uart_tx.v`, `rtl/uart_rx.v` | the transmitter and receiver RTL, with their own headers (SPDX MIT) |
| `design/annotations.json` | hand | format 1.2.0: the target device, none selected, with `min_clock_period` `UNKNOWN`; `tb_uart_loopback constrained_by target_device` |
| `requirements/requirements.json` | hand | 8 references and 7 illustrative requirements (below) |
| `derived/engineering_model.json` | `build` | format 1.2.0: 4 components (the top, `u_tx`, `u_rx`, `target_device`), 1 null-status value |
| `derived/digital/uart_loopback_001.v` | `build` | the file Icarus compiles: 13 240 bytes, 357 lines, sha256 `597eebf2…fd83`; the two header lines, `source/uart_tx.v` from line 3, `source/uart_rx.v` from line 115, the harness from line 242 |
| `validation/golden/cases.json`, `validation/corners/cases.json` | `build` | 8 V3 cases; 6 V4 cases (REQ-DIG-007 is blocked when compiled) |
| `dataset-item.json` | `build` | the manifest: digital `AVAILABLE`, mechanical and electrical `NOT_APPLICABLE`, the other six `NOT_IMPLEMENTED` |

There is no `simulation/` directory (no script runs) and no per-sample README
(`check` reports any file the manifest does not record). Invalid and boundary
inputs are built by the tests as copies, not committed.

## Requirements

`requirements/requirements.json` follows
`engineering-model/v1/engineering-requirements`; every entry has domain
`digital` and scenario `loopback`, the only one
`schemas/engineering-model/v1/digital-vocabulary.schema.json` names, which
carries only its name: every case runs the same file. The adapter also
refuses a derivation paired with another metric than the one it computes.

- **References** REF-DIG-001 to 008: one per metric but
  `outputs_unknown_after_reset`, each comparing Icarus with its closed form.
  Their source is model verification, not a design requirement.
- **Requirements** REQ-DIG-001 to 007, all `illustrative: true`: example
  limits chosen to exercise the pipeline, not customer, interface or
  certification requirements; no standard or peer device was consulted.
  Meeting one is `WARNING`, never `PASS`.

| Id | Component | Limit | Source of the limit |
|---|---|---|---|
| REQ-DIG-001 | u_tx | bit rate ≥ 112 896 Bd ("no slower than 115200 Bd less 2 %") | example |
| REQ-DIG-002 | u_tx | bit rate ≤ 117 504 Bd ("no faster than 115200 Bd plus 2 %") | example |
| REQ-DIG-003 | u_rx | bytes received ≥ the bytes sent ("every byte the testbench offers arrives") | `components/tb_uart_loopback/domains/digital/byte_count`, `DERIVED` |
| REQ-DIG-004 | u_rx | bit errors ≤ 0 ("no bit is lost or received wrong") | example |
| REQ-DIG-005 | u_rx | framing errors ≤ 0 | example |
| REQ-DIG-006 | tb_uart_loopback | unknown outputs ≤ 0 "at the first falling clock edge after reset is released" | example |
| REQ-DIG-007 | tb_uart_loopback | clock period ≥ the shortest the target device can meet | `UNKNOWN`: `BLOCKED` |

## Expected outputs

Each row is a test; the ones that name real Icarus ran on Icarus 13.0, the
others on a stand-in that replays Icarus 13.0's recorded output (**Verified**:
every row's test passed in the complete suite, `TASKS.md` T-013).

| Input | Receipt | Test |
|---|---|---|
| The committed sample | V0–V3 `PASS`; V4 `BLOCKED`: REQ-DIG-001..006 `WARNING WITHIN_ILLUSTRATIVE_LIMIT`, REQ-DIG-007 `BLOCKED MISSING_REQUIRED_INPUT`; overall `BLOCKED`, not eligible; 15 results | Example above; `test_the_committed_sample_validates_as_designed` (real Icarus), `test_the_committed_sample_validates_as_designed_with_recorded_icarus_output` (stand-in) |
| `BAUD_RATE` 115 200 → 230 400, rebuilt | V1–V3 `PASS` (W holds at D_r 13); REQ-DIG-002 `FAIL CORNER_LIMITS_FAILED` at 230 414.75 Bd: the design's `FAIL`, not the simulator's | `test_a_mutated_baud_rate_fails_only_the_bit_rate_requirement`, `test_the_fail_copies_give_the_verified_metrics_and_verdicts` (real Icarus) |
| A 20 MHz clock (half period 25 ns), rebuilt | W fails at D_r 10: REF-DIG-006..008 `BLOCKED REFERENCE_NOT_APPLICABLE`, the other references `PASS`; 1 byte received, 15 bit errors (7 + the missing byte's 8), 1 framing error; REQ-DIG-003, 004, 005 `FAIL` | `test_a_mis_sampling_receiver_fails_on_the_bytes_and_its_references_do_not_apply`, and the real-Icarus fail copies |
| The instances told 40 MHz, the clock at 50 MHz | V1 `FAIL`: "u_tx CLK_FREQ 40000000 Hz is not the frequency of its clock (half period 1e-08 s, 50000000 Hz)", and the same for u_rx; REQ-DIG-002 `FAIL` | the real-Icarus fail copies |
| The receiver alone at 57 600 Bd | W fails: the receiver's references do not apply; 1 byte, 12 bit errors (4 + 8), no framing count; REQ-DIG-003, 004 `FAIL`, REQ-DIG-005 `INCONCLUSIVE` | the real-Icarus fail copies |
| The transmitter at 121 000 Bd / 120 500 Bd | both bytes, no error; REF-DIG-006..008 not applicable / `PASS` | `test_the_sampling_condition_is_conservative_at_its_edge` |
| The RTL defects above | as the table of Validation capabilities | `test_rtl_defects_fail_their_references` |
| A limit on the boundary, one float beyond, and with a tolerance | `WARNING`, `FAIL`, `WARNING` on both operators | `test_the_limit_boundaries_are_exact`, `test_the_limit_boundaries_with_real_icarus` (4340 cycles: `WARNING` at ≤ 4340, `FAIL` at ≤ 4339) |
| `min_clock_period` as `UNKNOWN`, `UNSPECIFIED`, `NOT_AVAILABLE` | `BLOCKED MISSING_REQUIRED_INPUT` naming the status and path; a schema-valid receipt | `test_each_null_status_of_the_device_limit_blocks_with_its_status_and_path` |
| A real (non-illustrative) copy of REQ-DIG-007 on a `SPECIFIED` 1e-8 s fixture limit; the same as `AI_ASSUMPTION`, met and violated | `PASS`; `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` both times | `test_the_device_limit_passes_only_when_specified_and_real_never_when_ai_assumed` |
| Icarus not on `PATH` | the 14 compiled cases `BLOCKED TOOL_NOT_INSTALLED`, attributed to `ecad-validator`; REQ-DIG-007 `BLOCKED MISSING_REQUIRED_INPUT`; 15 results, none with a simulator version | `test_without_icarus_every_case_is_blocked_and_the_receipt_holds` |
| A source with `` `include ``, `$fopen`, `defparam` or a hierarchical write | V1 `FAIL SOURCE_REJECTED` naming the line; V2–V4 `BLOCKED DERIVATION_NOT_AVAILABLE`; Icarus never called | `test_a_refused_source_gives_a_receipt_and_never_reaches_icarus` |
| Every class rule broken in turn; the resource guard; a parameter above 2^31 - 1 | V1 `FAIL SOURCE_REJECTED` naming the rule, Icarus never called (through `validate`); refused at extraction, kind `rejected`, naming C7 or C4 | `test_only_the_uart_8n1_loopback_is_accepted`; `test_the_resource_guard_refuses_a_run_longer_than_max_cycles`, `test_a_parameter_is_at_most_what_an_unsized_decimal_holds` |
| The simulation file edited without a rebuild | `v2.dataset-reproduction` `FAIL DERIVATION_DIVERGED`; `v2.digital.model-invariants` `PASS`; every compiled case run, then `BLOCKED COMMITTED_CASE_STALE` | `test_a_simulation_file_edited_without_a_rebuild_is_divergent_and_not_counted` |
| An RTL copy edited without a rebuild | V0 `FAIL`: "not a byte-identical copy of rtl/uart_tx.v"; reproduction `FAIL`; every case `COMMITTED_CASE_STALE` | `test_an_rtl_copy_edited_without_a_rebuild_is_caught_at_v0_and_v2_and_not_counted` |
| An origin edited, a copy edited, an origin inside the item, outside the repository or not a regular file | `check` and V0 name each | `test_a_copied_source_is_bound_to_its_origin` |

## Evidence

- **The simulation file** (`derived/digital/uart_loopback_001.v`, 13 240
  bytes, sha256 `597eebf2…fd83`) is hash-bound in the manifest and cited,
  with its case document, by every check whose case ran. Its separator lines
  carry each leaf's digest, which is its source's.
- **Each check's execution record** holds the command
  (`[<vvp>, "simulation.vvp"]`), the tool version from `iverilog -V`, the
  metrics, and vvp's stdout and stderr verbatim. Stdout names no host path
  (**Verified**: `test_icarus_reproduces_the_closed_forms`), and two runs'
  stdout are identical. The command's first element is the absolute
  executable path (STATE-2).
- **The compiled program is never evidence.** It lives only in the deleted
  stage directory, and its `:vpi_module` lines hold absolute install paths
  (**Verified** on a probe program: `:vpi_module
  "/opt/homebrew/Cellar/icarus-verilog/13.0/lib/ivl/system.vpi";`).
- **Results** (`results.json`) record, for each requirement and reference,
  the inputs it rests on with their statuses, the simulator and its version,
  the configuration (command, scenario `loopback`, seed 0), the fidelity
  `SIMPLIFIED`, the components (`cad_components`, the instances a metric
  depends on), and the run's environment (OS, machine, Python, the tool
  versions).

## Training data

None. Training records are specified in the plan (§15) and not produced by
any domain yet. The digital results carry what a record would need (inputs
with statuses, simulator version, evidence, fidelity); the spec's digital
tasks are PLANNED.

## Future work

PLANNED, none started:

- a Verilator adapter, after the cases contract admits it (plan §20 Q9) and
  CI has a Verilator of 5 or later, with a check that two simulators agree;
  ModelSim/Questa as an optional adapter that reports `BLOCKED` when absent;
- a screen of the compiled program and `vvp -N` (SEC-3), and the SEC-2
  runner guard (plan §7.2), which is its own foundation change;
- a framing-fault scenario, so the receiver's stop-bit check is exercised;
- more of Verilog: negedge and asynchronous reset, `assign`, `generate`,
  `$clog2` (for `rtl/spi_master.v`, a second sample), deeper hierarchy,
  SystemVerilog, VHDL; FSM extraction; each with its closed forms;
- timing against a real device once one is selected, and SDC/XDC/PCF
  constraints;
- pinning Icarus in CI after the `hdl` job's first run, and a run on the
  x86_64 runner (only arm64 containers have run the job's steps).
