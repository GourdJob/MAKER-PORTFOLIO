`timescale 1ns / 1ps
// Synchronous FIFO. `dout` is the head entry (valid while !empty); pulse `rd_en` to pop it.
// Writes while full and reads while empty are ignored.
module sync_fifo #(
    parameter WIDTH = 8,
    parameter DEPTH_LOG2 = 4   // 16 entries
)(
    input  wire             clk,
    input  wire             rst,
    input  wire             wr_en,
    input  wire [WIDTH-1:0] din,
    input  wire             rd_en,
    output wire [WIDTH-1:0] dout,
    output wire             empty,
    output wire             full
);
    reg [WIDTH-1:0]    mem [0:(1 << DEPTH_LOG2) - 1];
    reg [DEPTH_LOG2:0] wr_ptr = 0;   // extra MSB tells full from empty
    reg [DEPTH_LOG2:0] rd_ptr = 0;

    assign empty = (wr_ptr == rd_ptr);
    assign full  = (wr_ptr == {~rd_ptr[DEPTH_LOG2], rd_ptr[DEPTH_LOG2-1:0]});
    assign dout  = mem[rd_ptr[DEPTH_LOG2-1:0]];

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr[DEPTH_LOG2-1:0]] <= din;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty)
                rd_ptr <= rd_ptr + 1'b1;
        end
    end
endmodule
