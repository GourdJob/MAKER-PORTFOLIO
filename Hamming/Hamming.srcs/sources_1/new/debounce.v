`timescale 1ns / 1ps
// Synchronizes and debounces a button. `clean` is the stable level, `pulse` is one clock on a press.
module debounce #(
    parameter CYCLES = 120000   // 10 ms at 12 MHz
)(
    input  wire clk,
    input  wire noisy,
    output reg  clean = 1'b0,
    output reg  pulse = 1'b0
);
    reg [1:0]  s   = 2'b00;
    reg [23:0] cnt = 24'd0;

    always @(posedge clk) begin
        s     <= {s[0], noisy};
        pulse <= 1'b0;
        if (s[1] == clean)
            cnt <= 24'd0;
        else if (cnt == CYCLES - 1) begin
            clean <= s[1];
            pulse <= s[1];
            cnt   <= 24'd0;
        end else
            cnt <= cnt + 24'd1;
    end
endmodule
