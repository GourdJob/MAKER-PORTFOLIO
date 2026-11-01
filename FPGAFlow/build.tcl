# Non-project Vivado build for the PLTW S7 BNN decoder (does not touch FPGAFlow.xpr).
#   vivado -mode batch -source build.tcl
# Outputs: build/fpga/top.bit, build/fpga/reports/{utilization,timing}.rpt
set root [file dirname [file normalize [info script]]]
set out  $root/build/fpga
file mkdir $out/reports

read_verilog [glob $root/rtl/*.v]
read_xdc $root/constraints/pltw_s7.xdc

synth_design -top top -part xc7s25csga225-1
opt_design
place_design
route_design

report_utilization    -file $out/reports/utilization.rpt
report_utilization    -hierarchical -file $out/reports/utilization_hier.rpt
report_timing_summary -file $out/reports/timing.rpt
report_drc            -file $out/reports/drc.rpt
write_bitstream -force $out/top.bit
puts "BUILD_DONE"
