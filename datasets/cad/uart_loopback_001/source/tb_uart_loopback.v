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
