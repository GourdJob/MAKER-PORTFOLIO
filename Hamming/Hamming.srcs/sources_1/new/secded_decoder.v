`timescale 1ns / 1ps
// Extended Hamming(8,4) decoder: corrects 1 bit error, flags 2 bit errors.
//   syndrome == 0, parity ok  -> no error
//   parity bad                -> single error (syndrome = bit position, 0 = the parity bit itself), corrected
//   syndrome != 0, parity ok  -> double error, uncorrectable
module secded_decoder(
    input  wire [7:0] code,
    output wire [3:0] data,
    output wire [2:0] syndrome,
    output wire       corrected,
    output wire       uncorrectable
);
    wire s1 = code[1] ^ code[3] ^ code[5] ^ code[7];
    wire s2 = code[2] ^ code[3] ^ code[6] ^ code[7];
    wire s4 = code[4] ^ code[5] ^ code[6] ^ code[7];
    assign syndrome = {s4, s2, s1};

    wire parity_bad = ^code;

    assign corrected     = parity_bad;
    assign uncorrectable = (syndrome != 3'd0) && !parity_bad;

    wire [7:0] flip  = (parity_bad && syndrome != 3'd0) ? (8'b1 << syndrome) : 8'b0;
    wire [7:0] fixed = code ^ flip;

    assign data = {fixed[7], fixed[6], fixed[5], fixed[3]};
endmodule
