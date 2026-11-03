`timescale 1ns / 1ps
// End-to-end test: drives the UART pin, presses BTN0 to change the injection mode,
// and checks the recovered byte, status byte and PIO LED snapshot for each mode,
// plus a back-to-back burst that exercises the RX FIFO.
module tb_hamming_top;
    localparam CPB = 16;
    localparam real T = 83.333;   // 12 MHz clock period in ns

    reg        clk = 0;
    reg  [1:0] btn = 2'b00;
    reg        rx  = 1'b1;
    wire       tx;
    wire [3:0] led;
    wire [2:0] rgb;
    wire [7:0] pio_rx, pio_mask_hi, pio_mask_lo;
    wire [2:0] pio_syn_hi, pio_syn_lo;
    wire       pio_cor_hi, pio_unc_hi;

    hamming_top #(.CLKS_PER_BIT(CPB), .DEBOUNCE_CYCLES(4), .RGB_ACTIVE_LOW(0), .LED_ACTIVE_LOW(0)) dut (
        .clk(clk), .btn(btn), .uart_rx(rx), .uart_tx(tx), .led(led), .rgb(rgb),
        .pio_rx(pio_rx), .pio_mask_hi(pio_mask_hi), .pio_mask_lo(pio_mask_lo),
        .pio_syn_hi(pio_syn_hi), .pio_syn_lo(pio_syn_lo), .pio_cor_hi(pio_cor_hi), .pio_unc_hi(pio_unc_hi)
    );

    always #41.667 clk = ~clk;

    integer errors = 0;
    integer n;
    reg [7:0] got, status, sent;
    reg [7:0] burst_got [0:11];

    task send_byte(input [7:0] b);
        integer n;
        begin
            rx = 0; #(T * CPB);
            for (n = 0; n < 8; n = n + 1) begin rx = b[n]; #(T * CPB); end
            rx = 1; #(T * CPB);
        end
    endtask

    task recv_byte(output [7:0] b);
        integer n;
        begin
            @(negedge tx);
            #(T * CPB * 1.5);
            for (n = 0; n < 8; n = n + 1) begin b[n] = tx; #(T * CPB); end
        end
    endtask

    task xfer(input [7:0] sent, output [7:0] got, output [7:0] status);
        begin
            fork
                send_byte(sent);
                begin recv_byte(got); recv_byte(status); end
            join
        end
    endtask

    function integer popcount(input [7:0] v);
        integer k;
        begin
            popcount = 0;
            for (k = 0; k < 8; k = k + 1) popcount = popcount + v[k];
        end
    endfunction

    // PIO snapshot must match the byte just processed and the expected number of flips per nibble
    task check_pio(input [7:0] sent, input integer flips);
        begin
            if (pio_rx !== sent || popcount(pio_mask_hi) != flips || popcount(pio_mask_lo) != flips
                || pio_unc_hi !== (flips == 2) || pio_cor_hi !== (flips == 1)) begin
                errors = errors + 1;
                $display("FAIL pio: sent %h pio_rx %h mask_hi %b mask_lo %b cor %b unc %b (expected %0d flips)",
                         sent, pio_rx, pio_mask_hi, pio_mask_lo, pio_cor_hi, pio_unc_hi, flips);
            end
        end
    endtask

    task press_btn0;
        begin
            btn[0] = 1; #(T * 20);
            btn[0] = 0; #(T * 20);
        end
    endtask

    initial begin
        #(T * 50);

        // mode 0: clean
        for (n = 0; n < 20; n = n + 1) begin
            sent = n * 13 + 5;
            xfer(sent, got, status);
            if (got !== sent || status !== "O") begin
                errors = errors + 1;
                $display("FAIL mode0: sent %h got %h status %c", sent, got, status);
            end
            check_pio(sent, 0);
            if (pio_syn_hi !== 3'd0 || pio_syn_lo !== 3'd0) begin
                errors = errors + 1;
                $display("FAIL mode0: nonzero syndrome %b %b", pio_syn_hi, pio_syn_lo);
            end
        end

        // burst: 6 bytes back to back, replies must all come back in order
        fork
            for (n = 0; n < 6; n = n + 1) send_byte(8'hA0 + n);
            begin : burst_rx
                integer m;
                for (m = 0; m < 12; m = m + 1) recv_byte(burst_got[m]);
            end
        join
        for (n = 0; n < 6; n = n + 1)
            if (burst_got[2*n] !== 8'hA0 + n || burst_got[2*n+1] !== "O") begin
                errors = errors + 1;
                $display("FAIL burst: byte %0d got %h status %c", n, burst_got[2*n], burst_got[2*n+1]);
            end

        // mode 1: one flip per nibble, always corrected
        press_btn0;
        if (led[1:0] !== 2'd1) begin errors = errors + 1; $display("FAIL: mode not 1"); end
        for (n = 0; n < 60; n = n + 1) begin
            sent = n * 37 + 11;
            xfer(sent, got, status);
            if (got !== sent || status !== "C") begin
                errors = errors + 1;
                $display("FAIL mode1: sent %h got %h status %c", sent, got, status);
            end
            check_pio(sent, 1);
        end

        // mode 2: two flips per nibble, always flagged
        press_btn0;
        if (led[1:0] !== 2'd2) begin errors = errors + 1; $display("FAIL: mode not 2"); end
        for (n = 0; n < 60; n = n + 1) begin
            sent = n * 53 + 7;
            xfer(sent, got, status);
            if (status !== "X") begin
                errors = errors + 1;
                $display("FAIL mode2: sent %h got %h status %c", sent, got, status);
            end
            check_pio(sent, 2);
        end
        if (rgb !== 3'b001 || led[2] !== 1'b1) begin errors = errors + 1; $display("FAIL: LED/RGB not red after X"); end

        press_btn0;
        xfer(8'h3C, got, status);
        if (led[1:0] !== 2'd0 || got !== 8'h3C || status !== "O") begin
            errors = errors + 1;
            $display("FAIL wrap: mode %0d got %h status %c", led[1:0], got, status);
        end

        if (errors == 0) $display("PASS: tb_hamming_top");
        else             $display("FAILED: tb_hamming_top, %0d errors", errors);
        $finish;
    end

    initial begin
        #200_000_000;
        $display("FAILED: tb_hamming_top timeout");
        $finish;
    end
endmodule
