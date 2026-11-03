`timescale 1ns / 1ps
// RS(8,4) Reed-Solomon demo over UART with random symbol-error injection and an 8-digit display.
// PC sends 2 bytes = 4 data symbols {m3 m2 m1 m0} -> encoded to 8 symbols -> 0..3 random symbols
// corrupted -> decoded (syndromes, Berlekamp-Massey, Chien, Forney) -> FPGA replies with 10 bytes:
//   [0..3] corrupted codeword c7..c0 (2 symbols per byte)   [4..5] decoded message m3..m0
//   [6] status 'O' clean / 'C' corrected / 'X' uncorrectable  [7] '0'..'2' symbols fixed
//   [8] injected-position mask   [9] decoder-fixed mask (bit i = symbol c_i)
// Display: the corrupted codeword with dots under the injected symbols, then after SHOW_CYCLES the
// corrected codeword with dots under the symbols the decoder fixed ("--------" if uncorrectable).
// BTN0 cycles the injected symbol count 0 -> 1 -> 2 -> 3 -> 0. BTN1 held = reset.
// LED[1:0] = injection mode, LED[2] = last word uncorrectable, LED[3] = toggles every word.
// RGB: green = ok, yellow = corrected, red = uncorrectable.
module rs_top #(
    parameter CLKS_PER_BIT    = 104,         // 12 MHz / 115200 baud
    parameter DEBOUNCE_CYCLES = 120000,      // 10 ms
    parameter RX_TIMEOUT      = 1_200_000,   // 100 ms: drop a lone first byte so pairing resyncs
    parameter SHOW_CYCLES     = 24_000_000,  // 2 s showing the corrupted word
    parameter DIGIT_CYCLES    = 12000,
    parameter BLANK_CYCLES    = 600,
    parameter RGB_ACTIVE_LOW  = 1,
    parameter SEG_ACTIVE_LOW  = 0,           // common-cathode display
    parameter DIG_ACTIVE_LOW  = 0            // NPN digit transistors
)(
    input  wire       clk,
    input  wire [1:0] btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [3:0] led,
    output wire [2:0] rgb,        // {blue, green, red}
    output wire [7:0] seg,        // {dp, g, f, e, d, c, b, a}
    output wire [7:0] dig         // dig[0] = leftmost digit
);
    // ---------------------------------------------------------------- buttons, mode, randomness
    wire btn0_pulse, rst;
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) db0 (.clk(clk), .noisy(btn[0]), .clean(),    .pulse(btn0_pulse));
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) db1 (.clk(clk), .noisy(btn[1]), .clean(rst), .pulse());

    reg [1:0] mode = 2'd0;
    always @(posedge clk)
        if (rst)             mode <= 2'd0;
        else if (btn0_pulse) mode <= mode + 2'd1;

    wire [15:0] lfsr;
    lfsr16 u_lfsr (.clk(clk), .q_out(lfsr));
    reg  [31:0] rnd = 32'd0;      // the last 32 LFSR output bits
    always @(posedge clk) rnd <= {rnd[30:0], lfsr[0]};

    // ---------------------------------------------------------------- UART in, 2 bytes per message
    wire       rx_valid;
    wire [7:0] rx_data;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(clk), .rx(uart_rx), .data(rx_data), .valid(rx_valid));

    wire       fifo_empty, fifo_pop;
    wire [7:0] in_byte;
    sync_fifo #(.WIDTH(8), .DEPTH_LOG2(4)) u_fifo (
        .clk(clk), .rst(rst), .wr_en(rx_valid), .din(rx_data),
        .rd_en(fifo_pop), .dout(in_byte), .empty(fifo_empty), .full()
    );

    // ---------------------------------------------------------------- encode, corrupt, decode
    reg  [15:0] msg = 16'd0;
    wire [31:0] code, bad_code;
    wire [7:0]  inj_mask;
    rs_encoder      u_enc (.msg(msg), .code(code));
    symbol_injector u_inj (.code_in(code), .mode(mode), .rnd(rnd[20:0]), .code_out(bad_code), .inj_mask(inj_mask));

    localparam IDLE = 3'd0, GET2 = 3'd1, ENC = 3'd2, DEC = 3'd3, SEND = 3'd4, WAITB = 3'd5;
    reg [2:0] state = IDLE;

    wire [31:0] corrected;
    wire [7:0]  fixed_mask;
    wire [1:0]  nfixed;
    wire        dec_fail, dec_done;
    rs_decoder u_dec (
        .clk(clk), .rst(rst), .start(state == ENC), .received(bad_code),
        .corrected(corrected), .fixed_mask(fixed_mask), .nfixed(nfixed), .fail(dec_fail), .done(dec_done)
    );

    // ---------------------------------------------------------------- control FSM
    reg [7:0]  first_byte = 8'd0;
    reg [20:0] wait_cnt   = 21'd0;
    reg [31:0] rx_word    = 32'd0;   // corrupted codeword as received by the decoder
    reg [7:0]  rx_inj     = 8'd0;
    reg [3:0]  tx_idx     = 4'd0;
    reg        heartbeat  = 1'b0;
    reg        have_word  = 1'b0;    // display has something to show
    reg        show_fixed = 1'b0;    // display phase: 0 = corrupted, 1 = corrected
    reg [24:0] show_cnt   = 25'd0;

    assign fifo_pop = (state == IDLE || state == GET2) && !fifo_empty && !rst;

    wire       tx_busy;
    wire       tx_start = (state == SEND) && !tx_busy;
    reg  [7:0] tx_data;
    always @* begin
        case (tx_idx)
            4'd0:    tx_data = rx_word[31:24];
            4'd1:    tx_data = rx_word[23:16];
            4'd2:    tx_data = rx_word[15:8];
            4'd3:    tx_data = rx_word[7:0];
            4'd4:    tx_data = corrected[31:24];
            4'd5:    tx_data = corrected[23:16];
            4'd6:    tx_data = dec_fail ? "X" : (nfixed != 2'd0) ? "C" : "O";
            4'd7:    tx_data = "0" + nfixed;
            4'd8:    tx_data = rx_inj;
            default: tx_data = fixed_mask;
        endcase
    end
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (.clk(clk), .data(tx_data), .start(tx_start), .busy(tx_busy), .tx(uart_tx));

    always @(posedge clk) begin
        if (rst) begin
            state      <= IDLE;
            have_word  <= 1'b0;
            show_fixed <= 1'b0;
        end else begin
            case (state)
                IDLE: if (!fifo_empty) begin
                    first_byte <= in_byte;
                    wait_cnt   <= 21'd0;
                    state      <= GET2;
                end
                GET2: if (!fifo_empty) begin
                    msg   <= {first_byte, in_byte};
                    state <= ENC;
                end else if (wait_cnt == RX_TIMEOUT - 1)
                    state <= IDLE;                       // second byte never came
                else
                    wait_cnt <= wait_cnt + 21'd1;
                ENC: begin                               // decoder latches bad_code this cycle
                    rx_word <= bad_code;
                    rx_inj  <= inj_mask;
                    state   <= DEC;
                end
                DEC: if (dec_done) begin
                    heartbeat  <= ~heartbeat;
                    have_word  <= 1'b1;
                    show_fixed <= 1'b0;
                    show_cnt   <= 25'd0;
                    tx_idx     <= 4'd0;
                    state      <= SEND;
                end
                SEND:  if (!tx_busy) state <= WAITB;
                WAITB: if (!tx_busy) begin
                    if (tx_idx == 4'd9) state <= IDLE;
                    else begin
                        tx_idx <= tx_idx + 4'd1;
                        state  <= SEND;
                    end
                end
                default: state <= IDLE;
            endcase

            if (have_word && !show_fixed) begin
                if (show_cnt == SHOW_CYCLES - 1) show_fixed <= 1'b1;
                else                             show_cnt   <= show_cnt + 25'd1;
            end
        end
    end

    // ---------------------------------------------------------------- outputs
    seg7_mux #(.DIGIT_CYCLES(DIGIT_CYCLES), .BLANK_CYCLES(BLANK_CYCLES),
               .SEG_ACTIVE_LOW(SEG_ACTIVE_LOW), .DIG_ACTIVE_LOW(DIG_ACTIVE_LOW)) u_disp (
        .clk(clk),
        .sym(show_fixed ? corrected : rx_word),
        .dp(show_fixed ? fixed_mask : rx_inj),
        .dashes(show_fixed && dec_fail),
        .blank(!have_word),
        .seg(seg), .dig(dig)
    );

    wire last_fail = have_word && dec_fail;
    assign led = {heartbeat, last_fail, mode};

    wire [2:0] rgb_on = last_fail                      ? 3'b001 :
                        (have_word && nfixed != 2'd0) ? 3'b011 : 3'b010;
    assign rgb = RGB_ACTIVE_LOW ? ~rgb_on : rgb_on;
endmodule
