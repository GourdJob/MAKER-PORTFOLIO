`timescale 1ns / 1ps
// Chien search + Forney algorithm, combinational, all 8 positions in parallel.
//   Chien:   position i is in error  <=>  Lambda(alpha^-i) == 0
//   Forney:  e_i = Omega(alpha^-i) / Lambda'(alpha^-i)        (fcr = 1)
//            Omega(x) = S(x) * Lambda(x) mod x^4,  S(x) = S1 + S2 x + S3 x^2 + S4 x^3
//            Lambda'(x) = Lambda1 + Lambda3 x^2              (formal derivative, char 2)
// fail (uncorrectable) when L > 2, the number of roots in 0..7 differs from L
// (some roots would sit in the shortened-away positions 8..14), or an error value is unusable.
module rs_chien_forney(
    input  wire [19:0] lambda,     // {L4..L0}
    input  wire [2:0]  len,
    input  wire [15:0] s,          // {S4, S3, S2, S1}
    output reg  [31:0] err_val,    // e_i at [4i+3:4i], zero where no error
    output reg  [7:0]  err_mask,   // bit i = error located at symbol i
    output reg  [3:0]  nroots,
    output reg         fail
);
    `include "gf16.vh"

    wire [3:0] l0 = lambda[3:0],   l1 = lambda[7:4],   l2 = lambda[11:8],
               l3 = lambda[15:12], l4 = lambda[19:16];

    // (function results go through temporaries: xsim mis-evaluates a function call nested in another's arguments)
    reg [15:0] omega;              // {W3, W2, W1, W0}
    reg [3:0]  xinv, x2, x3, x4, lval, wval, dval, dinv;
    reg        bad;
    integer i, j, k;

    always @* begin
        omega = 16'h0000;
        for (k = 0; k < 4; k = k + 1)
            for (j = 0; j <= k; j = j + 1)
                omega[4*k +: 4] = omega[4*k +: 4] ^ gf_mul(lambda[4*j +: 4], s[4*(k-j) +: 4]);

        err_val  = 32'd0;
        err_mask = 8'd0;
        nroots   = 4'd0;
        bad      = 1'b0;
        for (i = 0; i < 8; i = i + 1) begin
            xinv = gf_alpha(-i);
            x2   = gf_mul(xinv, xinv);
            x3   = gf_mul(x2, xinv);
            x4   = gf_mul(x3, xinv);
            lval = l0 ^ gf_mul(l1, xinv) ^ gf_mul(l2, x2) ^ gf_mul(l3, x3) ^ gf_mul(l4, x4);
            wval = omega[3:0] ^ gf_mul(omega[7:4], xinv) ^ gf_mul(omega[11:8], x2) ^ gf_mul(omega[15:12], x3);
            dval = l1 ^ gf_mul(l3, x2);
            dinv = gf_inv(dval);
            if (lval == 4'h0) begin
                err_mask[i]       = 1'b1;
                nroots            = nroots + 4'd1;
                err_val[4*i +: 4] = gf_mul(wval, dinv);
                if (dval == 4'h0 || err_val[4*i +: 4] == 4'h0)
                    bad = 1'b1;
            end
        end
        fail = bad || (len > 3'd2) || (nroots != {1'b0, len});
    end
endmodule
