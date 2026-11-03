// PLTW S7 (XC7S25, Cmod S7 pinout) top level: UART <-> command parser <-> BNN engine.
// Runs directly on the 12 MHz oscillator; UART at 1 Mbaud = exactly 12 clocks per bit.
//   led[0] heartbeat   led[1] toggles per inference   led[2] network loaded   led[3] protocol error seen
//   btn[0] reset
module top #(
    parameter CLKS_PER_BIT = 12,
    parameter MAXW         = 256
) (
    input  wire       clk,
    input  wire [1:0] btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [3:0] led
);
    localparam NEU_AW = 10, PL_AW = 10;

    // power-on reset (+ button)
    reg [7:0] por = 8'hFF;
    reg       rst = 1'b1;
    always @(posedge clk) begin
        if (por != 0) por <= por - 1'b1;
        rst <= (por != 0) | btn[0];
    end

    wire [7:0] rx_data, tx_data;
    wire       rx_valid, tx_start, tx_busy;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (
        .clk(clk), .rst(rst), .rx(uart_rx), .data(rx_data), .valid(rx_valid));
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
        .clk(clk), .rst(rst), .data(tx_data), .start(tx_start), .tx(uart_tx), .busy(tx_busy));

    wire                lay_we, neu_we, pl_we, infer_start, eng_busy, eng_done, eng_pred;
    wire [1:0]          lay_addr;
    wire [47:0]         lay_wdata;
    wire [NEU_AW-1:0]   neu_addr;
    wire [39:0]         neu_wdata;
    wire [PL_AW-1:0]    pl_addr;
    wire [2*MAXW+7:0]   pl_wdata;
    wire [2:0]          n_layers;
    wire [MAXW-1:0]     x;
    wire                err_seen, infer_toggle;

    cmd_parser #(.MAXW(MAXW), .NEU_AW(NEU_AW), .PL_AW(PL_AW)) u_cmd (
        .clk(clk), .rst(rst),
        .rx_data(rx_data), .rx_valid(rx_valid), .tx_data(tx_data), .tx_start(tx_start), .tx_busy(tx_busy),
        .lay_we(lay_we), .lay_addr(lay_addr), .lay_wdata(lay_wdata),
        .neu_we(neu_we), .neu_addr(neu_addr), .neu_wdata(neu_wdata),
        .pl_we(pl_we), .pl_addr(pl_addr), .pl_wdata(pl_wdata), .n_layers(n_layers),
        .infer_start(infer_start), .x_out(x), .eng_busy(eng_busy), .eng_done(eng_done), .eng_pred(eng_pred),
        .err_seen(err_seen), .infer_toggle(infer_toggle));

    bnn_engine #(.MAXW(MAXW), .NEU_AW(NEU_AW), .PL_AW(PL_AW)) u_eng (
        .clk(clk), .rst(rst),
        .lay_we(lay_we), .lay_addr(lay_addr), .lay_wdata(lay_wdata),
        .neu_we(neu_we), .neu_addr(neu_addr), .neu_wdata(neu_wdata),
        .pl_we(pl_we), .pl_addr(pl_addr), .pl_wdata(pl_wdata), .n_layers(n_layers),
        .start(infer_start), .x_in(x), .busy(eng_busy), .done(eng_done), .pred(eng_pred));

    reg [23:0] hb = 0;
    always @(posedge clk) hb <= hb + 1'b1;

    assign led = {err_seen, n_layers != 0, infer_toggle, hb[23]};
endmodule
