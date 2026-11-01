// Engine unit test: load the exported network directly into the engine's write ports,
// run every golden vector, and compare the prediction bit-for-bit.
//   files from host/export.py:  layers.hex  neurons.hex  planes.hex  vectors.hex  (+ net.json counts)
`timescale 1ns/1ps
module tb_engine;
    parameter MAXW = 256, NEU_AW = 10, PL_AW = 10;
    parameter N_LAYERS = 3, N_NEURONS = 257, N_PLANES = 513, N_VEC = 2000;
    parameter DIR = "";

    reg clk = 0, rst = 1;
    always #41.667 clk = ~clk;

    reg              lay_we = 0, neu_we = 0, pl_we = 0, start = 0;
    reg [1:0]        lay_addr;
    reg [47:0]       lay_wdata;
    reg [NEU_AW-1:0] neu_addr;
    reg [39:0]       neu_wdata;
    reg [PL_AW-1:0]  pl_addr;
    reg [2*MAXW+7:0] pl_wdata;
    reg [2:0]        n_layers = 0;
    reg [MAXW-1:0]   x;
    wire             busy, done, pred;

    bnn_engine #(.MAXW(MAXW), .NEU_AW(NEU_AW), .PL_AW(PL_AW)) dut (
        .clk(clk), .rst(rst),
        .lay_we(lay_we), .lay_addr(lay_addr), .lay_wdata(lay_wdata),
        .neu_we(neu_we), .neu_addr(neu_addr), .neu_wdata(neu_wdata),
        .pl_we(pl_we), .pl_addr(pl_addr), .pl_wdata(pl_wdata), .n_layers(n_layers),
        .start(start), .x_in(x), .busy(busy), .done(done), .pred(pred));

    reg [47:0]       lays [0:3];
    reg [39:0]       neus [0:(1<<NEU_AW)-1];
    reg [2*MAXW+7:0] pls  [0:(1<<PL_AW)-1];
    reg [MAXW+7:0]   vecs [0:N_VEC-1];

    integer i, errs, ones, cycles, t0;

    initial begin
        $readmemh({DIR, "layers.hex"}, lays);
        $readmemh({DIR, "neurons.hex"}, neus);
        $readmemh({DIR, "planes.hex"}, pls);
        $readmemh({DIR, "vectors.hex"}, vecs);
        repeat (4) @(posedge clk);
        rst <= 0;
        for (i = 0; i < N_LAYERS; i = i + 1) begin
            @(posedge clk); lay_we <= 1; lay_addr <= i; lay_wdata <= lays[i];
        end
        for (i = 0; i < N_NEURONS; i = i + 1) begin
            @(posedge clk); lay_we <= 0; neu_we <= 1; neu_addr <= i; neu_wdata <= neus[i];
        end
        for (i = 0; i < N_PLANES; i = i + 1) begin
            @(posedge clk); neu_we <= 0; pl_we <= 1; pl_addr <= i; pl_wdata <= pls[i];
        end
        @(posedge clk); pl_we <= 0; n_layers <= N_LAYERS;

        errs = 0; ones = 0;
        for (i = 0; i < N_VEC; i = i + 1) begin
            @(posedge clk); x <= vecs[i][MAXW-1:0]; start <= 1; t0 = $time;
            @(posedge clk); start <= 0;
            @(posedge done); @(negedge clk);
            cycles = ($time - t0) / 83.333;
            ones = ones + pred;
            if (pred !== vecs[i][MAXW]) begin
                errs = errs + 1;
                if (errs <= 10) $display("MISMATCH vec %0d: rtl=%b golden=%b", i, pred, vecs[i][MAXW]);
            end
        end
        $display("tb_engine: %0d vectors, %0d mismatches, %0d predicted flips, %0d cycles/inference",
                 N_VEC, errs, ones, cycles);
        if (errs == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
