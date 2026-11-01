`timescale 1ns / 1ps
// RS(8,4) decoder: syndromes -> Berlekamp-Massey -> Chien search + Forney -> correction.
// Pulse `start` with the received word; `done` pulses 6 clocks later with the results held until the next start.
// On fail the received word is passed through unchanged (fixed_mask = 0, nfixed = 0).
module rs_decoder(
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    input  wire [31:0] received,
    output reg  [31:0] corrected  = 32'd0,
    output reg  [7:0]  fixed_mask = 8'd0,
    output reg  [1:0]  nfixed     = 2'd0,
    output reg         fail       = 1'b0,
    output reg         done       = 1'b0
);
    reg [31:0] r        = 32'd0;
    reg        bm_start = 1'b0;

    wire [15:0] s;
    rs_syndrome u_syn (.r(r), .s(s));

    wire [19:0] lambda;
    wire [2:0]  len;
    wire        bm_done;
    rs_bm u_bm (.clk(clk), .rst(rst), .start(bm_start), .s(s), .lambda(lambda), .len(len), .done(bm_done));

    wire [31:0] err_val;
    wire [7:0]  err_mask;
    wire [3:0]  nroots;
    wire        cf_fail;
    rs_chien_forney u_cf (.lambda(lambda), .len(len), .s(s),
                          .err_val(err_val), .err_mask(err_mask), .nroots(nroots), .fail(cf_fail));

    always @(posedge clk) begin
        bm_start <= 1'b0;
        done     <= 1'b0;
        if (rst) begin
            corrected  <= 32'd0;
            fixed_mask <= 8'd0;
            nfixed     <= 2'd0;
            fail       <= 1'b0;
        end else begin
            if (start) begin
                r        <= received;      // syndromes settle from r on the next cycle
                bm_start <= 1'b1;
            end
            if (bm_done) begin
                corrected  <= cf_fail ? r : r ^ err_val;
                fixed_mask <= cf_fail ? 8'd0 : err_mask;
                nfixed     <= cf_fail ? 2'd0 : nroots[1:0];
                fail       <= cf_fail;
                done       <= 1'b1;
            end
        end
    end
endmodule
