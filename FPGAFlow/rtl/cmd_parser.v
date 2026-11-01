// Host command parser + reply generator (see host/export.py for the host side).
//
// Host -> FPGA frame: 0xA5, type, payload..., checksum = (type + sum(payload)) mod 256
//   0x01 LAYER   (7 B):  layer, n_in[2], n_out[2], neuron_base[2]          (little-endian)
//   0x02 NEURON  (7 B):  addr[2], plane_start[2], n_planes, threshold[2]
//   0x03 PLANE  (67 B):  addr[2], shift, mask[32], w[32]
//   0x04 NLAYERS (1 B):  n_layers
//   0x10 INFER  (34 B):  seq, label, x[32]
// FPGA -> host reply (5 B): 0x5A, type, b1, b2, checksum = (type + b1 + b2) mod 256
//   write ack: type, 0, 0      infer: 0x10, seq, {5'b0, pred^label, label, pred}
//   error:     0xEE, code, received type   (code 1 = bad checksum, 2 = unknown type, 3 = busy)
module cmd_parser #(
    parameter MAXW   = 256,
    parameter NEU_AW = 10,
    parameter PL_AW  = 10
) (
    input  wire              clk,
    input  wire              rst,
    // UART
    input  wire [7:0]        rx_data,
    input  wire              rx_valid,
    output reg  [7:0]        tx_data,
    output reg               tx_start,
    input  wire              tx_busy,
    // engine configuration
    output reg               lay_we,
    output reg  [1:0]        lay_addr,
    output reg  [47:0]       lay_wdata,
    output reg               neu_we,
    output reg  [NEU_AW-1:0] neu_addr,
    output reg  [39:0]       neu_wdata,
    output reg               pl_we,
    output reg  [PL_AW-1:0]  pl_addr,
    output reg  [2*MAXW+7:0] pl_wdata,
    output reg  [2:0]        n_layers,
    // inference
    output reg               infer_start,
    output reg  [MAXW-1:0]   x_out,
    input  wire              eng_busy,
    input  wire              eng_done,
    input  wire              eng_pred,
    // status
    output reg               err_seen,
    output reg               infer_toggle
);
    localparam SOF = 8'hA5, RSOF = 8'h5A;
    localparam T_LAYER = 8'h01, T_NEURON = 8'h02, T_PLANE = 8'h03, T_NLAYERS = 8'h04, T_INFER = 8'h10;
    localparam NB = MAXW / 8;
    localparam MAXP = 3 + 2 * NB;           // longest payload (PLANE)

    localparam R_SOF = 2'd0, R_TYPE = 2'd1, R_PAY = 2'd2, R_CHK = 2'd3;

    reg [1:0] rstate;
    reg [7:0] rtype, rsum;
    reg [7:0] plen, pcnt;
    reg [7:0] pb [0:MAXP-1];

    function [7:0] payload_len(input [7:0] t);
        case (t)
            T_LAYER:   payload_len = 8'd7;
            T_NEURON:  payload_len = 8'd7;
            T_PLANE:   payload_len = MAXP;
            T_NLAYERS: payload_len = 8'd1;
            T_INFER:   payload_len = 2 + NB;
            default:   payload_len = 8'd0;
        endcase
    endfunction

    // ---------------------------------------------------------------- replies
    // Replies are queued in a small FIFO so a short command arriving while the previous
    // reply is still being transmitted can't overwrite it.
    reg [7:0]  rq [0:4];             // reply currently being transmitted
    reg [2:0]  rq_left;
    reg        reply_req;            // reply from the receive path (registered pulse)
    reg [7:0]  reply_t, reply_b1, reply_b2;
    reg        eng_pending;          // inference reply waiting to be queued
    reg [23:0] eng_reply;
    reg [23:0] fifo [0:3];
    reg [1:0]  f_wr, f_rd;
    reg [2:0]  f_cnt;
    reg [7:0]  infer_seq, infer_label;
    reg        waiting_infer;
    reg        push, pop;
    reg [23:0] push_data;

    integer i;

    always @(posedge clk) begin
        lay_we <= 1'b0;
        neu_we <= 1'b0;
        pl_we <= 1'b0;
        infer_start <= 1'b0;
        tx_start <= 1'b0;
        reply_req <= 1'b0;
        if (rst) begin
            rstate        <= R_SOF;
            n_layers      <= 0;
            rq_left       <= 0;
            err_seen      <= 1'b0;
            infer_toggle  <= 1'b0;
            waiting_infer <= 1'b0;
            eng_pending   <= 1'b0;
            f_wr          <= 0;
            f_rd          <= 0;
            f_cnt         <= 0;
        end else begin
            // ---------------- receive
            if (rx_valid) begin
                case (rstate)
                    R_SOF: if (rx_data == SOF) rstate <= R_TYPE;
                    R_TYPE: begin
                        rtype <= rx_data;
                        rsum  <= rx_data;
                        plen  <= payload_len(rx_data);
                        pcnt  <= 0;
                        if (payload_len(rx_data) == 0) begin
                            reply_req <= 1'b1;
                            {reply_t, reply_b1, reply_b2} <= {8'hEE, 8'd2, rx_data};
                            err_seen  <= 1'b1;
                            rstate    <= R_SOF;
                        end else rstate <= R_PAY;
                    end
                    R_PAY: begin
                        pb[pcnt] <= rx_data;
                        rsum     <= rsum + rx_data;
                        pcnt     <= pcnt + 1'b1;
                        if (pcnt + 1'b1 == plen) rstate <= R_CHK;
                    end
                    R_CHK: begin
                        rstate <= R_SOF;
                        if (rx_data != rsum) begin
                            reply_req <= 1'b1;
                            {reply_t, reply_b1, reply_b2} <= {8'hEE, 8'd1, rtype};
                            err_seen  <= 1'b1;
                        end else begin
                            case (rtype)
                                T_LAYER: begin
                                    lay_we    <= 1'b1;
                                    lay_addr  <= pb[0][1:0];
                                    lay_wdata <= {pb[2], pb[1], pb[4], pb[3], pb[6], pb[5]};
                                    reply_req <= 1'b1;
                                    {reply_t, reply_b1, reply_b2} <= {rtype, 8'd0, 8'd0};
                                end
                                T_NEURON: begin
                                    neu_we    <= 1'b1;
                                    neu_addr  <= {pb[1], pb[0]};
                                    neu_wdata <= {pb[3], pb[2], pb[4], pb[6], pb[5]};
                                    reply_req <= 1'b1;
                                    {reply_t, reply_b1, reply_b2} <= {rtype, 8'd0, 8'd0};
                                end
                                T_PLANE: begin
                                    pl_we   <= 1'b1;
                                    pl_addr <= {pb[1], pb[0]};
                                    pl_wdata[2*MAXW+7:2*MAXW] <= pb[2];
                                    for (i = 0; i < NB; i = i + 1) begin
                                        pl_wdata[MAXW + 8*i +: 8] <= pb[3 + i];
                                        pl_wdata[8*i +: 8]        <= pb[3 + NB + i];
                                    end
                                    reply_req <= 1'b1;
                                    {reply_t, reply_b1, reply_b2} <= {rtype, 8'd0, 8'd0};
                                end
                                T_NLAYERS: begin
                                    n_layers  <= pb[0][2:0];
                                    reply_req <= 1'b1;
                                    {reply_t, reply_b1, reply_b2} <= {rtype, 8'd0, 8'd0};
                                end
                                T_INFER: begin
                                    if (eng_busy || waiting_infer) begin
                                        reply_req <= 1'b1;
                                        {reply_t, reply_b1, reply_b2} <= {8'hEE, 8'd3, rtype};
                                        err_seen  <= 1'b1;
                                    end else begin
                                        for (i = 0; i < NB; i = i + 1)
                                            x_out[8*i +: 8] <= pb[2 + i];
                                        infer_seq     <= pb[0];
                                        infer_label   <= pb[1];
                                        infer_start   <= 1'b1;
                                        waiting_infer <= 1'b1;
                                    end
                                end
                                default: ;
                            endcase
                        end
                    end
                endcase
            end

            // ---------------- inference result -> pending reply
            if (eng_done && waiting_infer) begin
                waiting_infer <= 1'b0;
                infer_toggle  <= ~infer_toggle;
                eng_pending   <= 1'b1;
                eng_reply     <= {T_INFER, infer_seq,
                                  {5'd0, eng_pred ^ infer_label[0], infer_label[0], eng_pred}};
            end

            // ---------------- FIFO push: receive-path reply first, else a pending inference reply
            push = 1'b0;
            if (reply_req) begin
                push = 1'b1;
                push_data = {reply_t, reply_b1, reply_b2};
            end else if (eng_pending) begin
                push = 1'b1;
                push_data = eng_reply;
                eng_pending <= 1'b0;
            end

            // ---------------- FIFO pop into the transmitter, then send 5 bytes
            pop = (rq_left == 0) && (f_cnt != 0);
            if (pop) begin
                rq[0]   <= RSOF;
                rq[1]   <= fifo[f_rd][23:16];
                rq[2]   <= fifo[f_rd][15:8];
                rq[3]   <= fifo[f_rd][7:0];
                rq[4]   <= fifo[f_rd][23:16] + fifo[f_rd][15:8] + fifo[f_rd][7:0];
                rq_left <= 3'd5;
                f_rd    <= f_rd + 1'b1;
            end else if (rq_left != 0 && !tx_busy && !tx_start) begin
                tx_data  <= rq[3'd5 - rq_left];
                tx_start <= 1'b1;
                rq_left  <= rq_left - 1'b1;
            end

            if (push && (f_cnt != 4 || pop)) begin
                fifo[f_wr] <= push_data;
                f_wr <= f_wr + 1'b1;
            end else if (push) err_seen <= 1'b1;       // FIFO overflow: reply dropped
            f_cnt <= f_cnt + (push && (f_cnt != 4 || pop)) - pop;
        end
    end
endmodule
