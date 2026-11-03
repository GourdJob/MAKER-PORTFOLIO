`timescale 1ns / 1ps
// Free-running 16-bit Fibonacci LFSR, polynomial x^16 + x^15 + x^13 + x^4 + 1.
module lfsr16(
    input  wire        clk,
    output wire [15:0] q_out
);
    reg [15:0] q = 16'hACE1;
    always @(posedge clk)
        q <= {q[14:0], q[15] ^ q[14] ^ q[12] ^ q[3]};
    assign q_out = q;
endmodule
