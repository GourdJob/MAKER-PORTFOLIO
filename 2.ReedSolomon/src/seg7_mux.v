`timescale 1ns / 1ps
// 8-digit multiplexed seven-segment driver. Lights one digit at a time, DIGIT_CYCLES each,
// with all segments off for the first BLANK_CYCLES of every slot to stop ghosting.
// Digit 0 is the leftmost and shows sym[31:28] (codeword symbol c7); digit 7 shows sym[3:0] (c0).
// seg = {dp, g, f, e, d, c, b, a}. Defaults suit common-cathode displays with NPN digit transistors.
module seg7_mux #(
    parameter DIGIT_CYCLES   = 12000,   // 1 ms per digit at 12 MHz -> 125 Hz refresh
    parameter BLANK_CYCLES   = 600,
    parameter SEG_ACTIVE_LOW = 0,
    parameter DIG_ACTIVE_LOW = 0
)(
    input  wire        clk,
    input  wire [31:0] sym,       // 8 hex symbols {c7..c0}
    input  wire [7:0]  dp,        // bit i = decimal point under symbol c_i
    input  wire        dashes,    // show "--------" instead of sym
    input  wire        blank,     // all digits off
    output wire [7:0]  seg,
    output wire [7:0]  dig        // dig[0] = leftmost digit
);
    reg [15:0] cnt = 16'd0;
    reg [2:0]  idx = 3'd0;        // digit being shown

    always @(posedge clk) begin
        if (cnt == DIGIT_CYCLES - 1) begin
            cnt <= 16'd0;
            idx <= idx + 3'd1;
        end else
            cnt <= cnt + 16'd1;
    end

    wire [2:0] sym_i = 3'd7 - idx;                 // digit 0 shows c7
    wire [3:0] nib   = sym[4*sym_i +: 4];

    reg [6:0] gfedcba;
    always @* begin
        case (nib)
            4'h0: gfedcba = 7'h3F;  4'h1: gfedcba = 7'h06;  4'h2: gfedcba = 7'h5B;  4'h3: gfedcba = 7'h4F;
            4'h4: gfedcba = 7'h66;  4'h5: gfedcba = 7'h6D;  4'h6: gfedcba = 7'h7D;  4'h7: gfedcba = 7'h07;
            4'h8: gfedcba = 7'h7F;  4'h9: gfedcba = 7'h6F;  4'hA: gfedcba = 7'h77;  4'hB: gfedcba = 7'h7C;
            4'hC: gfedcba = 7'h39;  4'hD: gfedcba = 7'h5E;  4'hE: gfedcba = 7'h79;  default: gfedcba = 7'h71;
        endcase
    end

    wire       on      = !blank && (cnt >= BLANK_CYCLES);
    wire [7:0] seg_on  = !on    ? 8'h00 :
                         dashes ? 8'h40 : {dp[sym_i], gfedcba};
    wire [7:0] dig_on  = on ? (8'd1 << idx) : 8'h00;

    assign seg = SEG_ACTIVE_LOW ? ~seg_on : seg_on;
    assign dig = DIG_ACTIVE_LOW ? ~dig_on : dig_on;
endmodule
