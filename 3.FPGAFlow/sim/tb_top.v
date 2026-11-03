// End-to-end test through the UART: stream load.bin (the exact bytes hil.py sends), then
// INFER frames built from vectors.hex, decode the FPGA's replies off uart_tx and compare.
`timescale 1ns/1ps
module tb_top;
    parameter MAXW = 256, N_VEC = 50, CPB = 12;
    localparam real TCLK = 83.333;

    reg clk = 0;
    always #(TCLK / 2) clk = ~clk;

    reg  rx = 1'b1;
    wire tx;
    wire [3:0] led;
    top #(.CLKS_PER_BIT(CPB), .MAXW(MAXW)) dut (.clk(clk), .btn(2'b00), .uart_rx(rx), .uart_tx(tx), .led(led));

    // host-side UART receiver on the FPGA's TX line
    wire [7:0] r_data;
    wire       r_valid;
    reg host_rst = 1'b1;
    initial begin repeat (5) @(posedge clk); host_rst <= 1'b0; end
    uart_rx #(.CLKS_PER_BIT(CPB)) host_rx (.clk(clk), .rst(host_rst), .rx(tx), .data(r_data), .valid(r_valid));

    task send_byte(input [7:0] b);
        integer k;
        begin
            rx <= 1'b0; repeat (CPB) @(posedge clk);
            for (k = 0; k < 8; k = k + 1) begin rx <= b[k]; repeat (CPB) @(posedge clk); end
            rx <= 1'b1; repeat (CPB) @(posedge clk);
        end
    endtask

    // collect replies
    reg [7:0] rb [0:4];
    integer   rn = 0, acks = 0, errs_reply = 0, infer_replies = 0, mism = 0;
    reg [7:0] exp_pred [0:N_VEC-1];
    always @(posedge clk) if (r_valid) begin
        if (rn == 0 && r_data != 8'h5A) ;            // wait for reply SOF
        else begin
            rb[rn] = r_data;
            rn = rn + 1;
            if (rn == 5) begin
                rn = 0;
                if (rb[4] != ((rb[1] + rb[2] + rb[3]) & 8'hFF)) errs_reply = errs_reply + 1;
                else if (rb[1] == 8'hEE) begin
                    errs_reply = errs_reply + 1;
                    $display("ERROR reply: code %0d type %h", rb[2], rb[3]);
                end else if (rb[1] == 8'h10) begin
                    infer_replies = infer_replies + 1;
                    if (rb[3][0] !== exp_pred[rb[2]][0]) begin
                        mism = mism + 1;
                        if (mism <= 10) $display("MISMATCH seq %0d: rtl=%b golden=%b", rb[2], rb[3][0], exp_pred[rb[2]][0]);
                    end
                end else acks = acks + 1;
            end
        end
    end

    reg [MAXW+7:0] vecs [0:N_VEC-1];
    integer fd, c, nbytes, i, k;
    reg [7:0] sum, b;

    initial begin
        $readmemh("vectors.hex", vecs);
        repeat (300) @(posedge clk);                  // power-on reset
        fd = $fopen("load.bin", "rb");
        nbytes = 0;
        c = $fgetc(fd);
        while (c != -1) begin
            send_byte(c[7:0]);
            nbytes = nbytes + 1;
            c = $fgetc(fd);
        end
        $fclose(fd);
        repeat (2000) @(posedge clk);
        $display("load: %0d bytes sent, %0d acks, %0d error replies, led=%b", nbytes, acks, errs_reply, led);

        for (i = 0; i < N_VEC; i = i + 1) begin
            exp_pred[i] = {7'd0, vecs[i][MAXW]};
            sum = 8'h10 + i[7:0] + {7'd0, vecs[i][MAXW + 4]};
            send_byte(8'hA5); send_byte(8'h10); send_byte(i[7:0]); send_byte({7'd0, vecs[i][MAXW + 4]});
            for (k = 0; k < MAXW / 8; k = k + 1) begin
                b = vecs[i][8*k +: 8];
                sum = sum + b;
                send_byte(b);
            end
            send_byte(sum);
        end
        repeat (5000) @(posedge clk);
        $display("tb_top: %0d infer frames, %0d replies, %0d mismatches, %0d error replies",
                 N_VEC, infer_replies, mism, errs_reply);
        if (mism == 0 && infer_replies == N_VEC && errs_reply == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
