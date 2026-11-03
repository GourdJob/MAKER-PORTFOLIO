The repository holds 3 FPGA error-correction projects, built on a Spartan-7 (xc7s25, Cmod S7 / PLTW S7 carrier). Each one is written in Verilog with no Xilinx IP, checked against a Python reference model, and tested on the physical board over USB-UART. 

Results at a glance (sources for every number are under "Backing for statistics" in each project)

- FPGAFlow (main project): neural-network decoder for a distance-3 surface code, running on a Spartan-7 with 0 DSP blocks
  - 1.63% logical error rate on the board (best seed); 1.68% mean over 5 seeds
  - PyMatching on the same 1,000,000 test shots: 1.72%
  - Bit-exact: 0 mismatches between the FPGA and the golden model over 1,000,000 hardware shots, for each of 5 models
  - Negative result: my teacher-ranked dedicated-neuron design was no better than randomly chosen detectors (knockout +59% vs +57% LER); a standard 3-bit first layer beat it at every hardware budget tested
  - Resources: 1535 LUTs (10.5%), 15.5 BRAM tiles, 0 DSPs; 2063 cycles per inference at 12 MHz (about 172 us)
- Reed-Solomon RS(8,4): corrects up to 2 symbol errors; RTL matches the Python reference on 5,780 vectors including uncorrectable cases; 978 LUTs, 0 DSPs
- Hamming(8,4) SECDED: corrects 1 bit error and detects 2; exhaustively tested; 153 LUTs, 0 DSPs

Scope of the PyMatching comparison

- The comparison holds only for the setting tested: rotated surface code, distance 3, 3 rounds, uniform circuit-level depolarizing noise, p = 0.005, generated with Stim
- PyMatching is run as standard (uncorrelated) minimum-weight perfect matching on the circuit's detector error model; neural decoders are known to edge out plain MWPM at small distances because MWPM ignores X/Z correlations
- This is not evidence that the decoder beats PyMatching in general, at larger distances, at other noise rates, or against correlated matching or belief-matching
- The hardware engine is also not yet real-time: about 172 us per inference vs a surface-code round of about 1 us on superconducting hardware

Terminology

- "BNN" in this repo means a network whose hidden activations are binary (+-1) and whose arithmetic is XNOR-popcount. The engine supports both strictly binary networks (all weights +-1) and mixed-precision networks where some weights use several binary bit-planes (for example, 3-bit first-layer weights). The headline 1.63% / 1.68% models are mixed-precision: 3-bit first layer, binary everywhere else.

layout
- Hamming/       project 1: SECDED Hamming(8,4) codec over UART
- ReedSolomon/   project 2: RS(8,4) codec with 7-segment display
- FPGAFlow/      project 3: BNN quantum error-correction decoder
- GUIDE.md       guide file - this file. Headings have been added to each code file for overarching descriptions.

PROJECT 1: HAMMING (SECDED Hamming(8,4))

The PC sends bytes over UART. The FPGA splits each byte into two nibbles, encodes each nibble into an 8-bit extended Hamming codeword, flips 0, 1 or 2 random bits (chosen with BTN0), decodes, and replies with the recovered byte and a status character. Single errors are corrected and double errors are detected. LEDs and the carrier's PIO LEDs show the injected error mask and syndromes for the last byte.

Important folders and files

- Hamming/Hamming.srcs/sources_1/new/   RTL
  - hamming_top.v      top level: UART -> FIFO -> encode -> inject -> decode -> reply
  - secded_encoder.v   4 data bits -> 8-bit codeword
  - secded_decoder.v   syndrome + overall parity; corrects 1 error, flags 2
  - error_injector.v   flips 0/1/2 random bits using lfsr16.v
  - uart_rx.v, uart_tx.v, sync_fifo.v, debounce.v   support modules
  - BlinkingLED.v, ClockDivider.v, led_test_top.v   early bring-up experiments (not part of the codec)
- Hamming/Hamming.srcs/sim_1/new/       testbenches
  - tb_secded.v        exhaustive self-checking test: every nibble x every 0/1/2-bit error mask
  - tb_hamming_top.v   end-to-end test at the UART pin, all injection modes, plus a FIFO burst
  - testbench.v, testbench1.v   early bring-up testbenches
- Hamming/tools/
  - host_test.py       PC-side test script
  - hamming_top.bit    prebuilt bitstream
  - add_l3_to_project.tcl, cleanup_project.tcl   Vivado project setup scripts
- Hamming/Hamming.xpr   Vivado project

Usage

- Open Hamming/Hamming.xpr in Vivado, run simulation (tb_secded or tb_hamming_top), or program the board with Hamming/tools/hamming_top.bit
- pip install pyserial
- python Hamming/tools/host_test.py COM5 20                 send 20 random bytes
- python Hamming/tools/host_test.py COM5 --hex 55 A7 FF     send specific bytes
- python Hamming/tools/host_test.py COM5 --text "Hello"     send a string
- python Hamming/tools/host_test.py COM5 --burst 16         back-to-back burst (tests the 16-byte FIFO)
- Press BTN0 to cycle injected errors 0 -> 1 -> 2; hold BTN1 to reset
- Reply status: O = no error, C = corrected, X = double error detected
- Note: the .tcl scripts use the absolute path C:/users/johna/Hamming; edit it if the folder moves

Backing for statistics

- Correctness over all single and double errors: tb_secded.v (exhaustive, self-checking)
- Resource use (153 LUTs, 180 registers, 0 DSP, 0 BRAM): Hamming/Hamming.runs/impl_1/hamming_top_utilization_placed.rpt

PROJECT 2: REEDSOLOMON (RS(8,4) over GF(16))

RS(8,4) is a shortened RS(15,11) code over GF(16) (primitive polynomial x^4 + x + 1) that corrects up to 2 symbol errors. The PC sends 4 data symbols (2 bytes). The FPGA encodes them into 8 symbols, corrupts 0 to 3 random symbols (chosen with BTN0), and decodes with syndromes, Berlekamp-Massey, Chien search and Forney. I chose this syndrome-based decoder over interpolation-based alternatives (e.g. Berlekamp–Welch) because it maps to small, regular GF(16) multiply/XOR logic, with BM finishing in 4 clock cycles for t = 2. Replies with 10 bytes and shows the corrupted word->corrected word, on an 8-digit 7-segment display driven through 2N3904 transistors. I found this project to be very cool testing on terminal because stream whizzes by like those scenes in the matrix.

Code conventions (needed to reproduce the reference model)

- Field: GF(16), primitive polynomial x^4 + x + 1, alpha = 2 (the element x)
- Code: narrow-sense RS defined by its generator polynomial g(x) = (x - alpha^1)(x - alpha^2)(x - alpha^3)(x - alpha^4), first consecutive root 1; a word is a codeword iff c(alpha^j) = 0 for j = 1..4
- Shortening: RS(15,11) with the top 7 positions fixed to zero, leaving positions 0..7; still 4 parity symbols, so t = 2
- Codeword polynomial: c(x) = c0 + c1 x + ... + c7 x^7; symbol c_i sits at position i, with error locator alpha^i
- Systematic layout: c7 c6 c5 c4 = data m3 m2 m1 m0, c3..c0 = parity = x^4 m(x) mod g(x), computed by an LFSR in the same order as rs_encoder.v
- Wire / display order: word[31:0] = {c7, c6, ..., c0}, 4 bits per symbol
- Syndromes: S_j = r(alpha^j), j = 1..4
- Decoder failure rule: declare uncorrectable if L > 2, if the number of Chien roots found in positions 0..7 differs from L, or if Forney gives a zero denominator or a zero error value; these rules are mirrored exactly in rs_ref.py so 3-error cases can be compared bit-for-bit

Important folders and files

- ReedSolomon/src/   RTL
  - rs_top.v            top level: UART, injection, display sequencing, reply
  - rs_encoder.v        systematic encoder (4 parity symbols)
  - rs_syndrome.v       computes S1..S4
  - rs_bm.v             Berlekamp-Massey: error-locator polynomial, 1 iteration per clock
  - rs_chien_forney.v   error positions (Chien) and values (Forney)
  - rs_decoder.v        ties syndrome -> BM -> Chien/Forney together
  - gf16.vh             GF(16) multiply / inverse functions
  - symbol_injector.v   random 0-3 symbol corruption using lfsr16.v
  - seg7_mux.v          multiplexed 7-segment driver
  - uart_rx.v, uart_tx.v, sync_fifo.v, debounce.v   support modules
  - rs_top.xdc          pin constraints
- ReedSolomon/sim/   testbenches
  - tb_gf16.v           exhaustive check of GF(16) arithmetic against an independent log/antilog table
  - tb_rs_codec.v       encoder + decoder vs the Python reference-for 0/1/2/3-symbol errors
  - tb_rs_top.v         end-to-end test at the UART pins, all modes, display sequencer, timeout
  - vectors.mem         5,780 test vectors written by rs_ref.py
- ReedSolomon/tools/
  - rs_ref.py           bit-exact Python reference model of the codec; writes sim/vectors.mem
  - rs_host.py          PC-side script for the board
  - create_project.tcl  recreates the Vivado project
- ReedSolomon/docs/wiring_guide.html   7-segment display and transistor driver wiring
- ReedSolomon/vivado/  generated Vivado project

Usage

- python ReedSolomon/tools/rs_ref.py                  self-test the reference model and write sim/vectors.mem
- vivado -mode batch -source ReedSolomon/tools/create_project.tcl   create the project (run rs_ref.py first)
- In Vivado: run tb_gf16, tb_rs_codec or tb_rs_top; or build and program rs_top
- pip install pyserial
- python ReedSolomon/tools/rs_host.py COM5 10               send 10 random messages
- python ReedSolomon/tools/rs_host.py COM5 --hex 1234 BEEF  send specific messages
- add --delay 4 to watch the display show the corrupted word, then the corrected word
- Press BTN0 to cycle injected symbol errors 0 -> 1 -> 2 -> 3; hold BTN1 to reset
- Reply status: O = clean, C = corrected, X = uncorrectable
- Note: create_project.tcl comments mention C:/users/johna/ReedSolomon; the script itself uses relative paths

Backing for statistics

- RTL matches the Python model including 3-error (uncorrectable) behavior: tb_rs_codec.v with sim/vectors.mem from tools/rs_ref.py
- GF(16) arithmetic correct for all inputs: tb_gf16.v
- Resource use (978 LUTs, 369 registers, 0 DSP, 0 BRAM): ReedSolomon/vivado/ReedSolomon.runs/impl_1/rs_top_utilization_placed.rpt

PROJECT 3: FPGAFLOW (BNN quantum error-correction decoder)

A neural-network decoder for a distance-3 rotated surface code, 3 rounds, circuit-level depolarizing noise (p = 0.005 is the main operating point). Stim simulates the circuit and produces 24 detector bits per shot. The network predicts whether the logical observable flipped. Networks are trained in PyTorch with quantization-aware training (binary weights and activations, optionally 3-bit first-layer weights), converted into a bit-exact integer "golden" model, exported to a bit-plane format, and loaded at runtime over UART into a reprogrammable XNOR-popcount inference engine on the FPGA. No DSP blocks are used. The project also tests my teacher-ranked (AWQ-style) saliency idea and dedicated-neuron expansion against random and plain controls across 5 seeds.

Pipeline (one line per stage)

- gen_data.py -> train.py / neuronexp.py -> golden.py -> export.py -> tb_engine / tb_top (simulation) -> build.tcl + program.tcl -> hil.py (board)

Important folders

- FPGAFlow/rtl/          hardware
  - bnn_engine.v      runtime-programmable BNN engine (neuron-serial, plane-serial XNOR-popcount)
  - cmd_parser.v      UART frame parser: loads layers/neurons/planes, runs inference
  - top.v             top level, 12 MHz clock, 1 Mbaud UART
  - uart_rx.v, uart_tx.v
- FPGAFlow/sim/          testbenches
  - tb_engine.v       loads an exported network into the engine and checks every golden vector
  - tb_top.v          full system test through the UART pins
- FPGAFlow/host/         Python: data, training, golden model, export, hardware tests, figures
- FPGAFlow/data/         Stim circuits (.stim), datasets (.npz), PyMatching baseline (baseline_d3_r3.json)
- FPGAFlow/models/       trained checkpoints (.pt); study/, nexp/, pilot*/ subfolders per experiment
- FPGAFlow/build/        exported networks, one folder per model (net.json, *.hex, load.bin, hil_result.json)
- FPGAFlow/build/fpga/   bitstream (top.bit) and Vivado reports (reports/utilization.rpt, reports/timing.rpt)
- FPGAFlow/jobs/         job lists for the experiment queues (study.txt, nexp.txt, pilot*.txt)
- FPGAFlow/logs/         per-job training logs
- FPGAFlow/results/      all result data, analyses and hardware-test logs (main evidence folder)
- FPGAFlow/portfolio/    final figures (PNG/SVG), summary.pdf, results_video.mp4
- FPGAFlow/constraints/pltw_s7.xdc   pin constraints
- FPGAFlow/build.tcl, program.tcl    Vivado build and JTAG programming

Host scripts (FPGAFlow/host/)

- gen_data.py       Stim datasets + PyMatching baseline
- train.py          trains the full-precision teacher, plain BNN and saliency-expanded BNN
- neuronexp.py      dedicated-neuron expansion (+-2 / +-4 / +-7 detector weights)
- golden.py         bit-exact integer model of the hardware; checks against PyTorch
- export.py         writes engine hex files, load.bin and golden test vectors
- hil.py            hardware-in-the-loop test: streams shots to the board, compares to golden
- demo.py           live demo readout (FPGA LER vs PyMatching)
- showdown.py       loads several designs in turn and scores them on the same shots
- make_study.py, run_jobs.py, sweep.sh, overnight.py   experiment queues and automation
- analyze_study.py, analyze_nexp.py, summarize.py      tables and figures from the results
- make_figures.py, make_video.py                       portfolio figures, summary.pdf and video
- requirements.txt  Python dependencies

Usage (run from FPGAFlow/)

- pip install -r host/requirements.txt
- python host/gen_data.py --d 3 --p 0.001 0.003 0.005 0.01                generate data + baseline
- python host/train.py --data data/d3_r3_p0.005.npz --model fp             train the teacher
- python host/train.py --data data/d3_r3_p0.005.npz --model bnn            train a plain BNN
- python host/train.py --data data/d3_r3_p0.005.npz --model expanded --salient 0.05 --k 2
- add --saliency random to any expanded run for the random control
- python host/make_study.py && python host/run_jobs.py jobs/study.txt --parallel 3   full 5-seed study
- python host/golden.py models/<model>.pt                                  golden LER + mismatches vs PyTorch
- python host/export.py models/<model>.pt                                  writes build/<model>/
- vivado -mode batch -source build.tcl                                     build build/fpga/top.bit
- vivado -mode batch -source program.tcl                                   program the board over JTAG
- python host/hil.py --port COM10 --model build/<model> --n all            1M-shot hardware test
- python host/demo.py --port COM10 --n 200000                              live demo
- python host/showdown.py --n 30000 --pause                                multi-design showdown for video
- python host/analyze_study.py ; python host/analyze_nexp.py               regenerate analysis tables
- python host/make_figures.py ; python host/make_video.py                  regenerate portfolio media

Backing for statistics

- 1.63% logical error rate on the Spartan-7
  - FPGAFlow/results/hil_full_L0n24.log  (fpga_ler 0.016315, model exp_d3_r3_p0.005_s5_k3_awq_L0n24)
  - also FPGAFlow/results/OVERNIGHT_STATUS.md, "FPGA hardware tests" table
- 5-seed mean 1.68%
  - FPGAFlow/results/analysis_study.md, table A, row n=24 (0.01682 +- 0.00030, n=5)
  - same value in table C, row "L0 3-bit BNN, width 128"
  - raw per-seed results: FPGAFlow/results/study.jsonl
- PyMatching 1.72%
  - FPGAFlow/data/baseline_d3_r3.json, p = 0.005 entry (pymatching_ler 0.017178, 1,000,000 test shots)
  - repeated in every hil_full_*.log as pymatching_ler
- Bit-exact over 1M hardware shots, 0 mismatches
  - FPGAFlow/results/hil_full_*.log (5 models; each ends with mismatches_vs_golden 0, bad_replies 0, PASS (bit-exact))
  - per-model copies: FPGAFlow/build/<model>/hil_result.json
- PyTorch -> golden model agreement
  - output of host/golden.py (golden vs pytorch mismatches)
  - golden LER recorded in FPGAFlow/build/<model>/net.json and FPGAFlow/results/export_*.log
- Golden -> simulation agreement
  - FPGAFlow/results/sim_tb_engine.log  (2000 vectors, 0 mismatches)
  - FPGAFlow/results/sim_tb_top.log     (50 inference frames through UART, 0 mismatches)
- Knocking out dedicated neurons raised LER 59%; random detectors 57%
  - FPGAFlow/results/analysis_nexp.md, first table
  - uniform / awq / n=12: 0.02371 -> 0.03770 (+59%)
  - uniform / random / n=12: 0.02384 -> 0.03747 (+57%)
  - raw data: FPGAFlow/results/nexp.jsonl
- Learned +-2 / +-4 / +-7 weight values in dedicated neurons
  - FPGAFlow/results/analysis_nexp.md, second table
- 3-bit first layer beats dedicated neurons at every hardware budget
  - XNOR-bit cost vs LER for 3-bit first layer: FPGAFlow/results/analysis_study.md, table C
  - XNOR-bit cost vs LER for neuron expansion: FPGAFlow/results/OVERNIGHT_STATUS.md, "Neuron-expansion study" table
  - figure: FPGAFlow/portfolio/3_cost_vs_accuracy.png and 6_neuron_expansion.png
- Teacher-ranked (AWQ) saliency vs wanda / inverse / random controls
  - FPGAFlow/results/analysis_study.md, table A
  - figure: FPGAFlow/portfolio/2_saliency.png
- 5 seeds per configuration
  - n=5 in every row of analysis_study.md and OVERNIGHT_STATUS.md; job lists in FPGAFlow/jobs/study.txt and nexp.txt
- 0 DSPs, 1535 LUTs, 2254 registers, 15.5 BRAM tiles
  - FPGAFlow/build/fpga/reports/utilization.rpt
  - figure: FPGAFlow/portfolio/4_fpga_resources.png
- Timing
  - FPGAFlow/build/fpga/reports/timing.rpt
- 2063 clock cycles per inference (about 172 us at 12 MHz)
  - FPGAFlow/results/sim_tb_engine.log
- About 2,555-2,603 shots/s end-to-end over UART
  - shots_per_s in FPGAFlow/results/hil_full_*.log
- Full-precision teacher LERs (w32 to w384)
  - FPGAFlow/results/analysis_study.md, first line
- Model selection uses a validation split, not the test set
  - FPGAFlow/host/train.py: load_data() splits off val; fit() keeps the best epoch by val LER
- All portfolio figures and the video are generated from the result files above
  - FPGAFlow/host/make_figures.py and make_video.py (source files listed in their docstrings)
  - FPGAFlow/results/make_figures.log
