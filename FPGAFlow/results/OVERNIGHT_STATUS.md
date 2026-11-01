# Overnight run status

Last update: 2026-10-30 00:32:06

| step | result | minutes | output |
|---|---|---|---|
| neuron-expansion study (remaining jobs) | OK | 158.6 | results\nexp_progress_overnight.log |
| analyze main study | OK | 0.1 | results\analysis_study.md |
| export best 96-wide 3-bit-first-layer model | OK | 0.0 | results\export_exp_d3_r3_p0.005_s5_k3_awq_w96_L0n24_seed2.log |
| FPGA test best 96-wide 3-bit-first-layer model (1M shots) | OK | 6.6 | results\hil_full_exp_d3_r3_p0.005_s5_k3_awq_w96_L0n24_seed2.log |
| export best neuron-expansion model (nexp_d3_r3_p0.005_n12_awq_uniform_seed3) | OK | 0.1 | results\export_nexp_d3_r3_p0.005_n12_awq_uniform_seed3.log |
| FPGA test best neuron-expansion model (nexp_d3_r3_p0.005_n12_awq_uniform_seed3) (1M shots) | OK | 6.6 | results\hil_full_nexp_d3_r3_p0.005_n12_awq_uniform_seed3.log |
| portfolio figures + summary.pdf | OK | 0.1 | results\make_figures.log |

## FPGA hardware tests

| model | shots | mismatches vs golden | FPGA LER | PyMatching LER |
|---|---|---|---|---|
| exp_d3_r3_p0.005_s5_k3_awq_L0n24 | 1,000,000 | 0 | 0.016315 | 0.017178 |
| exp_d3_r3_p0.005_s5_k3_awq_w96_L0n24_seed2 | 1,000,000 | 0 | 0.016913 | 0.017178 |
| nexp_d3_r3_p0.005_n12_awq_uniform_seed3 | 1,000,000 | 0 | 0.022238 | 0.017178 |

## Neuron-expansion study (results/nexp.jsonl)

| schedule | variant | salient n | seeds | test LER mean ± std | XNOR bits | dedicated neurons |
|---|---|---|---|---|---|---|
| tiered | awq | 3 | 5 | 0.02754 ± 0.00092 | 21271 | 11 |
| tiered | awq | 6 | 5 | 0.02893 ± 0.00190 | 22189 | 17 |
| tiered | awq | 12 | 5 | 0.02498 ± 0.00106 | 24025 | 29 |
| tiered | plain | 3 | 5 | 0.02948 ± 0.00249 | 21256 | 11 |
| tiered | plain | 6 | 5 | 0.02741 ± 0.00218 | 22168 | 17 |
| tiered | plain | 12 | 5 | 0.02554 ± 0.00133 | 23992 | 29 |
| tiered | random | 3 | 5 | 0.02771 ± 0.00182 | 21271 | 11 |
| tiered | random | 6 | 5 | 0.02601 ± 0.00071 | 22189 | 17 |
| tiered | random | 12 | 5 | 0.02758 ± 0.00189 | 24025 | 29 |
| uniform | awq | 3 | 5 | 0.02667 ± 0.00086 | 21882 | 15 |
| uniform | awq | 6 | 5 | 0.02418 ± 0.00022 | 24180 | 30 |
| uniform | awq | 12 | 5 | 0.02336 ± 0.00121 | 28776 | 60 |
| uniform | plain | 3 | 5 | 0.02793 ± 0.00191 | 21864 | 15 |
| uniform | plain | 6 | 5 | 0.02679 ± 0.00226 | 24144 | 30 |
| uniform | plain | 12 | 5 | 0.02394 ± 0.00110 | 28704 | 60 |
| uniform | random | 3 | 5 | 0.02699 ± 0.00174 | 21882 | 15 |
| uniform | random | 6 | 5 | 0.02493 ± 0.00066 | 24180 | 30 |
| uniform | random | 12 | 5 | 0.02354 ± 0.00102 | 28776 | 60 |

Pipeline finished.
