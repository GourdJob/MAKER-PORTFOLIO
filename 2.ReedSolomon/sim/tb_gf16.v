`timescale 1ns / 1ps
// Exhaustive check of the GF(16) functions in gf16.vh against an independent log/antilog model
// built by repeated multiply-by-alpha (shift left, reduce with x^4 + x + 1).
module tb_gf16;
    `include "gf16.vh"

    reg [3:0] expt [0:14];
    reg [3:0] logt [0:15];
    integer i, a, b, errors, checks;
    reg [3:0] v, want;

    initial begin
        errors = 0;
        checks = 0;

        v = 4'h1;
        for (i = 0; i < 15; i = i + 1) begin
            expt[i] = v;
            logt[v] = i;
            v = {v[2:0], 1'b0} ^ (v[3] ? 4'h3 : 4'h0);
        end

        for (i = 0; i < 15; i = i + 1) begin
            checks = checks + 1;
            if (gf_alpha(i) !== expt[i] || gf_alpha(i - 15) !== expt[i]) begin
                errors = errors + 1;
                $display("FAIL gf_alpha(%0d) = %h, want %h", i, gf_alpha(i), expt[i]);
            end
        end

        for (a = 0; a < 16; a = a + 1)
            for (b = 0; b < 16; b = b + 1) begin
                want = (a == 0 || b == 0) ? 4'h0 : expt[(logt[a] + logt[b]) % 15];
                checks = checks + 1;
                if (gf_mul(a, b) !== want) begin
                    errors = errors + 1;
                    $display("FAIL gf_mul(%h, %h) = %h, want %h", a, b, gf_mul(a, b), want);
                end
            end

        for (a = 1; a < 16; a = a + 1) begin
            checks = checks + 1;
            v = gf_inv(a);
            if (gf_mul(a, v) !== 4'h1) begin
                errors = errors + 1;
                $display("FAIL gf_inv(%h) = %h", a, gf_inv(a));
            end
        end

        if (errors == 0) $display("PASS: tb_gf16, %0d checks", checks);
        else             $display("FAILED: tb_gf16, %0d of %0d checks failed", errors, checks);
        $finish;
    end
endmodule
