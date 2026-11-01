`timescale 1ns / 1ps
// Flips 0, 1 or 2 distinct bits of an 8-bit codeword. rnd picks the positions.
module error_injector(
    input  wire [7:0] code_in,
    input  wire [1:0] mode,   // 0 = none, 1 = one bit, 2 = two bits
    input  wire [5:0] rnd,
    output wire [7:0] code_out
);
    wire [2:0] a = rnd[2:0];
    wire [2:0] b = (rnd[5:3] == a) ? a + 3'd1 : rnd[5:3];

    wire [7:0] m1 = 8'b1 << a;
    wire [7:0] m2 = 8'b1 << b;

    assign code_out = code_in ^ ((mode == 2'd0) ? 8'b0 :
                                 (mode == 2'd1) ? m1   : (m1 | m2));
endmodule
