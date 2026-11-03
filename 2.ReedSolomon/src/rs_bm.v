`timescale 1ns / 1ps
// Berlekamp-Massey: finds the error-locator polynomial Lambda(x) from the syndromes.
// Blahut's form, one iteration per clock, 2t = 4 iterations:
//   delta  = sum_j Lambda_j * S_(r-j)                    (discrepancy)
//   Lambda <= Lambda - delta * x * B(x)
//   if delta != 0 and 2L <= r-1:  B <= Lambda / delta,  L <= r - L     (length change)
//   else:                         B <= x * B(x)
// Lambda's roots are the inverses of the error locations; L = number of errors it explains.
module rs_bm(
    input  wire        clk,
    input  wire        rst,
    input  wire        start,     // one-cycle pulse, s must be stable until done
    input  wire [15:0] s,         // {S4, S3, S2, S1}
    output reg  [19:0] lambda = 20'h00001,   // {L4, L3, L2, L1, L0}
    output reg  [2:0]  len    = 3'd0,        // L
    output reg         done   = 1'b0         // one-cycle pulse when lambda/len are final
);
    `include "gf16.vh"

    reg [19:0] b    = 20'h00001;
    reg [2:0]  r    = 3'd1;       // iteration 1..4
    reg        busy = 1'b0;

    // S_k for k = 1..4, zero outside that range
    function [3:0] syn(input integer k);
        syn = (k >= 1 && k <= 4) ? s[4*(k-1) +: 4] : 4'h0;
    endfunction

    // (function results go through temporaries: xsim mis-evaluates a function call nested in another's arguments)
    reg [3:0]  delta, dinv, sk;
    reg [19:0] xb, lam_next, b_next;
    reg [2:0]  len_next;
    reg        grow;
    integer j, ri;

    always @* begin
        ri    = r;
        delta = 4'h0;
        for (j = 0; j < 5; j = j + 1) begin
            sk    = syn(ri - j);
            delta = delta ^ gf_mul(lambda[4*j +: 4], sk);
        end

        xb   = {b[15:0], 4'h0};                       // x * B(x), truncated to degree 4
        grow = (delta != 4'h0) && ({len, 1'b0} <= r - 3'd1);
        dinv = gf_inv(delta);

        for (j = 0; j < 5; j = j + 1) begin
            lam_next[4*j +: 4] = lambda[4*j +: 4] ^ gf_mul(delta, xb[4*j +: 4]);
            b_next[4*j +: 4]   = grow ? gf_mul(dinv, lambda[4*j +: 4]) : xb[4*j +: 4];
        end
        len_next = grow ? r - len : len;
    end

    always @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            busy <= 1'b0;
        end else if (start) begin
            lambda <= 20'h00001;
            b      <= 20'h00001;
            len    <= 3'd0;
            r      <= 3'd1;
            busy   <= 1'b1;
        end else if (busy) begin
            lambda <= lam_next;
            b      <= b_next;
            len    <= len_next;
            r      <= r + 3'd1;
            if (r == 3'd4) begin
                busy <= 1'b0;
                done <= 1'b1;
            end
        end
    end
endmodule
