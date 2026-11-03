# Creates the Vivado project for the RS(8,4) demo.
#   From the Vivado Tcl console:  source C:/users/johna/ReedSolomon/tools/create_project.tcl
#   Or batch:                     vivado -mode batch -source C:/users/johna/ReedSolomon/tools/create_project.tcl
# Run tools/rs_ref.py first so sim/vectors.mem exists.
set root [file normalize [file join [file dirname [info script]] ..]]

create_project ReedSolomon $root/vivado -part xc7s25csga225-1 -force

add_files -fileset sources_1 [glob $root/src/*.v] $root/src/gf16.vh
set_property file_type {Verilog Header} [get_files $root/src/gf16.vh]
set_property include_dirs $root/src [get_filesets sources_1]
add_files -fileset constrs_1 $root/src/rs_top.xdc

add_files -fileset sim_1 [glob $root/sim/*.v] $root/sim/vectors.mem
set_property include_dirs $root/src [get_filesets sim_1]

set_property top rs_top [get_filesets sources_1]
set_property top tb_rs_top [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {all} -objects [get_filesets sim_1]
update_compile_order -fileset sources_1
update_compile_order -fileset sim_1
puts "Project created: $root/vivado/ReedSolomon.xpr"
