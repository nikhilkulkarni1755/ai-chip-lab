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

Two comparisons were made. The second one is the real one.

**1. Against the reference implied by `rules-base.json` (superseded).** ORFS ships no measured gcd metadata in the repo at the pinned commit (the golden
`metadata-base-ok.json` files were deleted in Feb 2025; no power value). I un-padded the rule limits with ORFS's generator formulas
(`docs/t2_crosscheck_tolerance.md`, commit a2c2d54, fixed before comparing). sky130hd/gcd matched; nangate45/gcd did not (setup WNS -0.162 vs implied -0.1805,
TNS -7.09 vs -7.94, wirelength 4429 vs ~6277; all better than the reference). This criterion compared against an *inferred* number and is kept in
`results/p2_21_orfs_crosscheck.json` as `superseded` (Decision P2-5 in COORDINATION.md).

**2. Against ORFS's measured CI build of the exact pinned commit (`matches_published_dashboard`).** The public QoR dashboard
(https://dashboard.precisioninno.com, `GET /api/commits/25781/metrics`, retrieved 2026-10-12, raw files in `results/t2/published/`) holds the CI build of commit
3a964e13f itself. Tolerances were pre-registered in `docs/t2_dashboard_crosscheck_tolerance.md` (commit 9b81746, before the comparison; the raw files were
fetched first). Result: **true for both designs**, and in fact exact: setup WNS, setup TNS, instance area, placement area and cell count, routed wirelength (4429 / 11728), power total
(6.33406 mW / 9.85037 mW) and final DRC (0) equal the dashboard values to every printed digit; 430 (nangate45) and 439 (sky130hd) numeric metrics were compared and
only 9 differ per design, all of them FastRoute wall-clock profiling fields. A first run of the comparison script reported DRC 63/289 vs 0: that was a script bug
(iteration-0 rows of the detailed-route series overwrote the final value); the per-iteration series (63 -> 18 -> 10 -> 0 errors) is itself identical to ours. The tolerance was not touched.

**Why the implied comparison missed (evidence).**
* Our nangate45 numbers equal the measured CI numbers of the same commit, so the flow behaves as ORFS's own CI does; the miss against the implied band comes from
  `rules-base.json`, whose nangate45/gcd limits were last regenerated on 2026-08-21, four weeks before the pinned commit (2026-09-19). Rules are padded limits that only get
  rewritten when someone regenerates them; they are not a snapshot of the pinned commit.
* The Part 1 checker warning that `synth__netlist__hash` / `synth__canonical_netlist__hash` differ from the rules' recorded hashes is therefore not a different Yosys build. The
  hashes recorded in the rules are also from the 08-21 generation. The pinned commit is itself the merge of PR #4543 "synth: strip src attributes again after techmap under
  SYNTH_REPEATABLE_BUILD", which changes the netlist text (hence its hash) without changing its logic; nangate45/gcd sets `SYNTH_REPEATABLE_BUILD ?= 1`, sky130hd/gcd does not, and
  precisely the sky130hd hashes still match the rules while the nangate45 ones do not. The dashboard stores numeric metrics only, so it cannot confirm hash equality, but identical
  area, timing and power to six digits at every stage means an equivalent netlist. This explanation is supported by the commit history and the numbers, not by a hash comparison
  with ORFS's CI.
* Context only (not used for any criterion): the older `metadata-base-ok.json` golden files and the history of `rules-base.json` would show the drift of the references over
  months; they describe older flows and were not compared.
