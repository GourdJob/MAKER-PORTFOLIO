`timescale 1ns / 1ps
// Encoder + decoder against tools/rs_ref.py (vectors.mem): every message's codeword must have zero
// syndromes, and every 0/1/2/3-symbol error case must give exactly the reference decoder's result
// (corrected word, fail flag, number fixed, fixed positions).
// Vector line: msg[95:80] errpat[79:48] exp_word[47:16] fail[15:12] nfixed[11:8] mask[7:0]
module tb_rs_codec;
    localparam MAXV = 8192;

    reg clk = 0;
    always #41.667 clk = ~clk;

    reg [95:0] vec [0:MAXV-1];

    reg  [15:0] msg = 16'd0;
    wire [31:0] code;
    wire [15:0] code_syn;
    rs_encoder  enc (.msg(msg), .code(code));
    rs_syndrome syn (.r(code), .s(code_syn));

    reg  [31:0] received = 32'd0;
    reg         start    = 1'b0;
    wire [31:0] corrected;
    wire [7:0]  fixed_mask;
    wire [1:0]  nfixed;
    wire        fail, done;
    rs_decoder dec (.clk(clk), .rst(1'b0), .start(start), .received(received),
                    .corrected(corrected), .fixed_mask(fixed_mask), .nfixed(nfixed), .fail(fail), .done(done));

    integer n, errors, by_count [0:3], nerr, k;
    reg [31:0] errpat;

    initial begin
        for (n = 0; n < MAXV; n = n + 1) vec[n] = 96'bx;
        $readmemh("vectors.mem", vec);
        errors = 0;
        for (k = 0; k < 4; k = k + 1) by_count[k] = 0;

        n = 0;
        while (n < MAXV && vec[n][0] !== 1'bx) begin
            msg    = vec[n][95:80];
            errpat = vec[n][79:48];
            #1;
            if (code_syn !== 16'h0000 || code[31:16] !== msg) begin
                errors = errors + 1;
                $display("FAIL encode %h -> %h, syndromes %h", msg, code, code_syn);
            end

            nerr = 0;
            for (k = 0; k < 8; k = k + 1) nerr = nerr + (errpat[4*k +: 4] != 4'h0);
            by_count[nerr] = by_count[nerr] + 1;

            @(negedge clk);
            received = code ^ errpat;
            start    = 1'b1;
            @(negedge clk);
            start    = 1'b0;
            @(posedge done);
            #1;
            if (corrected !== vec[n][47:16] || fail !== vec[n][12] ||
                nfixed !== vec[n][9:8] || fixed_mask !== vec[n][7:0]) begin
                errors = errors + 1;
                $display("FAIL #%0d msg %h err %h: got word %h fail %b fixed %0d mask %b, want %h %b %0d %b",
                         n, msg, errpat, corrected, fail, nfixed, fixed_mask,
                         vec[n][47:16], vec[n][12], vec[n][9:8], vec[n][7:0]);
            end
            n = n + 1;
        end

        if (n == 0) begin
            $display("FAILED: tb_rs_codec, vectors.mem not found - run tools/rs_ref.py");
        end else if (errors == 0)
            $display("PASS: tb_rs_codec, %0d vectors (%0d clean, %0d one-error, %0d two-error, %0d three-error)",
                     n, by_count[0], by_count[1], by_count[2], by_count[3]);
        else
            $display("FAILED: tb_rs_codec, %0d of %0d vectors failed", errors, n);
        $finish;
    end
endmodule
