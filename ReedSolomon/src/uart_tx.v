`timescale 1ns / 1ps
// 8N1 UART transmitter. Pulse `start` while `busy` is low to send `data`.
module uart_tx #(
    parameter CLKS_PER_BIT = 104   // 12 MHz / 115200
)(
    input  wire       clk,
    input  wire [7:0] data,
    input  wire       start,
    output reg        busy = 1'b0,
    output reg        tx   = 1'b1
);
    reg [15:0] cnt    = 16'd0;
    reg [3:0]  idx    = 4'd0;
    reg [9:0]  shreg  = 10'h3FF;

    always @(posedge clk) begin
        if (!busy) begin
            if (start) begin
                shreg <= {1'b1, data, 1'b0};
                busy  <= 1'b1;
                cnt   <= 16'd0;
                idx   <= 4'd0;
                tx    <= 1'b0;
            end
        end else if (cnt == CLKS_PER_BIT - 1) begin
            cnt <= 16'd0;
            if (idx == 4'd9) begin
                busy <= 1'b0;
                tx   <= 1'b1;
            end else begin
                idx <= idx + 4'd1;
                tx  <= shreg[idx + 4'd1];
            end
        end else
            cnt <= cnt + 16'd1;
    end
endmodule
