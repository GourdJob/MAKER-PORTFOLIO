## Cmod S7 (xc7s25csga225-1) constraints for `hamming_top` (and `led_test_top`, same ports).
## Pin numbers follow the Digilent Cmod S7 master XDC.

## Configuration
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

## Clock (12 MHz)
set_property -dict { PACKAGE_PIN M9  IOSTANDARD LVCMOS33 } [get_ports clk]; #IO_L13P_T2_MRCC_14 Sch=gclk
create_clock -add -name sys_clk_pin -period 83.33 -waveform {0 41.66} [get_ports clk];

## LEDs
set_property -dict { PACKAGE_PIN E2  IOSTANDARD LVCMOS33 } [get_ports {led[0]}]; #Sch=led[1]
set_property -dict { PACKAGE_PIN K1  IOSTANDARD LVCMOS33 } [get_ports {led[1]}]; #Sch=led[2]
set_property -dict { PACKAGE_PIN J1  IOSTANDARD LVCMOS33 } [get_ports {led[2]}]; #Sch=led[3]
set_property -dict { PACKAGE_PIN E1  IOSTANDARD LVCMOS33 } [get_ports {led[3]}]; #Sch=led[4]

## RGB LED (active low)
set_property -dict { PACKAGE_PIN F2  IOSTANDARD LVCMOS33 } [get_ports {rgb[0]}]; #IO_L10P_T1_34 Sch=led0_r
set_property -dict { PACKAGE_PIN D3  IOSTANDARD LVCMOS33 } [get_ports {rgb[1]}]; #IO_L9N_T1_DQS_34 Sch=led0_g
set_property -dict { PACKAGE_PIN F1  IOSTANDARD LVCMOS33 } [get_ports {rgb[2]}]; #IO_L10N_T1_34 Sch=led0_b

## Buttons
set_property -dict { PACKAGE_PIN D2  IOSTANDARD LVCMOS33 } [get_ports {btn[0]}]; #Sch=btn[0]
set_property -dict { PACKAGE_PIN D1  IOSTANDARD LVCMOS33 } [get_ports {btn[1]}]; #Sch=btn[1]

## USB-UART bridge
set_property -dict { PACKAGE_PIN K15 IOSTANDARD LVCMOS33 } [get_ports uart_rx]; #Sch=uart_txd_in  (PC -> FPGA)
set_property -dict { PACKAGE_PIN L12 IOSTANDARD LVCMOS33 } [get_ports uart_tx]; #Sch=uart_rxd_out (FPGA -> PC)

## Breadboard LEDs on the DIP pins - live decoding display (MSB at the top pin of each header)
## J1 PIO01-08: received byte
set_property -dict { PACKAGE_PIN L1  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[7]}]; #Sch=pio[01]
set_property -dict { PACKAGE_PIN M4  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[6]}]; #Sch=pio[02]
set_property -dict { PACKAGE_PIN M3  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[5]}]; #Sch=pio[03]
set_property -dict { PACKAGE_PIN N2  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[4]}]; #Sch=pio[04]
set_property -dict { PACKAGE_PIN M2  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[3]}]; #Sch=pio[05]
set_property -dict { PACKAGE_PIN P3  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[2]}]; #Sch=pio[06]
set_property -dict { PACKAGE_PIN N3  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[1]}]; #Sch=pio[07]
set_property -dict { PACKAGE_PIN P1  IOSTANDARD LVCMOS33 } [get_ports {pio_rx[0]}]; #Sch=pio[08]
## J1 PIO09: HI nibble uncorrectable
set_property -dict { PACKAGE_PIN N1  IOSTANDARD LVCMOS33 } [get_ports pio_unc_hi];  #Sch=pio[09]

## J2 PIO48-41: HI codeword error mask
set_property -dict { PACKAGE_PIN A4  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[7]}]; #Sch=pio[48]
set_property -dict { PACKAGE_PIN A3  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[6]}]; #Sch=pio[47]
set_property -dict { PACKAGE_PIN B4  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[5]}]; #Sch=pio[46]
set_property -dict { PACKAGE_PIN B3  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[4]}]; #Sch=pio[45]
set_property -dict { PACKAGE_PIN C1  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[3]}]; #Sch=pio[44]
set_property -dict { PACKAGE_PIN B1  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[2]}]; #Sch=pio[43]
set_property -dict { PACKAGE_PIN B2  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[1]}]; #Sch=pio[42]
set_property -dict { PACKAGE_PIN A2  IOSTANDARD LVCMOS33 } [get_ports {pio_mask_hi[0]}]; #Sch=pio[41]
## J2 PIO40: HI nibble corrected
set_property -dict { PACKAGE_PIN C5  IOSTANDARD LVCMOS33 } [get_ports pio_cor_hi];       #Sch=pio[40]

## J3 PIO16-23: LO codeword error mask
set_property -dict { PACKAGE_PIN P14 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[7]}]; #Sch=pio[16]
set_property -dict { PACKAGE_PIN P15 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[6]}]; #Sch=pio[17]
set_property -dict { PACKAGE_PIN N13 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[5]}]; #Sch=pio[18]
set_property -dict { PACKAGE_PIN N15 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[4]}]; #Sch=pio[19]
set_property -dict { PACKAGE_PIN N14 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[3]}]; #Sch=pio[20]
set_property -dict { PACKAGE_PIN M15 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[2]}]; #Sch=pio[21]
set_property -dict { PACKAGE_PIN M14 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[1]}]; #Sch=pio[22]
set_property -dict { PACKAGE_PIN L15 IOSTANDARD LVCMOS33 } [get_ports {pio_mask_lo[0]}]; #Sch=pio[23]

## J4 PIO31-29: HI syndrome, PIO28-26: LO syndrome
set_property -dict { PACKAGE_PIN J11 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_hi[2]}]; #Sch=pio[31]
set_property -dict { PACKAGE_PIN M13 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_hi[1]}]; #Sch=pio[30]
set_property -dict { PACKAGE_PIN L13 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_hi[0]}]; #Sch=pio[29]
set_property -dict { PACKAGE_PIN J15 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_lo[2]}]; #Sch=pio[28]
set_property -dict { PACKAGE_PIN K14 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_lo[1]}]; #Sch=pio[27]
set_property -dict { PACKAGE_PIN L14 IOSTANDARD LVCMOS33 } [get_ports {pio_syn_lo[0]}]; #Sch=pio[26]

## All IO is asynchronous to the board clock (UART, buttons, LEDs) - no IO timing to check
set_false_path -from [get_ports {uart_rx btn[*]}]
set_false_path -to   [get_ports {uart_tx led[*] rgb[*] pio_*}]
