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
`docs/t2_crosscheck_tolerance.md` fixes the tolerance (committed before the comparison); `results/t2_crosscheck.json` has the
result. The published reference values are only *implied* by the rules (ORFS removed the golden `metadata-base-ok.json` files
and has no published power number). sky130hd/gcd matches within the stated band on every metric; nangate45/gcd does **not** match on
3 of 6 band metrics (setup WNS, setup TNS, routed wirelength), all three on the *better* side (e.g. wirelength 4429 vs implied
reference ~6277). Placement-stage numbers match closely (placeopt area 827.5 vs implied 827.8). Probable cause, not proven:
the nangate45 rules were last regenerated on 2026-08-21, four weeks before the pinned flow commit (2026-09-19), so later
CTS/routing changes moved the numbers. We did not widen the tolerance.
