`timescale 1ns / 1ps
// Systematic RS(8,4) encoder over GF(16).
// parity(x) = m(x) * x^4 mod g(x), g(x) = (x+a)(x+a^2)(x+a^3)(x+a^4) = x^4 + D x^3 + C x^2 + 8 x + 7
// (g(x) printed by tools/rs_ref.py). The 4-stage LFSR divider is unrolled over the 4 data symbols.
// code[31:0] = {c7..c0}: c7..c4 = data m3..m0, c3..c0 = parity.
module rs_encoder(
    input  wire [15:0] msg,     // {m3, m2, m1, m0}
    output wire [31:0] code
);
    `include "gf16.vh"

    localparam [3:0] G0 = 4'h7, G1 = 4'h8, G2 = 4'hC, G3 = 4'hD;

    reg [3:0] p0, p1, p2, p3, fb;
    integer k;

    always @* begin
        {p3, p2, p1, p0} = 16'h0000;
        for (k = 3; k >= 0; k = k - 1) begin   // m3 first
            fb = msg[4*k +: 4] ^ p3;
            p3 = p2 ^ gf_mul(fb, G3);
            p2 = p1 ^ gf_mul(fb, G2);
            p1 = p0 ^ gf_mul(fb, G1);
            p0 =      gf_mul(fb, G0);
        end
    end

    assign code = {msg, p3, p2, p1, p0};
endmodule
