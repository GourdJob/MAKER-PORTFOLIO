//////////////////////////////////////////////////////////////////////////////////
// Company: Johnathan .Co
// Engineer: Johnathan Chen
// 
// Create Date: 
// Design Name: 
// Module Name: ClockDivider
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////

`timescale 1ns / 1ps
// counter based
module clock_divider(
    input wire clk, // 100MHz
    output reg divided_clk =0 // 1Hz => 0.5s ON and 0.5s OFF
);
    localparam div_value = 6024096;

    //counter
    integer counter_value = 0; // 32 bit vide reg bus

    always@ (posedge clk )// sensitivity list // rising edge 0-1
    begin
        // keep counting until 1000
        if (counter_value == div_value)
            counter_value <= 0; // reset value
        else
            counter_value <= counter_value+1; //count 
    end

    // divide clock
    always@ (posedge clk)
    begin
        if(counter_value == div_value)
            divided_clk <= ~divided_clk; // flip the signal
        else
            divided_clk <= divided_clk; // store value
    end
endmodule
