> **Status of this document.** This is the design the digital domain was built
> from, written before any code (2026-09-27): three independent designs, each
> with a different priority (the smallest change, data honesty and security,
> reuse by later domains), scored by a fourth reviewer who checked their claims
> against the code, against Icarus Verilog 13 on macOS and against Icarus 11 in
> an ubuntu:22.04 container, and wrote this synthesis. It is kept as the record
> of what was decided and why, not as a description of the code. Where the
> implementation departs from it, the decision and its reason are in `MEMORY.md`
> and the branch review's table in the plan. Examples: a byte that never arrives
> counts as eight bit errors; V1 compares clocks in whole Hz; the grammar also
> refuses `bool`, `wone` and `wreal`; REQ-DIG-006 names the one instant it
> measures. The code, `docs/digital-domain-v1.md` and `TASKS.md` T-013 describe
> what exists and what verified it. The scratch evidence the design cites was
> produced on a local machine and is not in the repository; what the
> implementation relies on is re-checked by its tests and the commands recorded
> in T-013.

# Digital / FPGA domain design (final): `uart_loopback_001` on Icarus Verilog

**Mode:** Architecture. This is a design. Nothing is implemented, committed or
pushed. The clone `design-base-digital` (`feat/domain-electrical` at `2ba5fe0`)
was only read: `git status --short` prints 0 lines (**Verified**, 2026-09-27).

**Evidence labels** follow `CLAUDE.md`. **Verified** means I ran it on
2026-09-27 on one of:
- this Mac: Icarus Verilog 13.0 (`/opt/homebrew/bin`), Verilator 5.052 with
  `SDKROOT=…/MacOSX26.sdk`, CPython 3.14.4 (the scratchpad venv);
- `ubuntu:22.04` under Colima, which runs **linux/arm64** (not the x86_64 the
  CI runner uses): apt `iverilog 11.0-1.1`, `verilator 4.038-1`. Containers
  were created with `docker create` + `docker cp` + `docker start -a`, named
  `ecad-judge-*`, and removed.

**Scratch evidence** is under
a local scratch directory (`judge/`) that is not part of the repository.
The three input designs' own evidence (`minimal-lens/`, `honesty/`,
`extensible-lens/`) was read and re-run, never edited. One exception, stated so
nobody trusts a stray file: running `honesty/proto_writer.py --help` wrote a
file named `--help` into `honesty/` (the script takes its output path from
`argv[1]`); I moved it to `judge/honesty_regenerated.v`. It is byte-identical to
`honesty/gen/uart_loopback_001.v`, which confirms that prototype is
deterministic.

| File (under `judge/`) | What it holds |
|---|---|
| `final/source/tb_uart_loopback.v`, `uart_tx.v`, `uart_rx.v` | the three sample sources of §1, byte for byte |
| `final/writer.py` | scratch prototype of `write_simulation` (§4); not repository code |
| `final/v/committed.v` | the simulation file of §4.2 (12 852 B, sha256 `191bd8f16c0167764878d099ac5a1fc8c4a2e509e06e433997452cb5944d3e84`) |
| `final/v/*.v`, `*.out` | the committed file and 13 variants (§5.4, §6.4), with Icarus 13 stdout |
| `final/closed_forms.py` | independent closed forms of §5, checked against every variant: 0 mismatches |
| `final/proto_top.py` | scratch prototype of the declarative-top grammar and class rules C1–C6: accepts the committed files, refuses 12 probes |
| `final/arch10/probe.py` | the two-step Icarus flow through a copy of `run_process` with `collect` (§7.2) |
| `final/vl/` | Verilator 5.052 builds and runs of the final harness |
| `ctr2/container.log` | the 13 final files on Icarus 11 (`ubuntu:22.04` arm64) |
| `ctr/container*.log` | Icarus 11 on the three input designs; Verilator 4.038 refusals; option-order probes |
| `mac/` | Icarus 13 probes: `include`, `$fopen`, `$readmemh`, `$system`, `.sfunc`, `$fatal`, DPI, `defparam`, hierarchical write, `$stop`, `IVERILOG_ICONFIG`, option order |
| `min/`, `hon/`, `ext/`, `ext20/`, `hon54/`, `honv/`, `min_fail-*` | re-runs of the input designs' files and my counter-examples |

**Base design:** *minimal*. Its architecture is kept: one self-contained
derived simulation file, the RTL text carried verbatim in the model and bound
to the sources by hash, no protocol change, a restricted pure-Python grammar,
ARCH-10 and ARCH-2's output-copy half as the only engine changes, the derived
sampling condition W, and the `hdl` CI job before `cad-dataset`.

**Grafts:**
- **From *extensible*:** the declarative top (no behaviour in any source; the
  adapter writes the clock, stimulus and measurements), the falling-edge
  harness with N bytes, the complementary bytes `0x35`/`0xCA`,
  `tx_idle_after_reset`, `rx_bit_errors`, the `VALIDATOR_VERSION` bump, the
  RTL defect copies (including the framing-detection gap), `collect_problems`
  and the size cap, and the next-header CI slice helper.
- **From *honesty*:** a posedge-only, nonblocking-only RTL grammar, the
  keyword-class refusal table, `outputs_unknown_after_reset`, the bit rate in
  Bd, a DERIVED `byte_count` for a quantity limit, refusing case arguments,
  RESULT-2 on the iverilog path, the `IVERILOG_ICONFIG` test, and a new
  production-registry `NOT_IMPLEMENTED` test.

Every conflict is resolved in §0.3.

---

## 0. Assessment of the three designs

### 0.1 Scores (1-10)

| Criterion | minimal | honesty | extensible |
|---|---|---|---|
| Correctness against the code and the tools | 7 | 6 | 5 |
| Data honesty | 9 | 9 | 8 |
| Completeness against the plan's per-domain list | 8 | 9 | 8 |
| Testability (verdict paths reachable, killable mutants) | 7 | 7 | 8 |
| Blast radius on merged code (10 = smallest) | 9 | 4 | 4 |
| Usefulness to later domains | 6 | 7 | 8 |
| **Total** | **46** | **42** | **41** |

**minimal (46).**
- Its citations hold: I re-ran its simulation file on Icarus 13 and 11
  (identical metric lines), its two FAIL copies (217/2170/165 and
  173/1730/**101**), its 61 grammar probes (0 unexpected), its sweep counts
  (68 of 68 recovered where W holds; 15 of 76 where it fails, all `0xFF`) and
  its Verilator claim (unarmed: `tx_bit_cycles 1`, armed: 434).
- Two things only it gets right:
  - the sampling condition W is derived from the receiver's actual schedule
    and has no fudge constant;
  - no protocol change and no merged-schema relaxation.
- It loses points for:
  - `TX_BYTE = 0xA5` is a bit palindrome, so a receiver with its bit order
    reversed still reports 165 (**Verified** with the final harness: 0 bit
    errors, `v/palindrome_a5_bit_order.out`);
  - its class rules U1–U7 never look at the stimulus `initial` block, so
    nothing ties what the testbench sends to the `TX_BYTE` and `RESET_CYCLES`
    facets;
  - three false claims (§0.2).

**honesty (42).**
- It has the best record of tool facts: every F-row I re-ran holds
  (`IVERILOG_ICONFIG`, `.sfunc`, `-N`, `$fatal`, DPI, `-m`).
- It loses points for:
  - Icarus simulates a canonical *reprint* of the RTL, not the committed
    bytes, so "HDL compilation" is of text the sample does not contain;
  - screens, argument refusal and `vvp -N` in merged `hdl.py`, six new
    component kinds, a new annotation section and a relaxed merged schema
    rule;
  - a receiver condition with a heuristic method constant;
  - a bit-rate reference that is wrong for an even first byte (§0.2).

**extensible (41).**
- It has the best harness (declarative top, falling-edge sampling, N bytes,
  bit-order-sensitive bytes; identical on Icarus 11, 13 and Verilator 5.052,
  **Verified**) and the most useful RTL defect study (the receiver's framing
  check is never exercised).
- It loses points for:
  - annotations its own schema refuses;
  - a protocol change it calls forced, which is not;
  - receiver references that claim a lossless link whenever the
    configuration is "matched", which the RTL does not deliver at 20 MHz;
  - an RTL body screened by token only;
  - a new `markers.py` abstraction with one user.

### 0.2 Claims in the designs that are false against the code or the tool

| # | Design | Claim | What is true |
|---|---|---|---|
| F1 | extensible | §1.5 "No annotations-schema change is needed: format 1.0.0 already has `components_without_cad` (Observed)"; §2.3 "Unchanged: … design-annotations" | `components_without_cad[].domains` is closed to `mechanical`, `electrical`, `control`, `thermal` (`design-annotations.schema.json:200-216`). The design's own `annotations.json` fails: "components_without_cad/0/domains: Additional properties are not allowed ('digital' was unexpected)" (**Verified**, `ecad_model.schemas.validate`). `build` and V0 would refuse the committed sample. |
| F2 | extensible | DD5/§8 "Protocol change: `case_target(model, sample_id)`. It is forced" | Not forced. Carrying each leaf's text in the model (minimal D1, honesty §2.4) lets `write_models(model, …)` emit one self-contained file under the existing `case_target(sample_id)`. The rejected alternative's premise ("`write_models` cannot read sources") is answered by that. |
| F3 | extensible | §5.2 `bytes_sent`, `lossless_loopback`, `no_framing_errors` apply whenever tx and rx are "matched" | False for this RTL. With a matched 20 MHz configuration, the design's own harness receives 1 of 2 bytes, with 7 bit errors and 1 framing error (**Verified**, `judge/ext20/`). REF-DIG-006…008 would then FAIL V3 on a closed form the RTL never satisfied, instead of `REFERENCE_NOT_APPLICABLE`. |
| F4 | honesty | §5.3 `bit_rate` (f/B_t) applies "always" | The harness measures the first low run of the line. With an even first byte that run covers the start bit and bit 0: `0x54` gives 1302 cycles and 38 402.46 Bd (**Verified**, `judge/hon54/`). REF-DIG-005 would FAIL V3; it needs the odd-first-byte condition its `bit_period_cycles` already has. |
| F5 | minimal | Mutant 35 `digital-sampling-upper-bound-inclusive` (`<` → `<=`) is "killed by D9 (152/153)" | At D_r = 10 the binding bound (b = 9) is `1529 < 10·D_t`, which is never an equality, so the mutant agrees with the code at 152 and at 153 (**Verified**, arithmetic). The first equalities are (D_t, D_r) = (107, 7), (260, 17), (413, 27), (566, 37). |
| F6 | minimal | §13 SEC-3: "The dataset path is closed by content reconciliation, which requires arguments equal to `[]`" | The runner executes the whole committed document first (`dataset.py:1267`) and filters stale cases afterwards (`dataset.py:1277-1279`). A forged case with arguments runs; it is only not counted. On Linux, `iverilog … file.v -N /tmp/x` wrote `/tmp/x` (**Verified**, Icarus 11). |
| F7 | minimal | §6.3 "V0-V3 PASS (2 + 1 + 2 + 6 checks)" | V0 has three checks: `v0.dataset-schemas-and-hashes`, `v0.dataset-input-immutability` and `v0.pinned-clean-source` (`dataset.py:965`, `1109-1130`). |
| F8 | honesty | F8: vvp prints "`$finish called at <t> (1ps)` to stdout" (stated generally) | True of Icarus 13 only. Icarus 11, CI's version, prints no such line (**Verified**, all 13 final files). The metric lines are identical. |
| F9 | honesty | §7.3 "SEC-1, the HDL part (named defect, plan §2 and R5)" as the basis for screens and `-N` | The plan names SEC-1's remedy as "container or seccomp confinement" (plan R5). Tool-level screens and `-N` change merged `hdl.py` behaviour that no named defect asks for. |
| F10 | extensible | §3.1 the RTL body rule "no `#`" refuses "delays and instances (`#`)" | Only instances with parameter overrides carry `#`. `uart_rx u (.rx(x));` inside a leaf passes a token screen, and so does a hierarchical reference (`.` is an accepted operator). Icarus lets another module's register be written that way: `u.secret = 1` took effect (**Verified**, `judge/mac/defp.v`). |

Overstated, not load-bearing:
- honesty says the `const "1.1.0"` rule "contradicts the rule's own
  description at line 22". The description does not cover a document with
  two additions, so relaxing it is a choice, not a correction.
- extensible's "`git check-attr` prints nothing" holds for `-a`;
  `git check-attr text rtl/uart_tx.v` prints `text: unspecified`.

**Checked and holding** (**Verified** by a re-run, or **Observed** in the code):
- every file hash and size the three designs give;
- the metric lines of all three harnesses on Icarus 13, Icarus 11 (arm64) and
  Verilator 5.052;
- Verilator 4.038: "Invalid option: --binary", "Invalid option: --timing",
  "Unsupported: timing control statement in this location";
- Verilator 5.052's stdout carries wall-time lines that differ between runs;
  7 `WIDTHEXPAND` warnings on the RTL;
- macOS Icarus 13 reads `-s b` after the files as a file name
  ("-s: No such file or directory"), while Linux Icarus 11 parses it as an
  option; `-m /abs` after the files looks for a VPI module there and exits 0;
- `include` reads outside files and leaks their identifiers into stderr;
  `$fopen` writes; `$readmemh("/etc/hosts")` opens the file; `$system` is
  "not defined by any module", exit 1; `wire f = $fopen(…)` compiles to
  `.sfunc` and writes; `$fatal` exits 1; `$stop` blocks on an open stdin,
  continues on `/dev/null`, and exits 1 under `-N`;
- the scrubbed environment of `run_process` stops `IVERILOG_ICONFIG`;
- today's `HDLAdapter` returns `PASS RTL_TESTBENCH_PASSED` with `metrics {}`
  and inherits the environment (**Verified**, `judge/final/arch10/`);
- no `spice` job at `2ba5fe0`, no electrical documentation, a stale README
  row, a stale `test_domain_adapter.py:3` (extensible B1–B3);
- plan §7.2 has no ARCH-10, ARCH-2, REUSE-1 or SEC-1 rows: they sit at
  plan:62, 92-93, 577-581, 908-910 and 956 (extensible B2).

### 0.3 Decision log

| # | Decision | From | Rejected alternatives and why |
|---|---|---|---|
| D1 | Iverilog compiles **one derived file**, `derived/digital/<id>.v`. It holds each leaf module's source text verbatim, carried in the model (`hdl.text`) and bound to `design.sources` by hash, then a harness written from the model. **No protocol change.** | minimal | extensible's `case_target(model, sample_id)` with the RTL copies as case inputs: not forced (F2), touches both production adapters, the fixture, `results.py:297` and six test sites, and a copy edited without a rebuild would still run, since source files are not derived inputs the staleness guard sees (`dataset.py:1253-1262`). honesty's canonical reprint: Icarus would compile text the sample does not contain, and a printer bug could change semantics under a passing round-trip. Re-reading sources inside `write_models`: a hidden input (`MEMORY.md:75`). |
| D2 | **The top is declarative.** `source/tb_uart_loopback.v` states the clock half-period, the reset length, the parameters each instance receives, the bytes and the wiring, and nothing else. The adapter writes the clock, the stimulus and every measurement from the model. | extensible | minimal's behavioural testbench as a source: its class rules never inspect the `initial` block, so nothing ties what is sent to the facets, and the grammar must accept `initial`, `repeat`, event controls, delays and initialisers in untrusted text. honesty's annotations for clock, reset and stimulus: moves source-of-truth values out of the hash-cited HDL into JSON. |
| D3 | **A restricted pure-Python grammar** in `tools/ecad_model/verilog.py`, with two file forms: synchronous RTL (posedge only, nonblocking only, one module per file, no instances, no wires) and the declarative top. It refuses by name every `$`, every directive except a leading `` `timescale 1ns / 1ps ``, strings, attributes, DPI, hierarchical references, `ecad_` names and the text `ECAD_METRIC`. | minimal (grammar), honesty (posedge and nonblocking only, keyword classes), extensible (declarative top form), synthesis (`ECAD_METRIC` reserved) | extensible's token screen of RTL bodies: admits parameterless instances and hierarchical references (F10). `iverilog -E` or `verilator --json-only`: tool-dependent, version-bound, and they run native code on untrusted text before any refusal. |
| D4 | **One network class**, the 8N1 UART loopback (rules C1–C7), named in the `AVAILABLE` reason. Anything else is `SOURCE_REJECTED` and never reaches Icarus. The resource guard (END ≤ 2 000 000 cycles) is an extraction refusal. | all three; `MEMORY.md:77-78` | Generic HDL: the closed forms describe this pair only. A V1 finding for the guard: it bounds nothing, since the cases run whatever V1 says (`MEMORY.md:78`). |
| D5 | **Nine metrics, all `SIMPLIFIED`**, read from `ECAD_METRIC <name> <value>` lines the harness declares with `$display("ECAD_METRIC <name> %0d"\|"%.17g", …)`. A name is read only if it is declared once and reported once with a finite plain-decimal value. The parser lives in `hdl.py`. | minimal (markers), extensible and honesty (metric set) | extensible's `markers.py`: a shared module with one user now; QUALITY.md says to wait for the third occurrence (ngspice's parser is the first, hdl's the second). A new fidelity value: changes `base.py:29` and the results schema (Q-D4). |
| D6 | **Two bytes, `0x35` then `0xCA`**: complements; neither is its own bit reversal; `0x35` is odd, so the start bit is the line's first low interval. | extensible | minimal's `0xA5`: a bit palindrome, blind to a reversed bit order (**Verified**). honesty's four bytes: more cycles, and nothing more is detected. |
| D7 | **Closed forms from the class contract**: D_t = ⌊CLK_FREQ/BAUD_RATE⌋ and D_r = ⌊CLK_FREQ/(BAUD_RATE·OVERSAMPLE)⌋, computed from the facets and never from the RTL's localparam expressions. Receiver references are gated by W; bit-period and bit-rate references by an odd first byte. | minimal (W), extensible (contract, not self-reference) | extensible's "matched" gate (F3). honesty's condition with `SYNC_ALLOWANCE_CYCLES = 3`: a heuristic constant where W is exact. minimal's references built on the parser's evaluation of `BAUD_DIV`: V3 would check the RTL against itself. |
| D8 | **Engine changes:** <br>• ARCH-10: both Icarus steps through `run_process`; <br>• ARCH-2, output-copy half: opt-in `collect` in `run_process`; <br>• ARCH-2, metric half: declared markers in `hdl.py`, with truncated output `INCONCLUSIVE` and exit ≠ 0 `FAIL` with no metrics; <br>• non-empty case `arguments` refused (`BLOCKED RTL_ARGUMENTS_REFUSED`); <br>• RESULT-2 mapped locally, as ngspice does. | minimal + extensible (collect with problems and cap), honesty (argument refusal, RESULT-2) | honesty's program screen and `vvp -N`: not named by any defect (F9); PLANNED as SEC-3. Keeping arguments on the argv (minimal, extensible): with ARCH-2 the metrics are read from the inputs' declarations, and `-s`, `-D`, `-y`, `-c` or `-f` would compile something else, while `-m` or `-L` load native code. The same reasoning made ngspice run with nothing but `-b <deck>` (`MEMORY.md:67`). Refused rather than dropped silently: QUALITY.md says never fail silently. No committed case uses iverilog (**Verified**, `git grep`). |
| D9 | **Model format 1.2.0** adds an optional `components[].hdl`. Annotations 1.2.0 add a `digital` facet on `components_without_cad`. Provenance 1.1.0 adds `artifacts[].copied_from`. **No new component kinds** (`other`). The 1.1.0 `const` rule is unchanged. | minimal | honesty's six kinds and extensible's two: vocabulary changes the `hdl` member already makes unnecessary. honesty's relaxation of the 1.1.0 rule: a merged-contract change this sample does not need (open question Q-D6). |
| D10 | **REUSE-1:** `copied_from {path, sha256}` in the provenance, checked by `cited_source_problems` (so by `check` and V0). The copy must be byte-identical and the origin must lie in the repository but outside the item. `VALIDATOR_VERSION` goes 1.0.0 → 1.1.0. | all three; extensible (version bump) | Restating it in the manifest: a format change nothing needs (Q-D5). Leaving the validator's version as is: plan §9.3 bumps a producer whose behaviour changes. |
| D11 | **Verilator is PLANNED**, not a second adapter (§7.8). **ModelSim/Questa is PLANNED only**: licensed, with no adapter and no stub. | all three | A Verilator adapter now: it needs Q9, a CI Verilator ≥ 5, a filter for wall-time lines, a C++ build per case, and a 2-state caveat. |
| D12 | **The fixture coexists.** `test_without_its_adapter…` is re-scoped to a registry without `digital`. A new test keeps the production-registry `NOT_IMPLEMENTED` path covered with a `pcb` sample. | all three (coexist), honesty (new test) | Replacing `VerilogFixtureAdapter`: about 1 000 lines of runner regressions build on its subclasses (`test_domain_adapter.py:269-1110`). |
| D13 | **CI:** the `hdl` job goes between `validation-evidence` and `cad-dataset`. Its test slices to the next job header. | minimal (placement), extensible (helper) | After `cad-dataset`: it would join the existing slice `test_ci_and_runner.py:59-61`. |
| D14 | **The layout stays `datasets/cad/<id>/`.** | the brief | Plan §21 moves it with the first non-mechanical sample. The brief overrides it (`CLAUDE.md` precedence 1), and the conflict is recorded here and in the plan. |
| D15 | **A fixed-length run.** END = RESET + (N + 2) · 12 · max(T_tx, T_rx, 16). A spurious extra byte inside two idle frames is counted. | minimal (fixed length), extensible (formula) | extensible's early stop at the N-th byte: an extra `rx_valid` after it would never be seen. |

---

## 1. Sample

### 1.1 Identity and layout

- **Sample id / `design_id`:** `uart_loopback_001`.
- **Directory:** `datasets/cad/uart_loopback_001/` (D14). The mutation harness
  finds the item as `Path(relative).parts[:3]` (`run_mutations.py:574`).

| Path | Written by | Role |
|---|---|---|
| `source/provenance.json` | hand | licence, origin, domain `digital`, three `verilog` artefacts, two with `copied_from` (§1.4) |
| `source/tb_uart_loopback.v` | hand | the declarative top (§1.3) |
| `source/uart_tx.v` | byte copy of `rtl/uart_tx.v` | transmitter RTL |
| `source/uart_rx.v` | byte copy of `rtl/uart_rx.v` | receiver RTL |
| `design/annotations.json` | hand | the unselected target device (§1.5) |
| `requirements/requirements.json` | hand | 8 references and 7 requirements (§6) |
| `derived/engineering_model.json` | `build` | format 1.2.0 |
| `derived/digital/uart_loopback_001.v` | `build` | the one file Icarus compiles (§4) |
| `validation/golden/cases.json` | `build` | 8 V3 cases |
| `validation/corners/cases.json` | `build` | 6 V4 cases; REQ-DIG-007 is blocked at compile time (`requirements.py:151-162`) |
| `dataset-item.json` | `build` | the manifest |

Deliberately absent:
- **`simulation/`:** `simulation_files()` returns `[]`, as in electrical.
- **A per-sample README:** `integrity()` reports unrecorded files
  (`dataset.py:640-643`).
- **`spi_master.v`:** it uses `$clog2` (`rtl/spi_master.v:36-37`) and a
  parameterised range (`:18`), both refused. It is PLANNED as a second sample.

### 1.2 The RTL copies (REUSE-1)

| Copy | Origin | Bytes | sha256 (both, **Verified**) |
|---|---|---|---|
| `source/uart_tx.v` | `rtl/uart_tx.v` | 3367 | `5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a` |
| `source/uart_rx.v` | `rtl/uart_rx.v` | 4195 | `c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81` |

- **Line ends and encoding:** LF in index and worktree (`git ls-files --eol`:
  `i/lf w/lf attr/`). UTF-8 with non-ASCII only inside `//` comments: 2 lines
  in `uart_tx.v`, 5 in `uart_rx.v`, 0 in code (**Verified**).
- **Headers:** both state `SPDX-License-Identifier: MIT` and
  `Copyright (c) 2026 EmbeddedOS Foundation` (`uart_tx.v:16-17`,
  `uart_rx.v:5-6`). Both were added in `f15a4aa` by "EmbeddedOS CI". The
  copies keep the headers unmodified.
- **Attributes:** `git check-attr text rtl/uart_tx.v` prints `unspecified`.
  The PR adds `rtl/uart_tx.v -text` and `rtl/uart_rx.v -text`; the copies are
  covered by `datasets/cad/** -text` (`.gitattributes:41`). Without the new
  lines, a Windows checkout with `core.autocrlf` would change the origins'
  bytes, and REUSE-1 would fail there.
- `tests/test_rtl_models.py` stays byte-identical, sha256
  `7a9ced8edde3a4100b67a3cfddfc8096d53f0222b8747087df5e70eb471a2866`
  (**Verified**).

### 1.3 `source/tb_uart_loopback.v`, exactly

2152 bytes, ASCII, LF only, sha256
`2962c844a2191ab756ad190e184365ab1893650ae67fee5a078b610ff7719fed`
(**Verified**). With the two RTL files it compiles on Icarus 13 and `vvp` exits
0 printing nothing: it has no clock and no measurement (**Verified**).

```verilog
// tb_uart_loopback.v -- loopback top for the 8N1 UART pair in rtl/ (eCAD digital MVP, issue #27)
//
// Self-authored for the eCAD multi-domain validation pipeline. It states what
// is simulated and nothing else: the clock, the reset, the parameters both
// instances receive, the bytes sent, and how the two instances are wired. It
// holds no behaviour: ecad_model.domains.digital writes the clock, the
// stimulus and the measurements into the harness it simulates, from the
// engineering model built from this file.
//
// No board, oscillator or peer device is modelled. The clock half-period, the
// clock frequency the instances are told, the baud rate, the reset length and
// the bytes are design choices of this testbench, not a rating, measurement or
// datasheet value of any part. 50 MHz and 115200 baud are the defaults that
// rtl/uart_tx.v and rtl/uart_rx.v declare; CLK_HALF_PERIOD_NS is in the 1 ns
// time unit below, so the clock period is 20 ns, which is CLK_FREQ. The two
// bytes are complements and neither reads the same with its bit order
// reversed, so a stuck bit or a swapped bit order changes what is received;
// TX_BYTE_0 is odd, so the start bit is the line's first low interval.
//
// SPDX-License-Identifier: MIT

`timescale 1ns / 1ps

module tb_uart_loopback;

    localparam CLK_HALF_PERIOD_NS = 10;
    localparam CLK_FREQ           = 50_000_000;
    localparam BAUD_RATE          = 115_200;
    localparam RESET_CYCLES       = 4;
    localparam [7:0] TX_BYTE_0    = 8'h35;
    localparam [7:0] TX_BYTE_1    = 8'hCA;

    reg        clk;
    reg        rst_n;
    reg  [7:0] tx_data;
    reg        tx_valid;
    wire       tx_ready;
    wire       line;
    wire [7:0] rx_data;
    wire       rx_valid;
    wire       rx_error;

    uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_tx (
        .clk(clk), .rst_n(rst_n), .tx_data(tx_data), .tx_valid(tx_valid),
        .tx_ready(tx_ready), .tx(line)
    );

    uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_rx (
        .clk(clk), .rst_n(rst_n), .rx(line),
        .rx_data(rx_data), .rx_valid(rx_valid), .rx_error(rx_error)
    );

endmodule
```

Line numbers used below: the localparams are lines 26–31; `u_tx` is line 43
and `u_rx` line 48.

### 1.4 `source/provenance.json` (format 1.1.0)

```json
{
  "$schema": "https://embeddedos.org/schemas/cad-dataset/v1/source-provenance.schema.json",
  "provenance_version": "1.1.0",
  "domain": "digital",
  "artifacts": [
    {"path": "source/tb_uart_loopback.v", "format": "verilog"},
    {"path": "source/uart_tx.v", "format": "verilog",
     "copied_from": {"path": "rtl/uart_tx.v", "sha256": "5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a"}},
    {"path": "source/uart_rx.v", "format": "verilog",
     "copied_from": {"path": "rtl/uart_rx.v", "sha256": "c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81"}}
  ],
  "description": "8N1 UART loopback: rtl/uart_tx.v and rtl/uart_rx.v, copied unmodified, wired transmitter to receiver by a self-authored declarative top that states the clock half-period, the reset length, the parameters each instance receives and two bytes. No board, oscillator or peer device is modelled; no value is a property of a real part. Authored for the eCAD multi-domain validation pipeline (issue #27).",
  "artifact_type": "hdl_source",
  "artifact_version": "1.0",
  "units": "Verilog with `timescale 1ns / 1ps; CLK_FREQ read as Hz and BAUD_RATE as Bd, as the RTL's header comments state; SI in the engineering model",
  "coordinate_system": "none (HDL has no geometry)",
  "created_at": "<YYYY-MM-DD: the day tb_uart_loopback.v is written>",
  "collected_at": "<the same day>",
  "origin": {"kind": "self_authored", "author": "EmbeddedOS (EoS) Research Foundation"},
  "license": {
    "spdx": "MIT",
    "attribution": "Copyright (c) 2024-2026 EmbeddedOS (EoS) Research Foundation (LICENSE); source/uart_tx.v and source/uart_rx.v keep their own header, Copyright (c) 2026 EmbeddedOS Foundation",
    "license_verified": true,
    "license_text": {"path": "LICENSE", "sha256": "2779b5d4987171210e3c18f461e4ee832426c3c52ca3e53a7dce23af057c4c0a"},
    "redistribution_permitted": true,
    "training_use_permitted": true,
    "basis": "source/tb_uart_loopback.v is hand-written in this repository; source/uart_tx.v and source/uart_rx.v are byte-identical copies of rtl/uart_tx.v and rtl/uart_rx.v, first-party files committed in f15a4aa that state SPDX-License-Identifier: MIT; all three are under the repository's MIT LICENSE; no third-party code, library, IP or part data"
  }
}
```

- `hdl_source` is already in the `artifact_type` enum
  (`source-provenance.schema.json:50`).
- The `LICENSE` digest is **Verified**.
- The dates are written on the day of authoring. A date nobody observed is not
  supplied.
- Whether "EmbeddedOS Foundation" and "EmbeddedOS (EoS) Research Foundation"
  are one entity is **Unknown** (Q-D8). Both are quoted; neither is assumed.

### 1.5 `design/annotations.json` (format 1.2.0)

```json
{
  "$schema": "https://embeddedos.org/schemas/engineering-model/v1/design-annotations.schema.json",
  "annotations_version": "1.2.0",
  "design_id": "uart_loopback_001",
  "materials": {}, "parts": {}, "joints": [], "attachments": [],
  "components_without_cad": [{
    "component_id": "target_device",
    "name": "the FPGA or ASIC this RTL would be implemented on (none is selected)",
    "kind": "other",
    "domains": {"digital": {"min_clock_period": {
      "value": null, "unit": "s", "status": "UNKNOWN",
      "source": {"kind": "design_annotation", "ref": "datasets/cad/uart_loopback_001/design/annotations.json"},
      "note": "no target device is selected and the design has not been synthesised, so the shortest clock period it would meet is unknown"}}}
  }],
  "relationships": [{"relation": "constrained_by", "from": "tb_uart_loopback", "to": "target_device"}]
}
```

### 1.6 Every input value, with its status and source

- "TB" is `{"kind": "design_annotation", "ref": "datasets/cad/uart_loopback_001/source/tb_uart_loopback.v", "sha256": "2962c844…7fed"}`.
- "RX" is the same form for `source/uart_rx.v`, with sha256 `c1bebcc6…ab81`.
- A note reads "`<NAME> = <literal>` as `<file>:<line>` states it; not a
  rating or measurement of any part". The wording is generic, as
  `MEMORY.md:79` decided: the adapter writes it for every accepted file. The
  testbench's own comment says these values are design choices.

| Model path (`components/<id>/domains/digital/…`) | Value | Unit | Status | Source |
|---|---|---|---|---|
| `tb_uart_loopback/clock_half_period` | 1e-08 (= 10 / 1e9) | s | SPECIFIED | TB:26, "in its 1 ns time unit" |
| `tb_uart_loopback/reset_cycles` | 4 | cycles | SPECIFIED | TB:29 |
| `tb_uart_loopback/tx_bytes` | [53, 202] | 1 | SPECIFIED | TB:30-31 (`8'h35`, `8'hCA`) |
| `tb_uart_loopback/byte_count` | 2 | 1 | DERIVED, `derived_from` `…/tx_bytes` | `computation`: "ecad_model.domains.digital 1.0.0: the number of TX_BYTE_i localparams" |
| `u_tx/clk_freq`, `u_tx/baud_rate` | 50 000 000, 115 200 | Hz, Bd | SPECIFIED | TB:27-28, passed by the override at TB:43 |
| `u_rx/clk_freq`, `u_rx/baud_rate` | 50 000 000, 115 200 | Hz, Bd | SPECIFIED | TB:27-28, override at TB:48 |
| `u_rx/oversample` | 16 | 1 | SPECIFIED | RX:23 (`localparam OVERSAMPLE = 16`) |
| `target_device/min_clock_period` | null | s | **UNKNOWN** | annotations |
| RTL parameter defaults (50 MHz, 115 200) | — | — | not quantities | overridden, so the simulation never reads them |
| RTL localparam expressions (`BAUD_DIV`, `SAMPLE_POINT`, state codes) | — | — | not quantities | parsed, not evaluated: the closed forms use the class contract (D7) |
| Method constants (§4.1) | — | — | not quantities | `domains/digital.py` `VERSION`, written into the hash-bound simulation file |
| Illustrative limits (§6) | — | — | `illustrative: true` | `requirements.json` |

- **Unknowns:** the index has one entry, `target_device/…/min_clock_period`,
  with `needed_by: ["digital"]` (`builder.py:393-396` takes the domain from
  the path).
- **Statuses:** nothing is MEASURED, SIMULATED, ESTIMATED or AI_ASSUMPTION.
- **Scratch prototype:** `final/proto_top.py` extracts exactly these values
  from the committed files (**Verified**).

---

## 2. Engineering model (format 1.2.0)

### 2.1 How each spec §8 concept is represented

| Spec §8 | Where | State |
|---|---|---|
| DigitalSystem | The model of a sample whose primary domain is `digital`. <br>• `design.name` is the top module's name; `revision` "1.0". <br>• `design.sources` lists the three files by repository path, `verilog` and sha256, in provenance order; there is no `gravity`. | IMPLEMENTED |
| Module | One component per module instance, plus the top. Each has an `hdl` member with its module, source file and ports. An instance also has its hierarchical path, parameter → facet map, port → signal map and the module text verbatim (D1). Kind `other` (D9). | IMPLEMENTED (one level of hierarchy) |
| Signal | The top's `hdl.signals` (reg or wire, width) and each instance port's `signal`. A net is "the signal a port names", never stored twice (as electrical nets, `MEMORY.md:75`). A leaf's internal registers are not extracted. | PARTIAL |
| Clock | `clock_half_period` on the top. The signal driving both `clk` ports is the clock by rule C5. V1 checks it against each instance's `clk_freq`; the metric `clock_period_s` measures it. | IMPLEMENTED |
| Reset | `reset_cycles` on the top. The signal on both `rst_n` ports is the reset (C5). Active-low and synchronous is the class's interface contract (`uart_tx.v:10`), not extracted. It is measured by `tx_idle_after_reset` and `outputs_unknown_after_reset`. | PARTIAL |
| Interface | `hdl.ports` (direction, width, signal) and `hdl.parameters`. | IMPLEMENTED |
| Protocol | UART 8N1, LSB first, a 16× oversampling receiver: the class C1–C7, named in the `AVAILABLE` reason; `FRAME_BITS = 10` is a method constant. | PARTIAL (not a stored field) |
| StateMachine | Not extracted. The FSMs are exercised only by simulation. | PLANNED |
| Constraint | `target_device/min_clock_period` (UNKNOWN). SDC/XDC/PCF inputs are PLANNED. | PARTIAL |
| Behaviour | `hdl.text`: each leaf module's source verbatim, sha256-bound. | IMPLEMENTED |

**Relationships:**
- `contains`, from the design to the top, and from the top to `u_tx` and to
  `u_rx`, citing TB;
- the annotation's `constrained_by` (`tb_uart_loopback` → `target_device`),
  citing the annotations.

### 2.2 Example components, as `build` writes them (keys sorted; text abridged)

```json
{"component_id": "tb_uart_loopback", "name": "tb_uart_loopback (declarative top)", "kind": "other",
 "cad_ref": null, "material": null, "geometry": null, "physical": null, "placement": null,
 "hdl": {"module": "tb_uart_loopback", "source": "datasets/cad/uart_loopback_001/source/tb_uart_loopback.v", "ports": {},
         "signals": {"clk": {"kind": "reg", "width": 1}, "line": {"kind": "wire", "width": 1},
                     "rst_n": {"kind": "reg", "width": 1}, "rx_data": {"kind": "wire", "width": 8},
                     "rx_error": {"kind": "wire", "width": 1}, "rx_valid": {"kind": "wire", "width": 1},
                     "tx_data": {"kind": "reg", "width": 8}, "tx_ready": {"kind": "wire", "width": 1},
                     "tx_valid": {"kind": "reg", "width": 1}}},
 "domains": {"digital": {
   "clock_half_period": {"value": 1e-08, "unit": "s", "status": "SPECIFIED", "source": TB,
     "note": "CLK_HALF_PERIOD_NS = 10 as source/tb_uart_loopback.v:26 states it, in its 1 ns time unit; not a rating or measurement of any part"},
   "reset_cycles": {"value": 4, "unit": "cycles", "status": "SPECIFIED", "source": TB, "note": "…:29 …"},
   "tx_bytes": {"value": [53, 202], "unit": "1", "status": "SPECIFIED", "source": TB, "note": "…:30-31 …"},
   "byte_count": {"value": 2, "unit": "1", "status": "DERIVED",
     "source": {"kind": "computation", "ref": "ecad_model.domains.digital 1.0.0: the number of TX_BYTE_i localparams"},
     "derived_from": ["components/tb_uart_loopback/domains/digital/tx_bytes"]}}}}

{"component_id": "u_rx", "name": "u_rx (uart_rx, source/uart_rx.v)", "kind": "other",
 "cad_ref": null, "material": null, "geometry": null, "physical": null, "placement": null,
 "hdl": {"module": "uart_rx", "instance": "tb_uart_loopback.u_rx",
         "source": "datasets/cad/uart_loopback_001/source/uart_rx.v",
         "parameters": {"BAUD_RATE": "baud_rate", "CLK_FREQ": "clk_freq"},
         "ports": {"clk": {"direction": "input", "width": 1, "signal": "clk"},
                   "rst_n": {"direction": "input", "width": 1, "signal": "rst_n"},
                   "rx": {"direction": "input", "width": 1, "signal": "line"},
                   "rx_data": {"direction": "output", "width": 8, "signal": "rx_data"},
                   "rx_error": {"direction": "output", "width": 1, "signal": "rx_error"},
                   "rx_valid": {"direction": "output", "width": 1, "signal": "rx_valid"}},
         "text": "// uart_rx.v\n// UART Receiver — 8N1 format, configurable baud rate\n…endmodule\n"},
 "domains": {"digital": {
   "baud_rate": {"value": 115200, "unit": "Bd", "status": "SPECIFIED", "source": TB,
     "note": "u_rx BAUD_RATE = BAUD_RATE = 115_200 as source/tb_uart_loopback.v:28 and :48 state it; not a rating or measurement of any part"},
   "clk_freq": {"value": 50000000, "unit": "Hz", "status": "SPECIFIED", "source": TB, "note": "…:27 and :48 …"},
   "oversample": {"value": 16, "unit": "1", "status": "SPECIFIED", "source": RX,
     "note": "OVERSAMPLE = 16 as source/uart_rx.v:23 states it; not a rating or measurement of any part"}}}}
```

- **Component order:** the top, then instances in top order, then
  `components_without_cad`.
- **Writers never depend on dict order:** `_json_bytes` sorts keys, so the
  harness writer sorts signals, parameters and connections by name.
- **Size:** the model carries about 7.5 KB of RTL text. This is the price of
  D1.
- **Walks skip `hdl`:** `index_unknowns`, `resolve`, `input_leaves` and
  lineage are unchanged, because `hdl` holds no quantity and the walks stop at
  quantities (`builder.py:419-427`, `results.py:91-104`, **Observed**).

### 2.3 Schema changes (all compatible, all in v1)

**`schemas/engineering-model/v1/engineering-model.schema.json`:**

1. `model_version` (line 23) becomes `["1.0.0", "1.1.0", "1.2.0"]`; the
   description adds "1.2.0: the hdl member".
2. `component` gains an optional `"hdl": {"$ref": "#/definitions/hdl"}`. It is
   not added to `required` (line 105), and no kind is added.
3. New definitions:

   ```json
   "hdlName": {"type": "string", "pattern": "^(?!ecad_)[A-Za-z_][A-Za-z0-9_]{0,63}$"},
   "hdl": {
     "description": "Where a component sits in the elaborated HDL design (format 1.2.0): its module, the sample file that defines it and its ports. The top lists the signals it declares; an instance names its hierarchical path, the facet that holds each parameter value the top passes, the top signal each port connects to, and its module's source text verbatim, bound to design.sources by hash. Behaviour is carried only as that text.",
     "type": "object", "additionalProperties": false, "required": ["module", "source", "ports"],
     "properties": {
       "module": {"$ref": "#/definitions/hdlName"},
       "source": {"$ref": "common.schema.json#/definitions/relativePath"},
       "instance": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]{0,63}(\\.[A-Za-z_][A-Za-z0-9_]{0,63})+$"},
       "parameters": {"type": "object", "maxProperties": 64, "propertyNames": {"$ref": "#/definitions/hdlName"},
                      "additionalProperties": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}},
       "ports": {"type": "object", "maxProperties": 256, "propertyNames": {"$ref": "#/definitions/hdlName"},
                 "additionalProperties": {"type": "object", "additionalProperties": false, "required": ["direction", "width"],
                   "properties": {"direction": {"enum": ["input", "output"]},
                                  "width": {"type": "integer", "minimum": 1, "maximum": 64},
                                  "signal": {"$ref": "#/definitions/hdlName"}}}},
       "signals": {"type": "object", "maxProperties": 256, "propertyNames": {"$ref": "#/definitions/hdlName"},
                   "additionalProperties": {"type": "object", "additionalProperties": false, "required": ["kind", "width"],
                     "properties": {"kind": {"enum": ["reg", "wire"]}, "width": {"type": "integer", "minimum": 1, "maximum": 64}}}},
       "text": {"type": "string", "minLength": 1, "maxLength": 1048576}
     },
     "allOf": [{"if": {"required": ["instance"]},
                "then": {"required": ["parameters", "text"], "not": {"required": ["signals"]},
                         "properties": {"ports": {"additionalProperties": {"required": ["signal"]}}}},
                "else": {"required": ["signals"], "not": {"anyOf": [{"required": ["parameters"]}, {"required": ["text"]}]},
                         "properties": {"ports": {"maxProperties": 0}}}}]
   }
   ```
4. A second top-level `allOf` rule, beside lines 39–55:
   `{"if": {"properties": {"components": {"contains": {"required": ["hdl"]}}}}, "then": {"properties": {"model_version": {"const": "1.2.0"}}}}`.
   The existing 1.1.0 rule is unchanged, so a component cannot carry both
   `circuit` and `hdl` (Q-D6).

**`schemas/engineering-model/v1/design-annotations.schema.json`:**
- `annotations_version` (lines 23–28) gains `"1.2.0"`.
- `components_without_cad[].domains` (lines 200–216) gains
  `"digital": {"$ref": "#/definitions/facet"}` (F1 is why this is needed).
- A new `allOf` rule: an item of `components_without_cad` whose `domains` has
  `digital` requires `annotations_version` const `"1.2.0"`.

**`schemas/cad-dataset/v1/source-provenance.schema.json`:**
- `provenance_version` (line 25) becomes `{"enum": ["1.0.0", "1.1.0"]}`.
- The closed artefact item (lines 36–44) gains an optional
  `"copied_from": {"type": "object", "additionalProperties": false, "required": ["path", "sha256"], "properties": {"path": relativePath, "sha256": sha256}}`,
  described as "a byte-identical copy of this repository file; check and V0
  re-hash both (REUSE-1)".
- A new `allOf` rule: `artifacts` containing a `copied_from` requires
  `provenance_version` const `"1.1.0"`.

**New `schemas/engineering-model/v1/digital-vocabulary.schema.json`**, the
shape of `electrical-vocabulary.schema.json`:
- `scenarios`: items `{"name": {"enum": ["loopback"]}}`, closed;
- `derivations`: enum `clock_period`, `idle_high_after_reset`,
  `bit_period_cycles`, `bit_rate`, `frame_cycles`, `bytes_sent`,
  `lossless_loopback`, `no_framing_errors`.

**Unchanged:**
- `common.schema.json`: units are free strings, a vector value is a
  `numberOrMatrix`, and `domains.digital` already exists
  (`engineering-model.schema.json:215`);
- engineering-requirements, validation-results (its fidelity enum is kept),
  dataset-item, and all of `hardware-validation/v1`. The cases adapter enum
  already has `iverilog` (`validation-cases.schema.json:48`), so Q9 is not
  triggered for Icarus.

### 2.4 Versions

| Constant | Value | Covers |
|---|---|---|
| `ecad_model.HDL_MODEL_VERSION` | "1.2.0" | what the digital adapter writes; `MODEL_VERSION` (1.0.0) and `CIRCUIT_MODEL_VERSION` (1.1.0, `__init__.py:18`) are unchanged |
| `ecad_model.verilog.VERSION` | "1.0.0" | the grammar and the harness reader |
| `domains.digital.MODEL_BUILDER_VERSION` | "1.0.0" | the model; producer `("ecad_model.domains.digital", "1.0.0 (ecad_model.verilog 1.0.0)")` (`MEMORY.md:70`) |
| `domains.digital.VERSION` | "1.0.0" | the simulation file, its harness, the method constants and the case target |
| `dataset.VALIDATOR_VERSION` | 1.0.0 → **1.1.0** | V0 gains the REUSE-1 check (`dataset.py:70`); no test pins it (`test_validation_contract.py` uses its own "1.0.0" in synthetic receipts, **Observed**) |
| `requirements.VERSION`, `results.VERSION` | unchanged | their output is unchanged |

### 2.5 Why the RTL text goes into the model (amends plan §8.2, ARCH-1, for HDL)

`write_models` receives only the model (`base.py:113`), and re-reading the
sources there is a hidden input (`MEMORY.md:75`). For Icarus to compile a file
written from the model, the model must carry what the adapter does not model:
the leaves' behaviour.

It carries the text verbatim, not reprinted and not as a syntax tree:
- the bytes Icarus compiles are the committed RTL;
- V2 binds them by hash (§3.5);
- the domain-neutral reproduction check compares the file exactly.

The top is fully modelled (declarations, instances, overrides, values), so the
harness writes it from the model, as the electrical deck writes each netlist
element from the model (`electrical.py:560-567`).

---

## 3. Extraction

### 3.1 `tools/ecad_model/verilog.py`: the grammar (format layer, no roles)

Pure Python with anchored regular expressions. Statement parsing is recursive
descent with an explicit depth counter (`MAX_DEPTH = 32`) that raises
`HdlRefused`, never `RecursionError`. It runs in-process, because it is not
native code (`MEMORY.md:58`), and it avoids `re` features newer than Python
3.10 (`ci.yml:21`).

**Public API.** Each function has a doctest.

```python
VERSION = "1.0.0"
MAX_SOURCE_BYTES = 1 << 20; MAX_LINE_CHARS = 1024; MAX_NAME_CHARS = 64; MAX_WIDTH = 64; MAX_DEPTH = 32; MAX_MODULES = 16
RTL_KEYWORDS = frozenset("module endmodule parameter localparam input output wire reg always posedge begin end if else case endcase default".split())
TOP_KEYWORDS = frozenset("module endmodule localparam reg wire".split())
class HdlRefused(ExtractionError)      # kind "rejected"; message "<path>:<line>: <reason>"
@dataclass(frozen=True) class Port: name: str; direction: str; width: int; line: int
@dataclass(frozen=True) class Leaf: name: str; path: str; text: str; parameters: Dict[str, int]; ports: Tuple[Port, ...]; literal_localparams: Dict[str, Tuple[int, int]]
@dataclass(frozen=True) class Instance: module: str; name: str; overrides: Dict[str, Union[int, str]]; connections: Dict[str, str]; line: int
@dataclass(frozen=True) class Top: name: str; path: str; localparams: Dict[str, Tuple[int, Optional[int], int]]; signals: Dict[str, Tuple[str, int, int]]; instances: Tuple[Instance, ...]
@dataclass(frozen=True) class Design: top: Top; leaves: Dict[str, Leaf]
def parse_source(data: bytes, path: str) -> Union[Leaf, Top]
def elaborate(parsed: Sequence[Union[Leaf, Top]]) -> Design
def read_harness(text: str, path: str) -> HarnessView    # §3.5: the harness's structure and values, by form
```

**File-level refusals** (the guards of `spice.py`):
- more than `MAX_SOURCE_BYTES`, or empty;
- a Git LFS pointer;
- invalid UTF-8;
- CR, NUL, or any control character other than TAB and LF;
- a line longer than 1024 characters;
- no final LF;
- an unterminated `/* */`.

Non-ASCII is accepted only inside `//` and `/* */` comments, which the copied
RTL needs.

**Lexical refusals**, each named with its reason. The class comes from
honesty's table; the **Verified** behaviours are the Icarus probes of §0.2.

| Refused | Reason given |
|---|---|
| any backtick other than one line exactly `` `timescale 1ns / 1ps `` as the first non-comment line: `` `include `` | "reads another file" (Icarus read an outside file and printed its identifiers) |
| `` `define ``, `` `undef ``, a macro use | "text substitution" |
| `` `ifdef ``/`` `ifndef ``/`` `elsif ``/`` `else ``/`` `endif `` | "conditional compilation" |
| `` `resetall ``, `` `default_nettype ``, `` `celldefine ``, `` `line ``, `` `pragma ``, a second or other `` `timescale `` | "compiler directive" |
| every `$` outside a comment, with its class | files (`$fopen`, `$readmem*`, `$dump*`, … wrote or read files), a shell (`$system`), plusargs, randomness, printing and run control (only the harness prints and finishes) |
| `"` | "a string" (so `import "DPI-C"` is refused at its string) |
| `(*`, `\`, `'b1` (unsized based), digits `x z ?`, real literals, `$` in identifiers | "outside the lexical subset" |
| `=== !== ** <<< >>> -> :: ++ -- +=` and `{ }` | "operator outside the subset" (PLANNED) |
| an identifier of more than 64 characters, or starting `ecad_` | "reserved for the harness" |
| the text `ECAD_METRIC` anywhere, comments included | "reserved for the harness's metric markers" (a comment with a `$display("ECAD_METRIC …` string would otherwise count as a second declaration and withhold that metric) |

**Keywords.** Every Verilog-2005 and SystemVerilog-2012 reserved word outside
the file kind's allow-list is refused, naming its class:

| Class | Words |
|---|---|
| "calls C code" | `import export chandle bind` |
| "outside the synchronous RTL subset (PLANNED)" | `assign initial negedge function task generate genvar for while repeat forever integer real time realtime event signed inout casex casez wait fork join disable automatic or` |
| "changes another scope or the simulator" | `defparam force release deassign specify specparam primitive table config library` (Icarus applied `defparam u.P = 7`, **Verified**) |
| "SystemVerilog (PLANNED)" | `logic bit int byte always_ff always_comb interface package class program typedef enum struct assert` … |
| "gate-level primitive (PLANNED)" | `and nand nor or xor not buf bufif0 pullup supply0 supply1 tri wand wor` … |

**Grammar** (EBNF; one module per file; the only accepted forms):

```
source    := TIMESCALE module EOF
module    := rtl | top                          -- decided by the token after the name: "#" or "(" is RTL, ";" is the top
rtl       := "module" NAME [ "#" "(" param { "," param } ")" ] "(" port { "," port } ")" ";" { rtl_item } "endmodule"
param     := "parameter" NAME "=" DECIMAL
port      := "input" [ "wire" ] [ range ] NAME | "output" "reg" [ range ] NAME
range     := "[" DECIMAL ":" "0" "]"                                    -- width 1 .. 64
rtl_item  := "localparam" NAME "=" cexpr ";"
           | "reg" [ range ] NAME { "," NAME } ";"
           | "always" "@" "(" "posedge" NAME ")" stmt
stmt      := "begin" { stmt } "end"
           | "if" "(" expr ")" stmt [ "else" stmt ]
           | "case" "(" expr ")" { expr { "," expr } ":" stmt | "default" [ ":" ] stmt } "endcase"
           | NAME [ "[" expr "]" ] "<=" expr ";"                           -- nonblocking only
expr      := ternary over || && | ^ & == != < <= > >= << >> + - * / %, unary ! ~ -, "(" expr ")",
             NAME, NAME "[" expr "]", DECIMAL, SIZED
cexpr     := expr restricted to DECIMAL, SIZED, the module's parameters, earlier localparams, + - * / and ( )
top       := "module" NAME ";" { top_item } "endmodule"
top_item  := "localparam" [ "[7:0]" ] NAME "=" ( DECIMAL | SIZED ) ";"
           | ( "reg" | "wire" ) [ range ] NAME ";"                          -- no initial value
           | NAME "#" "(" override { "," override } ")" NAME "(" conn { "," conn } ")" ";"
override  := "." NAME "(" ( NAME | DECIMAL ) ")"
conn      := "." NAME "(" NAME ")"                                        -- no positional, no .*, no .p()
DECIMAL   := [0-9][0-9_]*        SIZED := W "'" ( "b" [01_]+ | "d" [0-9_]+ | "h" [0-9a-fA-F_]+ ), value < 2^W, W <= 64
```

**Semantic refusals, in a leaf:**
- a name declared twice;
- an identifier not declared before use (no implicit nets);
- `=` (blocking);
- an assignment to anything but a reg;
- a reg assigned in two `always` blocks;
- an `always` clocked on anything but an input port;
- two clock ports in one module;
- an `output reg` that no statement assigns;
- a parameter declared both in the header and the body;
- a sized literal that does not fit (`2'd4`);
- a hierarchical reference (a `.` after a name);
- an instance.

**Semantic refusals, in the top:**
- a name declared twice;
- a `[7:0]` localparam whose literal is not 8 bits;
- ports.

**Elaboration refusals** (`elaborate`):
- more than `MAX_MODULES` sources;
- a module defined twice;
- zero or more than one top;
- an instance of a module no source defines;
- a leaf instantiated twice, or never;
- an unknown port, a port connected twice, an unconnected port;
- a connection that is not a declared top signal;
- a width mismatch;
- an output onto a reg;
- a wire driven by two outputs;
- an input on a wire no output drives;
- an override naming an undeclared parameter or a localparam;
- an override that is neither a top localparam nor a decimal literal.

**Evidence:**
- minimal's prototype of a superset grammar accepts `uart_tx.v` and
  `uart_rx.v` and refuses its 61 probes, each with its reason (**Verified**,
  "unexpected: 0 of 61");
- `final/proto_top.py` accepts the committed top and refuses 12 probes:
  `include`, `$system`, `initial`, a reg initialiser, an `ecad_` name, `rx`
  fed from `tx_valid`, an inert localparam, `8'h1CA`, `` `timescale 1ns/1ns ``,
  CRLF, non-ASCII in code, a missing `TX_BYTE_0` (**Verified**);
- the full grammar of this section is **NOT RUN**: it is written at
  implementation time against V1–V12.

### 3.2 `DigitalAdapter.extract` (`tools/ecad_model/domains/digital.py`)

1. **Sources.** Every declared source must be of format `verilog`, and there
   must be 2 to `MAX_MODULES` of them; otherwise `ValueError`, which V1
   reports as `DATASET_INPUT_INVALID` (`dataset.py:998-1003`).
2. **Each source.** `regular_file(path, verilog.MAX_SOURCE_BYTES)`, whose
   `UnsupportedFormat` is re-raised as `ExtractionError("rejected", …)`, as
   `electrical.py:711-714` does. Then `verilog.parse_source`.
3. **Elaborate:** `verilog.elaborate`.
4. **Annotations.** `materials`, `parts`, `joints` or `attachments` are
   refused, as at `electrical.py:612-614`. A `components_without_cad` id may
   not collide with a component; relationship endpoints must exist. Each
   breach is a `ValueError`.
5. **Class rules** C1–C7 (§3.3). A breach raises
   `ExtractionError("rejected", "<path>: not the UART 8N1 loopback the digital domain validates: rule Cn: …")`.
   V1 then gives `FAIL SOURCE_REJECTED` (`dataset.py:987`), V2–V4 give
   `DERIVATION_NOT_AVAILABLE`, and no text reaches Icarus.
6. **Build the model** (§2), including `unknowns = index_unknowns(model)`.
7. **Return**
   `Extraction(model, producer=("ecad_model.domains.digital", "1.0.0 (ecad_model.verilog 1.0.0)"))`,
   with `files=[]` and `tools=[]`.

### 3.3 The class: `loopback_roles(model) -> Roles`

`Roles` holds the top and, by name, the transmitter, the receiver and the
clock, reset, data, valid, ready, line, rx_data, rx_valid and rx_error
signals. The harness writer reads it.

| Rule | Requirement |
|---|---|
| C1 | One top with no ports, and exactly two instances, each of a different leaf. Every leaf is instantiated once, and no leaf instantiates anything. |
| C2 | **The transmitter's module declares exactly** inputs `clk:1`, `rst_n:1`, `tx_data:8`, `tx_valid:1` and outputs `tx_ready:1`, `tx:1`, with parameters exactly `CLK_FREQ` and `BAUD_RATE`. This is the interface of `uart_tx.v:21-31`. |
| C3 | **The receiver's module declares exactly** inputs `clk:1`, `rst_n:1`, `rx:1` and outputs `rx_data:8`, `rx_valid:1`, `rx_error:1`, with parameters exactly `CLK_FREQ` and `BAUD_RATE` and a localparam `OVERSAMPLE` that is a decimal literal. This is the interface of `uart_rx.v:10-23`. |
| C4 | Each instance overrides both parameters by name, with a top localparam or a decimal literal. |
| C5 | **Wiring:** <br>• one reg drives both `clk` ports (the clock), and one reg both `rst_n` ports (the reset); <br>• regs drive `tx_data` and `tx_valid`, on the transmitter only; <br>• the transmitter's `tx` and the receiver's `rx` share one wire, the line, and no other port connects to it; <br>• `tx_ready`, `rx_data`, `rx_valid` and `rx_error` are wires, each driven by its output alone; <br>• every declared signal is connected. |
| C6 | **Top localparams:** exactly `CLK_HALF_PERIOD_NS` (decimal ≥ 1), `RESET_CYCLES` (decimal ≥ 1) and `TX_BYTE_0` … `TX_BYTE_{N-1}` (consecutive, 1 ≤ N ≤ `MAX_BYTES` = 16, each `[7:0]` and sized), plus those an override names. No inert data. |
| C7 | **Resource guard:** END ≤ `MAX_CYCLES` = 2 000 000, where END = `RESET_CYCLES + (N + 2) · RUN_BITS_PER_FRAME · max(T_tx, T_rx, MIN_BIT_CYCLES)` and T_x = ⌊clk_freq_x / baud_rate_x⌋. |

**Guard arithmetic:**
- committed sample: END = 4 + 4·12·434 = **20 836**;
- 1200 Bd: END = 1 999 972, accepted; 1199 Bd: END = 2 001 652, refused
  (arithmetic);
- runtime: 2 000 000 cycles ran in 3.17 s under vvp here (**Verified**).

With N ≥ 1 the guard also gives T_tx ≤ 55 555 < 2¹⁶ (**Inferred**, arithmetic),
so the RTL's 16-bit `baud_cnt` never wraps for an accepted sample.

**The `AVAILABLE` reason** (`description`): "the UART 8N1 loopback only (a
transmitter and a receiver with the port and parameter interfaces of
rtl/uart_tx.v and rtl/uart_rx.v, wired transmitter to receiver by a
declarative top): reset, frame-timing and byte-recovery metrics from one
Icarus Verilog run of a harness written from the model, compared with
closed-form references".

### 3.4 V1: `sanity_problems(model)` → `DOMAIN_SANITY_FAILED`

1. **Facet vocabulary and units:**

   | Facet | Unit |
   |---|---|
   | `clock_half_period`, `min_clock_period` | `s` |
   | `reset_cycles` | `cycles` |
   | `tx_bytes`, `byte_count`, `oversample` | `1` |
   | `clk_freq` | `Hz` |
   | `baud_rate` | `Bd` |

   An unknown facet name, or a unit other than the vocabulary's, is a problem.
2. **Values:**
   - `clock_half_period` > 0;
   - `reset_cycles` an integer ≥ 1;
   - 1 to 16 bytes, each an integer from 0 to 255;
   - `byte_count` = `len(tx_bytes)`;
   - each `clk_freq` and `baud_rate` a positive integer, with
     `baud_rate ≤ clk_freq`;
   - `oversample` an even integer ≥ 2;
   - a known `min_clock_period` > 0.
3. **The clock the harness drives is the frequency each instance is told:**
   `|2·clock_half_period·clk_freq − 1| ≤ 1e-9`. The committed value is
   exactly 1.0 (**Verified**). The 40 MHz copy (§6.4) reads "u_tx CLK_FREQ
   40000000 Hz is not the frequency of its clock (half period 1e-08 s,
   50000000 Hz)".
4. **The receiver ticks:** ⌊clk_freq/(baud_rate·oversample)⌋ ≥ 1 ("the
   receiver's divider is 0: it never samples"). minimal **Verified** that such
   a divider never ticks.

The committed model gives `[]`. A V1 finding does not stop the cases; the
resource guard is C7.

### 3.5 V2: `invariant_problems(model, {}, {sim_path: bytes})` → `DOMAIN_MODEL_INCONSISTENT`

1. **The RTL is the model's, byte for byte.** The file begins with the two
   header lines and, for each leaf in model order, the separator
   `// ---- <hdl.source> sha256 <sha256(hdl.text)> ----` followed by
   `hdl.text`. The expected prefix is built from the model, so no splitting
   of untrusted text is needed.
2. **The text is the source's.** Each leaf's `hdl.text` hashes to the
   `design.sources` entry that `hdl.source` names.
3. **An independent re-read.** `verilog.read_harness` parses the harness by
   form:
   - its declarations, instances, overrides and connections, with the top
     grammar extended by literal initialisers and literal-only overrides
     under the module name `ecad_harness`;
   - the half period (`always #N clk = ~clk;`), the reset cycles
     (`repeat (N) @(posedge clk);`), the stimulus bytes, the expected bytes
     (`ecad_expected[i] = 8'dV;`) and END (`if (ecad_cycle == N) begin`);
   - its system identifiers, which must lie in `{$display, $finish, $realtime}`.

   Each is compared with the model: the half period with
   `round(clock_half_period · 1e9)`, the bytes with `tx_bytes`, and END with
   C7's formula. This catches a writer that hard-codes a value.
4. **Writer equality.** The harness lines equal `write_harness(model)`
   character for character.
5. **Declared metrics.** `hdl.declared_metrics` (the tool adapter's own
   function) finds exactly the vocabulary's nine names, once each, in
   `METRICS` order.
6. **Citations.** Every SPECIFIED digital facet cites its stating file by path
   and sha256: the top's facets and the instances' `clk_freq`/`baud_rate`
   cite the top, `oversample` cites `uart_rx.v`.
7. **Sources.** Each instance's `hdl.source` is one of `design.sources`.

The domain-neutral `v2.dataset-reproduction` also compares the file exactly
(comparator `exact`, `dataset.py:696-709`) and the source hashes
(`dataset.py:852-859`).

---

## 4. Domain model and case target

### 4.1 `write_models(model, sample_id)`

```python
[DerivedFile(path=f"derived/digital/{sample_id}.v", data=write_simulation(model), role="domain_model",
             media_type="text/x-verilog", producer="ecad_model.domains.digital", version=VERSION,
             derived_from=("derived/engineering_model.json",), comparator="exact")]
```

`.v` is already `text/x-verilog` (`base.py:31`).

**Method constants**, versioned by `VERSION` and written into the hash-bound
file:

| Constant | Value | Purpose |
|---|---|---|
| `FRAME_BITS` | 10 | 8N1: start, 8 data, stop |
| `RUN_BITS_PER_FRAME` | 12 | frame plus turnaround, in END |
| `MIN_BIT_CYCLES` | 16 | END floor |
| `MAX_CYCLES` | 2 000 000 | resource guard (C7) |
| `MAX_BYTES` | 16 | stimulus length (C6) |
| `CASE_TIMEOUT_S` | 60 | per Icarus step |
| `HARNESS_TASKS` | `{"$display", "$finish", "$realtime"}` | the harness's system identifiers |
| harness initial values | `clk = 1'b0`, `rst_n = 1'b0`, `tx_data = 8'd0`, `tx_valid = 1'b0` | the driven regs |
| sampling | falling clock edge | race-free observation |

**File layout:**
- line 1: `// <id>: the RTL of <design.name> verbatim, then the harness the digital domain writes from the model`;
- line 2: `// written by ecad_model.domains.digital 1.0.0 from derived/engineering_model.json; regenerate with build, never edit`;
- for each leaf in model order: `// ---- <hdl.source> sha256 <hash> ----`, then `hdl.text` verbatim;
- `// ---- harness ----`, then the harness of §4.2.

The committed file is 12 852 bytes and 353 lines, sha256
`191bd8f16c0167764878d099ac5a1fc8c4a2e509e06e433997452cb5944d3e84`
(**Verified**, `final/v/committed.v`). Its separators are at lines 3, 115 and
242.

### 4.2 The harness, exactly (lines 242–353 of the committed file)

```verilog
// ---- harness ----
`timescale 1ns / 1ps

module ecad_harness;

    reg        clk = 1'b0;
    wire       line;
    reg        rst_n = 1'b0;
    wire [7:0] rx_data;
    wire       rx_error;
    wire       rx_valid;
    reg  [7:0] tx_data = 8'd0;
    wire       tx_ready;
    reg        tx_valid = 1'b0;

    uart_tx #(.BAUD_RATE(115200), .CLK_FREQ(50000000)) u_tx (.clk(clk), .rst_n(rst_n), .tx(line), .tx_data(tx_data), .tx_ready(tx_ready), .tx_valid(tx_valid));
    uart_rx #(.BAUD_RATE(115200), .CLK_FREQ(50000000)) u_rx (.clk(clk), .rst_n(rst_n), .rx(line), .rx_data(rx_data), .rx_error(rx_error), .rx_valid(rx_valid));

    // ecad: clock, stimulus and measurements
    always #10 clk = ~clk;

    initial begin
        repeat (4) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        while (!tx_ready) @(posedge clk);
        tx_data <= 8'd53;
        tx_valid <= 1'b1;
        @(posedge clk);
        tx_valid <= 1'b0;
        @(posedge clk);
        while (!tx_ready) @(posedge clk);
        tx_data <= 8'd202;
        tx_valid <= 1'b1;
        @(posedge clk);
        tx_valid <= 1'b0;
    end

    integer    ecad_cycle = 0;
    realtime   ecad_first_rise = -1.0;
    realtime   ecad_second_rise = -1.0;
    always @(posedge clk) begin
        ecad_cycle <= ecad_cycle + 1;
        if (ecad_first_rise < 0.0) ecad_first_rise = $realtime;
        else if (ecad_second_rise < 0.0) ecad_second_rise = $realtime;
    end

    reg        ecad_line_before = 1'b1;
    reg        ecad_ready_before = 1'b1;
    integer    ecad_idle_after_reset = -1;
    integer    ecad_unknown_after_reset = -1;
    integer    ecad_start_fall = -1;
    integer    ecad_start_rise = -1;
    realtime   ecad_start_fall_at = 0.0;
    realtime   ecad_start_rise_at = 0.0;
    integer    ecad_busy_from = -1;
    integer    ecad_busy_to = -1;
    integer    ecad_received = 0;
    integer    ecad_bit_errors = 0;
    integer    ecad_framing_errors = 0;
    integer    ecad_k;
    reg  [7:0] ecad_expected [0:1];
    reg  [7:0] ecad_difference;
    initial begin
        ecad_expected[0] = 8'd53;
        ecad_expected[1] = 8'd202;
    end

    // Every signal is sampled on the falling clock edge, half a cycle after the rising edge the design acts on.
    always @(negedge clk) begin
        if (ecad_idle_after_reset < 0 && rst_n === 1'b1) begin
            ecad_idle_after_reset = (line === 1'b1 && tx_ready === 1'b1) ? 1 : 0;
            ecad_unknown_after_reset = (^tx_ready === 1'bx) + (^line === 1'bx) + (^rx_data === 1'bx)
                                       + (^rx_valid === 1'bx) + (^rx_error === 1'bx);
        end
        if (ecad_start_fall < 0 && ecad_line_before === 1'b1 && line === 1'b0) begin
            ecad_start_fall = ecad_cycle;
            ecad_start_fall_at = $realtime;
        end else if (ecad_start_fall >= 0 && ecad_start_rise < 0 && line === 1'b1) begin
            ecad_start_rise = ecad_cycle;
            ecad_start_rise_at = $realtime;
        end
        if (ecad_busy_from < 0 && ecad_ready_before === 1'b1 && tx_ready === 1'b0) ecad_busy_from = ecad_cycle;
        else if (ecad_busy_from >= 0 && ecad_busy_to < 0 && tx_ready === 1'b1) ecad_busy_to = ecad_cycle;
        if (rx_valid === 1'b1) begin
            if (ecad_received < 2) begin
                ecad_difference = rx_data ^ ecad_expected[ecad_received];
                for (ecad_k = 0; ecad_k < 8; ecad_k = ecad_k + 1)
                    if (ecad_difference[ecad_k] !== 1'b0) ecad_bit_errors = ecad_bit_errors + 1;
            end
            ecad_received = ecad_received + 1;
        end
        if (rx_error === 1'b1) ecad_framing_errors = ecad_framing_errors + 1;
        ecad_line_before = line;
        ecad_ready_before = tx_ready;
        if (ecad_cycle == 20836) begin
            $display("ECAD_METRIC clock_period_s %.17g", (ecad_second_rise - ecad_first_rise) / 1.0e9);
            if (ecad_idle_after_reset >= 0) $display("ECAD_METRIC tx_idle_after_reset %0d", ecad_idle_after_reset);
            if (ecad_start_rise >= 0) begin
                $display("ECAD_METRIC tx_bit_cycles %0d", ecad_start_rise - ecad_start_fall);
                $display("ECAD_METRIC tx_bit_rate_bd %.17g", 1.0e9 / (ecad_start_rise_at - ecad_start_fall_at));
            end
            if (ecad_busy_to >= 0) $display("ECAD_METRIC tx_frame_cycles %0d", ecad_busy_to - ecad_busy_from);
            $display("ECAD_METRIC rx_bytes_received %0d", ecad_received);
            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors);
            $display("ECAD_METRIC rx_framing_errors %0d", ecad_framing_errors);
            if (ecad_unknown_after_reset >= 0) $display("ECAD_METRIC outputs_unknown_after_reset %0d", ecad_unknown_after_reset);
            $finish;
        end
    end

endmodule
```

**What comes from the model** (everything else is the template):
- the signal names, kinds and widths;
- the instances' modules, names, overrides (from the `clk_freq`/`baud_rate`
  facets) and connections;
- `#10` = `round(clock_half_period · 1e9)`;
- `repeat (4)` = `reset_cycles`;
- the bytes, in the stimulus and in `ecad_expected`;
- `N` in `[0:N-1]` and `< N`;
- END.

**Why it is written this way:**
- **Race-free.** The design and the stimulus act on the rising edge with
  nonblocking assignments; everything is observed half a cycle later.
- **No hierarchical reference, and no reliance on X before reset.** It runs on
  a 2-state simulator too: Verilator 5.052 prints the same metric lines
  (**Verified**). minimal's harness needed an arming step for that, D11.
- **Unobserved metrics are not printed.** A metric that was never observed is
  missing, and the comparator says `INCONCLUSIVE` (`cases.py:99-101`).
- **Exact rounding.** `/ 1.0e9` is correctly rounded, so `clock_period_s`
  prints `2e-08`, equal to the closed form 2·h. `%.17g` round-trips; 5e-08
  prints as `4.9999999999999998e-08`, the same double (**Verified**).

**Verified behaviour:**
- Icarus 13: compile exit 0, stderr empty; run exit 0; two runs identical.
- Icarus 11 (`ubuntu:22.04` arm64) prints identical metric lines for all 13
  files and no other line (`ctr2/container.log`). Icarus 13 adds
  `…/uart_loopback_001.v:349: $finish called at 416720000 (1ps)`, with a
  relative path.
- Verilator 5.052 (`--binary --timing -Wno-fatal`) prints identical metric
  lines for the committed file and the 20 MHz copy, plus 12 `WIDTHEXPAND`
  warnings and wall-time report lines.

### 4.3 Case target and scenario

```python
CaseTarget(adapter="iverilog", inputs=(f"derived/digital/{sample_id}.v",), arguments=lambda scenario: [],
           timeout_seconds=CASE_TIMEOUT_S)
```

- `_case` compiles it unchanged (`requirements.py:55-65`): `domain` maps to
  `eda_circuit` (`requirements.py:30`), with `seed` 0.
- **One scenario, `loopback`,** carrying only its name. Every case runs the
  same file, so borrowing a measured value for a limit-blocked requirement is
  correct (`results.py:293-306`). The case engine stores the adapter's whole
  metric dict (`cases.py:482`).

### 4.4 Metric markers

- **Declaration:** the harness declares each name with
  `$display("ECAD_METRIC <name> %0d", …)` or `"%.17g"`.
- **Report:** vvp prints `ECAD_METRIC <name> <value>`.
- **Reading:** `hdl.declared_metrics` and `hdl.parse_metrics` (§7.3).
- **Everything else in stdout is ignored**, including Icarus 13's
  `$finish called at …` and Verilator's report lines.

---

## 5. Metrics and references

### 5.1 The nine metrics (all `SIMPLIFIED`, scenario `loopback`)

| # | Metric | Unit | What the harness measures | Derivation (V3) |
|---|---|---|---|---|
| 1 | `clock_period_s` | s | time between the first two rising clock edges | `clock_period` |
| 2 | `tx_idle_after_reset` | 1 | 1 if the line and `tx_ready` are high at the first falling edge after reset is released, else 0 | `idle_high_after_reset` |
| 3 | `tx_bit_cycles` | cycles | clock cycles of the line's first low run (the start bit, when the first byte is odd) | `bit_period_cycles` |
| 4 | `tx_bit_rate_bd` | Bd | 1e9 / (simulated ns of that run) | `bit_rate` |
| 5 | `tx_frame_cycles` | cycles | cycles `tx_ready` stays low for the first byte | `frame_cycles` |
| 6 | `rx_bytes_received` | 1 | `rx_valid` pulses before END | `bytes_sent` |
| 7 | `rx_bit_errors` | bits | bits differing between each byte sent and the byte received in its place (the first N received) | `lossless_loopback` |
| 8 | `rx_framing_errors` | 1 | `rx_error` pulses before END | `no_framing_errors` |
| 9 | `outputs_unknown_after_reset` | 1 | outputs with any X/Z bit (`tx_ready`, the line, `rx_data`, `rx_valid`, `rx_error`) at the first falling edge after reset is released | none (V4 only) |

**Fidelity: `SIMPLIFIED`.** Relative to the RTL as written, the simulation is
exact at the logic level: counts are integers, and three simulators agree
(**Verified**). Relative to hardware, it idealises:
- a jitter-free clock with no oscillator tolerance;
- zero gate and wire delay;
- no setup or hold;
- no metastability, so the receiver's two-flop synchroniser
  (`uart_rx.v:40-44`) acts logically;
- an ideal line.

Metric 9 depends on 4-state X semantics: Icarus sees an unreset output (1);
2-state Verilator reports 0 for the same RTL (**Verified**,
`final/vl/r_m_tx_not_reset.out`). `EXACT_GEOMETRY` is a geometry notion, and
`REDUCED_ORDER` and `EMPIRICAL` misdescribe an RTL run. `SIMPLIFIED`
understates rather than overstates (Q-D4).

### 5.2 Closed forms (`digital.reference_value`), from the model only

Definitions:
- h = `clock_half_period`;
- D_t = ⌊clk_freq(u_tx) / baud_rate(u_tx)⌋;
- OS = `oversample(u_rx)` and SP = OS // 2: the class's mid-bit sample, as
  `uart_rx.v:22-25` states it;
- D_r = ⌊clk_freq(u_rx) / (baud_rate(u_rx) · OS)⌋;
- B = `tx_bytes`, N = len(B).

`tb/…`, `u_tx/…` and `u_rx/…` below stand for
`components/<id>/domains/digital/<facet>`.

| Derivation | Value | Applies when (else `ReferenceBlocked(msg, [])` → `REFERENCE_NOT_APPLICABLE`) | `reference_inputs` |
|---|---|---|---|
| `clock_period` | 2·h | always | `tb/clock_half_period` |
| `idle_high_after_reset` | 1 (the 8N1 idle level is mark) | always | `tb/reset_cycles` |
| `bit_period_cycles` | D_t | B[0] is odd | `u_tx/clk_freq`, `u_tx/baud_rate`, `tb/tx_bytes` |
| `bit_rate` | 1 / (2·h·D_t) | B[0] is odd (F4) | the three above plus `tb/clock_half_period` |
| `frame_cycles` | FRAME_BITS · D_t | always | `u_tx/clk_freq`, `u_tx/baud_rate` |
| `bytes_sent` | N | W | `tb/tx_bytes`, `u_tx/clk_freq`, `u_tx/baud_rate`, `u_rx/clk_freq`, `u_rx/baud_rate`, `u_rx/oversample` |
| `lossless_loopback` | 0 | W | the same without `tb/tx_bytes` |
| `no_framing_errors` | 0 | W | as `lossless_loopback` |

A null input raises `ReferenceBlocked(msg, missing)`, which gives
`MISSING_REQUIRED_INPUT`.

**The sampling condition W** is minimal's derivation, extended here to N
bytes:
- **Detection.** The receiver detects a start at the first tick m (every D_r
  cycles, free-running from reset) at which `rx_sync` is low. `rx_sync` is the
  line two edges earlier, so with S the line's first low edge,
  φ = m − 2 − S ∈ [0, D_r − 1].
- **Sampling.** It then samples bit b (0 confirms the start, 1…8 are data, 9
  is the stop) at the line position S + φ + (SP + OS·b)·D_r.
- **The condition,** for every phase φ:

  **for all b in 0…9: b·D_t ≤ (SP + OS·b)·D_r and (SP + OS·b)·D_r + D_r − 1 < (b + 1)·D_t**

  D_r = 0 fails it.
- **N bytes.** The stop sample then lies inside the stop bit, so the receiver
  is back in IDLE before the next start edge, and every byte meets the same
  condition with its own φ (**Inferred** from the RTL's schedule).
- **Committed sample:** D_t = 434, D_r = 27. For b = 9: 3906 ≤ 4104 and
  4130 < 4340, so W holds.

**Evidence that W is sound and conservative:**
- minimal's sweep of 144 one-byte runs: where W held, 68 of 68 recovered;
  where it failed, 15 of 76 still recovered, all `0xFF` (**Verified** from
  its recorded output).
- On the final harness (§5.4), W holds for the committed file, 230 400 Bd, 3
  bytes at 9600 Bd and a transmitter at 120 500 Bd (D_t 414), and all
  recover.
- W fails for 20 MHz, a receiver at 57 600 Bd, and a transmitter at
  121 000 Bd (D_t 413, the equality point with D_r 27). The first two
  misread; the third still recovers: W is sufficient, not necessary.
- Consequence: a borderline design gets `REFERENCE_NOT_APPLICABLE`, never a
  false `PASS` or a false V3 `FAIL`.

**`dependencies(model, metric, scenario)`** is coarse, as in electrical
(`electrical.py:776-785`): every digital facet of the top and the instances,
sorted. The runner adds a requirement's limit quantity
(`dataset.py:1313-1315`).

**`components_for`:**
- `tx_*` metrics → `["u_tx (uart_tx)"]`;
- `rx_*` metrics and `outputs_unknown_after_reset` →
  `["u_rx (uart_rx)", "u_tx (uart_tx)"]`;
- `clock_period_s` → `["tb_uart_loopback (top)"]`.

### 5.3 Values: Icarus against the closed forms (**Verified**, `final/closed_forms.py`: 0 mismatches)

The golden stores 12 significant figures (`requirements.py:143`).

| Metric | Measured (Icarus 13 = 11 = Verilator 5.052) | Closed form | Stored golden | Tolerance |
|---|---|---|---|---|
| `clock_period_s` | 2e-08 | 2e-08 | 2e-08 | 1e-15 s |
| `tx_idle_after_reset` | 1 | 1 | 1.0 | 0 |
| `tx_bit_cycles` | 434 | 434 | 434.0 | 0 |
| `tx_bit_rate_bd` | 115207.3732718894 | 115207.3732718894 | 115207.373272 (\|Δ\| 1.1e-7) | 1e-3 Bd |
| `tx_frame_cycles` | 4340 | 4340 | 4340.0 | 0 |
| `rx_bytes_received` | 2 | 2 | 2.0 | 0 |
| `rx_bit_errors` | 0 | 0 | 0.0 | 0 |
| `rx_framing_errors` | 0 | 0 | 0.0 | 0 |
| `outputs_unknown_after_reset` | 0 | — | — | — |

### 5.4 What the checks catch (**Verified**, Icarus 13, `final/v/`, RTL edits in `final/mut/`)

| Copy | Metrics that change | Checks that change |
|---|---|---|
| receiver bit order reversed (`shift_reg[7 - bit_idx]`) | `rx_bit_errors` 8 | REF-DIG-007 FAIL, REQ-DIG-004 FAIL |
| the same with minimal's single byte `0xA5` | nothing (a palindrome) | none: the reason for D6 |
| transmitter divider off by one (`== BAUD_DIV`) | 435 / 114942.53 / 4350 | REF-DIG-003, -004, -005 FAIL |
| transmitter line not reset (`tx <= tx`) | `tx_idle_after_reset` 0, `outputs_unknown_after_reset` 1 | REF-DIG-002 FAIL, REQ-DIG-006 FAIL |
| receiver stop-bit check removed | nothing | none: a correct loopback always delivers a good stop bit, so framing detection is never exercised (extensible's finding; PLANNED fault scenario, Q-D7) |
| first byte even (`0x34`) | `tx_bit_cycles` 1302, 38402.46 Bd | REF-DIG-003, -004 `REFERENCE_NOT_APPLICABLE` |

The goldens are blind to a wrong override that leaves D_t unchanged
(`BAUD_RATE(115201)` still gives 434). V2's independent re-read (§3.5) covers
that.

---

## 6. Requirements (`requirements/requirements.json`)

### 6.1 The document, exactly

```json
{
  "$schema": "https://embeddedos.org/schemas/engineering-model/v1/engineering-requirements.schema.json",
  "requirements_version": "1.0.0",
  "design_id": "uart_loopback_001",
  "reference_values": [
    {"reference_id": "REF-DIG-001", "title": "The harness clock runs at twice its half period", "domain": "digital",
     "metric": "clock_period_s", "scenario": {"name": "loopback"}, "unit": "s", "absolute_tolerance": 1e-15,
     "derivation": "clock_period", "source": COMPUTATION},
    {"reference_id": "REF-DIG-002", "title": "The line and tx_ready are high after reset", "domain": "digital",
     "metric": "tx_idle_after_reset", "scenario": {"name": "loopback"}, "unit": "1", "absolute_tolerance": 0,
     "derivation": "idle_high_after_reset", "source": COMPUTATION},
    {"reference_id": "REF-DIG-003", "title": "A start bit lasts CLK_FREQ // BAUD_RATE cycles", "domain": "digital",
     "metric": "tx_bit_cycles", "scenario": {"name": "loopback"}, "unit": "cycles", "absolute_tolerance": 0,
     "derivation": "bit_period_cycles", "source": COMPUTATION},
    {"reference_id": "REF-DIG-004", "title": "The bit rate is the clock divided by the transmitter's divider", "domain": "digital",
     "metric": "tx_bit_rate_bd", "scenario": {"name": "loopback"}, "unit": "Bd", "absolute_tolerance": 0.001,
     "derivation": "bit_rate", "source": COMPUTATION},
    {"reference_id": "REF-DIG-005", "title": "A frame keeps the transmitter busy for ten bit periods", "domain": "digital",
     "metric": "tx_frame_cycles", "scenario": {"name": "loopback"}, "unit": "cycles", "absolute_tolerance": 0,
     "derivation": "frame_cycles", "source": COMPUTATION},
    {"reference_id": "REF-DIG-006", "title": "Every byte sent is received", "domain": "digital",
     "metric": "rx_bytes_received", "scenario": {"name": "loopback"}, "unit": "1", "absolute_tolerance": 0,
     "derivation": "bytes_sent", "source": COMPUTATION},
    {"reference_id": "REF-DIG-007", "title": "The loopback recovers every bit", "domain": "digital",
     "metric": "rx_bit_errors", "scenario": {"name": "loopback"}, "unit": "bits", "absolute_tolerance": 0,
     "derivation": "lossless_loopback", "source": COMPUTATION},
    {"reference_id": "REF-DIG-008", "title": "The receiver reports no framing error", "domain": "digital",
     "metric": "rx_framing_errors", "scenario": {"name": "loopback"}, "unit": "1", "absolute_tolerance": 0,
     "derivation": "no_framing_errors", "source": COMPUTATION}
  ],
  "requirements": [
    {"requirement_id": "REQ-DIG-001", "title": "The line runs no slower than 115200 Bd less 2 %", "domain": "digital",
     "component": "u_tx", "metric": "tx_bit_rate_bd", "scenario": {"name": "loopback"}, "operator": ">=",
     "limit": {"value": 112896.0}, "unit": "Bd", "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-002", "title": "The line runs no faster than 115200 Bd plus 2 %", "domain": "digital",
     "component": "u_tx", "metric": "tx_bit_rate_bd", "scenario": {"name": "loopback"}, "operator": "<=",
     "limit": {"value": 117504.0}, "unit": "Bd", "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-003", "title": "Every byte the testbench offers arrives", "domain": "digital",
     "component": "u_rx", "metric": "rx_bytes_received", "scenario": {"name": "loopback"}, "operator": ">=",
     "limit": {"quantity": "components/tb_uart_loopback/domains/digital/byte_count"}, "unit": "1",
     "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-004", "title": "No bit is received wrong", "domain": "digital",
     "component": "u_rx", "metric": "rx_bit_errors", "scenario": {"name": "loopback"}, "operator": "<=",
     "limit": {"value": 0}, "unit": "bits", "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-005", "title": "No framing error is reported", "domain": "digital",
     "component": "u_rx", "metric": "rx_framing_errors", "scenario": {"name": "loopback"}, "operator": "<=",
     "limit": {"value": 0}, "unit": "1", "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-006", "title": "No output is unknown once reset is released", "domain": "digital",
     "component": "tb_uart_loopback", "metric": "outputs_unknown_after_reset", "scenario": {"name": "loopback"},
     "operator": "<=", "limit": {"value": 0}, "unit": "1", "source": EXAMPLE, "illustrative": true},
    {"requirement_id": "REQ-DIG-007", "title": "The clock period is no shorter than the target device can meet", "domain": "digital",
     "component": "tb_uart_loopback", "metric": "clock_period_s", "scenario": {"name": "loopback"}, "operator": ">=",
     "limit": {"quantity": "components/target_device/domains/digital/min_clock_period"}, "unit": "s",
     "source": EXAMPLE, "illustrative": true}
  ]
}
```

`COMPUTATION` and `EXAMPLE` stand for the objects below, written out in full
in the file:
- `COMPUTATION = {"kind": "computation", "ref": "model verification: an independent closed-form derivation, not a design requirement"}`;
- `EXAMPLE = {"kind": "requirement", "ref": "example requirement for the uart_loopback_001 MVP, chosen to exercise the pipeline; not a customer, interface or certification requirement; no standard or peer device was consulted"}`.

The ±2 % band and the byte equality are example rules, and no standard was
consulted (Q4).

### 6.2 Expected verdicts

Every V3 reference is expected to PASS.

| Requirement | Committed value | Expected |
|---|---|---|
| REQ-DIG-001 | 115207.37 ≥ 112896 | `WARNING WITHIN_ILLUSTRATIVE_LIMIT` |
| REQ-DIG-002 | 115207.37 ≤ 117504 | `WARNING` |
| REQ-DIG-003 | 2 ≥ 2 (limit resolves to the DERIVED `byte_count`) | `WARNING` |
| REQ-DIG-004 | 0 ≤ 0 | `WARNING` |
| REQ-DIG-005 | 0 ≤ 0 | `WARNING` |
| REQ-DIG-006 | 0 ≤ 0 | `WARNING` |
| REQ-DIG-007 | limit UNKNOWN | **`BLOCKED MISSING_REQUIRED_INPUT`**, finding `UNKNOWN: components/target_device/domains/digital/min_clock_period`. Its result shows 2e-08 measured by `v3.REF-DIG-001`, the first sorted check whose case has equal arguments (`results.py:296-306`). |

### 6.3 Expected receipt (**Inferred** from §5.3 and `dataset.py:1197-1395`)

| Gate | Checks | Verdict |
|---|---|---|
| V0 | `dataset-schemas-and-hashes` (schemas, hashes, cited sources with REUSE-1 and `LICENSE`), `dataset-input-immutability`, `pinned-clean-source` | PASS, on a clean tree |
| V1 | `v1.digital.extraction-and-sanity` | PASS |
| V2 | `v2.dataset-reproduction`, `v2.digital.model-invariants` | PASS |
| V3 | 8 golden cases | PASS |
| V4 | 6 `WARNING`, 1 `BLOCKED` | BLOCKED |

- The receipt is `BLOCKED` overall and not eligible for ebuild.
- There are 15 results.
- 14 cases are compiled.
- Without Icarus, the 14 cases are `BLOCKED TOOL_NOT_INSTALLED`, attributed
  to `ecad-validator` (`cases.py:444-454`).

### 6.4 Test-built copies (not committed)

Each copy is rebuilt. The metrics are **Verified** on Icarus 13, and on
Icarus 11 where marked 11.

| Copy | Edit | Metrics | Verdicts |
|---|---|---|---|
| **FAIL from a mutated input** | `BAUD_RATE = 230_400` (END 10 420) | 2e-08, 1, 217, 230414.74654377881, 2170, 2, 0, 0, 0 (11) | V1–V3 PASS (W holds at D_r 13). REQ-DIG-002 **FAIL** (230414.7 > 117504); the rest WARNING, REQ-DIG-007 BLOCKED. The FAIL is the design's. |
| Mis-sampling receiver | `CLK_HALF_PERIOD_NS = 25`, `CLK_FREQ = 20_000_000` (END 8308) | 4.9999999999999998e-08, 1, 173, 115606.94, 1730, **1, 7, 1**, 0 (11) | W fails: REF-DIG-006…008 `REFERENCE_NOT_APPLICABLE`, the other references PASS. REQ-DIG-003, -004, -005 **FAIL**; REQ-DIG-001/002 WARNING. |
| Clock mismatch | `CLK_FREQ = 40_000_000`, half period 10 ns | 2e-08, 1, 347, 144092.22, 3470, 2, 0, 0, 0 | V1 `DOMAIN_SANITY_FAILED` (§3.4 rule 3). V3 PASS; REQ-DIG-002 FAIL. |
| Receiver at 57 600 Bd | `.BAUD_RATE(57_600)` on `u_rx` only | 434 …, **1, 4, 0** | W fails: receiver references not applicable. REQ-DIG-003, -004 FAIL. |
| W at its edge | transmitter at 121 000 Bd (D_t 413, the equality point) / 120 500 Bd (D_t 414) | both 2 bytes, 0 errors | 413: `REFERENCE_NOT_APPLICABLE` (W conservative); 414: PASS |
| Three bytes | `TX_BYTE_2 = 8'h5A`, 9600 Bd (END 312 484) | 5208, 9600.6144393241175, 52080, 3, 0, 0 | all PASS; kills a hard-coded N or END |
| RTL defects | §5.4 copies, with `copied_from` removed, since a modified file is no copy | §5.4 | §5.4 |

**Boundaries:**
- **Stand-in, the bit rate:**
  - `>= 115207.3732718894` WARNING, `>= nextafter(…, inf)` FAIL;
  - `<=` the same value WARNING, `nextafter(…, 0)` FAIL.
- **Stand-in, tolerance folding:** `rx_bytes_received >= 3` FAIL, and with
  `tolerance: 1` WARNING.
- **Real Icarus:** `tx_frame_cycles <= 4340` WARNING, `<= 4339` FAIL.
- **W on hand-built models:**
  - (D_t, D_r) = (152, 10) not applicable, (153, 10) applies;
  - (168, 10) applies, (169, 10) not;
  - (107, 7) not, (108, 7) applies.

**Null statuses.** `min_clock_period` as `UNKNOWN` (committed), `UNSPECIFIED`
(citing the annotations by hash as the silent document) and `NOT_AVAILABLE`
each give `BLOCKED MISSING_REQUIRED_INPUT <STATUS>: <path>` and a
schema-valid receipt.

**AI and PASS paths**, on a non-illustrative copy of REQ-DIG-007:
- `min_clock_period` `SPECIFIED` at 1e-8 s, labelled "test fixture value, no
  real device", gives `PASS`;
- `AI_ASSUMPTION` (source kind `ai`) at 1e-8 (met) and at 5e-8 (violated)
  gives `INCONCLUSIVE INPUT_IS_AI_ASSUMPTION` both times;
- the illustrative original with `SPECIFIED` 1e-8 gives `WARNING`.

**Invalid inputs:** every refusal of §3.1 and every class rule of §3.3, each
through `validate`, never reaching Icarus.

---

## 7. Tool-adapter changes (ARCH-10; ARCH-2's output-copy and metric halves; RESULT-2 on the iverilog path)

### 7.1 ARCH-10: `tools/ecad_validation/adapters/hdl.py` onto `run_process`

**Today (Observed):**
- one private `tempfile.TemporaryDirectory` (`hdl.py:51`);
- `subprocess.run` for compile (`:72-79`) and for run (`:93-100`), with the
  inherited environment and no output cap;
- `request.arguments` appended after the files (`:69`);
- a timeout always records the compile argv (`:108`);
- no metrics (`:122-132`).

**Verified** on the committed file: `PASS RTL_TESTBENCH_PASSED`, `metrics {}`,
and no `env` passed (`judge/final/arch10/`). So every V3/V4 comparator would
say `INCONCLUSIVE` (ARCH-2).

**New constants:**

```python
MAX_INPUT_BYTES = 1 << 20
PROGRAM = "simulation.vvp"
DECLARED = re.compile(r'\$display\("ECAD_METRIC ([a-z][a-z0-9_]*) %(?:0d|\.17g)"')
REPORTED = re.compile(r"^ECAD_METRIC ([a-z][a-z0-9_]*) (\S+)$")
NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")   # before float(), which reads 1_0, nan, inf
TRUNCATED = "[output truncated]"                                         # what process._limited appends (process.py:59)
RECEIPT_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_SUMMARY_PROBLEMS = 10
```

**New `run()` flow.** `capability()` is unchanged (`hdl.py:19-31`).

1. **Capability unavailable** → `BLOCKED`, `_receipt_reason(capability.reason)`
   (§7.5), with the raw reason in the summary. `VVP_NOT_INSTALLED` and the
   fixture's `IVERILOG_NOT_INSTALLED` pass through.
2. **No inputs** → `BLOCKED RTL_INPUT_MISSING` (unchanged).
3. **`request.arguments` non-empty** → `BLOCKED RTL_ARGUMENTS_REFUSED`, naming
   them; nothing runs (D8).
4. **Any input over `MAX_INPUT_BYTES`** → `BLOCKED RTL_INPUT_TOO_LARGE`;
   nothing is read or run.
5. **Declarations:** `declared, twice = declared_metrics([text of each input, UTF-8, errors="replace"])`.
6. **Compile**, inside `tempfile.TemporaryDirectory(prefix="ecad-hdl-") as stage`:
   `run_process(ProcessRequest(argv=[capability.executable or "iverilog", "-g2012", "-o", PROGRAM, *relatives], input_root=request.product_root, input_files=request.input_files, timeout_seconds=request.timeout_seconds, collect=(PROGRAM,), collect_into=Path(stage)))`.

   | Outcome | Verdict and reason |
   |---|---|
   | `UNAVAILABLE` | `BLOCKED TOOL_NOT_INSTALLED` |
   | `TIMED_OUT` | `INCONCLUSIVE RTL_EXECUTION_TIMED_OUT`; command = the compile argv; stdout is text |
   | `CRASHED` | `INCONCLUSIVE RTL_EXECUTION_ERROR` |
   | exit ≠ 0 | `FAIL RTL_COMPILE_FAILED`; command = the compile argv, with its (now capped) output, as today |
   | exit 0, program not collected | `INCONCLUSIVE RTL_PROGRAM_MISSING`, with the collect problem in the summary; vvp is not run |

7. **Run:** `run_process(ProcessRequest(argv=["vvp", PROGRAM], input_root=Path(stage), input_files=[Path(stage) / PROGRAM], timeout_seconds=request.timeout_seconds))`.
   The run workspace holds only the program.
   - Outcomes map as in step 6, with the run argv.
   - Exit 0 → `PASS RTL_TESTBENCH_PASSED`.
   - Exit ≠ 0 → `FAIL RTL_TESTBENCH_FAILED` with **no** metrics.
8. **On PASS:**
   - stdout ending with `TRUNCATED` → `INCONCLUSIVE OUTPUT_TRUNCATED`,
     `metrics = {}`;
   - otherwise `metrics = parse_metrics(stdout, declared)[0]`, with the
     summary "committed RTL testbench executed: n of m declared metrics read"
     plus up to 10 problems (with "declared more than once" for each name in
     `twice`).
9. **The record:**
   - `command` = the run argv (`[<abs vvp>, "simulation.vvp"]`; the absolute
     path is STATE-2, still open);
   - `stdout`, `stderr` = vvp's;
   - `tool_version` = the capability's;
   - `output_files` = `[]`.

   On success the compile step's output is dropped, as today (`hdl.py:122-132`).

**Behaviour changes, each named:**

| Change | Named by |
|---|---|
| both steps get the scrubbed environment (`process.py:112-127`) and the 4 MiB cap (`process.py:55-59`) | ARCH-10 |
| the program crosses between the steps through `collect` | ARCH-2, output half |
| metrics are parsed; truncated output is `INCONCLUSIVE`; exit ≠ 0 has no metrics | ARCH-2, metric half |
| arguments are refused | ARCH-2 (with the ngspice precedent) and SEC-1 |
| the timeout path names the step that timed out | consequence of the two calls |
| an unreceiptable probe reason is mapped | RESULT-2 |

**Unchanged:** `-g2012`; a symlinked input is still a `ValueError`, now from
`run_process` (`process.py:97-98`), which the engine maps to
`ADAPTER_EXECUTION_ERROR` (`cases.py:382-396`); per-step timeouts, so at most
2 × 60 s per case.

**Verified** in scratch (`final/arch10/probe.py`, a copy of `run_process` with
`collect`):
- compile and run each saw exactly `HOME LANG LC_ALL PATH TMPDIR`;
- `simulation.vvp` crossed between the two workspaces;
- the nine metric lines were printed;
- `IVERILOG_ICONFIG` set in `os.environ` created no file.

### 7.2 ARCH-2, output-copy half: `tools/ecad_validation/adapters/process.py`

- **New fields.** `ProcessRequest` gains `collect: Tuple[str, ...] = ()` and
  `collect_into: Optional[Path] = None`. `ProcessResult` gains
  `collected: List[Path]` (paths under `collect_into`) and
  `collect_problems: Dict[str, str]`. `MAX_COLLECT_BYTES = 64 * 1024 * 1024`.
- **Before running, a `ValueError`** (the child never runs) when:
  - `collect` is given without `collect_into`;
  - a name is not one plain file name: empty, `.`, `..`, containing `/` or
    `\`, or absolute.
- **After a `COMPLETED` run** (any exit code), before the workspace is
  deleted, each name gets one outcome:

  | What the workspace holds | Result |
  |---|---|
  | nothing | "not produced" |
  | a symlink (checked with `lstat`) | "a symbolic link; not copied" |
  | not a regular file | "not a regular file; not copied" |
  | more than `MAX_COLLECT_BYTES` | "larger than … bytes; not copied" |
  | a regular file within the limit | `shutil.copyfile` to `collect_into/<name>`, appended to `collected` |

- **After a timeout, crash or unavailable tool:** nothing is collected; a
  partial output is not a result.
- **With the default `()`,** the flow is byte-for-byte today's, and `outputs`
  is unchanged (`process.py:155-159`). No other caller passes `collect`, so
  ngspice (`ngspice.py:189-196`), kicad, python_control and mujoco are
  untouched.

### 7.3 ARCH-2, metric half: the parser (`hdl.py`, public, each with a doctest)

```python
def declared_metrics(texts: Sequence[str]) -> Tuple[List[str], List[str]]:
    """(names declared exactly once across the texts, in order; names declared more than once)."""
def parse_metrics(stdout: str, declared: Sequence[str]) -> Tuple[Dict[str, float], Dict[str, str]]:
    """(metrics; problems: "not reported", "reported more than once", "not a number: <token>", "not finite")."""
```

- A declared name becomes a metric only if exactly one stdout line reports it
  with a finite `NUMBER`.
- Values are floats, as ngspice's. `%0d` of X prints `x`, and `%.17g` of NaN
  prints `nan`, which `NUMBER` refuses (**Verified**).
- Undeclared lines are ignored.
- The decision rules are those of `ngspice.py:44-124`, duplicated rather than
  shared: this is the second occurrence (QUALITY.md; D5).

### 7.4 Version

- The first-line rule is unchanged (`capabilities.py:46-48`). **Verified**
  first lines: "Icarus Verilog version 13.0 (stable) (v13_0)" and "Icarus
  Verilog version 11.0 (stable) ()", both exit 0.
- There is no `VERSION_PATTERNS` entry: `test_ngspice_adapter.py:514-536` pins
  the first-line rule for iverilog.
- vvp's version is not probed; a mixed installation is a risk (Q-D3).

### 7.5 RESULT-2 on the iverilog path

`hdl.py` gets its own `_receipt_reason`, the mapping of `ngspice.py:127-149`:

| Probe reason | Receipt reason |
|---|---|
| `VERSION_PROBE_ERROR:<msg>` | `VERSION_PROBE_ERROR` |
| `VERSION_PROBE_EXIT_-9` | `VERSION_PROBE_EXIT_NONZERO` |
| `None` | `TOOL_NOT_INSTALLED` (today's fallback, `hdl.py:40`) |
| a valid code | itself |

It is the second copy of the same temporary shim. Both go when
`fix/version-probe-reason-codes` lands (`MEMORY.md:69`).

### 7.6 Timeouts, resource limits, evidence

- **Limits:**
  - 60 s per step;
  - the grammar's bounds;
  - C7's END ≤ 2 000 000 cycles, about 3 s here;
  - 1 MiB per input;
  - 64 MiB per collected file;
  - 4 MiB per stream, buffered and then truncated.
- **No confinement:** there is no CPU, memory, filesystem or network
  confinement (SEC-1, plan R5).
- **Evidence per case** (`cases.py:398-418, 455-485`): the case document, the
  simulation file and the execution record, each with its digest. The chain
  is copy (= origin, REUSE-1) → model (V2 reproduction) → simulation file
  (exact) → execution record → check → result.
- **The compiled program is never evidence:** its `:vpi_module` lines hold
  absolute install paths (**Verified**), and it lives only in the deleted
  stage directory.

### 7.7 Why no other adapter changes

- `cases.ADAPTERS` (`cases.py:29-35`), ngspice, kicad, mujoco,
  python_control and `capabilities.py` are untouched.
- `run_process`'s new fields default to collecting nothing.
- The kicad metric parser (ARCH-2) stays with the PCB PR.

### 7.8 Verilator: PLANNED, argued

| For a second adapter in this PR | Against (decisive) |
|---|---|
| It is installed. The final harness runs **unchanged** under Verilator 5.052 and prints identical metric lines for the committed file and the 20 MHz copy (**Verified**, `final/vl/`). A cross-simulator V3 check would be real evidence. | **Q9:** the merged cases contract's adapter enum has no `verilator` (`validation-cases.schema.json:48`); such a case is `CASE_SCHEMA_INVALID` (`cases.py:171-191`). Amending a merged contract is the maintainer's decision (plan:950). |
| | **CI cannot run it:** apt Verilator on `ubuntu:22.04` is 4.038 (**Verified**). It rejects `--binary` and `--timing` ("Invalid option") and refuses the harness: "Unsupported: timing control statement in this location" (**Verified**). CI would need Verilator ≥ 5 from source or a pinned image. |
| | **Records:** every run prints `- Verilator: $finish at 417us; walltime 0.004 s; speed …`, which differs between runs (**Verified**). Markers ignore it, but the execution records would differ. |
| | **Cost and semantics:** a C++ build of 4.2–4.5 s per case (**Verified**), against 0.05 s for Icarus. It needs executable-bit collection. It is 2-state, so metric 9 is vacuous and an unreset output gives different metrics (`tx_bit_cycles` 4 against 434, **Verified**). The Mac's default SDK fails to link (the brief). Verilator lints `$system` and DPI without error (**Verified**), so it needs its own screen design (SEC-1). |

**Plan for the later PR:**
- a `verilator` tool adapter: `verilator --binary --timing -Wno-fatal --top-module ecad_harness -Mdir obj <file>`,
  then `obj/Vecad_harness`, both through `run_process` with `collect` extended
  to keep executable bits;
- the same marker parser, which is then the third occurrence and moves to a
  shared module (extensible's `markers.py`);
- a V3 check that the two simulators agree, per extensible §7.7's design (one
  case per entry and simulator, keyed by case id).

It is blocked on Q9 and a CI Verilator ≥ 5.

**ModelSim/Questa:** PLANNED only. It is licensed, and there is no adapter
and no stub.

---

## 8. Protocol, registry and fixture

### 8.1 Protocol: no change

`base.py:105-139` suffices:
- `case_target(sample_id)` names one derived file;
- `write_models(model, …)` has everything, since the RTL text is in the model
  (D1);
- a scenario carries only its name.

`base.py:17-20` ("Changes since the foundation: `Extraction.producer`") stays
true. Nothing in `base.py`, `mechanical.py`, `electrical.py` or the fixture
changes, so no matching changes are needed.

**Considered and not changed:**
- `case_target(model, sample_id)` (F2);
- a fidelity value (Q-D4);
- `CaseTarget.scenario_inputs` (one file serves every case);
- several simulators per entry (§7.8).

### 8.2 Registry side effects (not protocol changes)

- `domains/__init__.py:29` gains `"digital": DigitalAdapter()`, with its
  import. The doctest at `:73-75` still gives `['AVAILABLE', 'NOT_APPLICABLE']`.
- `robotic_joint_001/dataset-item.json:109-113` and
  `servo_supply_001/dataset-item.json:92-96` each regenerate one entry:
  `digital` → `NOT_APPLICABLE`, "the digital adapter reads verilog, which this
  sample does not have" (`domains/__init__.py:94`). No other byte changes.
  The mechanical rebuild needs OCP.
- `test_electrical_domain.py:888-891` pops `digital` and asserts
  `NOT_APPLICABLE` with that reason before its `NOT_IMPLEMENTED` set check.
  This strengthens it.

### 8.3 Fixture: coexist (D12)

`VerilogFixtureAdapter` (`test_domain_adapter.py:67-164`) keeps domain
`digital`. Every fixture test already passes
`{**REGISTRY, "digital": VerilogFixtureAdapter()}` or patches the registry
(`:269, 428, 443, 461, 470, 481, 603, 708, 750, 768, 972, 989, 1110`,
**Observed**).

**The one production-registry test.**
`test_without_its_adapter_the_domain_is_not_implemented_and_nothing_runs`
(`:361-381`) calls `build(item)` and `validate(item, …)` without a registry.
- **Change:** it passes `{k: v for k, v in REGISTRY.items() if k != "digital"}`
  to both.
- **Assertions:** unchanged.
- **Docstring:** the module docstring (`:1-24`, "The only production adapter
  is mechanical") is corrected.
- **New test:** `test_a_domain_with_no_production_adapter_is_not_implemented`
  (D30) keeps the production-registry `NOT_IMPLEMENTED` path covered with a
  `pcb` sample.

A future fixture test that forgets the registry runs the production adapter
and fails loudly (`SOURCE_REJECTED` on the blinker).

---

## 9. Tests

### Conventions

- **Expected values** are typed by hand from the sources and the formulas of
  §5, never computed by the code under test.
- **Imports:** new files set `sys.path` as `test_electrical_spice.py:27-28`
  does, with no `noqa`.
- **The stand-in Icarus** (fast tests) follows `_passing_icarus`
  (`test_domain_adapter.py:203-221`):
  - it uses `mock.patch.dict("ecad_validation.cases.ADAPTERS", {"iverilog": StandIn})`;
  - `StandIn.run` returns `hdl.parse_metrics(RECORDED[copy], hdl.declared_metrics([input text])[0])[0]`
    with tool version `"stand-in 0"`;
  - `RECORDED` holds the Icarus 13 stdouts of the committed file and the
    copies (`final/v/*.out`), re-recorded through the real adapter at
    implementation time and labelled "Icarus Verilog 13.0, macOS arm64,
    2026-09-27; identical ECAD_METRIC lines on 11.0, ubuntu:22.04 arm64".
- **`require_icarus()`** needs `HDLAdapter().capability()` to be available with
  a version matching `^Icarus Verilog version \d+\.\d+`. Otherwise it raises
  `unittest.SkipTest(reason)`, or `AssertionError` with
  `ECAD_REQUIRE_HDL_TOOLS=1` (the pattern of `test_electrical_spice.py:52-72`).
- **A trap for H1:** `mock.patch.object(hdl.subprocess, "run", …)` patches the
  `subprocess` module itself, so it also reaches `run_process` and the version
  probe (**Verified**: three calls). H1 therefore patches
  `ecad_validation.adapters.process.subprocess.run` and asserts on the `env`
  of each call it sees.

### `tests/unit/test_verilog_source.py` (fast: grammar)

| # | Test | Asserts |
|---|---|---|
| V1 | `test_the_committed_rtl_copies_parse_to_their_hand_read_interfaces` | module names; parameters `{CLK_FREQ: 50000000, BAUD_RATE: 115200}`; six ports each with direction and width; `OVERSAMPLE` 16 at line 23 |
| V2 | `test_the_committed_top_parses_to_its_hand_read_structure` | 6 localparams with values, widths and lines 26–31; 9 signals; 2 instances with overrides and connections |
| V3 | `test_directives_other_than_the_leading_timescale_are_refused` | `` `include``, `` `define``, a macro use, `` `ifdef``, `` `resetall``, a second or late `` `timescale``, `` `timescale 1ns/1ns``; each message names the directive, its reason and file:line |
| V4 | `test_system_tasks_and_functions_are_refused_with_their_class` | `$fopen $fwrite $readmemh $system $dumpfile $value$plusargs $clog2 $display $finish $stop $random`, and `a$b` |
| V5 | `test_keywords_outside_each_file_kind_are_refused_by_class` | one subTest per class; in RTL `initial assign negedge function task generate for while repeat forever integer real inout defparam force import`; in the top `always initial assign` |
| V6 | `test_lexical_forms_the_grammar_cannot_see_through_are_refused` | strings, `(* *)`, `\esc`, `'b1`, `8'hxx`, `?`, reals, `=== !== ** <<< {}`; a 65-character name; `ecad_x`; `ECAD_METRIC` inside a comment |
| V7 | `test_bytes_and_encoding_bounds_are_exact` | accepted at the byte and line limits, refused one over; CR, NUL, invalid UTF-8, no final LF, empty, LFS pointer, unterminated `/*`; the RTL's comment dashes accepted, non-ASCII in code refused |
| V8 | `test_rtl_bodies_are_clocked_nonblocking_and_single_driven` | `=`, `@(a)`, `@*`, `@(posedge a or negedge b)`, `#5`, a reg in two `always` blocks, an assignment to an input or undeclared name, `u.x`, an instance in a leaf, a wire in a leaf, an unassigned `output reg`, a clock that is not an input; `MAX_DEPTH` nesting accepted and one more refused as `HdlRefused`, never `RecursionError` |
| V9 | `test_rtl_headers_outside_the_subset_are_refused` | non-ANSI, `input reg`, `[7:1]`, `[W-1:0]`, a parameter without a decimal default, two modules in one file, text after `endmodule`, `2'd4` |
| V10 | `test_a_top_outside_the_declarative_form_is_refused` | ports on the top, `reg clk = 0;`, a localparam expression, an override expression, positional, `.*` and `.p()` connections |
| V11 | `test_elaboration_resolves_one_top_with_every_leaf_once` | zero or two tops, a module defined twice, an unknown module, a leaf twice or never, an unknown port, a port twice, an unconnected port, a width mismatch, an output onto a reg, two drivers, an undriven input, an override of an undeclared parameter or a localparam, `MAX_MODULES` + 1 sources |
| V12 | `test_the_harness_reader_returns_what_the_harness_states` | §4.2 read back (signals, instances, 10, 4, [53, 202] twice, 20836, the nine names); an extra module, a `$fopen`, a second `` `timescale`` or text after `endmodule` refused by name |
| V13 | doctest list (`test_engineering_model.py:1216-1217`) gains `"verilog"` and `"domains.digital"` | the examples run |

### `tests/unit/test_hdl_adapter.py` (fast; `process.subprocess.run` and `process.shutil.which` faked)

| # | Test | Asserts |
|---|---|---|
| H1 | `test_both_icarus_steps_run_through_run_process_with_the_scrubbed_environment` | With `ECAD_TEST_SECRET`, `IVERILOG_ICONFIG`, `IVERILOG_VPI_MODULE_PATH` and `IVERILOG_DUMPER` in `os.environ`: <br>• 2 calls, neither `env` holding them, keys ⊆ the scrubbed set; <br>• `HOME` and `TMPDIR` inside each `cwd`; the two `cwd`s differ, and neither is the product root; <br>• the compile cwd holds only the input, the run cwd only `simulation.vvp`; <br>• argv exactly `[iverilog, -g2012, -o, simulation.vvp, derived/digital/x.v]` and `[vvp, simulation.vvp]`; `shell` False (ARCH-10) |
| H2 | `test_both_steps_are_capped_at_the_process_output_limit` | compile exit 1 with 5 MiB of stderr → `FAIL RTL_COMPILE_FAILED`, stderr ending `[output truncated]`; a run printing 5 MiB then markers → `INCONCLUSIVE OUTPUT_TRUNCATED`, `{}` |
| H3 | `test_the_compiled_program_is_carried_to_the_run_step` | the fake vvp finds the fake compiler's bytes; none collected → `INCONCLUSIVE RTL_PROGRAM_MISSING` with the collect problem, and vvp is not called |
| H4 | `test_case_arguments_never_reach_a_command_line` | `["-N/tmp/x"]`, `["-mevil"]`, `["-s", "b"]` → `BLOCKED RTL_ARGUMENTS_REFUSED`; `run_process` not called |
| H5 | `test_declared_metrics_are_read_once_each_and_nothing_else` | the nine recorded values; declared twice (across inputs too); reported twice; `nan inf 1e999 1_0 0x10 x`; undeclared, double-spaced and embedded lines ignored; Icarus 13's `$finish` line and Verilator's report lines ignored |
| H6 | `test_a_failed_run_reports_no_metrics` | vvp exit 1 with markers → `FAIL RTL_TESTBENCH_FAILED`, `{}` |
| H7 | `test_timeouts_and_crashes_name_the_step_that_failed` | compile and run `TIMED_OUT`, each with its argv and str stdout keeping the partial output; `OSError` → `INCONCLUSIVE RTL_EXECUTION_ERROR` |
| H8 | `test_an_oversized_input_is_neither_read_nor_run` | `BLOCKED RTL_INPUT_TOO_LARGE`; `run_process` not called |
| H9 | `test_unavailable_paths_keep_their_reason_codes` | no iverilog → `TOOL_NOT_INSTALLED`; `VVP_NOT_INSTALLED`; the fixture's `IVERILOG_NOT_INSTALLED`; `RTL_INPUT_MISSING`; compile exit ≠ 0 → `RTL_COMPILE_FAILED` with the compile argv |
| H10 | `test_a_version_probe_failure_gives_a_reason_the_receipt_accepts` | the §7.5 table; the raw text in the summary |
| H11 | `test_the_version_is_the_first_line_of_iverilog_V` | the 11.0 and 13.0 banners as is; no pattern entry; no output → `None` → a PASS becomes `BLOCKED TOOL_VERSION_UNAVAILABLE` via `execute_cases` |
| H12 | `test_examples_in_the_hdl_and_process_modules` | doctests |
| P1 | `test_run_process_collects_only_declared_regular_files` | real `sys.executable` children write `out.txt`, an undeclared file, a symlink, a directory, and 17 bytes with `MAX_COLLECT_BYTES` patched to 16: only `out.txt` is collected; each of the others is named in `collect_problems` |
| P2 | `test_nothing_is_collected_from_a_run_that_timed_out_or_crashed` | `collected == []` |
| P3 | `test_a_collect_name_that_is_not_one_plain_file_name_is_refused_before_running` | `""`, `.`, `..`, `a/b`, `a\b`, `/abs`, and `collect` without `collect_into` → `ValueError`; the child never runs |
| P4 | `test_a_request_that_collects_nothing_behaves_as_before` | default fields; `collected == []`, `collect_problems == {}`; `outputs` unchanged |

### `tests/unit/test_digital_domain.py` (fast; stand-in Icarus)

| # | Test | Asserts |
|---|---|---|
| D1 | `test_every_testbench_value_is_specified_by_its_file_and_names_no_part` | the §1.6 table: value, unit, status, source kind, ref, sha and note; `tx_bytes == [53, 202]` |
| D2 | `test_the_only_null_value_is_the_unselected_device_s_clock_limit` | one unknowns entry, `needed_by ["digital"]`; no MEASURED, SIMULATED, ESTIMATED or AI_ASSUMPTION; `byte_count` DERIVED from `tx_bytes` |
| D3 | `test_the_model_holds_the_hierarchy_ports_and_verbatim_rtl` | §2.2 typed; `sha256(hdl.text) ==` the source's; component order |
| D4 | `test_an_hdl_member_needs_format_1_2_0` | `hdl` at 1.0.0 or 1.1.0 invalid; an instance needs `text`, `parameters` and each port's `signal`; the top needs `signals` and no ports; the annotation `digital` facet needs 1.2.0; `copied_from` needs provenance 1.1.0; the committed mechanical and electrical models still valid |
| D5 | `test_only_the_uart_8n1_loopback_is_accepted` | C1–C6 each broken once → V1 `SOURCE_REJECTED` naming the rule, with `HDLAdapter.run` patched to raise if called; includes "rx fed from `tx_valid`", a width mismatch, two drivers, a third instance, an inert localparam |
| D6 | `test_v1_refuses_impossible_values_units_and_clocks` | each §3.4 rule, including the 40 MHz copy (rule 3) and a 1 MHz clock at 115 200 Bd (divider 0); the committed model gives `[]` |
| D7 | `test_the_resource_guard_refuses_a_run_longer_than_max_cycles` | 1200 Bd accepted (END 1 999 972); 1199 Bd refused (2 001 652) |
| D8 | `test_the_simulation_file_is_the_rtl_verbatim_then_the_harness` | the bytes equal the Verified file (sha256 `191bd8f1…3e84`); the harness lines typed; a 3-byte 9600 Bd variant's stimulus, expected array, `< 3` and END 312 484 typed |
| D9 | `test_v2_names_every_way_the_simulation_file_can_disagree_with_its_model` | one RTL byte, the half period, an override, a stimulus byte, an expected byte, END, a dropped or duplicated `$display`, an inserted `$fopen`, a swapped connection, a wrong separator hash, a facet sha that is not the top's |
| D10 | `test_references_are_the_closed_forms_written_out_here` | the 8 forms for the committed, 230 400 Bd and 3-byte models; a 115 000 Bd model gives 434 (floor, not 435 by rounding); `reference_inputs` as exact sets |
| D11 | `test_a_reference_does_not_apply_where_its_assumptions_fail` | an even first byte (REF-DIG-003, -004); W at (152, 10)/(153, 10), (168, 10)/(169, 10), (107, 7)/(108, 7), (413, 27)/(414, 27); the 20 MHz model; D_r = 0 |
| D12 | `test_each_metric_has_its_scenario_and_each_derivation_its_metric` | an unknown scenario, a scenario with parameters, a derivation paired with the wrong metric, unit `ms` for `clock_period_s` refused at compile |
| D13 | `test_the_model_names_the_adapter_that_built_it` | producer, `versions.engineering_model`, `versions.domain_models.digital` |
| D14 | `test_the_committed_sample_checks_and_rebuilds_to_the_same_bytes` | `check == []`; a copy rebuilds byte-identical. Manifest: digital `AVAILABLE` (the reason names the class and the BLOCKED list); mechanical and electrical `NOT_APPLICABLE`; six `NOT_IMPLEMENTED`; lineage; `artifact_type hdl_source`; `versions.extraction == "none"` |
| D15 | `test_the_committed_sample_validates_as_designed_with_recorded_icarus_output` | §6.3 in full; 15 schema-valid results; REQ-DIG-007 `measured_by v3.REF-DIG-001` = 2e-08; every fidelity `SIMPLIFIED`; each result's inputs |
| D16 | `test_a_mutated_baud_rate_fails_only_the_bit_rate_requirement` | the recorded 230 400 Bd output: REQ-DIG-002 FAIL; everything else as §6.4 |
| D17 | `test_a_mis_sampling_receiver_fails_on_the_bytes_and_its_references_do_not_apply` | the recorded 20 MHz output |
| D18 | `test_the_limit_boundaries_are_exact` | the §6.4 stand-in boundaries |
| D19 | `test_each_null_status_of_the_device_limit_blocks_with_its_status_and_path` | three statuses |
| D20 | `test_the_device_limit_passes_only_when_specified_and_real_never_when_ai_assumed` | §6.4 |
| D21 | `test_without_icarus_every_case_is_blocked_and_the_receipt_holds` | 14 `BLOCKED TOOL_NOT_INSTALLED` attributed to `ecad-validator`; REQ-DIG-007 `MISSING_REQUIRED_INPUT` |
| D22 | `test_a_refused_source_gives_a_receipt_and_never_reaches_icarus` | `` `include``, `$fopen`, `defparam` and hierarchical-write copies: V1 `SOURCE_REJECTED`, V2–V4 `DERIVATION_NOT_AVAILABLE`; a stand-in that fails if called |
| D23 | `test_a_simulation_file_edited_without_a_rebuild_is_divergent_and_not_counted` | V2 `DERIVATION_DIVERGED`; every entry `COMMITTED_CASE_STALE` (`dataset.py:1253-1263`); the stand-in records that it *was* run (SEC-2, documented) |
| D24 | `test_an_rtl_copy_edited_without_a_rebuild_is_caught_at_v0_and_v2_and_not_counted` | REUSE-1 at V0; V2 "derived from different bytes" (`dataset.py:855-856`); the cases stale through the derived input |
| D25 | `test_a_copied_source_is_bound_to_its_origin` | REUSE-1, each through `check` and V0: an origin edited (a scratch origin inside `REPO_ROOT`), a copy edited, a missing origin, an origin outside the repository (not read), an origin inside the item, provenance 1.0.0 with `copied_from` (schema) |
| D26 | `test_results_trace_source_to_evidence_and_regenerate_identically` | copy = model source = manifest artefact = `copied_from` = origin digest; the simulation file's digest in every execution's evidence; `regenerate_results` byte-identical |
| D27 | `test_hash_cited_rtl_is_never_converted_on_checkout` | `git check-attr text` is `unset` for `rtl/uart_tx.v`, `rtl/uart_rx.v` and every sample file |
| D28 | `test_the_icarus_requirement_turns_a_skip_into_a_failure` | `require_icarus` with the capability mocked, with and without `ECAD_REQUIRE_HDL_TOOLS` |
| D29 | `test_the_production_adapter_and_the_fixture_share_the_digital_slot` | `REGISTRY["digital"]` is a `DigitalAdapter`; an override yields the fixture; the blinker under the platform registry is `SOURCE_REJECTED` |
| D30 | `test_a_domain_with_no_production_adapter_is_not_implemented` (in `test_domain_adapter.py`) | a `pcb` sample: `build` refuses "pcb is NOT_IMPLEMENTED"; `validate` gives `BLOCKED DOMAIN_NOT_IMPLEMENTED` |

### `tests/unit/test_digital_icarus.py` (needs Icarus; skip with reason, or failure with `ECAD_REQUIRE_HDL_TOOLS=1`)

| # | Test | Asserts |
|---|---|---|
| I1 | `test_icarus_reproduces_the_closed_forms` | the nine §5.3 values; stdout identical over two runs; stderr empty; no stdout token starting with `/` |
| I2 | `test_the_committed_sample_validates_as_designed` | §6.3 with the real tool; the tool version starts with `Icarus Verilog version `; evidence re-hashes |
| I3 | `test_the_fail_copies_give_the_verified_metrics_and_verdicts` | 230 400 Bd, 20 MHz, 40 MHz, rx 57 600 Bd (§6.4) |
| I4 | `test_rtl_defects_fail_their_references` | the §5.4 rows, including the framing gap (all PASS) as a documented limitation |
| I5 | `test_the_limit_boundaries_with_real_icarus` | `tx_frame_cycles` ≤ 4340 WARNING, ≤ 4339 FAIL |
| I6 | `test_the_sampling_condition_is_conservative_at_its_edge` | 121 000 Bd: `REFERENCE_NOT_APPLICABLE` with 2 bytes received; 120 500 Bd: PASS |
| I7 | `test_the_compiler_sees_only_the_scrubbed_environment` | with `IVERILOG_ICONFIG=<scratch>/i.txt` in `os.environ`, no file is created (the behavioural kill of mutant 7) |
| I8 | `test_the_grammar_refuses_what_icarus_would_run` | `` `include``, `$fopen` and `$readmemh` each read or write under raw Icarus in a scratch directory, and each is refused by `parse_source` |
| I9 | `test_the_source_top_alone_compiles_and_measures_nothing` | exit 0; no `ECAD_METRIC` line |

### Which tests need Icarus

Only I1–I9. The V, H, P and D tests run on all nine matrix legs, including
Python 3.10 and `windows-2022`.

### Changes to existing tests (none weakened)

1. **`test_validation_adapters.py:94-122`.** The patch moves from
   `hdl.subprocess.run` to `ecad_validation.adapters.process.subprocess.run`,
   plus `process.shutil.which` returning `"/fake/iverilog"`, since
   `run_process` resolves the executable (`process.py:104`). The three
   assertions (`TIMED_OUT`, `RTL_EXECUTION_TIMED_OUT`, str stdout containing
   "VCD info") are kept verbatim.
2. **`test_domain_adapter.py`:** the registry argument of §8.3, the docstring,
   and D30.
3. **`test_electrical_domain.py:888-891`:** the `digital` pop of §8.2.
4. **`test_engineering_model.py:1216-1217`:** the doctest list.
5. **`test_ci_and_runner.py`:** adds `_job(name)` and
   `test_hdl_job_cannot_skip_silently` (§11.1). The existing cad-dataset test
   (`:56-69`) is untouched and stays exact.
6. **`tests/test_rtl_models.py`:** byte-identical. Verification row:
   `git diff --stat 2ba5fe0 -- tests/test_rtl_models.py` is empty.

---

## 10. Mutants (`tests/mutation/run_mutations.py`)

**Harness changes:**
- **Constants:**
  - `VG` = `tools/ecad_model/verilog.py`; `DG` = `domains/digital.py`;
    `HD` = `adapters/hdl.py`; `PR` = `adapters/process.py`;
  - `AS` = the annotations schema; `PS` = the provenance schema;
  - `DT`, `DA`, `DQ`, `DP` = the sample's top, annotations, requirements and
    provenance;
  - `VERILOG`, `HDLAD`, `DIGITAL`, `ICARUS` = the four new test files.
- **`environment`** (`:582-583`) adds `ECAD_REQUIRE_HDL_TOOLS="1"`.
- **The suites** (`:584`) become
  `(FAST, ADAPTER, NETLIST, NGSPICE, ELECTRICAL, VERILOG, HDLAD, DIGITAL, SPICE, ICARUS, SLOW)`.
- **The module docstring** names Icarus as needed.

**Rules:**
- A dataset mutant must still build: the harness rebuilds it (`:569-579`),
  and a failed rebuild is `HARNESS`, not a kill. Connectivity mutations are
  therefore code mutants or test-built copies.
- A mutant of an RTL copy would be killed by the REUSE-1 hash, not by
  behaviour (the ACC-1 lesson). RTL behaviour is covered by the I4 copies.
- Each anchor must occur exactly once (`:563-565`).

None of these has been run (**NOT RUN**). The killers are the designed ones.

| # | Name | File | Change | Killed by |
|---|---|---|---|---|
| 1 | process-collect-skipped | PR | collect loop removed | H3, P1 |
| 2 | process-collect-follows-symlink | PR | `lstat`/symlink test dropped | P1 |
| 3 | process-collect-unbounded | PR | size check dropped | P1 |
| 4 | process-collect-after-timeout | PR | collection also on `TIMED_OUT` | P2 |
| 5 | process-collect-name-unchecked | PR | plain-file-name check dropped | P3 |
| 6 | process-collect-by-default | PR | `()` collects every new file | P4 |
| 7 | hdl-compile-inherits-environment | HD | compile request gains `environment=dict(__import__("os").environ)` | H1, I7 |
| 8 | hdl-run-inherits-environment | HD | the same on the run request | H1 |
| 9 | hdl-compile-bypasses-run-process | HD | compile via direct `subprocess.run` wrapped in a `ProcessResult` | H1, H2 |
| 10 | hdl-run-bypasses-run-process | HD | the same for vvp | H1, H2 |
| 11 | hdl-program-not-carried | HD | `collect=(PROGRAM,)` → `()` | H3, I1 |
| 12 | hdl-program-missing-passes | HD | `RTL_PROGRAM_MISSING` branch removed | H3 |
| 13 | hdl-arguments-passed | HD | arguments appended to the compile argv | H4 |
| 14 | hdl-truncation-ignored | HD | `endswith(TRUNCATED)` → `False` | H2 |
| 15 | hdl-metrics-parsed-on-failure | HD | parse when exit ≠ 0 | H6 |
| 16 | hdl-undeclared-metrics-read | HD | every `REPORTED` line becomes a metric | H5 |
| 17 | hdl-duplicate-report-kept | HD | the first of two reports kept | H5 |
| 18 | hdl-non-finite-kept | HD | `isfinite` dropped | H5 |
| 19 | hdl-python-number-spellings | HD | `NUMBER` pre-check dropped | H5 (`1_0`) |
| 20 | hdl-declared-twice-read | HD | a twice-declared name read | H5 |
| 21 | hdl-oversize-input-read | HD | size guard dropped | H8 |
| 22 | hdl-reason-unsanitised | HD | `_receipt_reason` returns its input | H10 |
| 23 | hdl-timeout-names-compile-step | HD | the run timeout records the compile argv | H7 |
| 24 | vg-include-accepted | VG | `` `include`` skipped | V3, D22, I8 |
| 25 | vg-timescale-any | VG | the timescale value not compared | V3 |
| 26 | vg-system-task-accepted | VG | `$name` lexed as an identifier | V4, D22, I8 |
| 27 | vg-string-accepted | VG | strings skipped | V6 |
| 28 | vg-attribute-accepted | VG | `(*` skipped | V6 |
| 29 | vg-dpi-import-accepted | VG | `import` removed from the refused words | V5 |
| 30 | vg-initial-in-rtl-accepted | VG | `initial` added to `RTL_KEYWORDS` | V5 |
| 31 | vg-defparam-accepted | VG | `defparam` removed from the refused words | V5, D22 |
| 32 | vg-blocking-assign-accepted | VG | `=` allowed in `always` | V8 |
| 33 | vg-hierarchical-reference-accepted | VG | `.` after a name accepted in bodies | V8, D22 |
| 34 | vg-instance-in-leaf-accepted | VG | leaf instance item allowed | V8 |
| 35 | vg-non-ascii-code-accepted | VG | non-ASCII allowed outside comments | V7 |
| 36 | vg-size-limit-off-by-one | VG | `>` → `>=` | V7 (at the limit) |
| 37 | vg-depth-unbounded | VG | depth check dropped | V8 (`RecursionError`) |
| 38 | vg-range-lsb-ignored | VG | `[7:1]` read as width 8 | V9 |
| 39 | vg-literal-overflow-accepted | VG | sized-literal fit dropped | V9 |
| 40 | vg-top-initialiser-accepted | VG | `reg x = …;` allowed in the top | V10 |
| 41 | vg-width-mismatch-accepted | VG | width check dropped | V11 |
| 42 | vg-two-drivers-accepted | VG | single-driver check dropped | V11 |
| 43 | vg-second-top-accepted | VG | `len(tops) != 1` → `< 1` | V11 |
| 44 | vg-harness-names-allowed | VG | `ecad_` check dropped | V6 |
| 45 | vg-marker-text-allowed | VG | `ECAD_METRIC` check dropped | V6 |
| 46 | dg-rule-c2-unchecked | DG | transmitter signature not compared | D5 |
| 47 | dg-rule-c5-line-unchecked | DG | shared-line check dropped | D5 (rx from `tx_valid`) |
| 48 | dg-rule-c6-inert-localparam | DG | "named by an override" dropped | D5 |
| 49 | dg-resource-guard-off | DG | `> MAX_CYCLES` → `> 10**12` | D7 |
| 50 | dg-clock-consistency-unchecked | DG | V1 rule 3 dropped | D6, I3 (40 MHz) |
| 51 | dg-receiver-ticks-unchecked | DG | V1 rule 4 dropped | D6 |
| 52 | dg-facet-unit-unchecked | DG | V1 rule 1's unit comparison dropped | D6 |
| 53 | dg-frame-bits-nine | DG | `FRAME_BITS = 9` | D10, D15 |
| 54 | dg-bit-period-rounded | DG | `//` → `round(clk / baud)` | D10 (115 000 Bd: 435) |
| 55 | dg-half-period-as-period | DG | `2 * h` → `h` in `clock_period` | D10, D15 |
| 56 | dg-bit-rate-parity-ignored | DG | the odd-first-byte condition of `bit_rate` returns true | D11 |
| 57 | dg-sampling-condition-always | DG | W returns true | D11, D17 |
| 58 | dg-sampling-upper-bound-inclusive | DG | `<` → `<=` | D11 ((107, 7), F5) |
| 59 | dg-sampling-lower-bound-dropped | DG | `b·D_t ≤ …` removed | D11 ((169, 10)) |
| 60 | dg-harness-samples-rising-edge | DG | `negedge` → `posedge` in the measurement block | D8 |
| 61 | dg-end-cycle-hard-coded | DG | END written as `20836` | D8 (3-byte variant) |
| 62 | dg-byte-count-hard-coded | DG | `< {n}` → `< 2` | D8 (3-byte variant) |
| 63 | dg-marker-dropped | DG | the `rx_framing_errors` `$display` removed | D9, D15 (`INCONCLUSIVE`) |
| 64 | dg-rtl-not-verbatim | DG | `hdl.text = text.rstrip() + "\n"` | D3, D8 |
| 65 | dg-top-hash-not-bound | DG | sha dropped from the top's facet sources | D1, D9 |
| 66 | dg-overrides-not-written | DG | the harness instances written without `#(…)` | D8, D9 |
| 67 | digital-unregistered | DR | REGISTRY entry removed | D14, D29 |
| 68 | reuse-origin-unchecked | D | the origin not re-hashed | D25 |
| 69 | reuse-copy-unchecked | D | the copy not compared with the origin digest | D25 |
| 70 | reuse-origin-inside-item-allowed | D | the inside-the-item refusal dropped | D25 |
| 71 | schema-hdl-any-version | MS | the 1.2.0 `allOf` removed | D4 |
| 72 | annotations-digital-any-version | AS | the 1.2.0 rule removed | D4 |
| 73 | provenance-copy-version-rule-dropped | PS | the 1.1.0 rule removed | D4 |
| 74 | item-baud-rate-changed | DT | `115_200` → `230_400` (rebuilt) | D15 (recorded 434 against reference 217), I2 (REQ-DIG-002 FAIL) |
| 75 | item-byte-changed | DT | `8'hCA` → `8'hC5` | D1 (typed bytes), D8 |
| 76 | item-limit-tightened | DQ | REQ-DIG-002 `117504.0` → `115000.0` | D15 (FAIL, expected WARNING) |
| 77 | item-illustrative-cleared | DQ | REQ-DIG-004 `true` → `false` | D15 (PASS, expected WARNING) |
| 78 | item-operator-flipped | DQ | REQ-DIG-001 `>=` → `<=` | D15 |
| 79 | item-device-limit-invented | DA | UNKNOWN/null → SPECIFIED/1e-8 | D2, D15 (WARNING, expected BLOCKED) |
| 80 | item-origin-digest-changed | DP | the `uart_tx.v` `copied_from.sha256` changed | D14 (`check` fails: the binding is what it attacks) |
| 81 | item-artifact-type-changed | DP | `hdl_source` → `other` | D14 |

**Categories of spec §23:**
- requirements: 76–78;
- units: 52, and D12 at compile time;
- component values: 74, 75, 79;
- connectivity: 41, 42, 47, and D5's copies;
- metadata: 65, 71–73, 80, 81;
- simulator outputs: 14–20;
- invalid input: 24–45.

**Acceptance:** zero survivors after a green baseline, each kill naming its
test. The suite needs Icarus, ngspice, OCP and MuJoCo on one machine.

---

## 11. CI job, documentation, commit order

### 11.1 `.github/workflows/ci.yml`

The job goes between `validation-evidence` (`:51-85`) and `cad-dataset`
(`:87`), so the existing slice from `cad-dataset:` to `release:` stays exact
(`test_ci_and_runner.py:59-61`). If the electrical PR's `spice` job lands
first in the same gap, the order does not matter to either slice test. The job
is not added to `release.needs` (`:139`), and neither is `cad-dataset`.

```yaml
  hdl:
    name: Digital dataset (Icarus Verilog) and V0-V4
    runs-on: ubuntu-22.04
    env:
      # The HDL simulation tests skip without Icarus Verilog; here a skip is a failure.
      ECAD_REQUIRE_HDL_TOOLS: "1"
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: tools/requirements.txt

      - name: Install Icarus Verilog
        # A system package, installed rather than assumed; the version every receipt records is printed here.
        run: sudo apt-get update && sudo apt-get install -y iverilog && iverilog -V | head -n 1 && vvp -V | head -n 1

      - name: Install validation dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r tools/requirements.txt pytest

      - name: Complete test suite, HDL simulation tests mandatory
        run: python run_all_tests.py --tb=short

      - name: Committed derivation reproduces from the HDL
        run: python tools/cad_dataset.py check datasets/cad/uart_loopback_001

      - name: V0-V4 receipt
        run: >-
          python tools/cad_dataset.py validate datasets/cad/uart_loopback_001
          --output digital-validation

      - name: Upload digital evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: digital-dataset-${{ github.sha }}
          path: digital-validation/
          if-no-files-found: error
```

- `validate` exits 0 on a completed run whatever the verdicts
  (`datasets/cad/README.md:34`), so the BLOCKED receipt does not fail the
  job.
- In this job the CAD and SPICE tests skip, each with its reason.
- `iverilog -V` and `vvp -V` both exit 0 (**Verified**).

**`test_hdl_job_cannot_skip_silently`** uses `_job("hdl")`: a slice from
`"\n  hdl:\n"` to the next match of `\n  [A-Za-z0-9_-]+:\n`. It asserts:
- `ECAD_REQUIRE_HDL_TOOLS: "1"`;
- `apt-get install -y iverilog`;
- `run: python run_all_tests.py --tb=short`;
- the `check` and `validate` commands for `uart_loopback_001`;
- no `continue-on-error`;
- no `hdl:` inside the `cad-dataset` slice.

### 11.2 `.gitattributes`

Append:

```
# Origins that dataset items copy and bind by hash (REUSE-1).
rtl/uart_tx.v -text
rtl/uart_rx.v -text
```

### 11.3 Documentation

**New `docs/digital-domain-v1.md`**, with the spec §28 headings:

| Heading | Content |
|---|---|
| What the domain is | the UART 8N1 loopback class C1–C7 |
| Supported inputs | the §3.1 grammar, with its accepted and refused tables and the Verified reasons |
| Engineering model | the `hdl` member, format 1.2.0; §2.1 |
| Supported simulators | Icarus via `iverilog -g2012` and `vvp` on one derived file, version from the first line of `-V`; Verilator PLANNED (§7.8); ModelSim/Questa PLANNED, licensed, with no adapter |
| Validation capabilities | compilation, connectivity and interface, clock, reset idle and X, frame timing, bit rate, byte recovery, framing; V1; V2 |
| Known limitations | see the list below |
| Example | `build`, `check`, `validate` with outputs from a real run, run before the document is committed |
| Dataset samples | `uart_loopback_001` |
| Requirements | §6 |
| Expected outputs | §6.3 |
| Evidence | the record's fields; why the compiled program is not evidence |
| Training data | none (plan §15) |
| Future work | this document's PLANNED rows |

Known limitations to state:
- one class and one hierarchy level;
- synchronous posedge RTL only;
- W is conservative;
- framing detection is not exercised (§5.4);
- metric 9 needs a 4-state simulator;
- the `SIMPLIFIED` idealisations;
- no FSM extraction, no timing analysis, no constraints;
- SEC-1, SEC-2, SEC-3 and STATE-2.

**`docs/cad-dataset-engineering-model-v1.md`:**
- the `hdl` member and 1.2.0; annotations 1.2.0; provenance 1.1.0 and
  REUSE-1 in the `check`/V0 lists;
- Security: the HDL refusals;
- Versioning: the new producers and `VALIDATOR_VERSION` 1.1.0;
- Limitations (`:451-454`): three production domains and a stable protocol.
  The electrical half of that correction is still owed by the electrical
  docs commit.

**Other files:**
- `datasets/cad/README.md`: a `uart_loopback_001` row. The
  `robotic_joint_001` row made true ("the other eight `NOT_IMPLEMENTED`" is
  stale since electrical; electrical and digital are now `NOT_APPLICABLE`).
  Icarus in Commands.
- `tools/requirements.txt`, "Not installable from PyPI":
  `sudo apt install iverilog`; `brew install icarus-verilog`.
- `ECAD_MULTI_DOMAIN_DATASET_PLAN.md`:
  - plan:62: ARCH-10 fixed; ARCH-2 fixed for HDL (both halves);
  - REUSE-1 (plan:908-910) fixed;
  - SEC-1 partly for HDL; SEC-2 open; SEC-3 new;
  - §8.2: the HDL amendment of ARCH-1 (§2.5);
  - §10 row 3, §11, §11.1 (Verilator evidence), §16/§17 counts, §20 Q9
    evidence, §21 item 5 markers;
  - the note that electrical's rows are still stale.
- `MEMORY.md`:
  - decisions D1, D2, D3, D7, D8, D10, D11, D15, each with its rejected
    options;
  - traps:
    - options after the files (macOS reads them as files; Linux parses them,
      so `-N` writes and `-m` loads);
    - `$stop` on an open stdin;
    - `` `include``/`$fopen`/`$readmemh` reach absolute paths;
    - `wire f = $fopen(…)` compiles to `.sfunc`;
    - Icarus 13 prints `$finish called at`, and 11 does not;
    - `%.17g` prints 5e-08 as `4.9999999999999998e-08`;
    - Verilator 4.038 lacks `--binary`/`--timing`;
    - Verilator's report lines carry wall time;
    - `0xA5` is a bit palindrome;
    - `mock.patch.object(hdl.subprocess, "run")` patches every module's
      `subprocess.run`.
- `TASKS.md`: T-013, carrying plan §21 item 5 and §10's per-domain list
  verbatim, every verification row `NOT RUN`. T-012 (electrical) is also
  missing today.
- `CHANGELOG.md`: an entry.

### 11.4 Commit order

All commits are local, authored by `kartikey1306`, with no AI attribution
(the user's rule overrides the harness reminder). Nothing is pushed.

1. `fix(process): copy declared outputs out before the workspace is deleted`:
   ARCH-2's output half. P1–P4; mutants 1–6.
2. `fix(hdl): run both Icarus steps through run_process and read declared metric markers`:
   ARCH-10, ARCH-2's metric half, argument refusal and RESULT-2 on this path.
   H1–H12, the `test_validation_adapters.py` mock move; mutants 7–23.
3. `feat(provenance): copied artefacts are bound to their origin by hash`:
   REUSE-1, the provenance schema, `cited_source_problems`,
   `VALIDATOR_VERSION`, `.gitattributes`. A fixture-based D25; mutants 68–70
   and 73.
4. `feat(verilog): a strict Verilog grammar for the digital domain`: V1–V13;
   mutants 24–45.
5. `feat(digital): the UART loopback as the third production domain`: the
   model and annotation schemas, the vocabulary, `domains/digital.py`, the
   registry, the sample, the two regenerated manifest entries, the §9 test
   edits, the D and I tests; mutants 46–67, 71, 72 and 74–81.
6. `ci: the hdl job` and its test.
7. `docs: the digital domain` (§11.3).

---

## 12. Status after this PR, if its verification passes

Every row is a target. The repository suite, the mutation run and CI are
**NOT RUN**.

| Deliverable | Label | Evidence required, or reason |
|---|---|---|
| Sample `uart_loopback_001` (copied RTL + declarative top) | IMPLEMENTED | D14, D15, I2; the simulation file Verified in scratch |
| Restricted Verilog grammar and refusals | IMPLEMENTED | V1–V13, I8; mutants 24–45; top-form prototype Verified, full grammar written at implementation |
| Model `hdl` member, 1.2.0; annotations 1.2.0; provenance 1.1.0 | IMPLEMENTED | D4; mutants 71–73 |
| REUSE-1 | IMPLEMENTED | D25, D26; mutants 68–70, 80 |
| Class rules C1–C7, V1, V2 | IMPLEMENTED for the UART 8N1 loopback only | D5–D9 |
| 9 metrics (SIMPLIFIED), 8 closed forms with W | IMPLEMENTED for that class only | §5.3 Verified on Icarus 13 (macOS), 11 (arm64) and Verilator 5.052; x86_64 NOT RUN |
| V4: 6 WARNING, 1 BLOCKED; FAIL, boundary, null, AI and PASS copies | IMPLEMENTED | D15–D20, I3–I6 |
| Invalid and boundary samples | PARTIAL | test-built copies, not committed items (spec §21) |
| HDL compilation of the committed RTL | IMPLEMENTED | the first step of every case (H9, I1) |
| Connectivity and interface compatibility | PARTIAL | the class's fixed interface only |
| Clock and reset behaviour | PARTIAL | clock period and CLK_FREQ consistency, idle and X after reset; no reset in operation, no clock-domain crossing |
| Protocol behaviour | PARTIAL | frames, bit rate, byte recovery; framing detection not exercised (Verified gap) |
| FSM behaviour, internal signals, SDC/XDC/PCF, board and pin metadata | PLANNED | no extraction; refused inputs |
| Timing against a real device | BLOCKED | data: no target device is selected (REQ-DIG-007) |
| SystemVerilog, VHDL, deeper hierarchy, negedge/async reset, `assign`, `spi_master.v` (`$clog2`) | PLANNED | refused today |
| ARCH-10 | IMPLEMENTED | H1, H2, I7; mutants 7–10 |
| ARCH-2, `run_process` output copy | IMPLEMENTED | H3, P1–P4; mutants 1–6, 11 |
| ARCH-2, iverilog metric parser | IMPLEMENTED | H5–H8; mutants 14–21 |
| ARCH-2, kicad parser | PLANNED | the PCB PR |
| Case arguments refused on the iverilog path | IMPLEMENTED | H4; mutant 13 |
| RESULT-2 | PARTIAL | ngspice and iverilog paths only (H10); the general branch is not written |
| `DomainAdapter` protocol | unchanged | §8.1; mechanical and electrical untouched |
| SEC-1 for HDL | PARTIAL | the grammar closes the Verified file, shell and native-code constructs in sources; the arguments are refused; `run_process` is no sandbox |
| SEC-2 (committed documents run before reconciliation) | open (existing) | its own PR |
| SEC-3 (program screen, `vvp -N`, stdin) | PLANNED | §13.1 |
| STATE-2 | open (existing) | absolute vvp path in execution records |
| Verilator adapter; two simulators in one receipt | PLANNED | Q9; CI Verilator ≥ 5 (§7.8) |
| ModelSim/Questa | PLANNED | licensed; no adapter, no stub |
| CI `hdl` job | PARTIAL | written and slice-tested; execution NOT RUN (read-only push, local only) |
| Icarus pinned in CI | BLOCKED | apt 11.0-1.1 (Verified on arm64); no pin chosen |
| Linux x86_64 reproduction | PLANNED | only arm64 containers were run |
| Documentation (spec §28) | IMPLEMENTED | examples run before the claim |
| Mutation run, zero survivors (existing + 81 new) | NOT RUN | needs Icarus, ngspice, OCP and MuJoCo together |
| Training records | PLANNED | plan §15 |
| Dataset move (Q8) | BLOCKED | maintainer decision |
| Independent review | NOT RUN | `CLAUDE.md` rule 4 |

---

## 13. Risks and open questions

### 13.1 Risks

1. **SEC-2 plus the residual SEC-1 (SEC-3).**
   - The runner executes a committed case document before it decides the
     document is stale (`dataset.py:1267`, filtered at `1277`). A hand-edited
     committed `derived/digital/*.v` therefore runs before V2 calls it
     divergent (D23 records this).
   - That file can contain `$fopen`, `$readmemh` or `$system`, which the
     grammar refuses only in sources. `$system` is not runnable without a VPI
     module, but the file-access tasks work (**Verified**).
   - With arguments refused, a forged case can no longer load VPI modules or
     write through `-N`.
   - **Proposed SEC-3, for its own PR:** a post-compile screen of the program
     (every quoted `$name`, since `.sfunc` hides calls from a
     `%vpi_call`-only screen, **Verified**, and every `:vpi_module` basename),
     plus `vvp -N` (`$stop` then exits 1 instead of reading stdin,
     **Verified**).
   - Until then, plan R5's rule holds: validate only reviewed repository
     content.
2. **The class is one RTL pair.** The closed forms assume this contract: the
   divider formulas, and mid-bit sampling at SP + OS·b ticks. A receiver with a
   different schedule inside the same interface could meet W and misread; V3
   would then FAIL visibly, never PASS falsely.
3. **Stdout differs between Icarus versions.** Icarus 13 prints
   `$finish called at …` and 11 does not (**Verified**). Only marker lines are
   read, so the metrics are identical, but whole-stdout comparisons across
   hosts would differ.
4. **Version drift.**
   - x86_64 apt Icarus is **Inferred** to be 11.0-1.1 too, and its metrics
     **Inferred** identical (deterministic logic).
   - vvp's version is not checked against iverilog's.
   - An unrecognised probe is `BLOCKED TOOL_VERSION_UNAVAILABLE`, loudly.
5. **The compile step's output on success is dropped**, as today. A warning
   from a future Icarus would not reach the record (the committed file's is
   empty, **Verified**).
6. **Model size:** about 7.5 KB of RTL text in the engineering model (D1).
7. **REUSE-1 cost.** Any fix to `rtl/uart_*.v` fails `check` for the sample
   until it is re-copied, re-hashed and rebuilt. This is intended;
   `tests/test_rtl_models.py` does not read those files.
8. **Two committed manifests change in one entry each.** No derived number
   changes.
9. **Awkward names:**
   - `cad_components` lists HDL instances;
   - `datasets/cad/` and `tools/cad_dataset.py` hold an HDL sample;
   - `v0.pinned-clean-source` records `tools/constraints-cad.txt`
     (`dataset.py:1123`), which says nothing about Icarus.
10. **The electrical PR's missing commits** (`spice` job, docs, README row,
    T-012) at `2ba5fe0`: this PR's documentation must not claim them.

### 13.2 Open questions (maintainer)

| # | Question |
|---|---|
| Q9 | Amend `validation-cases.schema.json:48` for `verilator`, or check an open adapter id against the registry? And pin a Verilator ≥ 5 for CI (source build or image)? |
| Q8 | The layout stays `datasets/cad/` (the brief), against plan §21's move rule. |
| Q-D1 | Accept HDL text inside the engineering model (§2.5) as the HDL amendment of ARCH-1? |
| Q-D2 | Accept refusing case arguments on the iverilog path (D8) under ARCH-2, as ngspice dropped them, or keep today's pass-through until a SEC-3 PR? |
| Q-D3 | Should `HDLAdapter.capability()` require `vvp -V` to name the same version as `iverilog -V`? |
| Q-D4 | Add a fidelity value for exact-at-the-RTL simulation (`base.py:29` and the results schema)? `SIMPLIFIED` until then. |
| Q-D5 | Restate `copied_from` in `dataset-item.json`? |
| Q-D6 | Change the §9.3 rule to "that version or later", so one document can carry `circuit` and `hdl`? |
| Q-D7 | Add a framing-fault scenario so the receiver's stop-bit check is exercised? |
| Q-D8 | Are "EmbeddedOS Foundation" (the RTL headers) and "EmbeddedOS (EoS) Research Foundation" (`LICENSE`) the same licensor? |
| SEC-2/3 | Land the runner guard and the program screen before `validate` runs on anything unreviewed? |
| RESULT-2 | Its order against `fix/version-probe-reason-codes`, now that two adapters carry the shim. |
| Q4 | Every limit is illustrative; real requirements and a real device need a product owner. |

---

**Report (VERIFY.md format)**

- **Status:** design complete; nothing implemented.
- **Mode:** Architecture.
- **Files changed in the base clone:** none (`git status --short` empty at
  `2ba5fe0`).
- **Written:** this design, and scratch evidence under
  `design-scratch-digital/judge/`.

| Check | Result |
|---|---|
| Input designs' files and hashes; their harnesses on Icarus 13, Icarus 11 (arm64) and Verilator 5.052 | PASS (Verified) |
| Final simulation file: compile, run, determinism; Icarus 11 = 13 on 13 files; Verilator 5.052 agreement | PASS (Verified) |
| Closed forms against 8 variants | PASS (Verified, 0 mismatches) |
| RTL defect copies, the palindrome counter-example, the framing gap | PASS (Verified) |
| Two-step flow with `collect` through a copy of `run_process`; scrubbed environment; today's adapter returns no metrics | PASS (Verified) |
| Icarus probes (file access, `$system`, `.sfunc`, `$fatal`, DPI, `defparam`, hierarchical write, `$stop`, `IVERILOG_ICONFIG`, option order on macOS and Linux) | PASS (Verified) |
| Verilator 4.038 refusals | PASS (Verified) |
| Top-form grammar prototype: acceptance and 12 refusals | PASS (Verified, scratch only) |
| Affected existing tests at baseline (`test_validation_adapters.py`, `test_ci_and_runner.py`, the registry-dependent fixture test) | PASS: 15 passed |
| Repository suite with the change, mutation run, CI, Linux x86_64 | NOT RUN |

**Assumptions:**
- the ubuntu-22.04 amd64 runner installs the same apt Icarus 11.0-1.1 as the
  arm64 container;
- the provenance dates are written on the day of authoring.

**Next step:** an independent review of D1 (text in the model), D2
(declarative top), D8 (argument refusal) and D10 (REUSE-1). Then the commits
of §11.4, in order.
