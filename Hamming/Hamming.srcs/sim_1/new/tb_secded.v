`timescale 1ns / 1ps
// Exhaustive self-checking test of the SECDED(8,4) encoder/decoder/injector.
module tb_secded;
    reg  [3:0] d;
    reg  [7:0] mask;
    wire [7:0] code;
    wire [3:0] dec;
    wire [2:0] syn;
    wire       cor, unc;

    secded_encoder enc (.data(d), .code(code));
    secded_decoder dcd (.code(code ^ mask), .data(dec), .syndrome(syn), .corrected(cor), .uncorrectable(unc));

    reg  [7:0] inj_in;
    reg  [1:0] inj_mode;
    reg  [5:0] inj_rnd;
    wire [7:0] inj_out;
    error_injector inj (.code_in(inj_in), .mode(inj_mode), .rnd(inj_rnd), .code_out(inj_out));

    integer errors = 0;
    integer checks = 0;
    integer i, j, k;

    function integer popcount(input [7:0] v);
        integer n;
        begin
            popcount = 0;
            for (n = 0; n < 8; n = n + 1) popcount = popcount + v[n];
        end
    endfunction

    task check(input cond, input [255:0] what);
        begin
            checks = checks + 1;
            if (!cond) begin
                errors = errors + 1;
                $display("FAIL d=%h mask=%b: %0s (dec=%h syn=%b cor=%b unc=%b)", d, mask, what, dec, syn, cor, unc);
            end
        end
    endtask

    initial begin
        for (k = 0; k < 16; k = k + 1) begin
            d = k[3:0];

            mask = 8'h00; #1;
            check(dec == d && !cor && !unc && syn == 3'd0, "no error");

            for (i = 0; i < 8; i = i + 1) begin
                mask = 8'b1 << i; #1;
                check(dec == d,          "single: data recovered");
                check(cor && !unc,       "single: flagged corrected");
                check(syn == i[2:0],     "single: syndrome = position");
            end

            for (i = 0; i < 8; i = i + 1)
                for (j = i + 1; j < 8; j = j + 1) begin
                    mask = (8'b1 << i) | (8'b1 << j); #1;
                    check(unc && !cor, "double: flagged uncorrectable");
                end
        end

        inj_in = 8'hA5;
        for (i = 0; i < 3; i = i + 1)
            for (j = 0; j < 64; j = j + 1) begin
                inj_mode = i[1:0];
                inj_rnd  = j[5:0];
                #1;
                checks = checks + 1;
                if (popcount(inj_in ^ inj_out) != i) begin
                    errors = errors + 1;
                    $display("FAIL injector mode=%0d rnd=%0d flipped %0d bits", i, j, popcount(inj_in ^ inj_out));
                end
            end

        if (errors == 0) $display("PASS: tb_secded, %0d checks", checks);
        else             $display("FAILED: tb_secded, %0d of %0d checks failed", errors, checks);
        $finish;
    end
endmodule
