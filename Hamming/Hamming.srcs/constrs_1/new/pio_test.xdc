## Cmod S7 - LED test on J1 pin 1
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

## 12 MHz clock
set_property -dict { PACKAGE_PIN M9 IOSTANDARD LVCMOS33 } [get_ports clk]
create_clock -add -name sys_clk_pin -period 83.33 -waveform {0 41.66} [get_ports clk]

## J1 pin 1 (PIO01)
set_property -dict { PACKAGE_PIN L1 IOSTANDARD LVCMOS33 } [get_ports pio01]

## Onboard LED0
set_property -dict { PACKAGE_PIN E2 IOSTANDARD LVCMOS33 } [get_ports led0]