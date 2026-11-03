`timescale 1ns / 1ps
// 8N1 UART receiver. `valid` is a one-clock pulse when `data` holds a new byte.
module uart_rx #(
    parameter CLKS_PER_BIT = 104   // 12 MHz / 115200
)(
    input  wire       clk,
    input  wire       rx,
    output reg  [7:0] data  = 8'd0,
    output reg        valid = 1'b0
);
    localparam IDLE = 2'd0, START = 2'd1, DATA = 2'd2, STOP = 2'd3;

    reg [1:0]  sync  = 2'b11;
    reg [1:0]  state = IDLE;
    reg [15:0] cnt   = 16'd0;
    reg [2:0]  idx   = 3'd0;

    always @(posedge clk) begin
        sync  <= {sync[0], rx};
        valid <= 1'b0;
        case (state)
            IDLE: if (!sync[1]) begin
                cnt   <= 16'd0;
                state <= START;
            end
            START: if (cnt == (CLKS_PER_BIT - 1) / 2) begin
                cnt <= 16'd0;
                if (!sync[1]) begin
                    idx   <= 3'd0;
                    state <= DATA;
                end else
                    state <= IDLE;
            end else
                cnt <= cnt + 16'd1;
            DATA: if (cnt == CLKS_PER_BIT - 1) begin
                cnt        <= 16'd0;
                data[idx]  <= sync[1];
                idx        <= idx + 3'd1;
                if (idx == 3'd7) state <= STOP;
            end else
                cnt <= cnt + 16'd1;
            STOP: if (cnt == CLKS_PER_BIT - 1) begin
                valid <= 1'b1;
                state <= IDLE;
            end else
                cnt <= cnt + 16'd1;
        endcase
    end
endmodule
