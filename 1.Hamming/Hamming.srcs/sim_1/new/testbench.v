`timescale 1ns / 1ps

module led_blink_tb;

    reg clk;
    reg reset;
    wire led;

    // Instantiate Unit Under Test (UUT)
    led_blink uut (
        .clk(clk),
        .reset(reset),
        .led(led)
    );

    // Generate 100 MHz clock 
    always #5 clk = ~clk;

    initial begin
        // Initialize signals
        clk = 0;
        reset = 1;
        
        // Hold reset for 20 ns
        #20;
        reset = 0; 

        #2000000;
        $finish;
    end

endmodule
