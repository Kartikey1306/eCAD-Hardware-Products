"""The digital domain against real Icarus Verilog: datasets/cad/uart_loopback_001.

These run Icarus Verilog, installed as a system package (brew install
icarus-verilog, apt install iverilog), and need `iverilog -V` to name it on
its first line and vvp beside it. Without it the tests skip and say why. With
ECAD_REQUIRE_HDL_TOOLS=1 -- set by the CI job that installs Icarus -- a
missing or unidentified Icarus is a failure instead, so the skip can never go
silent where it matters.

Expected values are typed by hand from the sources and the closed forms of
the design (§5.3, §6.4), and, for the copies whose metrics no closed form
predicts, from Icarus Verilog 13.0's own output on macOS arm64, 2026-09-27
(design-digital.md §5.4 and §6.4) and, for the harness as the review's CS-1
change writes it, 2026-09-29, never obtained by calling the code under test.
A metric expected as None is one the harness does not print. Every sample
copy is a fixture in a scratch directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

ITEM = REPO_ROOT / "datasets" / "cad" / "uart_loopback_001"
TB, TX, RX = "source/tb_uart_loopback.v", "source/uart_tx.v", "source/uart_rx.v"
SIM = "derived/digital/uart_loopback_001.v"
BANNER = re.compile(r"^Icarus Verilog version \d+\.\d+")
# The closed forms of §5.3; Icarus 13.0 printed exactly these (and 11.0 the same lines).
CLOSED_FORMS = {"clock_period_s": 2e-08, "tx_idle_after_reset": 1.0, "tx_bit_cycles": 434.0,
                "tx_bit_rate_bd": 115207.3732718894, "tx_frame_cycles": 4340.0, "rx_bytes_received": 2.0,
                "rx_bit_errors": 0.0, "rx_framing_errors": 0.0, "outputs_unknown_after_reset": 0.0}
V3_PASSED = {f"v3.REF-DIG-00{n}": ("PASS", "GOLDEN_COMPARISON_PASSED") for n in range(1, 9)}
V4_COMMITTED = {**{f"v4.REQ-DIG-00{n}": ("WARNING", "WITHIN_ILLUSTRATIVE_LIMIT") for n in range(1, 7)},
                "v4.REQ-DIG-007": ("BLOCKED", "MISSING_REQUIRED_INPUT")}
NOT_APPLICABLE = ("BLOCKED", "REFERENCE_NOT_APPLICABLE")
GOLDEN_FAILED = ("FAIL", "GOLDEN_COMPARISON_FAILED")
CORNER_FAILED = ("FAIL", "CORNER_LIMITS_FAILED")
GOLDEN_INCONCLUSIVE = ("INCONCLUSIVE", "GOLDEN_METRICS_INCONCLUSIVE")
CORNER_INCONCLUSIVE = ("INCONCLUSIVE", "CORNER_METRICS_INCONCLUSIVE")


def require_icarus() -> Any:
    """The installed Icarus Verilog's capability, if it is available and its version names it.

    Otherwise the test is skipped with the reason, or fails when
    ECAD_REQUIRE_HDL_TOOLS=1, so an environment that must run these tests
    cannot pass by skipping them.
    """
    from ecad_validation.adapters.hdl import HDLAdapter

    capability = HDLAdapter().capability()
    if capability.available and capability.version and BANNER.match(capability.version):
        return capability
    message = ("needs Icarus Verilog whose `iverilog -V` first line names it, and vvp (brew install icarus-verilog; "
               f"apt install iverilog): available={capability.available}, version={capability.version!r}, "
               f"reason={capability.reason!r}")
    if os.environ.get("ECAD_REQUIRE_HDL_TOOLS") == "1":
        raise AssertionError(f"ECAD_REQUIRE_HDL_TOOLS=1 but {message}")
    raise unittest.SkipTest(message)


def _helpers() -> Any:
    from tests.unit import test_digital_domain

    return test_digital_domain


def _validate(item: Path) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """(receipt, its checks by id, results) of a validation with the real Icarus adapter."""
    from ecad_model.dataset import validate

    with tempfile.TemporaryDirectory() as output:
        run = Path(output) / "run"
        receipt = validate(item, run)
        results = json.loads((run / "results.json").read_bytes())
    return receipt, _helpers()._checks(receipt), results


def _outcomes(checks: Dict[str, Dict[str, Any]], prefix: str) -> Dict[str, Tuple[str, str]]:
    return _helpers()._outcomes(checks, prefix)


def _run(directory: Path, *argv: str) -> subprocess.CompletedProcess:
    """Raw Icarus in a scratch directory, stdin empty: a $stop would otherwise wait on it."""
    return subprocess.run(list(argv), cwd=directory, capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)


class TestRealIcarus(unittest.TestCase):
    def setUp(self):
        self.capability = require_icarus()

    def test_icarus_reproduces_the_closed_forms(self):
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.hdl import HDLAdapter

        runs = [HDLAdapter().run(AdapterRequest(case_id=f"run{n}", product_root=ITEM, input_files=[ITEM / SIM],
                                                timeout_seconds=60)) for n in (1, 2)]
        for result in runs:
            with self.subTest(result.summary):
                self.assertEqual((result.verdict.value, result.reason_code), ("PASS", "RTL_TESTBENCH_PASSED"))
                self.assertEqual(result.metrics, CLOSED_FORMS)
                self.assertEqual(result.summary, "committed RTL testbench executed: 9 of 9 declared metrics read")
                self.assertEqual(result.stderr, "")
                self.assertEqual([token for token in result.stdout.split() if token.startswith("/")], [],
                                 "no host path in the hash-bound stdout")
                self.assertEqual(result.tool_version, self.capability.version)
        self.assertEqual(runs[0].stdout, runs[1].stdout, "stdout is identical run to run")

    def test_the_committed_sample_validates_as_designed(self):
        from ecad_validation.contract import validate_document

        from ecad_model.dataset import regenerate_results, validate
        from ecad_model.schemas import validate as validate_schema

        with tempfile.TemporaryDirectory() as output:
            run = Path(output) / "run"
            receipt = validate(ITEM, run)
            written = (run / "results.json").read_bytes()
            evidence = [(e["sha256"], hashlib.sha256((run / "evidence" / "sha256" / e["sha256"]).read_bytes()).hexdigest())
                        for g in receipt["gates"] for c in g["checks"] for e in c["evidence"]]
            regenerated = regenerate_results(ITEM, run)
        validate_document(REPO_ROOT, "validation-receipt.schema.json", receipt)
        results = json.loads(written)
        validate_schema(results, "engineering-model/v1/validation-results")
        checks = _helpers()._checks(receipt)
        # v0.pinned-clean-source depends on the checkout, not the sample.
        for check_id in ("v0.dataset-schemas-and-hashes", "v0.dataset-input-immutability",
                         "v1.digital.extraction-and-sanity", "v2.dataset-reproduction", "v2.digital.model-invariants"):
            with self.subTest(check_id):
                self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
        gates = {g["gate"]: g["verdict"] for g in receipt["gates"]}
        self.assertEqual((gates["V1"], gates["V2"], gates["V3"], gates["V4"]), ("PASS", "PASS", "PASS", "BLOCKED"))
        self.assertEqual(_outcomes(checks, "v3."), V3_PASSED)
        self.assertEqual(_outcomes(checks, "v4."), V4_COMMITTED)
        for check_id in (*V3_PASSED, *(f"v4.REQ-DIG-00{n}" for n in range(1, 7))):
            self.assertEqual(checks[check_id]["metrics"], CLOSED_FORMS, check_id)
        self.assertEqual((receipt["overall_verdict"], receipt["eligible_for_ebuild"]), ("BLOCKED", False))
        self.assertEqual(len(results["results"]), 15)
        [tool] = [t for t in receipt["tools"] if t["tool_id"] == "iverilog"]
        self.assertTrue(tool["version"].startswith("Icarus Verilog version "), tool["version"])
        self.assertEqual(tool["version"], self.capability.version)
        for row in results["results"]:
            with self.subTest(row["check_id"]):
                self.assertEqual(row["model_fidelity"], "SIMPLIFIED")
                if row["status"] != "BLOCKED":
                    self.assertEqual((row["simulator"], row["simulator_version"]), ("iverilog", self.capability.version))
        for recorded, actual in evidence:
            self.assertEqual(actual, recorded)
        self.assertEqual(regenerated, written, "regenerate_results rebuilds the bytes the run wrote")

    def test_the_fail_copies_give_the_verified_metrics_and_verdicts(self):
        helpers = _helpers()
        told = "Hz is not the frequency of its clock (half period 1e-08 s, 50000000 Hz)"
        copies = {
            # V1-V3 PASS (W holds at D_r = 13); REQ-DIG-002 FAILs on the design, not the simulator.
            "230400 Bd": ({TB: ("BAUD_RATE          = 115_200;", "BAUD_RATE          = 230_400;")},
                          {"tx_bit_cycles": 217.0, "tx_bit_rate_bd": 230414.74654377881, "tx_frame_cycles": 2170.0},
                          [], V3_PASSED, {**V4_COMMITTED, "v4.REQ-DIG-002": CORNER_FAILED}),
            # 20 MHz: W fails at D_r = 10 and the receiver misreads.
            "20 MHz": ({TB: [("CLK_HALF_PERIOD_NS = 10;", "CLK_HALF_PERIOD_NS = 25;"),
                             ("CLK_FREQ           = 50_000_000;", "CLK_FREQ           = 20_000_000;")]},
                       {"clock_period_s": 4.9999999999999998e-08, "tx_bit_cycles": 173.0,
                        "tx_bit_rate_bd": 115606.93641618497, "tx_frame_cycles": 1730.0, "rx_bytes_received": 1.0,
                        "rx_bit_errors": 15.0, "rx_framing_errors": 1.0},
                       [], {**V3_PASSED, **{f"v3.REF-DIG-00{n}": NOT_APPLICABLE for n in (6, 7, 8)}},
                       {**V4_COMMITTED, **{f"v4.REQ-DIG-00{n}": CORNER_FAILED for n in (3, 4, 5)}}),
            # The instances are told 40 MHz, the harness drives 50 MHz: V1's clock rule.
            "40 MHz told, 50 MHz driven": (
                {TB: ("CLK_FREQ           = 50_000_000;", "CLK_FREQ           = 40_000_000;")},
                {"tx_bit_cycles": 347.0, "tx_bit_rate_bd": 144092.21902017292, "tx_frame_cycles": 3470.0},
                [f"u_tx CLK_FREQ 40000000 {told}", f"u_rx CLK_FREQ 40000000 {told}"], V3_PASSED,
                {**V4_COMMITTED, "v4.REQ-DIG-002": CORNER_FAILED}),
            # The receiver alone at 57 600 Bd: W fails at D_r = 54. One byte of two arrives with 4 bits wrong, and
            # the missing one's 8 count too; with a byte missing and no framing error, no framing count is printed.
            "receiver at 57600 Bd": (
                {TB: ("uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_rx",
                      "uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(57_600)) u_rx")},
                {"rx_bytes_received": 1.0, "rx_bit_errors": 12.0, "rx_framing_errors": None},
                [], {**V3_PASSED, **{f"v3.REF-DIG-00{n}": NOT_APPLICABLE for n in (6, 7, 8)}},
                {**V4_COMMITTED, **{f"v4.REQ-DIG-00{n}": CORNER_FAILED for n in (3, 4)},
                 "v4.REQ-DIG-005": CORNER_INCONCLUSIVE}),
        }
        for label, (edits, metrics, sanity, v3, v4) in copies.items():
            with self.subTest(label), helpers._scratch() as directory:
                item = helpers._copy(directory, edits)
                _, checks, _ = _validate(item)
                v1 = checks["v1.digital.extraction-and-sanity"]
                self.assertEqual((v1["verdict"], v1["findings"]),
                                 ("FAIL", sanity) if sanity else ("PASS", []))
                self.assertEqual(_outcomes(checks, "v3."), v3)
                self.assertEqual(_outcomes(checks, "v4."), v4)
                measured = checks["v3.REF-DIG-001"]["metrics"]
                self.assertEqual({metric: measured.get(metric) for metric in metrics}, metrics)

    def test_rtl_defects_fail_their_references(self):
        """The §5.4 copies: an RTL defect changes the metrics a reference or requirement checks. The last row
        is a documented limitation: the loopback always delivers a good stop bit, so removing the receiver's
        framing check changes nothing."""
        helpers = _helpers()
        passed = {**V3_PASSED, **V4_COMMITTED}
        defects: Dict[str, Tuple[Any, List[str], Dict[str, Optional[float]], Dict[str, Tuple[str, str]]]] = {
            "the receiver's bit order reversed": (
                {RX: ("shift_reg[bit_idx] <= rx_sync;", "shift_reg[7 - bit_idx] <= rx_sync;")}, [RX],
                {"rx_bit_errors": 8.0}, {**passed, "v3.REF-DIG-007": GOLDEN_FAILED, "v4.REQ-DIG-004": CORNER_FAILED}),
            # 0xA5 reads the same in either bit order, so one such byte hides the reversal above: the reason the
            # sample sends 0x35 and 0xCA (design D6). A documented limitation of that stimulus, not of the checks.
            "the receiver's bit order reversed, one palindrome byte (not detected)": (
                {TB: ("    localparam [7:0] TX_BYTE_0    = 8'h35;\n    localparam [7:0] TX_BYTE_1    = 8'hCA;\n",
                      "    localparam [7:0] TX_BYTE_0    = 8'hA5;\n"),
                 RX: ("shift_reg[bit_idx] <= rx_sync;", "shift_reg[7 - bit_idx] <= rx_sync;")}, [RX],
                {"rx_bytes_received": 1.0, "rx_bit_errors": 0.0, "tx_bit_cycles": 434.0}, passed),
            # Review CS-1: a receiver that delivers no byte. Before, the harness counted bit errors only in bytes
            # that arrived and printed 0 framing errors, so REF-DIG-007/008 and REQ-DIG-004/005 passed.
            "the receiver never sets rx_valid": (
                {RX: ("                                rx_valid <= 1;", "                                rx_valid <= 0;")},
                [RX], {"rx_bytes_received": 0.0, "rx_bit_errors": 16.0, "rx_framing_errors": None},
                {**passed, "v3.REF-DIG-006": GOLDEN_FAILED, "v3.REF-DIG-007": GOLDEN_FAILED,
                 "v3.REF-DIG-008": GOLDEN_INCONCLUSIVE, "v4.REQ-DIG-003": CORNER_FAILED,
                 "v4.REQ-DIG-004": CORNER_FAILED, "v4.REQ-DIG-005": CORNER_INCONCLUSIVE}),
            "the transmitter's divider off by one": (
                {TX: [("if (baud_cnt == BAUD_DIV - 1) begin\n                        baud_cnt <= 0;\n"
                       "                        bit_idx  <= 0;",
                       "if (baud_cnt == BAUD_DIV) begin\n                        baud_cnt <= 0;\n"
                       "                        bit_idx  <= 0;"),
                      ("if (baud_cnt == BAUD_DIV - 1) begin\n                        baud_cnt <= 0;\n"
                       "                        if (bit_idx == 7)",
                       "if (baud_cnt == BAUD_DIV) begin\n                        baud_cnt <= 0;\n"
                       "                        if (bit_idx == 7)"),
                      ("if (baud_cnt == BAUD_DIV - 1) begin\n                        baud_cnt <= 0;\n"
                       "                        state    <= IDLE;",
                       "if (baud_cnt == BAUD_DIV) begin\n                        baud_cnt <= 0;\n"
                       "                        state    <= IDLE;")]}, [TX],
                {"tx_bit_cycles": 435.0, "tx_bit_rate_bd": 114942.52873563218, "tx_frame_cycles": 4350.0},
                {**passed, **{f"v3.REF-DIG-00{n}": GOLDEN_FAILED for n in (3, 4, 5)}}),
            "the transmitter's line not reset": (
                {TX: ("tx       <= 1'b1;   // Idle line is high", "tx       <= tx;")}, [TX],
                {"tx_idle_after_reset": 0.0, "outputs_unknown_after_reset": 1.0},
                {**passed, "v3.REF-DIG-002": GOLDEN_FAILED, "v4.REQ-DIG-006": CORNER_FAILED}),
            "the receiver's stop-bit check removed (not detected)": (
                {RX: ("                            if (rx_sync) begin\n                                // Valid stop bit",
                      "                            if (1'b1) begin\n                                // Valid stop bit")},
                [RX], dict(CLOSED_FORMS), passed),
        }
        for label, (edits, uncopied, metrics, outcomes) in defects.items():
            with self.subTest(label), helpers._scratch() as directory:
                item = helpers._copy(directory, edits, uncopied=uncopied)
                _, checks, _ = _validate(item)
                for check_id in ("v1.digital.extraction-and-sanity", "v2.digital.model-invariants"):
                    self.assertEqual(checks[check_id]["verdict"], "PASS", checks[check_id]["findings"])
                self.assertEqual({**_outcomes(checks, "v3."), **_outcomes(checks, "v4.")}, outcomes)
                measured = checks["v3.REF-DIG-001"]["metrics"]
                self.assertEqual({metric: measured.get(metric) for metric in metrics}, metrics)

    def test_the_limit_boundaries_with_real_icarus(self):
        helpers = _helpers()
        with helpers._scratch() as directory:
            item = helpers._copy(directory, rebuild=False)
            helpers._add_requirements(
                item,
                helpers._requirement("REQ-DIG-101", "u_tx", "tx_frame_cycles", "<=", 4340, "cycles"),
                helpers._requirement("REQ-DIG-102", "u_tx", "tx_frame_cycles", "<=", 4339, "cycles"))
            _, checks, _ = _validate(item)
        self.assertEqual((checks["v4.REQ-DIG-101"]["verdict"], checks["v4.REQ-DIG-102"]["verdict"]), ("WARNING", "FAIL"))
        self.assertEqual(checks["v4.REQ-DIG-102"]["metrics"]["tx_frame_cycles"], 4340.0)

    def test_the_sampling_condition_is_conservative_at_its_edge(self):
        """The transmitter at 121 000 Bd gives D_t = 413, W's equality point with D_r = 27: both bytes still
        arrive, but W does not promise it, so the receiver's references do not apply. At 120 500 Bd (414) they do."""
        helpers = _helpers()
        for baud, bit_cycles, outcomes in (
            ("121_000", 413.0, {**V3_PASSED, **{f"v3.REF-DIG-00{n}": NOT_APPLICABLE for n in (6, 7, 8)}}),
            ("120_500", 414.0, V3_PASSED),
        ):
            with self.subTest(baud), helpers._scratch() as directory:
                item = helpers._copy(directory, {TB: ("uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_tx",
                                                      f"uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE({baud})) u_tx")})
                _, checks, _ = _validate(item)
                self.assertEqual(_outcomes(checks, "v3."), outcomes)
                measured = checks["v3.REF-DIG-001"]["metrics"]
                self.assertEqual((measured["tx_bit_cycles"], measured["rx_bytes_received"], measured["rx_bit_errors"],
                                  measured["rx_framing_errors"]), (bit_cycles, 2.0, 0.0, 0.0))

    def test_the_compiler_sees_only_the_scrubbed_environment(self):
        """IVERILOG_ICONFIG names a file iverilog writes its configuration to, when it compiles and when it only
        reports its version. The version probe and both steps run through run_process (review CS-6: the probe
        used to run with the caller's environment and wrote the file)."""
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.hdl import HDLAdapter

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "i.txt"
            with mock.patch.dict(os.environ, {"IVERILOG_ICONFIG": str(config)}):
                capability = HDLAdapter().capability()
                self.assertFalse(config.exists(), "the version probe saw IVERILOG_ICONFIG")
                result = HDLAdapter().run(AdapterRequest(case_id="env", product_root=ITEM, input_files=[ITEM / SIM],
                                                         timeout_seconds=60))
            self.assertEqual(capability, self.capability)
            self.assertEqual((result.verdict.value, result.metrics), ("PASS", CLOSED_FORMS))
            self.assertFalse(config.exists(), "the version probe or the compile step saw IVERILOG_ICONFIG")
            # `iverilog -V` with the caller's environment does write it: the probe's check can fail.
            done = subprocess.run([self.capability.executable or "iverilog", "-V"], cwd=directory,
                                  env={**os.environ, "IVERILOG_ICONFIG": str(config)}, capture_output=True, text=True,
                                  timeout=120, stdin=subprocess.DEVNULL)
            self.assertTrue(config.exists(), done.stderr)
            config.unlink()
            # The same compile with the caller's environment does write it: the check can fail.
            (Path(directory) / "sim.v").write_bytes((ITEM / SIM).read_bytes())
            done = subprocess.run([self.capability.executable or "iverilog", "-g2012", "-o", "sim.vvp", "sim.v"],
                                  cwd=directory, env={**os.environ, "IVERILOG_ICONFIG": str(config)},
                                  capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(config.exists())

    def test_the_grammar_refuses_what_icarus_would_run(self):
        """Each construct reads or writes a file under raw Icarus, and parse_source refuses it first."""
        from ecad_model import verilog

        # Each construct is the file's first token outside the grammar: the lexer reads the whole
        # file before any statement is parsed, so the refusal names it, not a later `initial`.
        timescale = "`timescale 1ns / 1ps\n"
        with tempfile.TemporaryDirectory() as directory:
            here = Path(directory)
            (here / "outside.vh").write_text('initial $display("read from outside.vh");\n')
            (here / "data.hex").write_text("5a\n")
            probes = {
                "`include": (timescale + 'module m;\n`include "outside.vh"\nendmodule\n',
                             lambda run: "read from outside.vh" in run.stdout, "x.v:3: `include: reads another file"),
                "$fopen": (timescale + 'module m;\nreg [31:0] f;\nalways #1 f = $fopen("wrote.txt");\n'
                           "initial #3 $finish;\nendmodule\n", lambda run: (here / "wrote.txt").exists(),
                           "x.v:4: $fopen: opens, reads or writes files"),
                "$readmemh": (timescale + 'module m;\nreg [7:0] mem [0:0];\nalways #1 $readmemh("data.hex", mem);\n'
                              'always #2 $display("read %h", mem[0]);\ninitial #3 $finish;\nendmodule\n',
                              lambda run: "read 5a" in run.stdout, "x.v:4: $readmemh: opens, reads or writes files"),
            }
            for label, (source, reached, refusal) in probes.items():
                with self.subTest(label):
                    (here / "x.v").write_text(source)
                    compiled = _run(here, self.capability.executable or "iverilog", "-g2012", "-o", "x.vvp", "x.v")
                    run = _run(here, "vvp", "x.vvp") if compiled.returncode == 0 else compiled
                    self.assertTrue(reached(run), f"{label} did not reach its file: {run.stdout!r} {run.stderr!r}")
                    with self.assertRaises(verilog.HdlRefused) as caught:
                        verilog.parse_source(source.encode(), "x.v")
                    self.assertTrue(str(caught.exception).startswith(refusal), str(caught.exception))

    def test_the_grammar_refuses_what_icarus_cannot_compile_and_keeps_what_it_can(self):
        """Names Icarus reserves under -g2012 and a unary operator applied to another: Icarus refuses each as a
        syntax error, and so does the grammar; the parenthesised forms compile under both."""
        from ecad_model import verilog

        leaf = ("`timescale 1ns / 1ps\nmodule m #(parameter P = 1) (input wire clk, output reg [7:0] y);\n"
                "{body}\nendmodule\n")
        probes = {
            **{f"reg {word}": (f"    reg [7:0] {word};\n    always @(posedge clk) begin {word} <= y; y <= {word}; end",
                               False) for word in ("bool", "wone", "wreal")},
            **{expression: (f"    always @(posedge clk) y <= {expression};", False)
               for expression in ("~~y", "!!y", "!~y", "- -y", "y + ~~y", "!-y")},
            **{expression: (f"    always @(posedge clk) y <= {expression};", True)
               for expression in ("~(~y)", "-(-y)", "!(!y)", "y - -y", "y + ~y")},
        }
        with tempfile.TemporaryDirectory() as directory:
            here = Path(directory)
            for label, (body, compiles) in probes.items():
                with self.subTest(label):
                    source = leaf.format(body=body)
                    (here / "m.v").write_text(source)
                    compiled = _run(here, self.capability.executable or "iverilog", "-g2012", "-o", "m.vvp", "m.v")
                    self.assertEqual(compiled.returncode == 0, compiles, compiled.stderr)
                    if compiles:
                        self.assertEqual(verilog.parse_source(source.encode(), "m.v").name, "m")
                    else:
                        with self.assertRaises(verilog.HdlRefused):
                            verilog.parse_source(source.encode(), "m.v")

    def test_the_source_top_alone_compiles_and_measures_nothing(self):
        """The declarative top has no clock and no measurement: it compiles with the RTL and prints nothing."""
        from ecad_validation.adapters.base import AdapterRequest
        from ecad_validation.adapters.hdl import HDLAdapter

        result = HDLAdapter().run(AdapterRequest(case_id="top", product_root=ITEM,
                                                 input_files=[ITEM / TB, ITEM / TX, ITEM / RX], timeout_seconds=60))
        self.assertEqual((result.verdict.value, result.reason_code, result.metrics), ("PASS", "RTL_TESTBENCH_PASSED", {}))
        self.assertEqual(result.summary, "committed RTL testbench executed: 0 of 0 declared metrics read")
        self.assertNotIn("ECAD_METRIC", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
