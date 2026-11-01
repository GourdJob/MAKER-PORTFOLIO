// GF(16) arithmetic, primitive polynomial x^4 + x + 1 (alpha = 4'h2).
// Include inside a module body:  `include "gf16.vh"
// Addition in GF(2^m) is XOR, so there is no gf_add.

// Multiply: carry-less product of two degree-3 polynomials, reduced with
// x^4 = x + 1, x^5 = x^2 + x, x^6 = x^3 + x^2.
function [3:0] gf_mul(input [3:0] a, input [3:0] b);
    reg [6:0] p;
    begin
        p[0] =  a[0]&b[0];
        p[1] = (a[1]&b[0]) ^ (a[0]&b[1]);
        p[2] = (a[2]&b[0]) ^ (a[1]&b[1]) ^ (a[0]&b[2]);
        p[3] = (a[3]&b[0]) ^ (a[2]&b[1]) ^ (a[1]&b[2]) ^ (a[0]&b[3]);
        p[4] = (a[3]&b[1]) ^ (a[2]&b[2]) ^ (a[1]&b[3]);
        p[5] = (a[3]&b[2]) ^ (a[2]&b[3]);
        p[6] =  a[3]&b[3];
        gf_mul = {p[3] ^ p[6], p[2] ^ p[5] ^ p[6], p[1] ^ p[4] ^ p[5], p[0] ^ p[4]};
    end
endfunction

// Multiplicative inverse (gf_inv(0) returns 0; callers never divide by zero).
function [3:0] gf_inv(input [3:0] a);
    case (a)
        4'h1: gf_inv = 4'h1;  4'h2: gf_inv = 4'h9;  4'h3: gf_inv = 4'hE;  4'h4: gf_inv = 4'hD;
        4'h5: gf_inv = 4'hB;  4'h6: gf_inv = 4'h7;  4'h7: gf_inv = 4'h6;  4'h8: gf_inv = 4'hF;
        4'h9: gf_inv = 4'h2;  4'hA: gf_inv = 4'hC;  4'hB: gf_inv = 4'h5;  4'hC: gf_inv = 4'hA;
        4'hD: gf_inv = 4'h4;  4'hE: gf_inv = 4'h3;  4'hF: gf_inv = 4'h8;
        default: gf_inv = 4'h0;
    endcase
endfunction

// alpha^k for any integer k (taken mod 15, negative k allowed). Used with constant k.
function [3:0] gf_alpha(input integer k);
    integer e;
    begin
        e = ((k % 15) + 15) % 15;
        case (e)
            0:  gf_alpha = 4'h1;  1:  gf_alpha = 4'h2;  2:  gf_alpha = 4'h4;  3:  gf_alpha = 4'h8;
            4:  gf_alpha = 4'h3;  5:  gf_alpha = 4'h6;  6:  gf_alpha = 4'hC;  7:  gf_alpha = 4'hB;
            8:  gf_alpha = 4'h5;  9:  gf_alpha = 4'hA;  10: gf_alpha = 4'h7;  11: gf_alpha = 4'hE;
            12: gf_alpha = 4'hF;  13: gf_alpha = 4'hD;  default: gf_alpha = 4'h9;
        endcase
    end
endfunction
