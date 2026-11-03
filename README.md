FPGA Error-Correction Hardware: Hamming -> Reed–Solomon -> Quantum Error-Correction Decoder

Verilog projects on a Spartan-7 FPGA. All checked against a Python reference model + tested on physical board.

Hardware: Digilent PLTW S7 / Cmod S7 with a Xilinx Spartan-7 XC7S25 FPGA (12 MHz clock, USB-JTAG/UART). Verilog only, no Xilinx IP cores. Pin constraints were adapted from the PLTW/Digilent board files.

Documentation: PLTW S7 board reference (https://digilent.com/reference/programmable-logic/pltw-s7/start), PLTW configuration and XDC instructions (https://s3.amazonaws.com/support-downloads.pltw.org/Software+Page/DE/CMOD+S7+Configuration+Files.pdf)

[Read the full guide (GUIDE.md)](GUIDE.md)-> folder layout, usage, source files for statistics

Headline results

- FPGAFlow (QEC decoder): a binary neural network with a 3-bit first layer, decoding a distance-3 surface code (3 rounds, circuit-level noise, p = 0.005)
  - 1.63% logical error rate on the board (best seed); 1.68% mean over 5 seeds; PyMatching 1.72% on the same 1M test shots
  - 0 mismatches between the FPGA and the golden model over 1,000,000 hardware shots
  - 0 DSP blocks, 1535 LUTs
  - The comparison applies only to this setting; see "Scope of the PyMatching comparison" in [GUIDE.md](GUIDE.md)
- Reed–Solomon RS(8,4) over GF(16): corrects 2 symbol errors; RTL matches the reference model on 5,780 vectors
- Hamming(8,4) SECDED: corrects 1 bit error and detects 2; exhaustively tested

Authorship and tools

- Hamming(8,4) and Reed-Solomon: I designed and wrote all Verilog, testbenches and Python reference models
- QEC decoder (FPGAFlow): I set the direction and wrote the decoder Verilog, the training code and the core implementation, including the teacher-ranked saliency and dedicated +-2/+-4/+-7 neuron design
- AI assistance (Claude): visualization and figures, circuit diagrams, data compilation, running training jobs, and most of the QEC decoder testbench code, are written from my Verilog. Before publishing, Claude also cleaned up code formatting, comments and docstrings across the repository. The design, logic and algorithms are mine
- Hardware: Cmod S7 / PLTW S7 boards on loan from the Niles North Engineering Department
- Feedback: researchers in Beerantum, an international quantum collective, answered design questions but wrote no code
- Libraries and tools: Vivado, xsim, Tcl; PyTorch (custom straight-through-estimator QAT), Stim, PyMatching, NumPy, pyserial
- Ideas built on: AWQ (activation-aware weight quantization) and XNOR-Net papers