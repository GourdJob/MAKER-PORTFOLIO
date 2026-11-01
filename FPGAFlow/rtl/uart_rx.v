// UART receiver, 8N1, LSB first. Samples each bit at its centre.
// CLKS_PER_BIT = f_clk / baud (12 MHz / 1 Mbaud = 12).
module uart_rx #(
    parameter CLKS_PER_BIT = 12
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        valid      // 1-cycle pulse when data is ready
);
    localparam CW = $clog2(CLKS_PER_BIT + 1);
    localparam S_IDLE = 2'd0, S_START = 2'd1, S_DATA = 2'd2, S_STOP = 2'd3;

    reg [1:0]    rx_sync;        // 2-FF synchroniser
    reg [1:0]    state;
    reg [CW-1:0] cnt;
    reg [2:0]    bit_idx;
    reg [7:0]    shift;

    wire rxs = rx_sync[1];

    always @(posedge clk) begin
        rx_sync <= {rx_sync[0], rx};
        valid   <= 1'b0;
        if (rst) begin
            state   <= S_IDLE;
            rx_sync <= 2'b11;
        end else begin
            case (state)
                S_IDLE: if (!rxs) begin
                    state <= S_START;
                    cnt   <= 0;
                end
                S_START: if (cnt == CLKS_PER_BIT / 2 - 1) begin
                    // centre of the start bit: still low -> real start bit
                    state   <= rxs ? S_IDLE : S_DATA;
                    cnt     <= 0;
                    bit_idx <= 0;
                end else cnt <= cnt + 1'b1;
                S_DATA: if (cnt == CLKS_PER_BIT - 1) begin
                    cnt   <= 0;
                    shift <= {rxs, shift[7:1]};
                    if (bit_idx == 3'd7) state <= S_STOP;
                    bit_idx <= bit_idx + 1'b1;
                end else cnt <= cnt + 1'b1;
                S_STOP: if (cnt == CLKS_PER_BIT - 1) begin
                    state <= S_IDLE;
                    if (rxs) begin          // valid stop bit
                        data  <= shift;
                        valid <= 1'b1;
                    end
                end else cnt <= cnt + 1'b1;
            endcase
        end
    end
endmodule
