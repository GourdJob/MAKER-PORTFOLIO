`timescale 1ns / 1ps
// Corrupts 0..3 distinct symbols of an 8-symbol codeword with random nonzero error values.
// rnd picks the positions (rnd[8:0]) and the values (rnd[20:9]).
module symbol_injector(
    input  wire [31:0] code_in,
    input  wire [1:0]  mode,      // number of symbols to corrupt
    input  wire [20:0] rnd,
    output wire [31:0] code_out,
    output wire [7:0]  inj_mask   // bit i = symbol c_i was corrupted
);
    // three distinct positions: bump b past a, then c past a and b (two bumps always suffice)
    wire [2:0] a  = rnd[2:0];
    wire [2:0] b  = (rnd[5:3] == a) ? a + 3'd1 : rnd[5:3];
    wire [2:0] c0 = rnd[8:6];
    wire [2:0] c1 = (c0 == a || c0 == b) ? c0 + 3'd1 : c0;
    wire [2:0] c  = (c1 == a || c1 == b) ? c1 + 3'd1 : c1;

    // nonzero error values
    wire [3:0] ea = (rnd[12:9]  == 4'h0) ? 4'hF : rnd[12:9];
    wire [3:0] eb = (rnd[16:13] == 4'h0) ? 4'hF : rnd[16:13];
    wire [3:0] ec = (rnd[20:17] == 4'h0) ? 4'hF : rnd[20:17];

    wire [31:0] pat_a = (mode >= 2'd1) ? ({28'd0, ea} << (4 * a)) : 32'd0;
    wire [31:0] pat_b = (mode >= 2'd2) ? ({28'd0, eb} << (4 * b)) : 32'd0;
    wire [31:0] pat_c = (mode == 2'd3) ? ({28'd0, ec} << (4 * c)) : 32'd0;

    assign code_out = code_in ^ pat_a ^ pat_b ^ pat_c;
    assign inj_mask = ((mode >= 2'd1) ? (8'd1 << a) : 8'd0) |
                      ((mode >= 2'd2) ? (8'd1 << b) : 8'd0) |
                      ((mode == 2'd3) ? (8'd1 << c) : 8'd0);
endmodule
