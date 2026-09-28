// uart_loopback_001: the RTL of tb_uart_loopback verbatim, then the harness the digital domain writes from the model
// written by ecad_model.domains.digital 1.0.0 from derived/engineering_model.json; regenerate with build, never edit
// ---- datasets/cad/uart_loopback_001/source/uart_tx.v sha256 5be9e1bdd20b37a3b79cb40c98fbfe241e8d6faca5ecb443b0e93378d7b4f01a ----
// uart_tx.v
// UART Transmitter — 8N1 format, configurable baud rate
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
    reg [2:0]  bit_idx;     // Current data bit index (0–7)
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
// ---- datasets/cad/uart_loopback_001/source/uart_rx.v sha256 c1bebcc6e894e86abd4b39af5501031b8c817f4395048ef65059eebfb710ab81 ----
// uart_rx.v
// UART Receiver — 8N1 format, configurable baud rate
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

    // 16x oversampling: sample at 16× baud rate, latch at sample 8
    localparam OVERSAMPLE    = 16;
    localparam BAUD_DIV      = CLK_FREQ / (BAUD_RATE * OVERSAMPLE);
    localparam SAMPLE_POINT  = OVERSAMPLE / 2;   // Sample at mid-bit

    localparam IDLE  = 2'd0;
    localparam START = 2'd1;
    localparam DATA  = 2'd2;
    localparam STOP  = 2'd3;

    reg [1:0]  state;
    reg [15:0] clk_cnt;      // Clock divider counter
    reg [3:0]  sample_cnt;   // Oversample counter (0–15)
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
                            // Falling edge detected — possible start bit
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
                                // False start — return to idle
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
