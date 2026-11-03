`timescale 1ns / 1ps
// Extended Hamming(8,4) encoder.
// code[7:1] = Hamming(7,4) positions 7..1 (p1=pos1, p2=pos2, d0=pos3, p4=pos4, d1=pos5, d2=pos6, d3=pos7)
// code[0]   = overall parity (enables double-error detection)
module secded_encoder(
    input  wire [3:0] data,
    output wire [7:0] code
);
    wire p1 = data[0] ^ data[1] ^ data[3];
    wire p2 = data[0] ^ data[2] ^ data[3];
    wire p4 = data[1] ^ data[2] ^ data[3];
    wire [7:1] h = {data[3], data[2], data[1], p4, data[0], p2, p1};

    assign code = {h, ^h};
endmodule
