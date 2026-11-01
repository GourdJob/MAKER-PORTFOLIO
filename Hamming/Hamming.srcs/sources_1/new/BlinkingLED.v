`timescale 1ns / 1ps
module top(
    input wire clk, // 12MHz
    output wire PIO26_C,PIO27_C,PIO28_C,PIO29_C 
);

    wire divided_clk;

    clock_divider u_clock_divider (
        .clk(clk),
        .divided_clk(divided_clk)
    );

    assign PIO26_C = divided_clk;
    assign PIO27_C = divided_clk;
    assign PIO28_C = divided_clk;
    assign PIO29_C = divided_clk;

endmodule