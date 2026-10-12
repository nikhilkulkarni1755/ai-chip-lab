# Why the Task 2 reference designs "pass" with negative slack

**Short version.** `gcd` on nangate45 (reference clock 0.25 ns) finishes with setup WNS = -0.162 ns and 51 violating endpoints;
`gcd` on sky130hd (1.1 ns) finishes with WNS = -1.46 ns. Neither is timing-closed at its reference clock. ORFS's threshold
check still passes (27/27 rules) because it is a **regression guard, not a signoff check**: it fails only if a metric gets worse
than a recorded baseline plus a margin.

## The actual rule values (from `flow/designs/<platform>/gcd/rules-base.json` in the pinned image, copies in `results/t2/rules_*_gcd.json`)
| rule | nangate45 limit | ours | sky130hd limit | ours |
|---|---|---|---|---|
| `finish__timing__setup__ws` >= | -0.193 ns | -0.162 | -1.52 ns | -1.46 |
| `finish__timing__setup__tns` >= | -7.99 ns | -7.09 | -65.3 ns | -64.9 |
| `finish__timing__hold__ws` >= | -0.0125 ns | +0.088 | -0.055 ns | +0.532 |
| `finish__design__instance__area` <= | 1115 µm² | 943.5 | 5812 µm² | 5412.7 |
| `detailedroute__route__drc_errors` <= | 0 | 0 | 0 | 0 |

The rules are written to allow what the reference run itself achieved, plus a margin (generator `flow/util/genRuleFile.py`:
setup WNS limit = reference WNS - 5 % of the clock period; TNS limit = reference TNS - 20 % of the period; area/counts +15 %).
The reference clocks are set aggressively on purpose (commit "tighten clock period of multiple designs", 2026-08-21), so
the benchmark designs sit slightly below closure: the rules lock in "this much negative slack and no more". A negative-slack
limit in the rules file is the evidence: a rule `finish__timing__setup__ws >= -0.193` would make no sense for a design expected to close.

## What "WNS >= 0 means the design meets timing" implies here
Neither reference design meets timing at its reference clock. The closure clock for nangate45/gcd in this lab is measured by
sweep B (`results/sweeps/phys_frontier.json`): the **fastest clock with WNS >= 0 is ~0.42-0.425 ns** (0.425 ns at 30/40/60 %
utilization, 0.420 ns at 50 % where WNS is +5.9e-05 ns, i.e. zero margin), versus the 0.25 ns reference clock. The sky130hd
closure clock was not swept.

## Cross-check against ORFS's published values

**What the "published reference" is, exactly.** At the pinned commit ORFS ships **no measured reference metrics for gcd**: the golden
`metadata-base-ok.json` files were removed from the repo in Feb 2025, there is no published power value, and the CI dashboard is
online-only. What *is* shipped is `rules-base.json` (limits). The reference values used here are therefore **implied**: the limits un-padded with the
formulas of ORFS's rule generator (`genRuleFile.py`, same commit). They are an inference of what ORFS's reference run produced
when the rules were last regenerated (nangate45 2026-08-21, sky130hd 2026-08-25), not a published measurement. The criterion
`matches_published` is named for the demo schema, but means "matches the reference implied by the shipped rules".

`docs/t2_crosscheck_tolerance.md` fixes the tolerance (committed as a2c2d54, before the comparison); `results/t2_crosscheck.json` has the result.

| design | metric | ours | implied reference (+- margin) | |
|---|---|---|---|---|
| sky130hd/gcd | setup WNS | -1.460 ns | -1.465 (0.055) | in |
| | setup TNS | -64.94 ns | -65.08 (0.22) | in |
| | instance area | 5412.7 | 5053.9 (15 %) | in |
| | placeopt area | 4055.1 | 4054.8 | in |
| | placeopt std cells | 478 | 478.3 | in |
| | wirelength | 11728 | 11786 | in |
| nangate45/gcd | setup WNS | -0.162 ns | -0.1805 (0.0125) | **out (better)** |
| | setup TNS | -7.09 ns | -7.94 (0.05) | **out (better)** |
| | instance area | 943.5 | 969.6 (15 %) | in |
| | placeopt area | 827.5 | 827.8 | in |
| | placeopt std cells | 711 | 711.3 | in |
| | wirelength | 4429 | 6277 (15 %) | **out (29 % shorter)** |

sky130hd/gcd matches; nangate45/gcd does **not** (3 of 6 band metrics), and the result stays false.

**Diagnosis of the nangate45 miss, from the evidence (not assumed).**
* The synthesis netlist hashes in the rules are reproduced **exactly** for sky130hd (both hashes equal), so the Yosys in this image
  is the one that produced ORFS's sky130hd reference. For nangate45 both hashes differ, so the synthesised netlist is not bit-identical to ORFS's.
* But the netlist difference is tiny: synth stdcell area is 626.696 vs implied 626.96 (-0.04 %), placeopt area/count also -0.04 %, CTS setup WNS
  -0.1566 vs implied -0.1565 (-0.06 %). Our run tracks the reference to <0.1 % through CTS (TNS +1.2 %).
* The departure starts at global routing (setup WNS +5.5 % better, TNS +9.4 %) and grows in detailed route (wirelength -29 %) and finish (WNS +10.5 %).
* So the evidence does **not** support "a different Yosys build explains the miss" as the main cause: synthesis, placement and CTS agree to
  tenths of a percent, and the gap opens in the routing stages. The more likely cause is that routing/finishing behaviour changed between the
  rule regeneration (2026-08-21) and the pinned flow commit (2026-09-19); we cannot prove it without ORFS's reference run, so it stays a hypothesis. The
  differing nangate45 hash is a real but, by these numbers, minor difference (possible cause: ABC/synthesis script changes after the rules were written).
* All deviations are in the favourable direction, and ORFS's own threshold check passes 27/27 for both designs.
