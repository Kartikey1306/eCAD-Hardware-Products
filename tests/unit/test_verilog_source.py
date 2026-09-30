"""The digital domain's Verilog grammar (tools/ecad_model/verilog.py).

No simulator is needed. TB, TX and RX are the three sources of the digital
sample uart_loopback_001 -- its declarative top and its byte copies of
rtl/uart_tx.v and rtl/uart_rx.v -- and HARNESS is the harness the digital
domain writes for them, all byte for byte: the sources are checked against
the digests the design recorded for the files it ran on Icarus Verilog, and
HARNESS against the digest of the committed simulation file. Every
expected module, port, value, line and reason is typed by hand from those
texts, never obtained by calling the code under test.
"""

from __future__ import annotations

import doctest
import hashlib
import importlib
import sys
import unittest
from pathlib import Path
from typing import List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

verilog = importlib.import_module("ecad_model.verilog")

# The sample's sources (design-digital.md sections 1.2 and 1.3); the non-ASCII
# in the RTL's comments is written as escapes.
TB = """// tb_uart_loopback.v -- loopback top for the 8N1 UART pair in rtl/ (eCAD digital MVP, issue #27)
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
""".encode("utf-8")

TX = """// uart_tx.v
// UART Transmitter \u2014 8N1 format, configurable baud rate
//
// Parameters:
//   CLK_FREQ  : System clock frequency in Hz (default 50 MHz)
//   BAUD_RATE : UART baud rate (default 115200)
//
// Ports:
//   clk       : System clock (rising edge)
//   rst_n     : Active-low synchronous reset
//   tx_data   : 8-bit data to transmit
//   tx_valid  : Pulse high for 1 cycle to start transmission
//   tx_ready  : High when transmitter is idle and ready
//   tx        : UART TX output line
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 EmbeddedOS Foundation

`timescale 1ns / 1ps

module uart_tx #(
    parameter CLK_FREQ  = 50_000_000,
    parameter BAUD_RATE = 115_200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] tx_data,
    input  wire       tx_valid,
    output reg        tx_ready,
    output reg        tx
);

    // Baud rate divider: number of clock cycles per bit
    localparam BAUD_DIV = CLK_FREQ / BAUD_RATE;

    // State machine
    localparam IDLE  = 2'd0;
    localparam START = 2'd1;
    localparam DATA  = 2'd2;
    localparam STOP  = 2'd3;

    reg [1:0]  state;
    reg [15:0] baud_cnt;    // Baud rate counter
    reg [2:0]  bit_idx;     // Current data bit index (0\u20137)
    reg [7:0]  shift_reg;   // Data shift register

    always @(posedge clk) begin
        if (!rst_n) begin
            state    <= IDLE;
            baud_cnt <= 0;
            bit_idx  <= 0;
            shift_reg<= 8'h00;
            tx       <= 1'b1;   // Idle line is high
            tx_ready <= 1'b1;
        end else begin
            case (state)

                IDLE: begin
                    tx       <= 1'b1;
                    tx_ready <= 1'b1;
                    if (tx_valid) begin
                        shift_reg <= tx_data;
                        baud_cnt  <= 0;
                        state     <= START;
                        tx_ready  <= 1'b0;
                    end
                end

                START: begin
                    tx <= 1'b0;   // Start bit (low)
                    if (baud_cnt == BAUD_DIV - 1) begin
                        baud_cnt <= 0;
                        bit_idx  <= 0;
                        state    <= DATA;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                DATA: begin
                    tx <= shift_reg[bit_idx];   // LSB first
                    if (baud_cnt == BAUD_DIV - 1) begin
                        baud_cnt <= 0;
                        if (bit_idx == 7) begin
                            state <= STOP;
                        end else begin
                            bit_idx <= bit_idx + 1;
                        end
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                STOP: begin
                    tx <= 1'b1;   // Stop bit (high)
                    if (baud_cnt == BAUD_DIV - 1) begin
                        baud_cnt <= 0;
                        state    <= IDLE;
                        tx_ready <= 1'b1;
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end

                default: state <= IDLE;

            endcase
        end
    end

endmodule
""".encode("utf-8")

RX = """// uart_rx.v
// UART Receiver \u2014 8N1 format, configurable baud rate
// Uses 16x oversampling for robust bit detection
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 EmbeddedOS Foundation

`timescale 1ns / 1ps

module uart_rx #(
    parameter CLK_FREQ  = 50_000_000,
    parameter BAUD_RATE = 115_200
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rx,
    output reg  [7:0] rx_data,
    output reg        rx_valid,   // Pulses high for 1 cycle when byte received
    output reg        rx_error    // Framing error (stop bit not high)
);

    // 16x oversampling: sample at 16\u00d7 baud rate, latch at sample 8
    localparam OVERSAMPLE    = 16;
    localparam BAUD_DIV      = CLK_FREQ / (BAUD_RATE * OVERSAMPLE);
    localparam SAMPLE_POINT  = OVERSAMPLE / 2;   // Sample at mid-bit

    localparam IDLE  = 2'd0;
    localparam START = 2'd1;
    localparam DATA  = 2'd2;
    localparam STOP  = 2'd3;

    reg [1:0]  state;
    reg [15:0] clk_cnt;      // Clock divider counter
    reg [3:0]  sample_cnt;   // Oversample counter (0\u201315)
    reg [2:0]  bit_idx;      // Data bit index
    reg [7:0]  shift_reg;
    reg        rx_sync;      // Synchronized RX input

    // Synchronize RX input to avoid metastability
    reg rx_meta;
    always @(posedge clk) begin
        rx_meta <= rx;
        rx_sync <= rx_meta;
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            state      <= IDLE;
            clk_cnt    <= 0;
            sample_cnt <= 0;
            bit_idx    <= 0;
            shift_reg  <= 0;
            rx_data    <= 0;
            rx_valid   <= 0;
            rx_error   <= 0;
        end else begin
            rx_valid <= 0;
            rx_error <= 0;

            if (clk_cnt == BAUD_DIV - 1) begin
                clk_cnt <= 0;

                case (state)

                    IDLE: begin
                        if (!rx_sync) begin
                            // Falling edge detected \u2014 possible start bit
                            sample_cnt <= 1;
                            state      <= START;
                        end
                    end

                    START: begin
                        sample_cnt <= sample_cnt + 1;
                        if (sample_cnt == SAMPLE_POINT) begin
                            if (!rx_sync) begin
                                // Confirmed start bit at mid-point
                                bit_idx    <= 0;
                                sample_cnt <= 0;
                                state      <= DATA;
                            end else begin
                                // False start \u2014 return to idle
                                state <= IDLE;
                            end
                        end
                    end

                    DATA: begin
                        sample_cnt <= sample_cnt + 1;
                        if (sample_cnt == OVERSAMPLE - 1) begin
                            sample_cnt         <= 0;
                            shift_reg[bit_idx] <= rx_sync;
                            if (bit_idx == 7) begin
                                state <= STOP;
                            end else begin
                                bit_idx <= bit_idx + 1;
                            end
                        end
                    end

                    STOP: begin
                        sample_cnt <= sample_cnt + 1;
                        if (sample_cnt == OVERSAMPLE - 1) begin
                            sample_cnt <= 0;
                            state      <= IDLE;
                            if (rx_sync) begin
                                // Valid stop bit
                                rx_data  <= shift_reg;
                                rx_valid <= 1;
                            end else begin
                                // Framing error
                                rx_error <= 1;
                            end
                        end
                    end

                    default: state <= IDLE;

                endcase
            end else begin
                clk_cnt <= clk_cnt + 1;
            end
        end
    end

endmodule
""".encode("utf-8")

# The harness of the design's section 4.2 as the review's CS-1 change writes it
# (a byte that never arrives counts 8 bit errors, and no framing count of 0 is
# printed then): lines 242-357 of the committed simulation file, its bytes
# checked through that whole file's digest.
HARNESS = """// ---- harness ----
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
    integer    ecad_missing = 0;
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
            // A byte sent that never arrived counts its 8 bits as errors, and a framing-error count of 0 is
            // not reported while a byte is missing: it says nothing of frames the receiver never finished.
            if (ecad_received < 2) ecad_missing = 2 - ecad_received;
            $display("ECAD_METRIC rx_bit_errors %0d", ecad_bit_errors + 8 * ecad_missing);
            if (ecad_framing_errors > 0 || ecad_missing == 0) $display("ECAD_METRIC rx_framing_errors %0d", ecad_framing_errors);
            if (ecad_unknown_after_reset >= 0) $display("ECAD_METRIC outputs_unknown_after_reset %0d", ecad_unknown_after_reset);
            $finish;
        end
    end

endmodule
"""

SAMPLE = "datasets/cad/uart_loopback_001/"
TB_PATH = SAMPLE + "source/tb_uart_loopback.v"
TX_PATH = SAMPLE + "source/uart_tx.v"
RX_PATH = SAMPLE + "source/uart_rx.v"
TB_SHA256 = "2962c844a2191ab756ad190e184365ab1893650ae67fee5a078b610ff7719fed"
TX_SHA256 = "5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a"
RX_SHA256 = "c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81"
# The whole committed simulation file (the design's section 4.1): two header
# lines, each leaf behind its separator, then HARNESS.
SIMULATION_HEADER = ("// uart_loopback_001: the RTL of tb_uart_loopback verbatim, then the harness the digital domain "
                     "writes from the model\n// written by ecad_model.domains.digital 1.0.0 from "
                     "derived/engineering_model.json; regenerate with build, never edit\n")
SIMULATION_SHA256 = "597eebf2679d10a236d344a6df5ff5d0fb4573ca0a863cf1b94bfdde3a94fd83"
METRICS = ("clock_period_s", "tx_idle_after_reset", "tx_bit_cycles", "tx_bit_rate_bd", "tx_frame_cycles",
           "rx_bytes_received", "rx_bit_errors", "rx_framing_errors", "outputs_unknown_after_reset")

C_CODE = "calls C code"
SUBSET = "outside the synchronous RTL subset (PLANNED)"
SCOPE = "changes another scope or the simulator"
SYSTEMVERILOG = "SystemVerilog (PLANNED)"
GATES = "gate-level primitive (PLANNED)"
ICARUS_TYPES = "an Icarus Verilog extended type (its -gxtypes, on by default)"
TOP_ONLY = ("not in a declarative top, which states values and wiring only; the adapter writes the clock, the "
            "stimulus and the measurements")
FILES = "opens, reads or writes files"
RUN_CONTROL = "run control, and only the harness ends a run ($stop waits for commands on stdin)"
HARNESS_ONLY = "; the harness uses only $display, $finish and $realtime"
HEADER = "module m (input wire clk, input wire a, output reg q);"
# TX line 53, inside the reset branch of its always block.
IDLE_LINE = "1'b1;   // Idle line is high"


def edit(data: bytes, old: str, new: str) -> bytes:
    """data with its one occurrence of old replaced by new."""
    text = data.decode("utf-8")
    if text.count(old) != 1:
        raise AssertionError(f"{old!r} occurs {text.count(old)} times")
    return text.replace(old, new).encode("utf-8")


def rtl(*body: str, header: str = HEADER) -> bytes:
    """A leaf of the given body lines: the timescale is line 1 and the header line 2, so the body starts on line 3."""
    return ("\n".join(("`timescale 1ns / 1ps", header, *body, "endmodule")) + "\n").encode("utf-8")


def small_leaves(count: int) -> List[Tuple[str, bytes]]:
    return [(f"source/l{index}.v", rtl("    always @(posedge clk) q <= a;", header=HEADER.replace(" m ", f" l{index} ")))
            for index in range(count)]


class TestVerilogGrammar(unittest.TestCase):
    def assert_refusal(self, error: Exception, expected: str) -> None:
        self.assertIsInstance(error, verilog.HdlRefused)
        self.assertEqual(getattr(error, "kind", None), "rejected")
        self.assertTrue(str(error).startswith(expected), f"{str(error)!r} does not start with {expected!r}")

    def refused(self, data: bytes, expected: str, path: str = "x.v") -> None:
        with self.assertRaises(verilog.HdlRefused) as caught:
            verilog.parse_source(data, path)
        self.assert_refusal(caught.exception, expected)

    def refused_design(self, sources: Sequence[Tuple[str, bytes]], expected: str) -> None:
        modules = [verilog.parse_source(data, path) for path, data in sources]
        with self.assertRaises(verilog.HdlRefused) as caught:
            verilog.elaborate(modules)
        self.assert_refusal(caught.exception, expected)

    def refused_harness(self, text: str, expected: str) -> None:
        with self.assertRaises(verilog.HdlRefused) as caught:
            verilog.read_harness(text, "h.v")
        self.assert_refusal(caught.exception, expected)

    def committed(self, tb: bytes = TB) -> List[Tuple[str, bytes]]:
        return [(TB_PATH, tb), (TX_PATH, TX), (RX_PATH, RX)]

    def test_the_committed_rtl_copies_parse_to_their_hand_read_interfaces(self):
        for data, digest, size in ((TX, TX_SHA256, 3367), (RX, RX_SHA256, 4195), (TB, TB_SHA256, 2152)):
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            self.assertEqual(len(data), size)
        tx = verilog.parse_source(TX, TX_PATH)
        self.assertIsInstance(tx, verilog.Leaf)
        self.assertEqual((tx.name, tx.path, tx.text), ("uart_tx", TX_PATH, TX.decode("utf-8")))
        self.assertEqual(list(tx.parameters.items()), [("CLK_FREQ", 50000000), ("BAUD_RATE", 115200)])
        self.assertEqual([(port.name, port.direction, port.width, port.line) for port in tx.ports],
                         [("clk", "input", 1, 25), ("rst_n", "input", 1, 26), ("tx_data", "input", 8, 27),
                          ("tx_valid", "input", 1, 28), ("tx_ready", "output", 1, 29), ("tx", "output", 1, 30)])
        # BAUD_DIV is an expression and the state codes are sized literals: none is a decimal literal.
        self.assertEqual(tx.literal_localparams, {})

        rx = verilog.parse_source(RX, RX_PATH)
        self.assertIsInstance(rx, verilog.Leaf)
        self.assertEqual((rx.name, rx.path, rx.text), ("uart_rx", RX_PATH, RX.decode("utf-8")))
        self.assertEqual(list(rx.parameters.items()), [("CLK_FREQ", 50000000), ("BAUD_RATE", 115200)])
        self.assertEqual([(port.name, port.direction, port.width, port.line) for port in rx.ports],
                         [("clk", "input", 1, 14), ("rst_n", "input", 1, 15), ("rx", "input", 1, 16),
                          ("rx_data", "output", 8, 17), ("rx_valid", "output", 1, 18), ("rx_error", "output", 1, 19)])
        self.assertEqual(rx.literal_localparams, {"OVERSAMPLE": (16, 23)})
        # The comments' non-ASCII is kept: the text is the file's, verbatim.
        self.assertIn("// UART Receiver \u2014 8N1 format", rx.text)
        self.assertIn("latch at sample 8", rx.text)

    def test_the_committed_top_parses_to_its_hand_read_structure(self):
        top = verilog.parse_source(TB, TB_PATH)
        self.assertIsInstance(top, verilog.Top)
        self.assertEqual((top.name, top.path), ("tb_uart_loopback", TB_PATH))
        self.assertEqual(list(top.localparams.items()), [
            ("CLK_HALF_PERIOD_NS", (10, None, 26)), ("CLK_FREQ", (50000000, None, 27)),
            ("BAUD_RATE", (115200, None, 28)), ("RESET_CYCLES", (4, None, 29)),
            ("TX_BYTE_0", (0x35, 8, 30)), ("TX_BYTE_1", (0xCA, 8, 31))])
        self.assertEqual(list(top.signals.items()), [
            ("clk", ("reg", 1, 33)), ("rst_n", ("reg", 1, 34)), ("tx_data", ("reg", 8, 35)),
            ("tx_valid", ("reg", 1, 36)), ("tx_ready", ("wire", 1, 37)), ("line", ("wire", 1, 38)),
            ("rx_data", ("wire", 8, 39)), ("rx_valid", ("wire", 1, 40)), ("rx_error", ("wire", 1, 41))])
        overrides = {"CLK_FREQ": "CLK_FREQ", "BAUD_RATE": "BAUD_RATE"}
        self.assertEqual(top.instances, (
            verilog.Instance("uart_tx", "u_tx", overrides,
                             {"clk": "clk", "rst_n": "rst_n", "tx_data": "tx_data", "tx_valid": "tx_valid",
                              "tx_ready": "tx_ready", "tx": "line"}, 43),
            verilog.Instance("uart_rx", "u_rx", overrides,
                             {"clk": "clk", "rst_n": "rst_n", "rx": "line", "rx_data": "rx_data",
                              "rx_valid": "rx_valid", "rx_error": "rx_error"}, 48)))

        tx, rx = verilog.parse_source(TX, TX_PATH), verilog.parse_source(RX, RX_PATH)
        for order in ([top, tx, rx], [tx, rx, top]):
            with self.subTest(order=[module.name for module in order]):
                design = verilog.elaborate(order)
                self.assertEqual(design.top, top)
                self.assertEqual(list(design.leaves.items()), [("uart_tx", tx), ("uart_rx", rx)])

    def test_directives_other_than_the_leading_timescale_are_refused(self):
        after = "`timescale 1ns / 1ps\n"  # TX line 19; a line inserted after it is line 20
        for line, expected in (
                ('`include "/etc/hosts"', "x.v:20: `include: reads another file"),
                ("`define WIDTH 8", "x.v:20: `define: text substitution"),
                ("`undef WIDTH", "x.v:20: `undef: text substitution"),
                ("`ifdef SIM", "x.v:20: `ifdef: conditional compilation"),
                ("`ifndef SIM", "x.v:20: `ifndef: conditional compilation"),
                ("`else", "x.v:20: `else: conditional compilation"),
                ("`endif", "x.v:20: `endif: conditional compilation"),
                ("`resetall", "x.v:20: `resetall: compiler directive"),
                ("`default_nettype none", "x.v:20: `default_nettype: compiler directive"),
                ("`celldefine", "x.v:20: `celldefine: compiler directive"),
                ('`line 1 "a.v" 0', "x.v:20: `line: compiler directive"),
                ("`pragma protect", "x.v:20: `pragma: compiler directive"),
                ("`timescale 1ns / 1ps", "x.v:20: `timescale: compiler directive: only one, `timescale 1ns / 1ps "
                                         "exactly, as the first line that is not a comment"),
                ("`", "x.v:20: a backtick outside a directive: outside the lexical subset")):
            with self.subTest(line=line):
                self.refused(edit(TX, after, after + line + "\n"), expected)
        self.refused(edit(TX, "parameter BAUD_RATE = 115_200", "parameter BAUD_RATE = `BAUD"),
                     "x.v:23: `BAUD: text substitution (a macro use)")
        timescale = "x.v:19: `timescale: compiler directive: only one, `timescale 1ns / 1ps exactly"
        for first in ("`timescale 1ns/1ns", "`timescale 1ns / 1ns", "`timescale 1ps / 1ps", "`timescale 1ns/1ps",
                      "`timescale 1ns / 1ps // the unit", "  `timescale 1ns / 1ps", "`timescale 1ns / 1ps "):
            with self.subTest(first=first):
                self.refused(edit(TX, after, first + "\n"), timescale)
        # Late: after the module line. Missing: the module is then the first token.
        self.refused(edit(TX, "`timescale 1ns / 1ps\n\nmodule uart_tx #(\n", "\nmodule uart_tx #(\n`timescale 1ns / 1ps\n"),
                     "x.v:21: `timescale: compiler directive")
        self.refused(edit(TX, after, ""), "x.v:20: no `timescale 1ns / 1ps before 'module': it is the first line "
                                         "that is not a comment")
        self.refused(edit(TX, after, "/* unit */ " + after), "x.v:19: `timescale: compiler directive")
        # A directive inside a comment is inert, and comments may precede the timescale.
        accepted = verilog.parse_source(edit(TX, "// Baud rate divider", '// `include "x.v" `define Baud rate divider'),
                                        "x.v")
        self.assertEqual(accepted.name, "uart_tx")
        self.assertEqual(verilog.parse_source(b"/* a\n block */\n// line\n\n" + TX, "x.v").name, "uart_tx")

    def test_system_tasks_and_functions_are_refused_with_their_class(self):
        reasons = {
            "$fopen": FILES, "$fwrite": FILES, "$fdisplay": FILES, "$readmemh": FILES, "$readmemb": FILES,
            "$writememh": FILES, "$dumpfile": FILES, "$dumpvars": FILES,
            "$system": "runs a shell command",
            "$value$plusargs": "reads the simulator's command line (plusargs)",
            "$test$plusargs": "reads the simulator's command line (plusargs)",
            "$random": "randomness", "$urandom": "randomness", "$dist_uniform": "randomness",
            "$display": "prints, and only the harness prints", "$write": "prints, and only the harness prints",
            "$monitor": "prints, and only the harness prints", "$strobe": "prints, and only the harness prints",
            "$finish": RUN_CONTROL, "$stop": RUN_CONTROL, "$fatal": RUN_CONTROL,
            "$clog2": "a system task or function outside the subset (PLANNED); a VPI module can define any $name",
            "$realtime": "a system task or function outside the subset (PLANNED); a VPI module can define any $name",
            "$my_vpi_task": "a system task or function outside the subset (PLANNED); a VPI module can define any $name",
            "$": "a $ outside a system task or function name: outside the lexical subset",
        }
        for name, reason in reasons.items():
            with self.subTest(name=name):
                self.refused(edit(TX, IDLE_LINE, f"{name};   // Idle line is high"), f"x.v:53: {name}: {reason}")
        self.refused(edit(TX, IDLE_LINE, "a$b;   // Idle line is high"),
                     "x.v:53: a$b: a $ inside an identifier: outside the lexical subset")
        # In the top, where a wire's initial value would call it (Icarus compiles that to .sfunc).
        self.refused(edit(TB, "    wire       line;\n", '    wire       line;\n    wire [31:0] f = $fopen("x", "w");\n'),
                     f"x.v:39: $fopen: {FILES}")
        # In a comment a $ name is inert.
        self.assertEqual(verilog.parse_source(edit(TX, "// Idle line is high", "// $fopen $system"), "x.v").name,
                         "uart_tx")

    def test_keywords_outside_each_file_kind_are_refused_by_class(self):
        self.assertEqual(verilog.RTL_KEYWORDS, {"module", "endmodule", "parameter", "localparam", "input", "output",
                                                "wire", "reg", "always", "posedge", "begin", "end", "if", "else",
                                                "case", "endcase", "default"})
        self.assertEqual(verilog.TOP_KEYWORDS, {"module", "endmodule", "localparam", "reg", "wire"})
        in_rtl = {"initial": SUBSET, "assign": SUBSET, "negedge": SUBSET, "function": SUBSET, "task": SUBSET,
                  "generate": SUBSET, "for": SUBSET, "while": SUBSET, "repeat": SUBSET, "forever": SUBSET,
                  "integer": SUBSET, "real": SUBSET, "inout": SUBSET, "defparam": SCOPE, "force": SCOPE,
                  "import": C_CODE}
        for word, reason in in_rtl.items():
            with self.subTest(rtl=word):
                self.refused(edit(TX, "    reg [1:0]  state;", f"    {word} reg [1:0]  state;"),
                             f"x.v:42: {word}: {reason}")
        classes = {
            C_CODE: ("import", "export", "chandle", "bind"),
            SUBSET: ("or", "casez", "casex", "fork", "join", "wait", "disable", "genvar", "time", "realtime",
                     "event", "signed", "automatic", "endfunction", "macromodule"),
            SCOPE: ("defparam", "force", "release", "deassign", "specify", "specparam", "primitive", "table",
                    "config", "library", "include"),
            SYSTEMVERILOG: ("logic", "bit", "int", "byte", "always_ff", "always_comb", "interface", "package",
                            "class", "program", "typedef", "enum", "struct", "assert", "string", "void", "unique"),
            GATES: ("and", "nand", "nor", "xor", "xnor", "not", "buf", "bufif0", "pullup", "supply0", "supply1",
                    "tri", "wand", "wor", "uwire", "nmos", "wone"),
            # Icarus Verilog 13.0 reserves these under -g2012 too: wone from -g2005 on, bool and wreal with its
            # extended types (-gxtypes, its default). Each compiled with -gno-xtypes or -g2001 respectively.
            ICARUS_TYPES: ("bool", "wreal"),
        }
        for reason, words in classes.items():
            with self.subTest(reason=reason):
                for word in words:
                    self.refused(edit(TX, "    reg [1:0]  state;", f"    {word} reg [1:0]  state;"),
                                 f"x.v:42: {word}: {reason}")
        # The three words Icarus alone reserves are refused as names too, not only where a keyword may stand.
        for word, reason in (("wone", GATES), ("bool", ICARUS_TYPES), ("wreal", ICARUS_TYPES)):
            with self.subTest(name=word):
                self.refused(edit(TX, "    reg [1:0]  state;", f"    reg [1:0]  state, {word};"),
                             f"x.v:42: {word}: {reason}")
        # Keywords are lower case: another spelling is an ordinary name.
        self.assertEqual(verilog.parse_source(edit(TX, "    reg [1:0]  state;", "    reg [1:0]  state, Initial;"),
                                              "x.v").name, "uart_tx")

        before = "    reg        clk;\n"  # TB line 33; a line inserted before it is line 33
        for line, expected in (("    always #10 clk = ~clk;", f"x.v:33: always: {TOP_ONLY}"),
                               ("    initial clk = 1'b0;", f"x.v:33: initial: {SUBSET}"),
                               ("    assign line = clk;", f"x.v:33: assign: {SUBSET}"),
                               ("    parameter P = 1;", f"x.v:33: parameter: {TOP_ONLY}"),
                               ("    input wire go;", f"x.v:33: input: {TOP_ONLY}"),
                               ('    import "DPI-C" function int getpid();', f"x.v:33: import: {C_CODE}"),
                               ("    defparam u_tx.BAUD_RATE = 9600;", f"x.v:33: defparam: {SCOPE}")):
            with self.subTest(top=line):
                self.refused(edit(TB, before, line + "\n" + before), expected)

    def test_lexical_forms_the_grammar_cannot_see_through_are_refused(self):
        expression = "CLK_FREQ / BAUD_RATE;"  # TX line 34
        for replacement, expected in (
                ('"abc";', 'x.v:34: a string: outside the lexical subset (file names and import "DPI-C" are strings)'),
                ("'b1;", "x.v:34: 'b1: an unsized based literal: outside the lexical subset"),
                ("8 'h35;", "x.v:34: 'h35: an unsized based literal"),
                ("8'hxx;", "x.v:34: 8'hxx: x, z and ? digits are outside the lexical subset"),
                ("4'b10??;", "x.v:34: 4'b10??: x, z and ? digits are outside the lexical subset"),
                ("4'bz;", "x.v:34: 4'bz: x, z and ? digits are outside the lexical subset"),
                ("8'HCA;", "x.v:34: 8'HCA: outside the lexical subset: a sized literal is W'b, W'd or W'h"),
                ("8'o17;", "x.v:34: 8'o17: outside the lexical subset"),
                ("8'sd5;", "x.v:34: 8'sd5: outside the lexical subset"),
                ("1.5;", "x.v:34: 1.5: a real literal: outside the lexical subset"),
                ("1e3;", "x.v:34: 1e3: a real literal"),
                ("2.0e-9;", "x.v:34: 2.0e-9: a real literal"),
                ("\\CLK_FREQ ;", "x.v:34: an escaped identifier (\\): outside the lexical subset")):
            with self.subTest(replacement=replacement):
                self.refused(edit(TX, expression, replacement), expected)
        for operator in ("===", "!==", "**", "<<<", ">>>", "->", "::", "++", "--", "+=", "-=", "<<=", "+:", "-:"):
            with self.subTest(operator=operator):
                self.refused(edit(TX, expression, f"CLK_FREQ {operator} BAUD_RATE;"),
                             f"x.v:34: {operator}: an operator outside the subset (PLANNED)")
        for braces, first in (("{CLK_FREQ};", "{"), ("CLK_FREQ};", "}")):
            with self.subTest(braces=braces):
                self.refused(edit(TX, expression, braces), f"x.v:34: {first}: an operator outside the subset (PLANNED)")
        self.refused(edit(TX, "    reg [1:0]  state;", "    (* keep *) reg [1:0]  state;"),
                     "x.v:42: (*: an attribute: outside the lexical subset")

        declared = "    reg [1:0]  state;\n"  # TX line 42; a line inserted after it is line 43
        longest = "n" * 64
        self.assertEqual(verilog.parse_source(edit(TX, declared, f"{declared}    reg {longest};\n"), "x.v").name,
                         "uart_tx")
        self.refused(edit(TX, declared, f"{declared}    reg {longest}x;\n"),
                     f"x.v:43: {'n' * 24}...: 65 characters exceeds the 64-character name limit")
        self.refused(edit(TX, declared, f"{declared}    reg ecad_x;\n"),
                     "x.v:43: ecad_x: names starting ecad_ are reserved for the harness")
        self.refused(edit(TB, "wire       line;", "wire       ecad_line;"),
                     "x.v:38: ecad_line: names starting ecad_ are reserved for the harness")
        self.refused(edit(TB, "module tb_uart_loopback;", "module ecad_harness;"),
                     "x.v:24: ecad_harness: names starting ecad_ are reserved for the harness")
        # Only the prefix is reserved.
        self.assertEqual(verilog.parse_source(edit(TX, declared, f"{declared}    reg ecad, ECAD_x, x_ecad_y;\n"),
                                              "x.v").name, "uart_tx")

        marker = "x.v:33: ECAD_METRIC: reserved for the harness's metric markers"
        comment = "// Baud rate divider: number of clock cycles per bit"  # TX line 33
        for text in ('// $display("ECAD_METRIC tx_bit_cycles %0d", 1);', "// ECAD_METRIC", "/* ECAD_METRIC */",
                     "localparam ECAD_METRIC_X = 1;", 'localparam X = "ECAD_METRIC";'):
            with self.subTest(marker=text):
                self.refused(edit(TX, comment, text), marker)

    def test_bytes_and_encoding_bounds_are_exact(self):
        self.assertEqual((verilog.VERSION, verilog.MAX_SOURCE_BYTES, verilog.MAX_LINE_CHARS, verilog.MAX_NAME_CHARS,
                          verilog.MAX_WIDTH, verilog.MAX_DEPTH, verilog.MAX_MODULES),
                         ("1.0.0", 1048576, 1024, 64, 64, 32, 16))
        room = 1048576 - len(TX)
        filler = b"//" + b"x" * 1021 + b"\n"
        rest = room % len(filler)
        at_limit = TX + filler * (room // len(filler)) + b"//" + b"x" * (rest - 3) + b"\n"
        self.assertGreaterEqual(rest, 3)
        self.assertEqual(len(at_limit), 1048576)
        self.assertEqual(verilog.parse_source(at_limit, "x.v").name, "uart_tx")
        self.refused(at_limit.replace(b"//x", b"//xx", 1), "x.v: 1048577 bytes exceeds the 1048576-byte source limit")

        self.assertEqual(verilog.parse_source(TX + b"//" + b"x" * 1022 + b"\n", "x.v").name, "uart_tx")
        self.refused(TX + b"//" + b"x" * 1023 + b"\n", "x.v:112: 1025 characters exceeds the 1024-character line limit")
        # Characters are counted, not bytes: 1024 characters of which 1022 take three bytes each.
        self.assertEqual(verilog.parse_source(TX + ("//" + "\u2014" * 1022 + "\n").encode("utf-8"), "x.v").name,
                         "uart_tx")

        comment = b"// UART Transmitter"  # TX line 2
        for byte, expected in ((b"\r", "x.v:2: a carriage return: lines end in LF only (U+000D)"),
                               (b"\x00", "x.v:2: a NUL character (U+0000)"),
                               (b"\x0b", "x.v:2: a control character (U+000B)"),
                               (b"\x0c", "x.v:2: a control character (U+000C)"),
                               (b"\x1b", "x.v:2: a control character (U+001B)"),
                               (b"\x7f", "x.v:2: a control character (U+007F)"),
                               ("\u0085".encode("utf-8"), "x.v:2: a control character (U+0085)"),
                               ("\u202e".encode("utf-8"), "x.v:2: a bidirectional control character (U+202E)"),
                               ("\u2066".encode("utf-8"), "x.v:2: a bidirectional control character (U+2066)"),
                               (b"\xff", "x.v:2: not UTF-8 (byte 0xff)"),
                               (b"\xe2\x80", "x.v:2: not UTF-8 (byte 0xe2)"),
                               (b"\xed\xa0\x80", "x.v:2: not UTF-8 (byte 0xed)"),
                               (b"\xc0\xaf", "x.v:2: not UTF-8 (byte 0xc0)")):
            with self.subTest(byte=byte):
                self.refused(TX.replace(comment, b"// UART " + byte + b"Transmitter"), expected)
        self.refused(TX.replace(b"\n", b"\r\n"), "x.v:1: a carriage return: lines end in LF only (U+000D)")
        self.refused(TX[:-1], "x.v:111: no final LF: the last line ends in LF")
        self.refused(b"", "x.v: is empty")
        self.refused(b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 3367\n",
                     "x.v: is a Git LFS pointer, not Verilog")
        self.refused(TX + b"/* open\n", "x.v:112: an unterminated /* comment")
        self.refused(b"\xef\xbb\xbf" + TX, "x.v:1: non-ASCII outside a comment (U+FEFF)")
        self.refused(edit(TX, "    reg [1:0]  state;", "    reg [1:0]  state\u00b5;"),
                     "x.v:42: non-ASCII outside a comment (U+00B5)")
        self.refused(edit(TX, "    reg [1:0]  state;", "    reg [1:0]  st\u00e4te;"),
                     "x.v:42: non-ASCII outside a comment (U+00E4)")
        # Non-ASCII in either kind of comment, and a tab, are accepted.
        accepted = edit(TX, "    reg [1:0]  state;", "    reg [1:0]\tstate; /* \u00b5s \u2014 \u00d7 */")
        self.assertEqual(verilog.parse_source(accepted, "x.v").name, "uart_tx")

    def test_rtl_bodies_are_clocked_nonblocking_and_single_driven(self):
        self.assertEqual(verilog.parse_source(rtl("    reg r;", "    always @(posedge clk) begin", "        r <= a;",
                                                  "        q <= r;", "    end"), "x.v").name, "m")
        for body, expected in (
                (("    always @(posedge clk) q = a;",), "x.v:3: q = ...: a blocking assignment; the subset assigns "
                                                        "with <= only"),
                (("    always @(a) q <= a;",), "x.v:3: always @(...: an always block is clocked by @(posedge <input>) "
                                               "only"),
                (("    always @* q <= a;",), "x.v:3: always @*...: an always block is clocked by @(posedge <input>)"),
                (("    always @(*) q <= a;",), "x.v:3: (*: an attribute"),
                (("    always @(posedge clk or negedge a) q <= a;",), f"x.v:3: or: {SUBSET}"),
                (("    always @(posedge clk, posedge a) q <= a;",), "x.v:3: one clock edge per always block: "
                                                                   "@(posedge clk)"),
                (("    always q <= a;",), "x.v:3: an always block is clocked: always @(posedge <input>)"),
                (("    always #5 q <= a;",), "x.v:3: always #: a delay; the RTL subset is untimed"),
                (("    always @(posedge clk) #5 q <= a;",), "x.v:3: a delay (#): the RTL subset is untimed"),
                (("    always @(posedge clk) q <= #5 a;",), "x.v:3: a delay (#): the RTL subset is untimed"),
                (("    always @(posedge clk) begin @(posedge clk) q <= a; end",),
                 "x.v:3: an event control inside a statement: only an always block waits, on @(posedge <input>)"),
                (("    always @(posedge clk) ;",), "x.v:3: an empty statement (;)"),
                (("    always @(posedge clk) q <= a;", "    always @(posedge clk) q <= !a;"),
                 "x.v:4: q is assigned in two always blocks (lines 3 and 4); each reg has one"),
                (("    always @(posedge clk) a <= 1'b1;",), "x.v:3: an assignment to input a: only regs are assigned"),
                (("    localparam K = 1;", "    always @(posedge clk) K <= 1;"),
                 "x.v:4: an assignment to localparam K: only regs are assigned"),
                (("    always @(posedge clk) q <= b;",), "x.v:3: b is not declared before this use: there are no "
                                                         "implicit nets"),
                (("    always @(posedge clk) z <= a;",), "x.v:3: z is not declared before this use"),
                (("    always @(posedge clk) q <= r;", "    reg r;"), "x.v:3: r is not declared before this use"),
                (("    always @(posedge clk) q <= u.x;",), "x.v:3: u.x: a hierarchical reference, which reads or "
                                                           "writes another module's registers"),
                (("    always @(posedge clk) u.secret <= 1'b1;",), "x.v:3: u.secret: a hierarchical reference"),
                (("    always @(posedge clk) q <= a.b;",), "x.v:3: a.b: a hierarchical reference"),
                (("    always @(posedge clk) q.b <= a;",), "x.v:3: q.b: a hierarchical reference"),
                (("    m2 u (.clk(clk));",), "x.v:3: an instance of m2: a leaf instantiates no module; a top is "
                                            "written module NAME; with no ports"),
                (("    m2 #(.P(1)) u (.clk(clk));",), "x.v:3: an instance of m2: a leaf instantiates no module"),
                (("    wire w;",), "x.v:3: a wire in a leaf: the subset declares regs, assigned in always blocks"),
                (("    reg r;", "    always @(posedge clk) r <= a;"), "x.v:2: output reg q is assigned by no "
                                                                      "statement"),
                (("    reg r;", "    always @(posedge r) q <= a;"), "x.v:4: always @(posedge r): r is declared reg, "
                                                                      "not input"),
                (("    always @(posedge q) q <= a;",), "x.v:3: always @(posedge q): q is declared output, not input"),
                (("    always @(posedge clk) q <= a;", "    reg r;", "    always @(posedge a) r <= clk;"),
                 "x.v:5: always @(posedge a): a second clock; clk clocks the block on line 3"),
                (("    reg r = 1'b0;",), "x.v:3: a reg is declared with no initial value and no array dimension"),
                (("    reg [7:0] mem [0:3];",), "x.v:3: a reg is declared with no initial value and no array dimension"),
                (("    reg [7:0] r;", "    always @(posedge clk) q <= r[3:0];"),
                 "x.v:4: a part select (name[a:b]): outside the subset"),
                (("    always @(posedge clk) q <= &a;",), "x.v:3: expected an operand, found '&'"),
                # Icarus 13.0 refuses each as a syntax error; a unary operator's operand is a primary.
                (("    always @(posedge clk) q <= ~~a;",), "x.v:3: ~ after ~: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= !!a;",), "x.v:3: ! after !: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= !~a;",), "x.v:3: ~ after !: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= - -a;",), "x.v:3: - after -: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= a + ~~a;",), "x.v:3: ~ after ~: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= a ?", "        !-a : a;"), "x.v:4: - after !: a unary operator's operand is a name, a number or a parenthesised expression, never another unary operator"),
                (("    always @(posedge clk) q <= (a;",), "x.v:3: expected ')', found ';'"),
                (("    always @(posedge clk) q <= a ? 1'b1;",), "x.v:3: expected ':', found ';'"),
                (("    always @(posedge clk) if (a) q <= a; else",), "x.v:4: expected a statement"),
                (("    q <= a;",), "x.v:3: 'q' where a localparam, reg or always item is expected")):
            with self.subTest(body=body):
                self.refused(rtl(*body), expected)
        # An else-if chain continues rather than nests, and a ternary and a bit select nest as expressions.
        chain = ("    always @(posedge clk)", "        if (a) q <= a;", *["        else if (!a) q <= !a;"] * 100,
                 "        else q <= a ? (a == 1'b1 ? !a : a) : a;")
        self.assertEqual(verilog.parse_source(rtl(*chain), "x.v").name, "m")
        # A parenthesised operand is a primary, and so is a unary operator's after a binary one: Icarus compiles both.
        self.assertEqual(verilog.parse_source(rtl("    always @(posedge clk) q <= ~(~a) ^ -(-a) ^ (a - -a) ^ !(!a);"),
                                              "x.v").name, "m")

        nested = "x.v:3: {0}: statements nested more than 32 deep"
        for count, accepted in ((32, True), (33, False)):
            with self.subTest(nesting=count):
                begins = rtl("    always @(posedge clk) " + "begin " * count + "q <= a; " + "end " * count)
                ifs = rtl("    always @(posedge clk) " + "if (a) " * count + "q <= a;")
                cases = rtl("    always @(posedge clk) " + "case (a) 1'b1: " * count + "q <= a; " + "endcase " * count)
                parentheses = rtl("    always @(posedge clk) q <= " + "(" * count + "a" + ")" * count + ";")
                selects = rtl("    reg [7:0] r;", "    always @(posedge clk) q <= " + "r[" * count + "0" + "]" * count
                              + ";")
                for data, word in ((begins, "begin"), (ifs, "if"), (cases, "case")):
                    if accepted:
                        self.assertEqual(verilog.parse_source(data, "x.v").name, "m")
                    else:
                        self.refused(data, nested.format(word))
                if accepted:
                    self.assertEqual(verilog.parse_source(parentheses, "x.v").name, "m")
                    self.assertEqual(verilog.parse_source(selects, "x.v").name, "m")
                else:
                    self.refused(parentheses, "x.v:3: an expression nested more than 32 deep")
                    self.refused(selects, "x.v:4: an expression nested more than 32 deep")
        # Far deeper still is the same refusal at the 33rd level, never a RecursionError: the first begin, if,
        # case or parenthesis is on line 4, so the 33rd is on line 36; the first select follows a reg, on line 5.
        self.refused(rtl("    always @(posedge clk)", *["begin"] * 5000, "q <= a;", *["end"] * 5000),
                     "x.v:36: begin: statements nested more than 32 deep")
        self.refused(rtl("    always @(posedge clk)", *["if (a)"] * 5000, "q <= a;"),
                     "x.v:36: if: statements nested more than 32 deep")
        self.refused(rtl("    always @(posedge clk)", *["case (a) 1'b1:"] * 5000, "q <= a;", *["endcase"] * 5000),
                     "x.v:36: case: statements nested more than 32 deep")
        self.refused(rtl("    always @(posedge clk) q <=", *["("] * 5000, "a", *[")"] * 5000, ";"),
                     "x.v:36: an expression nested more than 32 deep")
        self.refused(rtl("    reg [7:0] r;", "    always @(posedge clk) q <=", *["r["] * 5000, "0", *["]"] * 5000, ";"),
                     "x.v:37: an expression nested more than 32 deep")

    def test_rtl_headers_outside_the_subset_are_refused(self):
        for header, expected in (
                ("module m (clk, q);", "x.v:2: expected input or output, found 'clk': ports are declared in the "
                                       "header (ANSI style) only"),
                ("module m (input reg clk, output reg q);", "x.v:2: input reg: an input is a wire (input or input "
                                                           "wire), never a reg"),
                ("module m (input wire clk, output wire q);", "x.v:2: an output is declared output reg"),
                ("module m (input wire clk, output q);", "x.v:2: an output is declared output reg"),
                ("module m (input wire [7:1] clk, output reg q);", "x.v:2: [7:1]: a range is [N:0]; its least "
                                                                   "significant bit is 0"),
                ("module m (input wire [0:7] clk, output reg q);", "x.v:2: [0:7]: a range is [N:0]"),
                ("module m (input wire [64:0] clk, output reg q);", "x.v:2: [64:0]: wider than 64 bits"),
                ("module m (input wire clk, input wire clk, output reg q);", "x.v:2: clk is already declared on line 2"),
                ("module m ();", "x.v:2: a port list with no ports: a module with no ports is a top, written "
                                 "module NAME;"),
                ("module m #(parameter A = 1, B = 2) (input wire clk, output reg q);",
                 "x.v:2: expected 'parameter' starting each header item: parameter NAME = <decimal>, found 'B'"),
                ("module m #(parameter A = 8'd1) (input wire clk, output reg q);",
                 "x.v:2: parameter A: its default is one decimal literal"),
                ("module m #(parameter A = 1 + 1) (input wire clk, output reg q);",
                 "x.v:2: parameter A: its default is one decimal literal"),
                ("module m (input wire clk, output reg q)", "x.v:3: expected ';' after the port list, found 'always'"),
                ("module m = 1;", "x.v:2: module m: expected ';' (a top) or '#(' or '(' (RTL), found '='")):
            with self.subTest(header=header):
                self.refused(rtl("    always @(posedge clk) q <= !q;", header=header), expected)
        widest = rtl("    reg [63:0] r;", "    always @(posedge clk) r <= 64'hFFFFFFFFFFFFFFFF;",
                     "    always @(posedge clk) q <= r[63];", header="module m (input wire [63:0] clk, output reg q);")
        self.assertEqual(verilog.parse_source(widest, "x.v").ports[0].width, 64)
        self.refused(edit(TX, "input  wire [7:0] tx_data", "input  wire [BAUD_RATE-1:0] tx_data"),
                     "x.v:27: a range is [N:0] with decimal bounds")
        self.refused(edit(TX, "parameter BAUD_RATE = 115_200", "parameter BAUD_RATE = 17'd115200"),
                     "x.v:23: parameter BAUD_RATE: its default is one decimal literal")
        self.refused(edit(TX, "parameter BAUD_RATE = 115_200", "parameter BAUD_RATE = CLK_FREQ"),
                     "x.v:23: parameter BAUD_RATE: its default is one decimal literal")
        self.refused(rtl("    reg q;", "    always @(posedge clk) q <= a;"), "x.v:3: q is already declared on line 2")
        self.refused(edit(TX, "localparam START = 2'd1;", "localparam IDLE  = 2'd1;"),
                     "x.v:38: IDLE is already declared on line 37")
        self.refused(rtl("    reg r, r;", "    always @(posedge clk) q <= a;"), "x.v:3: r is already declared on line 3")
        self.refused(rtl("    parameter P = 1;", "    always @(posedge clk) q <= a;"),
                     "x.v:3: a parameter in the module body: parameters are declared in the #( ) header only")
        self.refused(rtl("    input wire b;", "    always @(posedge clk) q <= a;"),
                     "x.v:3: input in the module body: ports are declared in the header")
        self.refused(rtl("    localparam [1:0] K = 2'd1;", "    always @(posedge clk) q <= a;"),
                     "x.v:3: a leaf's localparam has no range: localparam NAME = <expression>;")
        self.refused(TX + b"module spare (input wire clk, output reg q);\nendmodule\n",
                     "x.v:112: a second module: one module per file")
        self.refused(TX + b"reg stray;\n", "x.v:112: text after endmodule: 'reg'")
        self.refused(TX[:-len(b"endmodule\n")], "x.v:110: module uart_tx has no endmodule")
        self.refused(edit(TX, "localparam IDLE  = 2'd0;", "localparam IDLE  = 2'd4;"), "x.v:37: 2'd4 does not fit in 2 bits")
        self.refused(edit(TX, "localparam IDLE  = 2'd0;", "localparam IDLE  = 65'd0;"), "x.v:37: 65'd0: wider than 64 bits")
        self.refused(edit(TX, "localparam IDLE  = 2'd0;", "localparam IDLE  = 64'h1_0000_0000_0000_0000;"),
                     "x.v:37: 64'h1_0000_0000_0000_0000 does not fit in 64 bits")
        self.refused(edit(TX, "localparam IDLE  = 2'd0;", "localparam IDLE  = 2'b100;"), "x.v:37: 2'b100 does not fit")
        # An unsized decimal is a 32-bit signed integer to Verilog; larger is implementation-defined.
        self.assertEqual(verilog.parse_source(edit(TX, "50_000_000", "2147483647"), "x.v").parameters["CLK_FREQ"],
                         2147483647)
        self.refused(edit(TX, "50_000_000", "2147483648"), "x.v:22: 2147483648 does not fit a 32-bit signed integer")
        # A localparam's expression is constant: parameters, earlier localparams, literals, + - * / and parentheses.
        for expression, expected in (("clk", "x.v:3: clk is declared input: a localparam's expression uses parameters"),
                                     ("K", "x.v:3: K is not declared before this use"),
                                     ("P % 2", "x.v:3: %: outside a localparam's constant expression"),
                                     ("P << 1", "x.v:3: <<: outside a localparam's constant expression"),
                                     ("P ? 1 : 0", "x.v:3: ?: outside a localparam's constant expression"),
                                     ("-P", "x.v:3: -: outside a localparam's constant expression"),
                                     ("P[0]", "x.v:3: P[: outside a localparam's constant expression")):
            with self.subTest(expression=expression):
                self.refused(rtl(f"    localparam K = {expression};", "    always @(posedge clk) q <= a;",
                                 header="module m #(parameter P = 1) (input wire clk, input wire a, output reg q);"),
                             expected)

    def test_a_top_outside_the_declarative_form_is_refused(self):
        self.refused(b"`timescale 1ns / 1ps\nmodule tb (input wire go);\n    uart_tx #(.CLK_FREQ(1)) u (.clk(go));\n"
                     b"endmodule\n", "x.v:3: an instance of uart_tx: a leaf instantiates no module; a top is written "
                                     "module NAME; with no ports")
        self.refused(edit(TB, "module tb_uart_loopback;", "module tb_uart_loopback (input wire go);"),
                     "x.v:30: a leaf's localparam has no range")
        for old, new, expected in (
                ("    reg        clk;", "    reg        clk = 0;", "x.v:33: reg clk = ...: a top declaration has no "
                                                                   "initial value; the adapter drives every reg"),
                ("    reg        clk;", "    reg        clk = 1'b0;", "x.v:33: reg clk = ...: a top declaration has "
                                                                      "no initial value"),
                ("    wire       line;", "    wire       line = 1'b1;", "x.v:38: wire line = ...: a top declaration "
                                                                         "has no initial value"),
                ("    reg        clk;", "    reg        clk, clk2;", "x.v:33: reg clk, ...: a top declares one signal "
                                                                      "per declaration"),
                ("= 50_000_000;", "= 25_000_000 * 2;", "x.v:27: localparam CLK_FREQ: a top localparam is one decimal "
                                                      "or sized literal, not an expression"),
                ("= 115_200;", "= CLK_FREQ;", "x.v:28: localparam BAUD_RATE: a top localparam is one decimal"),
                ("localparam [7:0] TX_BYTE_0    = 8'h35;", "localparam [7:0] TX_BYTE_0    = 9'h035;",
                 "x.v:30: localparam [7:0] TX_BYTE_0: its literal is 8 bits wide"),
                ("localparam [7:0] TX_BYTE_0    = 8'h35;", "localparam [7:0] TX_BYTE_0    = 53;",
                 "x.v:30: localparam [7:0] TX_BYTE_0: its literal is 8 bits wide"),
                ("localparam [7:0] TX_BYTE_0    = 8'h35;", "localparam [3:0] TX_BYTE_0    = 4'h5;",
                 "x.v:30: a top localparam's only range is [7:0]"),
                ("uart_tx #(.CLK_FREQ(CLK_FREQ),", "uart_tx #(.CLK_FREQ(CLK_FREQ * 2),",
                 "x.v:43: the override of CLK_FREQ is one top localparam or decimal literal, not an expression"),
                ("uart_tx #(.CLK_FREQ(CLK_FREQ),", "uart_tx #(.CLK_FREQ(32'd50000000),",
                 "x.v:43: the override of CLK_FREQ is one top localparam or decimal literal"),
                ("uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))", "uart_tx #(50_000_000, 115_200)",
                 "x.v:43: expected '.' before each override: .NAME(value), found '50_000_000'"),
                (".BAUD_RATE(BAUD_RATE)) u_tx", ".BAUD_RATE(BAUD_RATE), .CLK_FREQ(1)) u_tx",
                 "x.v:43: CLK_FREQ is overridden twice"),
                ("uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE)) u_tx (", "uart_tx u_tx (",
                 "x.v:43: an instance of uart_tx states its parameters"),
                ("        .clk(clk), .rst_n(rst_n), .tx_data(tx_data), .tx_valid(tx_valid),",
                 "        clk, .rst_n(rst_n), .tx_data(tx_data), .tx_valid(tx_valid),",
                 "x.v:44: u_tx: 'clk': connections are by name only, .port(signal)"),
                ("        .tx_ready(tx_ready), .tx(line)\n", "        .tx_ready(tx_ready), .*\n",
                 "x.v:45: u_tx: .*: connections are by name only, .port(signal)"),
                (".tx(line)\n", ".tx()\n", "x.v:45: u_tx.tx(): an unconnected port; every port is connected"),
                (".tx(line)\n", ".tx(line[0])\n", "x.v:45: u_tx.tx: a connection is one signal name, not an expression"),
                (".tx(line)\n", ".tx(1'b1)\n", "x.v:45: u_tx.tx: a connection is one signal name, not an expression"),
                ("    wire       rx_error;\n", "    wire       rx_error;\n    wire       clk;\n",
                 "x.v:42: clk is already declared on line 33"),
                (") u_rx (", ") line (", "x.v:48: line is already declared on line 38"),
                ("    wire       rx_error;\n", "    wire       rx_error;\n    tx_valid <= 1'b0;\n",
                 "x.v:42: 'tx_valid' where a localparam, reg, wire or instance is expected"),
                ("    wire       rx_error;\n", "    wire       rx_error;\n    u_tx.state = 2'd1;\n",
                 "x.v:42: 'u_tx' where a localparam, reg, wire or instance is expected")):
            with self.subTest(new=new):
                self.refused(edit(TB, old, new), expected)
        self.refused(TB[:-len(b"endmodule\n")], "x.v:52: the module has no endmodule")
        # An unranged localparam may take a sized literal; its range is then None.
        top = verilog.parse_source(edit(TB, "= 10;", "= 32'd10;"), "x.v")
        self.assertEqual(top.localparams["CLK_HALF_PERIOD_NS"], (10, None, 26))

    def test_elaboration_resolves_one_top_with_every_leaf_once(self):
        tb, tx, rx = self.committed()
        spare = ("source/spare.v", b"`timescale 1ns / 1ps\nmodule spare;\nendmodule\n")
        self.refused_design([tx, rx], f"{TX_PATH}, {RX_PATH}: no top module: a top is written module NAME; with no "
                                      "ports")
        self.refused_design([tb, tx, rx, spare], "source/spare.v: a second top module, spare; tb_uart_loopback in "
                                                 f"{TB_PATH} is the top")
        self.refused_design([tb, tx, rx, ("source/copy.v", TX)], f"source/copy.v: module uart_tx is already defined "
                                                                 f"in {TX_PATH}")
        self.refused_design([tb, tx, rx, ("source/m.v", rtl("    always @(posedge clk) q <= a;"))],
                            "source/m.v: module m is never instantiated by the top tb_uart_loopback")
        at_rx = f"{TB_PATH}:48: u_rx"
        at_tx = f"{TB_PATH}:43: u_tx"
        for old, new, expected in (
                ("uart_rx #(", "uart_rxx #(", f"{at_rx}: no source defines module uart_rxx"),
                ("uart_rx #(", "tb_uart_loopback #(", f"{at_rx}: the top tb_uart_loopback instantiates itself"),
                ("uart_rx #(", "uart_tx #(", f"{at_rx}: module uart_tx is already instantiated as u_tx; each leaf is "
                                             "instantiated once"),
                (".tx(line)\n", ".tx(line), .tx_idle(line)\n", f"{at_tx}: uart_tx has no port tx_idle"),
                ("        .tx_ready(tx_ready), .tx(line)\n", "        .tx(line)\n",
                 f"{at_tx}: port tx_ready is not connected; every port is connected by name"),
                ("    wire [7:0] rx_data;", "    wire [6:0] rx_data;", f"{at_rx}.rx_data is 8 bits wide and rx_data is 7"),
                ("    wire       tx_ready;", "    reg        tx_ready;",
                 f"{at_tx}.tx_ready is an output onto reg tx_ready: an output drives a wire"),
                (".rx_valid(rx_valid)", ".rx_valid(tx_ready)",
                 f"{TB_PATH}:37: wire tx_ready is driven by u_tx.tx_ready and u_rx.rx_valid"),
                (".rx(line),\n", ".rx(idle),\n", f"{at_rx}.rx: idle is not a signal the top declares"),
                ("uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))",
                 "uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE), .PARITY(1))",
                 f"{at_rx}: PARITY is not a parameter of uart_rx, whose header declares CLK_FREQ, BAUD_RATE"),
                ("uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))",
                 "uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE), .OVERSAMPLE(8))",
                 f"{at_rx}: OVERSAMPLE is not a parameter of uart_rx, whose header declares CLK_FREQ, BAUD_RATE"),
                ("uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))", "uart_rx #(.CLK_FREQ(CLK_FREQ), "
                 ".BAUD_RATE(line))", f"{at_rx}: the override of BAUD_RATE, line, is neither a top localparam nor a "
                                      "decimal literal"),
                ("uart_rx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))", "uart_rx #(.CLK_FREQ(CLK_FREQ), "
                 ".BAUD_RATE(BAUD))", f"{at_rx}: the override of BAUD_RATE, BAUD, is neither")):
            with self.subTest(new=new):
                self.refused_design(self.committed(edit(TB, old, new)), expected)
        undriven = edit(edit(TB, ".rx(line),\n", ".rx(idle),\n"), "    wire       line;\n",
                        "    wire       line;\n    wire       idle;\n")
        self.refused_design(self.committed(undriven), f"{TB_PATH}:49: input u_rx.rx is on wire idle, which no output "
                                                      "drives")
        self.refused(edit(TB, ".tx(line)\n", ".tx(line), .tx(line)\n"), f"{TB_PATH}:45: u_tx.tx is connected twice",
                     path=TB_PATH)
        # Literal overrides are the other accepted form.
        literal = edit(TB, "uart_tx #(.CLK_FREQ(CLK_FREQ), .BAUD_RATE(BAUD_RATE))",
                       "uart_tx #(.CLK_FREQ(50_000_000), .BAUD_RATE(115200))")
        design = verilog.elaborate([verilog.parse_source(data, path) for path, data in self.committed(literal)])
        self.assertEqual(design.top.instances[0].overrides, {"CLK_FREQ": 50000000, "BAUD_RATE": 115200})

        self.refused_design([], "no sources: a design is one top and the leaves it instantiates")
        self.refused_design([tb, tx, rx, *small_leaves(13)], "source/l0.v: module l0 is never instantiated")
        self.refused_design([tb, tx, rx, *small_leaves(14)], "source/l13.v: more than 16 sources")

    def test_the_harness_reader_returns_what_the_harness_states(self):
        separators = "".join(f"// ---- {path} sha256 {digest} ----\n{data.decode('utf-8')}"
                             for path, digest, data in ((TX_PATH, TX_SHA256, TX), (RX_PATH, RX_SHA256, RX)))
        simulation = (SIMULATION_HEADER + separators + HARNESS).encode("utf-8")
        self.assertEqual(hashlib.sha256(simulation).hexdigest(), SIMULATION_SHA256)
        self.assertEqual((len(simulation), simulation.count(b"\n")), (13240, 357))

        view = verilog.read_harness(HARNESS, "derived/digital/uart_loopback_001.v")
        self.assertEqual(list(view.signals.items()), [
            ("clk", ("reg", 1, 6)), ("line", ("wire", 1, 7)), ("rst_n", ("reg", 1, 8)), ("rx_data", ("wire", 8, 9)),
            ("rx_error", ("wire", 1, 10)), ("rx_valid", ("wire", 1, 11)), ("tx_data", ("reg", 8, 12)),
            ("tx_ready", ("wire", 1, 13)), ("tx_valid", ("reg", 1, 14))])
        self.assertEqual(view.initial_values, {"clk": 0, "rst_n": 0, "tx_data": 0, "tx_valid": 0})
        overrides = {"BAUD_RATE": 115200, "CLK_FREQ": 50000000}
        self.assertEqual(view.instances, (
            verilog.Instance("uart_tx", "u_tx", overrides,
                             {"clk": "clk", "rst_n": "rst_n", "tx": "line", "tx_data": "tx_data",
                              "tx_ready": "tx_ready", "tx_valid": "tx_valid"}, 16),
            verilog.Instance("uart_rx", "u_rx", overrides,
                             {"clk": "clk", "rst_n": "rst_n", "rx": "line", "rx_data": "rx_data",
                              "rx_error": "rx_error", "rx_valid": "rx_valid"}, 17)))
        self.assertEqual((view.clock, view.half_period, view.reset_cycles), ("clk", 10, 4))
        self.assertEqual(view.stimulus, (("tx_data", 53), ("tx_data", 202)))
        self.assertEqual((view.expected, view.expected_size, view.compared, view.awaited), ((53, 202), 2, 2, 2))
        self.assertEqual(view.end_cycle, 20836)
        self.assertEqual(view.metrics, METRICS)
        self.assertEqual(view.system_identifiers, ("$display", "$finish", "$realtime"))

        finish = "            $finish;\n"  # line 112
        for old, new, expected in (
                (finish, '            $fopen("x", "w");\n' + finish, f"h.v:112: $fopen: {FILES}{HARNESS_ONLY}"),
                (finish, '            $readmemh("/etc/hosts", ecad_expected);\n' + finish,
                 f"h.v:112: $readmemh: {FILES}{HARNESS_ONLY}"),
                (finish, '            $system("true");\n' + finish, f"h.v:112: $system: runs a shell command{HARNESS_ONLY}"),
                (finish, "            $stop;\n" + finish, f"h.v:112: $stop: {RUN_CONTROL}{HARNESS_ONLY}"),
                (finish, "            case (ecad_k) default: ecad_k = 0; endcase\n" + finish,
                 "h.v:112: case: not in the harness, which declares signals and instances, then measures"),
                (finish, "            fork join\n" + finish, f"h.v:112: fork: {SUBSET}"),
                (finish, '            import "DPI-C" function int getpid();\n' + finish, f"h.v:112: import: {C_CODE}"),
                (finish, "            module inner;\n" + finish, "h.v:112: a second module: the harness is one "
                                                                  "module, ecad_harness"),
                ("module ecad_harness;\n", "module ecad_harness;\n`timescale 1ns / 1ps\n",
                 "h.v:5: `timescale: compiler directive: only one"),
                ("module ecad_harness;\n", 'module ecad_harness;\n`include "x.v"\n', "h.v:5: `include: reads another file"),
                ("module ecad_harness;", "module harness;", "h.v:4: the harness module is ecad_harness, not harness"),
                ('"ECAD_METRIC rx_bit_errors %0d"', '"rx_bit_errors %0d"',
                 'h.v:109: "rx_bit_errors %0d": a string other than an ECAD_METRIC declaration'),
                ('"ECAD_METRIC rx_bit_errors %0d"', '"ECAD_METRIC rx_bit_errors %d"',
                 'h.v:109: "ECAD_METRIC rx_bit_errors %d": a string other than an ECAD_METRIC declaration'),
                ('"ECAD_METRIC rx_bit_errors %0d"', '"ECAD_METRIC rx_bit_errors %0d\\n"',
                 "h.v:109: an unterminated string, or one with a backslash escape"),
                ("    // ecad: clock, stimulus and measurements\n", '    // $display("ECAD_METRIC rx_bit_errors %0d", 0);\n',
                 "h.v:19: ECAD_METRIC: reserved for the harness's metric markers"),
                ("        ecad_line_before = line;\n", '        ecad_line_before = "ECAD_METRIC rx_bit_errors %0d";\n',
                 'h.v:95: "ECAD_METRIC rx_bit_errors %0d": an ECAD_METRIC declaration stands in $display( ) only'),
                ("    // ecad: clock, stimulus and measurements\n", "    /* ECAD_METRIC */\n",
                 "h.v:19: ECAD_METRIC: reserved for the harness's metric markers"),
                ("    integer    ecad_k;", "    integer    ECAD_METRIC_k;",
                 "h.v:62: ECAD_METRIC_k: ECAD_METRIC is reserved for the harness's metric markers"),
                ("    reg        clk = 1'b0;\n", "    localparam K = 1;\n    reg        clk = 1'b0;\n",
                 "h.v:6: a localparam in the harness: it writes every value as a literal"),
                ("uart_tx #(.BAUD_RATE(115200)", "uart_tx #(.BAUD_RATE(BAUD)",
                 "h.v:16: the override of BAUD_RATE is one decimal literal, not an expression"),
                ("    wire       line;", "    wire       line = 1'b1;", "h.v:7: wire line = ...: a top declaration has "
                                                                        "no initial value"),
                ("    reg        clk = 1'b0;", "    reg        clk = 0;", "h.v:6: reg clk: its initial value is a sized "
                                                                          "literal"),
                ("        tx_data <= 8'd53;", "        tx_data <= 8'd353;", "h.v:27: 8'd353 does not fit in 8 bits"),
                ("    always #10 clk = ~clk;\n", "    always #10 clk = ~clk;\n    always #10 clk = ~clk;\n",
                 "h.v:21: a second line of the form 'always #N clk = ~clk;'; the first is line 20"),
                ("    always #10 clk = ~clk;\n", "    always #10 clk = !clk;\n",
                 "h.v: no line of the form 'always #N clk = ~clk;'"),
                ("        if (ecad_cycle == 20836) begin", "        if (ecad_cycle >= 20836) begin",
                 "h.v: no line of the form 'if (ecad_cycle == N) begin'"),
                # The count a missing byte is taken from is one number, stated once.
                ("ecad_missing = 2 - ecad_received;", "ecad_missing = 3 - ecad_received;",
                 "h.v: no line of the form 'if (ecad_received < N) ecad_missing = N - ecad_received;'"),
                ("            if (ecad_received < 2) ecad_missing = 2 - ecad_received;\n",
                 "            if (ecad_received < 2) ecad_missing = 2 - ecad_received;\n" * 2,
                 "h.v:109: a second line of the form 'if (ecad_received < N) ecad_missing = N - ecad_received;'; "
                 "the first is line 108"),
                ("        repeat (4) @(posedge clk);", "        repeat (4) @(posedge rst_n);",
                 "h.v:23: the reset waits on posedge rst_n, not on the clock clk"),
                ("        ecad_expected[0] = 8'd53;\n        ecad_expected[1] = 8'd202;\n",
                 "        ecad_expected[1] = 8'd202;\n        ecad_expected[0] = 8'd53;\n",
                 "h.v:66: ecad_expected[1]: the expected bytes are assigned in index order, and the next is [0]"),
                ("\nendmodule\n", "\n    end endmodule\n", "h.v:116: endmodule stands on a line of its own")):
            with self.subTest(new=new):
                self.refused_harness(edit(HARNESS.encode("utf-8"), old, new).decode("utf-8"), expected)
        self.refused_harness(HARNESS + "module ecad_extra;\nendmodule\n",
                             "h.v:117: a second module: the harness is one module, ecad_harness")
        self.refused_harness(HARNESS + "wire stray;\n", "h.v:117: text after endmodule: 'wire'")
        self.refused_harness(HARNESS[:-len("endmodule\n")], "h.v:115: module ecad_harness has no endmodule")
        self.refused_harness(HARNESS.replace("\n", "\r\n"), "h.v:1: a carriage return: lines end in LF only")

    def test_what_icarus_was_seen_to_run_or_read_is_refused(self):
        """Each construct in the form Icarus Verilog 13.0 compiled and ran on 2026-09-27, before any refusal."""
        declared = "    wire       line;\n"  # TB line 38; a line inserted after it is line 39
        for data, expected in (
                # `include read a file outside the sources and printed its identifiers.
                (edit(TB, declared, declared + '`include "/private/tmp/secret.txt"\n'), "x.v:39: `include: reads "
                                                                                       "another file"),
                # $fopen wrote a file, also as a wire's initial value (compiled to .sfunc).
                (edit(TX, IDLE_LINE, '$fopen("written.txt", "w");'), f"x.v:53: $fopen: {FILES}"),
                (edit(TB, declared, declared + '    wire [31:0] f = $fopen("written.txt", "w");\n'),
                 f"x.v:39: $fopen: {FILES}"),
                # $readmemh opened /etc/hosts.
                (edit(TX, IDLE_LINE, '$readmemh("/etc/hosts", shift_reg);'), f"x.v:53: $readmemh: {FILES}"),
                (edit(TX, IDLE_LINE, '$system("touch /tmp/x");'), "x.v:53: $system: runs a shell command"),
                # $stop stops to read commands from stdin.
                (edit(TX, IDLE_LINE, "$stop;"), f"x.v:53: $stop: {RUN_CONTROL}"),
                (edit(TX, IDLE_LINE, '$fatal(1, "boom");'), f"x.v:53: $fatal: {RUN_CONTROL}"),
                (edit(TB, declared, declared + '    import "DPI-C" function int getpid();\n'), f"x.v:39: import: {C_CODE}"),
                # defparam u.P = 7 and u.secret = 1 changed another module.
                (edit(TB, declared, declared + "    defparam u_tx.BAUD_RATE = 9600;\n"), f"x.v:39: defparam: {SCOPE}"),
                (edit(TX, "            tx       <= " + IDLE_LINE, "            u_rx.shift_reg <= 8'd0;"),
                 "x.v:53: u_rx.shift_reg: a hierarchical reference"),
                (edit(TX, "    reg [1:0]  state;", "    uart_rx u (.clk(clk), .rst_n(rst_n), .rx(tx));\n    reg [1:0]  state;"),
                 "x.v:42: an instance of uart_rx: a leaf instantiates no module"),
                (TB + b"module b;\nendmodule\n", "x.v:54: a second module: one module per file"),
                (edit(TB, "wire       rx_error;", "wire       ecad_cycle;"), "x.v:41: ecad_cycle: names starting ecad_ "
                                                                           "are reserved for the harness"),
                (edit(TB, "// SPDX-License-Identifier: MIT", "// ECAD_METRIC rx_bit_errors 0"),
                 "x.v:20: ECAD_METRIC: reserved for the harness's metric markers")):
            with self.subTest(expected=expected):
                self.refused(data, expected)


class TestDocumentationExamples(unittest.TestCase):
    """QUALITY.md: every public function's example must be one that was actually run."""

    def test_examples_in_the_verilog_module(self):
        result = doctest.testmod(verilog, optionflags=doctest.ELLIPSIS)
        self.assertGreater(result.attempted, 0)
        self.assertEqual(result.failed, 0)


if __name__ == "__main__":
    unittest.main()
