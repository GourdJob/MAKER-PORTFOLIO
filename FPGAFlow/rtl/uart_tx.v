// UART transmitter, 8N1, LSB first.
module uart_tx #(
    parameter CLKS_PER_BIT = 12
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire       start,     // pulse while !busy to send data
    output reg        tx,
    output wire       busy
);
    localparam CW = $clog2(CLKS_PER_BIT + 1);

    reg [9:0]    frame;          // {stop, data, start}, shifted out LSB first
    reg [3:0]    bits_left;
    reg [CW-1:0] cnt;

    assign busy = (bits_left != 0);

    always @(posedge clk) begin
        if (rst) begin
            tx        <= 1'b1;
            bits_left <= 0;
        end else if (!busy) begin
            tx <= 1'b1;
            if (start) begin
                frame     <= {1'b1, data, 1'b0};
                bits_left <= 4'd10;
                cnt       <= 0;
                tx        <= 1'b0;   // start bit goes out immediately
            end
        end else if (cnt == CLKS_PER_BIT - 1) begin
            cnt       <= 0;
            frame     <= {1'b1, frame[9:1]};
            bits_left <= bits_left - 1'b1;
            tx        <= (bits_left == 1) ? 1'b1 : frame[1];
        end else begin
            cnt <= cnt + 1'b1;
            tx  <= frame[0];
        end
    end
endmodule
