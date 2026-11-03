`timescale 1ns / 1ps
// Syndromes S_j = r(alpha^j) = sum_i r_i * alpha^(j*i), j = 1..4.
// All zero <=> the received word is a valid codeword.
module rs_syndrome(
    input  wire [31:0] r,       // {r7..r0}
    output reg  [15:0] s        // {S4, S3, S2, S1}
);
    `include "gf16.vh"

    // (function results go through temporaries: xsim mis-evaluates a function call nested in another's arguments)
    integer i, j;
    reg [3:0] a;
    always @* begin
        s = 16'h0000;
        for (j = 1; j <= 4; j = j + 1)
            for (i = 0; i < 8; i = i + 1) begin
                a = gf_alpha(j * i);
                s[4*(j-1) +: 4] = s[4*(j-1) +: 4] ^ gf_mul(r[4*i +: 4], a);
            end
    end
endmodule
