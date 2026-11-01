# Run inside the open Hamming project:  source C:/users/johna/Hamming/tools/cleanup_project.tcl
# Removes the old blinky files from the project (they stay on disk), adds the RX FIFO and the LED test top.
# Top is left as hamming_top; for the LED test run:  set_property top led_test_top [get_filesets sources_1]
set src C:/users/johna/Hamming/Hamming.srcs

foreach f [list \
    $src/sources_1/new/BlinkingLED.v \
    $src/sources_1/new/ClockDivider.v \
    $src/sim_1/new/testbench.v \
    $src/sim_1/new/testbench1.v \
    C:/users/johna/Hamming/testbench_behav.wcfg] {
    set obj [get_files -quiet $f]
    if {$obj ne ""} { remove_files $obj }
}

foreach f [list $src/sources_1/new/sync_fifo.v $src/sources_1/new/led_test_top.v] {
    if {[get_files -quiet $f] eq ""} { add_files -fileset sources_1 $f }
}

# The single-pin blink test constraints clash with LED.xdc (same clk pin) - keep them out of the build
set blink_xdc [get_files -quiet *pio_test.xdc]
if {$blink_xdc ne ""} { set_property IS_ENABLED false $blink_xdc }

set_property top hamming_top [get_filesets sources_1]
set_property top tb_hamming_top [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
