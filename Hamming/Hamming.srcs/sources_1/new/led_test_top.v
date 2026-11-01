`timescale 1ns / 1ps
// LED wiring test. Same ports as hamming_top, so it uses LED.xdc unchanged - just set it as top.
//   Default:      all 32 PIO LEDs, the 4 onboard LEDs and the RGB LED (white) are on.
//   Hold BTN0:    one PIO LED at a time walks through all 32 (4 steps/s) so you can spot
//                 swapped or missing wires. Order: J1 pins 1-8, J2 pins 48-41, J3 pins 16-23,
//                 J4 pins 31-26, then J2 pin 40, then J1 pin 9. Onboard LEDs show the step number[3:0].
module led_test_top #(
    parameter RGB_ACTIVE_LOW = 1,
    parameter LED_ACTIVE_LOW = 0,          // match hamming_top: pin -> LED -> GND
    parameter STEP_CYCLES    = 3_000_000   // 0.25 s at 12 MHz
)(
    input  wire       clk,
    input  wire [1:0] btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [3:0] led,
    output wire [2:0] rgb,
    output wire [7:0] pio_rx,
    output wire [7:0] pio_mask_hi,
    output wire [7:0] pio_mask_lo,
    output wire [2:0] pio_syn_hi,
    output wire [2:0] pio_syn_lo,
    output wire       pio_cor_hi,
    output wire       pio_unc_hi
);
    reg [1:0]  btn_sync = 2'b00;
    reg [21:0] cnt      = 22'd0;
    reg [4:0]  step     = 5'd0;

    always @(posedge clk) begin
        btn_sync <= {btn_sync[0], btn[0]};
        if (cnt == STEP_CYCLES - 1) begin
            cnt  <= 22'd0;
            step <= step + 5'd1;
        end else
            cnt <= cnt + 22'd1;
    end

    wire        chase  = btn_sync[1];
    wire [31:0] walk   = 32'h8000_0000 >> step;   // MSB first = J1 pin 1
    wire [31:0] pio_on = chase ? walk : 32'hFFFF_FFFF;
    wire [31:0] pio_out = LED_ACTIVE_LOW ? ~pio_on : pio_on;
    assign {pio_rx, pio_mask_hi, pio_mask_lo, pio_syn_hi, pio_syn_lo, pio_cor_hi, pio_unc_hi} = pio_out;

    assign led     = chase ? step[3:0] : 4'b1111;
    assign rgb     = RGB_ACTIVE_LOW ? 3'b000 : 3'b111;
    assign uart_tx = 1'b1;   // UART idle
endmodule
