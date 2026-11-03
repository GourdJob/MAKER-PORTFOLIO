# Program the PLTW S7 over JTAG with build/fpga/top.bit (volatile: lost on power-off).
#   vivado -mode batch -source program.tcl
set root [file dirname [file normalize [info script]]]
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set dev [lindex [get_hw_devices xc7s25*] 0]
current_hw_device $dev
set_property PROGRAM.FILE $root/build/fpga/top.bit $dev
program_hw_devices $dev
puts "PROGRAM_DONE [get_property NAME $dev]"
close_hw_manager
