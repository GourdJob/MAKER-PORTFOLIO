# Neuron-expansion: inside the trained models

Knockout on the first 300,000 test shots: dedicated neurons' outputs set to 0.

| schedule | variant | salient n | LER (normal) | LER (dedicated off) | relative change |
|---|---|---|---|---|---|
| tiered | awq | 3 | 0.02777 | 0.02951 | +6% |
| tiered | awq | 6 | 0.02940 | 0.03492 | +19% |
| tiered | awq | 12 | 0.02528 | 0.03052 | +21% |
| tiered | plain | 3 | 0.02967 | 0.03243 | +9% |
| tiered | plain | 6 | 0.02770 | 0.03098 | +12% |
| tiered | plain | 12 | 0.02583 | 0.03188 | +23% |
| tiered | random | 3 | 0.02795 | 0.03138 | +12% |
| tiered | random | 6 | 0.02626 | 0.03021 | +15% |
| tiered | random | 12 | 0.02794 | 0.03392 | +21% |
| uniform | awq | 3 | 0.02697 | 0.02985 | +11% |
| uniform | awq | 6 | 0.02448 | 0.03025 | +24% |
| uniform | awq | 12 | 0.02371 | 0.03770 | +59% |
| uniform | plain | 3 | 0.02824 | 0.03071 | +9% |
| uniform | plain | 6 | 0.02712 | 0.03464 | +28% |
| uniform | plain | 12 | 0.02434 | 0.03495 | +44% |
| uniform | random | 3 | 0.02732 | 0.03045 | +11% |
| uniform | random | 6 | 0.02523 | 0.03161 | +25% |
| uniform | random | 12 | 0.02384 | 0.03747 | +57% |

Learned weight on the salient detector, by unit type (all non-plain models):

| unit | range | learned value: count |
|---|---|---|
| ±1±1 | ±2 | -2: 244 (39%), +0: 251 (40%), +2: 135 (21%) |
| ±2±2 | ±4 | -4: 234 (35%), +0: 221 (33%), +4: 205 (31%) |
| ±4±2±1 | ±7 | -7: 146 (44%), -5: 25 (8%), -3: 3 (1%), -1: 1 (0%), +5: 5 (2%), +7: 150 (45%) |
