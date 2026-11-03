`timescale 1ns / 1ps
// L3: SECDED Hamming(8,4) over UART with random error injection.
// PC sends a byte -> 16-byte RX FIFO -> each nibble is encoded to 8 bits -> 0/1/2 random bit flips
// are injected -> decoded -> FPGA replies with the recovered byte, then a status byte:
//   'O' = no error, 'C' = single error corrected, 'X' = double error detected (data unreliable)
// BTN0 cycles the injected error count (0 -> 1 -> 2 -> 0). BTN1 held = reset.
// LED[1:0] = injection mode, LED[2] = last byte uncorrectable, LED[3] = toggles on every byte.
// RGB: green = ok, yellow = corrected, red = uncorrectable.
// PIO LEDs (carrier board) show the last decoded byte's pipeline, held until the next byte:
//   pio_rx = received byte, pio_mask_hi/lo = code bits flipped by the injector,
//   pio_syn_hi/lo = decoder syndromes, pio_cor_hi/pio_unc_hi = HI nibble corrected/uncorrectable.
// Easter egg lmaooo
module hamming_top #(
    parameter CLKS_PER_BIT    = 104,      // 12 MHz / 115200 baud
    parameter DEBOUNCE_CYCLES = 120000,   // 10 ms at 12 MHz
    parameter RGB_ACTIVE_LOW  = 1,
    parameter LED_ACTIVE_LOW  = 0         // PIO LEDs wired pin -> LED -> GND; set to 1 if wired 3V3 -> LED -> pin
)(
    input  wire       clk,
    input  wire [1:0] btn,
    input  wire       uart_rx,
    output wire       uart_tx,
    output wire [3:0] led,
    output wire [2:0] rgb,        // {blue, green, red}
    output wire [7:0] pio_rx,
    output wire [7:0] pio_mask_hi,
    output wire [7:0] pio_mask_lo,
    output wire [2:0] pio_syn_hi,
    output wire [2:0] pio_syn_lo,
    output wire       pio_cor_hi,
    output wire       pio_unc_hi
);
    wire btn0_pulse, rst;
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) db0 (.clk(clk), .noisy(btn[0]), .clean(),    .pulse(btn0_pulse));
    debounce #(.CYCLES(DEBOUNCE_CYCLES)) db1 (.clk(clk), .noisy(btn[1]), .clean(rst), .pulse());

    reg [1:0] mode = 2'd0;
    always @(posedge clk)
        if (rst)             mode <= 2'd0;
        else if (btn0_pulse) mode <= (mode == 2'd2) ? 2'd0 : mode + 2'd1;

    wire [15:0] lfsr;
    lfsr16 u_lfsr (.clk(clk), .q_out(lfsr));

    wire       rx_valid;
    wire [7:0] rx_data;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(clk), .rx(uart_rx), .data(rx_data), .valid(rx_valid));

    // Buffers bytes that arrive while the previous reply is still being sent.
    wire       fifo_empty, fifo_full, fifo_pop;
    wire [7:0] in_byte;
    sync_fifo #(.WIDTH(8), .DEPTH_LOG2(4)) u_fifo (
        .clk(clk), .rst(rst),
        .wr_en(rx_valid), .din(rx_data),
        .rd_en(fifo_pop), .dout(in_byte),
        .empty(fifo_empty), .full(fifo_full)
    );

    wire [7:0] enc_hi, enc_lo, bad_hi, bad_lo;
    secded_encoder e_hi (.data(in_byte[7:4]), .code(enc_hi));
    secded_encoder e_lo (.data(in_byte[3:0]), .code(enc_lo));
    error_injector i_hi (.code_in(enc_hi), .mode(mode), .rnd(lfsr[5:0]),  .code_out(bad_hi));
    error_injector i_lo (.code_in(enc_lo), .mode(mode), .rnd(lfsr[11:6]), .code_out(bad_lo));

    wire [3:0] dec_hi, dec_lo;
    wire [2:0] syn_hi, syn_lo;
    wire       cor_hi, cor_lo, unc_hi, unc_lo;
    secded_decoder d_hi (.code(bad_hi), .data(dec_hi), .syndrome(syn_hi), .corrected(cor_hi), .uncorrectable(unc_hi));
    secded_decoder d_lo (.code(bad_lo), .data(dec_lo), .syndrome(syn_lo), .corrected(cor_lo), .uncorrectable(unc_lo));

    localparam IDLE = 3'd0, TX1 = 3'd1, WAIT1 = 3'd2, TX2 = 3'd3, WAIT2 = 3'd4;
    reg [2:0] state       = IDLE;
    reg [7:0] out_byte    = 8'd0;
    reg [7:0] status_byte = "O";
    reg [1:0] last_status = 2'd0;   // 0 ok, 1 corrected, 2 uncorrectable
    reg       heartbeat   = 1'b0;

    // Snapshot of the last byte's pipeline for the PIO LEDs
    reg [7:0] show_rx      = 8'd0;
    reg [7:0] show_mask_hi = 8'd0;
    reg [7:0] show_mask_lo = 8'd0;
    reg [2:0] show_syn_hi  = 3'd0;
    reg [2:0] show_syn_lo  = 3'd0;
    reg       show_cor_hi  = 1'b0;
    reg       show_unc_hi  = 1'b0;

    assign fifo_pop = (state == IDLE) && !fifo_empty && !rst;

    wire       tx_busy;
    wire       tx_start = (state == TX1 || state == TX2) && !tx_busy;
    wire [7:0] tx_data  = (state == TX1) ? out_byte : status_byte;
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (.clk(clk), .data(tx_data), .start(tx_start), .busy(tx_busy), .tx(uart_tx));

    always @(posedge clk) begin
        if (rst) begin
            state        <= IDLE;
            last_status  <= 2'd0;
            show_rx      <= 8'd0;
            show_mask_hi <= 8'd0;
            show_mask_lo <= 8'd0;
            show_syn_hi  <= 3'd0;
            show_syn_lo  <= 3'd0;
            show_cor_hi  <= 1'b0;
            show_unc_hi  <= 1'b0;
        end else case (state)
            IDLE: if (!fifo_empty) begin
                out_byte     <= {dec_hi, dec_lo};
                status_byte  <= (unc_hi | unc_lo) ? "X" : (cor_hi | cor_lo) ? "C" : "O";
                last_status  <= (unc_hi | unc_lo) ? 2'd2 : (cor_hi | cor_lo) ? 2'd1 : 2'd0;
                heartbeat    <= ~heartbeat;
                show_rx      <= in_byte;
                show_mask_hi <= enc_hi ^ bad_hi;
                show_mask_lo <= enc_lo ^ bad_lo;
                show_syn_hi  <= syn_hi;
                show_syn_lo  <= syn_lo;
                show_cor_hi  <= cor_hi;
                show_unc_hi  <= unc_hi;
                state        <= TX1;
            end
            TX1:   if (!tx_busy) state <= WAIT1;
            WAIT1: if (!tx_busy) state <= TX2;
            TX2:   if (!tx_busy) state <= WAIT2;
            WAIT2: if (!tx_busy) state <= IDLE;
        endcase
    end

    assign led = {heartbeat, last_status == 2'd2, mode};

    wire [2:0] rgb_on = (last_status == 2'd2) ? 3'b001 :
                        (last_status == 2'd1) ? 3'b011 : 3'b010;
    assign rgb = RGB_ACTIVE_LOW ? ~rgb_on : rgb_on;

    wire [31:0] pio_on  = {show_rx, show_mask_hi, show_mask_lo, show_syn_hi, show_syn_lo, show_cor_hi, show_unc_hi};
    wire [31:0] pio_out = LED_ACTIVE_LOW ? ~pio_on : pio_on;
    assign {pio_rx, pio_mask_hi, pio_mask_lo, pio_syn_hi, pio_syn_lo, pio_cor_hi, pio_unc_hi} = pio_out;
endmodule
