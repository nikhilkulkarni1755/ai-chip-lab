# systolic_os on sky130hd vs nangate45 (stage 62_pdk_compare)

Same RTL (4x4 INT8 output-stationary array), same flow, same 30 % core utilization; only the process design kit differs. nangate45 is a 45 nm open library, sky130hd a 130 nm one.

## Search and what it establishes
sky130hd, 30 % utilization (results/pdk_compare/sky130hd_points.jsonl):

| clock ns | setup WNS ns | area um2 | std cells | power mW | lock hold min |
|---|---|---|---|---|---|
| 8.0 | +1.037 | 119,978 | 14,278 | 63.0 | 14.7 |
| 6.75 | +0.188 | 121,473 | 14,473 | 76.1 | 19.2 |
| 5.5 | -0.224 | 138,784 | 15,845 | 120.3 | 23.8 |
| 4.0 | -1.722 | 151,607 | 16,771 | 195.4 | 28.1 |

The frontier is **a coarse bracket, not a precise frontier**: 5.5 ns fails and 6.75 ns closes, so the true closure period lies between them (resolution 1.25 ns). 6.75 ns is the fastest tested closing point and is used for the comparison. The nangate45 frontier is bracketed to 0.05 ns (1.20 fails, 1.25 closes). The plan was changed once after two results: a 6.75 ns refinement point was added (Decision P2-11a); the criteria were not touched.

## Comparison at each PDK's fastest tested closing clock
| | nangate45 (1.25 ns) | sky130hd (6.75 ns) | ratio |
|---|---|---|---|
| area um2 | 23,970 | 121,473 | 5.1x |
| standard cells | 11,924 | 14,473 | 1.2x |
| clock period | 1.25 ns | 6.75 ns | 5.4x (an upper bound on the slowdown at the true frontier) |
| total power | 102 mW | 76 mW | 0.75x (but at a 5.4x slower clock) |
| energy per cycle | 128 pJ | 514 pJ | 4.0x |

Power is lower only because the clock is 5.4x slower; energy per cycle is the fair figure and is 4x higher on sky130hd. Reported leakage on sky130hd is about 5e-8 W, essentially nil, because the sky130 Liberty files carry tiny leakage values; do not read it as a physical statement.

## Why sky130 is slower and larger
Transistors at 130 nm are bigger and have longer gate delay and higher capacitance than at 45 nm, so each gate is slower and each cell occupies more area; wires are also longer in absolute terms. The cell count differs by only 1.2x (similar logic, similar mapping), while the area ratio is 5.1x, which is the cell size difference. Roughly (130/45)^2 = 8.3 is the ideal scaling of area; the observed 5.1x is lower because the libraries are not equal-density.

Caveats: one array size, one utilization, coarse bracket; the two libraries have different drive-strength sets and the flows tune differently.
