## Cmod S7 (xc7s25csga225-1) constraints for `rs_top`.
## Pin numbers follow the Digilent Cmod S7 master XDC.

## Configuration
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

## Clock (12 MHz)
set_property -dict { PACKAGE_PIN M9  IOSTANDARD LVCMOS33 } [get_ports clk]; #Sch=gclk
create_clock -add -name sys_clk_pin -period 83.33 -waveform {0 41.66} [get_ports clk];

## Onboard LEDs
set_property -dict { PACKAGE_PIN E2  IOSTANDARD LVCMOS33 } [get_ports {led[0]}]; #Sch=led[1]
set_property -dict { PACKAGE_PIN K1  IOSTANDARD LVCMOS33 } [get_ports {led[1]}]; #Sch=led[2]
set_property -dict { PACKAGE_PIN J1  IOSTANDARD LVCMOS33 } [get_ports {led[2]}]; #Sch=led[3]
set_property -dict { PACKAGE_PIN E1  IOSTANDARD LVCMOS33 } [get_ports {led[3]}]; #Sch=led[4]

## RGB LED (active low)
set_property -dict { PACKAGE_PIN F2  IOSTANDARD LVCMOS33 } [get_ports {rgb[0]}]; #Sch=led0_r
set_property -dict { PACKAGE_PIN D3  IOSTANDARD LVCMOS33 } [get_ports {rgb[1]}]; #Sch=led0_g
set_property -dict { PACKAGE_PIN F1  IOSTANDARD LVCMOS33 } [get_ports {rgb[2]}]; #Sch=led0_b

## Buttons
set_property -dict { PACKAGE_PIN D2  IOSTANDARD LVCMOS33 } [get_ports {btn[0]}]; #Sch=btn[0]
set_property -dict { PACKAGE_PIN D1  IOSTANDARD LVCMOS33 } [get_ports {btn[1]}]; #Sch=btn[1]

## USB-UART bridge
set_property -dict { PACKAGE_PIN K15 IOSTANDARD LVCMOS33 } [get_ports uart_rx]; #Sch=uart_txd_in  (PC -> FPGA)
set_property -dict { PACKAGE_PIN L12 IOSTANDARD LVCMOS33 } [get_ports uart_tx]; #Sch=uart_rxd_out (FPGA -> PC)

## Seven-segment segments on DIP PIO41-48 (series resistors on the board): seg = {dp, g, f, e, d, c, b, a}
set_property -dict { PACKAGE_PIN A2  IOSTANDARD LVCMOS33 } [get_ports {seg[0]}]; #a  Sch=pio[41]
set_property -dict { PACKAGE_PIN B2  IOSTANDARD LVCMOS33 } [get_ports {seg[1]}]; #b  Sch=pio[42]
set_property -dict { PACKAGE_PIN B1  IOSTANDARD LVCMOS33 } [get_ports {seg[2]}]; #c  Sch=pio[43]
set_property -dict { PACKAGE_PIN C1  IOSTANDARD LVCMOS33 } [get_ports {seg[3]}]; #d  Sch=pio[44]
set_property -dict { PACKAGE_PIN B3  IOSTANDARD LVCMOS33 } [get_ports {seg[4]}]; #e  Sch=pio[45]
set_property -dict { PACKAGE_PIN B4  IOSTANDARD LVCMOS33 } [get_ports {seg[5]}]; #f  Sch=pio[46]
set_property -dict { PACKAGE_PIN A3  IOSTANDARD LVCMOS33 } [get_ports {seg[6]}]; #g  Sch=pio[47]
set_property -dict { PACKAGE_PIN A4  IOSTANDARD LVCMOS33 } [get_ports {seg[7]}]; #dp Sch=pio[48]

## Digit selects on DIP J1 PIO01-08 -> transistor bases (620 ohm series resistors on the board)
## dig[0] = leftmost digit (symbol c7) ... dig[7] = rightmost digit (symbol c0)
set_property -dict { PACKAGE_PIN L1  IOSTANDARD LVCMOS33 } [get_ports {dig[0]}]; #Sch=pio[01]
set_property -dict { PACKAGE_PIN M4  IOSTANDARD LVCMOS33 } [get_ports {dig[1]}]; #Sch=pio[02]
set_property -dict { PACKAGE_PIN M3  IOSTANDARD LVCMOS33 } [get_ports {dig[2]}]; #Sch=pio[03]
set_property -dict { PACKAGE_PIN N2  IOSTANDARD LVCMOS33 } [get_ports {dig[3]}]; #Sch=pio[04]
set_property -dict { PACKAGE_PIN M2  IOSTANDARD LVCMOS33 } [get_ports {dig[4]}]; #Sch=pio[05]
set_property -dict { PACKAGE_PIN P3  IOSTANDARD LVCMOS33 } [get_ports {dig[5]}]; #Sch=pio[06]
set_property -dict { PACKAGE_PIN N3  IOSTANDARD LVCMOS33 } [get_ports {dig[6]}]; #Sch=pio[07]
set_property -dict { PACKAGE_PIN P1  IOSTANDARD LVCMOS33 } [get_ports {dig[7]}]; #Sch=pio[08]

## All IO is asynchronous to the board clock - no IO timing to check
set_false_path -from [get_ports {uart_rx btn[*]}]
set_false_path -to   [get_ports {uart_tx led[*] rgb[*] seg[*] dig[*]}]
