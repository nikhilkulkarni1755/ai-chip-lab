# SRAM modelling with CACTI (stage 63_sram_cacti)

## What CACTI is
CACTI (HP Labs; version 7 here, official repository at commit `1ffd8dfb...`, built into the pinned image
`lab-cacti:20261012`) is an **analytical** model of memory arrays. Given capacity, port count, access width and a technology node, it
searches over internal organisations (how the array is cut into sub-arrays, how wide the word lines are) and reports area, access
time, cycle time, dynamic energy per access and leakage power from closed-form circuit equations and ITRS-style device
parameters. It does not use a foundry SRAM compiler and does not simulate transistors. Treat results as trends and order of magnitude.

## What was modelled
* Plain scratchpad (`-cache type "ram"`, no tags), 128-byte access (one row of the 128-wide array, 1-byte words as in SCALE-Sim),
  one read/write port, one bank, 350 K, `itrs-hp` cells and periphery, ECC off, CACTI's default optimisation target.
* Capacities = the buffer sizes used elsewhere in the lab: 16, 64 and 1024 kB per buffer (sweep A small/default/large; 64 kB is also the
  bundled `scale.cfg` used for the Task 3 roofline runs) and 2048 and 6144 kB (the bundled TPU-like `google.cfg`: 6 MiB ifmap and
  filter, 2 MiB ofmap). SCALE-Sim's per-buffer size is the total capacity of a double-buffered scratchpad (90 % active, 10 % prefetch
  inside it), so one SRAM of that size is modelled; nothing extra for double buffering.
* Node 45 nm. CACTI ships parameter sets for 22 to 180 nm. 45 nm equals the feature size of the Nangate45 library used by the lab's ORFS
  runs, but the device numbers are CACTI's, not Nangate45's, and the lab has no SRAM macro in any ORFS run, so there is **nothing to
  compare the absolute numbers against**. One 64 kB point at 90 nm checks the scaling.

## Results (`results/sram_cacti.json`, plot `demo/assets/sram_cacti.png`)
| per buffer | area mm2 | access ns | read energy per 128 B access | leakage |
|---|---|---|---|---|
| 16 kB | 0.141 | 0.37 | 0.078 nJ | 16 mW |
| 64 kB | 0.268 | 0.50 | 0.093 nJ | 61 mW |
| 1024 kB | 4.19 | 1.96 | 0.50 nJ | 0.91 W |
| 2048 kB | 8.10 | 2.64 | 0.83 nJ | 1.8 W |
| 6144 kB | 26.1 | 4.16 | 1.73 nJ | 5.4 W |

All seven registered pass/fail criteria pass (area, access time, read energy and leakage grow with capacity; area per kB stays in
0.002-0.05 mm2; 64 kB area ratio 90 nm / 45 nm = 4.00, the ideal square law; byte-identical repeat runs). The criteria were written before the
first run (commit 028b413) and not changed. CACTI accepted 6144 kB, which is not a power of two; the planned 4096 + 2048 fallback was not needed.

## How it relates to the rest of the lab
`results/sram_energy_model.json` combines these numbers with sweep A for ViT-S on a 128x128 output-stationary array, at the three SRAM
sizes. SRAM read energy per inference is 3.5, 4.2 and 22.6 uJ (16, 64, 1024 kB per buffer) while DRAM traffic falls from 5.78 M to
5.58 M to 2.92 M words. DRAM and MAC energy are **not modelled**; instead the break-even is computed: growing the buffers from 64 kB to
1024 kB pays off only if a DRAM word costs more than about 6.9 pJ (3.3 pJ for 16 to 64 kB). Whether that holds for real DRAM is outside
this model (DRAM access is commonly quoted as one to two orders of magnitude more costly than on-chip SRAM per bit; not measured here).
Leakage of three 1024 kB buffers (2.7 W at CACTI's ITRS-HP, 350 K setting) dominates; at an assumed 1 GHz it would be about 100 uJ over this run,
more than everything else in the SRAM model, which is why low-leakage cells would be the first thing to change in a real design.

## Caveats
* Analytical model; HP (high-leakage) device assumption; not Nangate45; no layout, no sense-amplifier or SRAM-macro specifics.
* All SRAM accesses are charged as reads (writes cost 1.2-2x in CACTI): a lower bound.
* Cycle time is not monotone in capacity (6144 kB 2.36 ns < 2048 kB 2.51 ns) because CACTI's optimiser picks different internal
  organisations; access time, area and energy, which the criteria cover, are monotone.
* The energy figure is an order-of-magnitude model; a single workload and one dataflow.
