// Runtime-programmable BNN inference engine (neuron-serial, plane-serial).
//
// Network description (written over UART by cmd_parser, read here):
//   layer regs  [l]   : n_in, n_out, neuron_base
//   neuron mem  [n]   : {plane_start[15:0], n_planes[7:0], threshold[15:0] signed}
//   plane mem   [p]   : {shift[7:0], mask[MAXW-1:0], w[MAXW-1:0]}
// Neuron output bit = 1 (+1) iff  sum_planes (2*popcount(~(w ^ x) & mask) - popcount(mask)) << shift  >= threshold
// Layer l's output bits become layer l+1's inputs; the final layer's bit 0 is the prediction.
module bnn_engine #(
    parameter MAXW     = 256,
    parameter NEU_AW   = 10,     // 1024 neurons
    parameter PL_AW    = 10,     // 1024 planes
    parameter MAX_LAY  = 4
) (
    input  wire             clk,
    input  wire             rst,
    // configuration writes
    input  wire             lay_we,
    input  wire [1:0]       lay_addr,
    input  wire [47:0]      lay_wdata,      // {n_in, n_out, neuron_base} 16b each
    input  wire             neu_we,
    input  wire [NEU_AW-1:0] neu_addr,
    input  wire [39:0]      neu_wdata,
    input  wire             pl_we,
    input  wire [PL_AW-1:0] pl_addr,
    input  wire [2*MAXW+7:0] pl_wdata,
    input  wire [2:0]       n_layers,
    // inference
    input  wire             start,
    input  wire [MAXW-1:0]  x_in,
    output reg              busy,
    output reg              done,           // 1-cycle pulse
    output reg              pred
);
    // ---------------------------------------------------------------- memories
    reg [47:0]       lay_mem [0:MAX_LAY-1];
    (* ram_style = "block" *) reg [39:0]       neu_mem [0:(1<<NEU_AW)-1];
    (* ram_style = "block" *) reg [2*MAXW+7:0] pl_mem  [0:(1<<PL_AW)-1];

    reg [NEU_AW-1:0] neu_raddr;
    reg [PL_AW-1:0]  pl_raddr;
    reg [39:0]       neu_rdata;
    reg [2*MAXW+7:0] pl_rdata;

    always @(posedge clk) begin
        if (lay_we) lay_mem[lay_addr] <= lay_wdata;
    end
    always @(posedge clk) begin
        if (neu_we) neu_mem[neu_addr] <= neu_wdata;
        neu_rdata <= neu_mem[neu_raddr];
    end
    always @(posedge clk) begin
        if (pl_we) pl_mem[pl_addr] <= pl_wdata;
        pl_rdata <= pl_mem[pl_raddr];
    end

    // ---------------------------------------------------------------- plane arithmetic
    function automatic [9:0] popcount(input [MAXW-1:0] v);
        integer i;
        begin
            popcount = 0;
            for (i = 0; i < MAXW; i = i + 1) popcount = popcount + v[i];
        end
    endfunction

    wire [MAXW-1:0]   p_w     = pl_rdata[MAXW-1:0];
    wire [MAXW-1:0]   p_mask  = pl_rdata[2*MAXW-1:MAXW];
    wire [2:0]        p_shift = pl_rdata[2*MAXW+2:2*MAXW];
    reg  [MAXW-1:0]   act_in, act_out;
    wire [9:0]        pc_match = popcount(~(p_w ^ act_in) & p_mask);
    wire [9:0]        pc_mask  = popcount(p_mask);
    wire signed [15:0] base_term = $signed({5'd0, pc_match, 1'b0}) - $signed({6'd0, pc_mask});
    wire signed [15:0] term      = base_term <<< p_shift;

    // ---------------------------------------------------------------- control FSM
    localparam S_IDLE = 4'd0, S_LAYER = 4'd1, S_NREQ = 4'd2, S_NWAIT = 4'd3, S_NREAD = 4'd4,
               S_PWAIT = 4'd5, S_PREAD = 4'd6, S_NDONE = 4'd7, S_LEND = 4'd8, S_DONE = 4'd9;

    reg [3:0]         state;
    reg [2:0]         layer;
    reg [15:0]        n_out, nbase, n;
    reg [7:0]         np, p;
    reg signed [15:0] thr, acc;

    always @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            state <= S_IDLE;
            busy  <= 1'b0;
            pred  <= 1'b0;
        end else begin
            case (state)
                S_IDLE: if (start && n_layers != 0) begin
                    act_in <= x_in;
                    layer  <= 0;
                    busy   <= 1'b1;
                    state  <= S_LAYER;
                end
                S_LAYER: begin
                    n_out   <= lay_mem[layer][31:16];
                    nbase   <= lay_mem[layer][15:0];
                    n       <= 0;
                    act_out <= 0;
                    state   <= S_NREQ;
                end
                S_NREQ: begin
                    neu_raddr <= nbase[NEU_AW-1:0] + n[NEU_AW-1:0];
                    state     <= S_NWAIT;
                end
                S_NWAIT: state <= S_NREAD;          // BRAM captures neu_raddr
                S_NREAD: begin
                    np       <= neu_rdata[23:16];
                    thr      <= neu_rdata[15:0];
                    acc      <= 0;
                    p        <= 0;
                    pl_raddr <= neu_rdata[39:24];
                    state    <= (neu_rdata[23:16] == 0) ? S_NDONE : S_PWAIT;
                end
                S_PWAIT: state <= S_PREAD;          // BRAM captures pl_raddr
                S_PREAD: begin
                    acc <= acc + term;
                    p   <= p + 1'b1;
                    if (p + 1'b1 == np) state <= S_NDONE;
                    else begin
                        pl_raddr <= pl_raddr + 1'b1;
                        state    <= S_PWAIT;
                    end
                end
                S_NDONE: begin
                    act_out[n[7:0]] <= (acc >= thr);
                    n <= n + 1'b1;
                    state <= (n + 1'b1 == n_out) ? S_LEND : S_NREQ;
                end
                S_LEND: begin
                    act_in <= act_out;
                    layer  <= layer + 1'b1;
                    state  <= (layer + 1'b1 == n_layers) ? S_DONE : S_LAYER;
                end
                S_DONE: begin
                    pred  <= act_out[0];
                    done  <= 1'b1;
                    busy  <= 1'b0;
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
