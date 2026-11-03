# Run inside the open Hamming project:  source C:/users/johna/Hamming/tools/add_l3_to_project.tcl
set src C:/users/johna/Hamming/Hamming.srcs

add_files -fileset sources_1 [list \
    $src/sources_1/new/secded_encoder.v \
    $src/sources_1/new/secded_decoder.v \
    $src/sources_1/new/error_injector.v \
    $src/sources_1/new/lfsr16.v \
    $src/sources_1/new/debounce.v \
    $src/sources_1/new/uart_rx.v \
    $src/sources_1/new/uart_tx.v \
    $src/sources_1/new/hamming_top.v]

add_files -fileset sim_1 [list \
    $src/sim_1/new/tb_secded.v \
    $src/sim_1/new/tb_hamming_top.v]

set_property top hamming_top [get_filesets sources_1]
set_property top tb_hamming_top [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
