`timescale 1ns / 1ps
// End-to-end test at the UART pins: sends 2-byte messages, presses BTN0 through modes 0..3 and checks
// the 10-byte reply, the injected/fixed masks, the display sequencer and the lone-byte timeout.
module tb_rs_top;
    localparam CPB  = 16;
    localparam SHOW = 4000;       // longer than a 10-byte reply (~1600 clocks), so the corrupted phase is still up
    localparam TOUT = 2000;
    localparam real T = 83.333;

    reg        clk = 0;
    reg  [1:0] btn = 2'b00;
    reg        rx  = 1'b1;
    wire       tx;
    wire [3:0] led;
    wire [2:0] rgb;
    wire [7:0] seg, dig;

    rs_top #(.CLKS_PER_BIT(CPB), .DEBOUNCE_CYCLES(4), .RX_TIMEOUT(TOUT), .SHOW_CYCLES(SHOW),
             .DIGIT_CYCLES(8), .BLANK_CYCLES(2), .RGB_ACTIVE_LOW(0)) dut (
        .clk(clk), .btn(btn), .uart_rx(rx), .uart_tx(tx), .led(led), .rgb(rgb), .seg(seg), .dig(dig)
    );

    always #41.667 clk = ~clk;

    integer errors = 0;
    integer miscorrected = 0, detected = 0;
    integer n, k;
    reg [7:0]  reply [0:9];
    reg [15:0] msg;
    reg [31:0] rx_word, diff;
    reg [7:0]  diff_mask;

    // reference encoder for checking the corrupted word
    wire [31:0] ref_code;
    rs_encoder ref_enc (.msg(msg), .code(ref_code));

    // never more than one digit on at a time
    always @(posedge clk)
        if ((dig & (dig - 8'd1)) != 8'd0) begin
            errors = errors + 1;
            $display("FAIL: more than one digit enabled (%b)", dig);
        end

    task send_byte(input [7:0] b);
        integer i;
        begin
            rx = 0; #(T * CPB);
            for (i = 0; i < 8; i = i + 1) begin rx = b[i]; #(T * CPB); end
            rx = 1; #(T * CPB);
        end
    endtask

    task recv_byte(output [7:0] b);
        integer i;
        begin
            @(negedge tx);
            #(T * CPB * 1.5);
            for (i = 0; i < 8; i = i + 1) begin b[i] = tx; #(T * CPB); end
        end
    endtask

    task xfer(input [15:0] m);
        integer i;
        begin
            msg = m;
            fork
                begin send_byte(m[15:8]); send_byte(m[7:0]); end
                for (i = 0; i < 10; i = i + 1) recv_byte(reply[i]);
            join
            rx_word = {reply[0], reply[1], reply[2], reply[3]};
            diff    = rx_word ^ ref_code;
            for (i = 0; i < 8; i = i + 1) diff_mask[i] = (diff[4*i +: 4] != 4'h0);
        end
    endtask

    task press_btn0;
        begin
            btn[0] = 1; #(T * 20);
            btn[0] = 0; #(T * 20);
        end
    endtask

    function integer popcount(input [7:0] v);
        integer i;
        begin
            popcount = 0;
            for (i = 0; i < 8; i = i + 1) popcount = popcount + v[i];
        end
    endfunction

    task fail_msg(input [127:0] what);
        begin
            errors = errors + 1;
            $display("FAIL %0s: msg %h rx %h decoded %h%h status %c fixed %c inj %b fixedmask %b",
                     what, msg, rx_word, reply[4], reply[5], reply[6], reply[7], reply[8], reply[9]);
        end
    endtask

    // check one reply in a correctable mode (0, 1 or 2 injected symbols)
    task check_ok(input integer nerr);
        begin
            if ({reply[4], reply[5]} !== msg)                     fail_msg("data");
            if (reply[6] !== ((nerr == 0) ? "O" : "C"))           fail_msg("status");
            if (reply[7] !== "0" + nerr)                          fail_msg("count");
            if (popcount(reply[8]) != nerr || reply[9] !== reply[8]) fail_msg("masks");
            if (diff_mask !== reply[8])                           fail_msg("inj positions");
        end
    endtask

    initial begin
        #(T * 50);

        // display is blank until the first word
        if (dig !== 8'h00) begin errors = errors + 1; $display("FAIL: display not blank at start"); end

        // mode 0
        for (n = 0; n < 10; n = n + 1) begin xfer(n * 16'h1357 + 16'h0042); check_ok(0); end

        // display: corrupted phase first, corrected phase after SHOW cycles
        if (dut.show_fixed !== 1'b0) begin errors = errors + 1; $display("FAIL: display skipped corrupted phase"); end
        #(T * (SHOW + 20));
        if (dut.show_fixed !== 1'b1) begin errors = errors + 1; $display("FAIL: display never reached corrected phase"); end

        // modes 1 and 2: always corrected
        press_btn0;
        if (led[1:0] !== 2'd1) begin errors = errors + 1; $display("FAIL: mode not 1"); end
        for (n = 0; n < 40; n = n + 1) begin xfer(n * 16'h2B17 + 16'h0101); check_ok(1); end
        press_btn0;
        if (led[1:0] !== 2'd2) begin errors = errors + 1; $display("FAIL: mode not 2"); end
        for (n = 0; n < 40; n = n + 1) begin xfer(n * 16'h3D29 + 16'h7007); check_ok(2); end
        if (rgb !== 3'b011) begin errors = errors + 1; $display("FAIL: RGB not yellow after corrections"); end

        // mode 3: beyond t = 2 - never 'O', never a silently right answer, positions still reported
        press_btn0;
        if (led[1:0] !== 2'd3) begin errors = errors + 1; $display("FAIL: mode not 3"); end
        for (n = 0; n < 40; n = n + 1) begin
            xfer(n * 16'h4F3B + 16'h0C0C);
            if (popcount(reply[8]) != 3 || diff_mask !== reply[8]) fail_msg("mode3 injection");
            if (reply[6] == "X") begin
                detected = detected + 1;
                if ({reply[4], reply[5]} !== rx_word[31:16] || reply[9] !== 8'h00) fail_msg("X passthrough");
                #(T * (SHOW + 20));
                if (!dut.u_disp.dashes) fail_msg("no dashes on X");
            end else if (reply[6] == "C" && {reply[4], reply[5]} !== msg)
                miscorrected = miscorrected + 1;
            else
                fail_msg("mode3 status");
        end

        // wrap to mode 0, then a lone byte must time out and not shift the pairing
        press_btn0;
        send_byte(8'hEE);
        #(T * (TOUT + 100));
        xfer(16'hBEEF);
        check_ok(0);

        if (errors == 0)
            $display("PASS: tb_rs_top (mode 3: %0d detected, %0d miscorrected)", detected, miscorrected);
        else
            $display("FAILED: tb_rs_top, %0d errors", errors);
        $finish;
    end

    initial begin
        #500_000_000;
        $display("FAILED: tb_rs_top timeout");
        $finish;
    end
endmodule
