# Task 3 roofline check: what it is, why the first version failed, what the new one proves

## The roofline in one paragraph
A layer does `2*M*N*K` floating-point (here INT8) operations and must move at least
`ifmap + filter + ofmap` bytes to and from DRAM. Their ratio is the layer's **arithmetic intensity (AI)**,
FLOP per byte (`model/analytic.py::layer_intensity`, hand-checked in `model/test_intensity.py`: ResNet-18
`Conv3_s`, M=841, N=128, K=64: 13,778,944 FLOP / 316,544 B = 43.53 FLOP/B; one byte per word because SCALE-Sim
hard-codes `word_size = 1`). An accelerator has a peak compute rate (`2*R*C` FLOP/cycle for an R x C array) and
a DRAM bandwidth B (bytes/cycle). Attainable performance is `min(peak, B * AI)`: layers with AI below the
**ridge** `peak / B` are limited by memory ("bandwidth-bound"), layers above it by compute. The testable claim
for a simulator is therefore directional: **low-AI layers should be the ones that wait on memory.**

## What SCALE-Sim 3.0.0's bandwidth modes really do (read from its source at the pinned tag v3.0.0)
The key is `InterfaceBandwidth` in the `[run_presets]` section of the config
(`scalesim/scale_config.py`, lines 76-90):

* **`CALC`** (the bundled `scale.cfg`, and what sweep A used): SCALE-Sim *computes* the DRAM bandwidth each
  layer needs. `scalesim/memory/read_buffer_estimate_bw.py` states in a comment "In estimate mode, operation is
  stall free" (line 120). Stall cycles are therefore zero **by construction**, and `BANDWIDTH_REPORT.csv`
  contains the *required* DRAM bandwidth. Correlating stalls with intensity here has nothing to correlate.
  What *is* meaningful here: a layer with low intensity must be reported as needing *more* DRAM bandwidth.
* **`USER`** (the bundled `google.cfg`): SCALE-Sim *enforces* a bandwidth. In `single_layer_sim.py` the
  ifmap and filter DRAM-side rates are taken from `IfmapSRAMBankBandwidth` / `FilterSRAMBankBandwidth`
  (words/cycle; `read_buffer.py` asserts bank bandwidth x number of banks = total) and the ofmap rate from
  `Bandwidth`. Stalls then appear when a double-buffered SRAM half cannot be refilled in time. If the buffers hold
  the whole layer (6 MiB in `google.cfg`) the data is prefetched *before* cycle 0, which is reported as
  "Total Cycles (incl. prefetch)" but **not** as stall cycles.

## Why the original check failed
`results/evidence/31_original_stalls.txt`: the Part 1 bundled run used `google.cfg`
(`InterfaceBandwidth = USER`, 10 words/cycle, 6144/6144/2048 kB SRAM). Every one of the 15 layer-runs
(5 AlexNet layers x ws/os/is) has `Stall Cycles = 0`, and the DRAM-bandwidth columns merely echo the 10-word cap
(10.0, 10.0). There was nothing to correlate with intensity. The first workaround (16 hand-picked synthetic
GEMMs on a 16x16 array, binary classification against a 5 % stall threshold, 80 % agreement gate) measured a
different thing: the result depends on an arbitrary threshold and on class balance, and the synthetic set is not
a real layer set. Its numbers are kept in `results/t3_summary.json` under `superseded`.
(Note: the hypothesis "the bundled run was in calculated-bandwidth mode" was wrong: it was USER mode, but with
buffers and bandwidth that hide all memory time. Sweep A, by contrast, did run in CALC mode.)

## The pre-registered replacement (`model/t3_roofline2_criteria.json`)
Written and committed before any new run; thresholds are not revisited. Layer set: **all 21 layers of the
bundled `Resnet18.csv`** on a 128 x 128 array with the bundled `scale.cfg` SRAM (64 kB per buffer).

* **Criterion B (mode independent, CALC mode):** per dataflow, Spearman rho(AI, required DRAM bandwidth
  reported by SCALE-Sim) <= -0.6. Low-AI layers must need more bandwidth.
* **Criterion A (USER mode):** per dataflow, Spearman rho(AI, stall fraction) <= -0.6 at **both** bandwidth
  levels B = 64 and 256 words/cycle and < +0.3 at both; stall cycles must not increase with B. The levels
  were chosen from the AI distribution by the ridge rule (ridge = peak / B = 512 and 128 FLOP/B).
* **Amendment P2-A2 (cost only):** the registered design had a third, lower level (B = 16) and required 2 of 3
  levels. A single 21-layer run took more than 27 minutes of exclusive machine time (large layers exceed
  170 s each at 1.7 GB), so the low level was dropped and "both levels" is required (stricter).
  Evidence: `logs/part2/31_roofline_fix/cost_probe.log`. No result existed when the amendment was made.
* One SCALE-Sim invocation per layer: the combined 21-layer run was OOM-killed (exit 137) because SCALE-Sim keeps
  every layer's matrices alive until the end. Layers are independent in SCALE-Sim, and
  `model/test_perlayer.py` shows identical per-layer rows for combined and per-layer runs.

## What the new check proves (and does not)

### Criterion B (CALC mode): evaluated on all 21 real layers, FAILS for all three dataflows
Spearman rho(AI, required DRAM bandwidth), 128 x 128, bundled `scale.cfg`, threshold rho <= -0.6
(`results/t3/roofline2/rl2_calc_<df>.json`; recomputed independently from the saved reports by arch and by demo):

| dataflow | rho(AI, required bw) | threshold | verdict |
|---|---|---|---|
| ws | +0.366 | <= -0.6 | FAIL (wrong sign) |
| os | -0.556 | <= -0.6 | FAIL (right sign, not strong enough) |
| is | -0.509 | <= -0.6 | FAIL (right sign, not strong enough) |

So with the pre-registered statistic and threshold the stage verdict is **FAIL on criterion B**, whatever criterion A
gives. Nothing was changed after seeing these numbers: not the criterion, not the layer set, not the statistic.
(Supplementary, not gating: rho against the *effective* intensity, FLOP per DRAM word SCALE-Sim actually moved,
is +0.46 / -0.80 / -0.66 for ws / os / is.)

**Why intensity does not rank-order the required bandwidth, ws in particular (an explanation, not a new criterion).**
In CALC mode the "required bandwidth" is not total traffic over total time. `read_buffer_estimate_bw.py`
(SCALE-Sim 3.0.0) splits the SRAM into an active part (90 %) and a prefetch part (10 %) and, every time the array has
consumed one more prefetch-sized set of *new* addresses, sets the bandwidth to `ceil(elements to prefetch /
cycles available)`, i.e. how fast new data are first touched by the array. That is a local property of the dataflow
and of the fold structure, not a ratio of the layer's compulsory bytes to its compute. Per-layer numbers for ws
(`rl2_calc_ws.json`) show it:
* The last, tiny classifier layer `FC` (M=1) has the lowest intensity of all (2.0 FLOP/B) and the highest required
  bandwidth (167 words/cycle), as the roofline predicts; but the three `Conv5_x` layers with K=4608 and M=25
  (intensity 49) need only 56.6 words/cycle, the lowest of the whole network, while the high-intensity
  layers `Conv3_1b/2a/2b` (intensity 596, the highest) need 162. A plausible reading (not separately tested): in weight
  stationary the cycle count of the deep layers is dominated by many long filter folds with few output pixels, so
  little new data is first touched per cycle, whereas the early layers with large M stream new ifmap data nearly
  every cycle.
* Re-fetch also decouples the two: the simulated ifmap DRAM reads are 5-13 times the ifmap tensor for the 3x3
  layers (64 kB buffers), so the "effective" intensity (FLOP per word moved, 42 to 128) is far flatter than the
  compulsory intensity (2 to 596). Intensity as defined by tensor sizes is a good predictor only when the
  working set fits on chip; at 64 kB it does not.
* 9 of the 21 layers repeat an earlier shape (identical numbers, handled as ties by average ranks), so the rank
  statistic has only 12 distinct points; moderate rho values are not strongly distinguishable from
  noise.
This explains the direction of the failure for ws; it does not rescue the check, and the roofline claim "low
intensity -> more required bandwidth" is **not confirmed by SCALE-Sim's CALC-mode output at the pre-registered
strength** (it holds weakly for os and is, not for ws).

### Criterion A (USER mode, stall fraction vs intensity under a fixed bandwidth): not evaluated (cost)
The 12 user-bandwidth runs (3 dataflows x B = 64, 256) need roughly 4 h of exclusive lock; the largest layers
exceed 170 s each. Per decision P2-8 only one probe hold (`rl2_user_ws_high`, at most 9 minutes) was run to measure
the cost, and criterion A is reported per cell as "not evaluated (cost)" together with that measurement, never as
pass or fail. See the probe result below.

**Probe result (decision P2-8).** One lock hold of `rl2_user_ws_high` (B = 256, ws): its largest layer, `Conv5_1b`
(M=25, N=512, K=4608), ran alone with the whole 480 s budget and was killed at 481 s without finishing; 0 of 21
layers completed (`results/evidence/31_a_probe.txt`, `results/t3/roofline2/rl2_user_ws_high/blocked.json`). A single
layer of one criterion-A cell therefore does not fit in a 10-minute lock hold, SCALE-Sim cannot checkpoint inside a
layer, and criterion A is **not evaluated (cost)**: ws B=256 `blocked` (probe), the other five cells `not_run`. It is
neither a pass nor a fail. The stage verdict is FAIL because of criterion B alone.
