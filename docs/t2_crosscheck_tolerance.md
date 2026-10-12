# Task 2 cross-check against ORFS's published results: tolerance (written BEFORE comparing)

**What ORFS publishes at the pinned commit (tag 26Q3-600-g3a964e13f).** Only `flow/designs/<platform>/gcd/rules-base.json`
(27 rules per design). The golden `metadata-base-ok.json` for gcd was removed from ORFS in Feb 2025 (commit 2152d38a, not in
the pinned tree) and CI dashboards are online-only, so there is no published *metrics file* for gcd and no published *power*
number (no power rule exists). Published reference values are therefore **implied** by the rules, using the generator
`flow/util/genRuleFile.py` at the same commit (read from the ORFS git history):

| rule kind | generator formula (limit from reference value `r`, clock period `T`) | implied reference | margin |
|---|---|---|---|
| `padding p` (area, counts, wirelength) | `limit = r*(1+p/100)` (some rounded to integers) | `r = limit/(1+p/100)` | `p %` of `r` |
| `period_padding` setup/hold **ws**, p=5 | `limit = min(r,0) - max(min(r,0)*p/100, T*p/100)` = `r - 0.05*T` for r<0 | `r = limit + 0.05*T` | `0.05*T` |
| `period_padding` setup/hold **tns**, p=20 | same formula with p=20 | `r = limit + 0.20*T` | `0.20*T` |

(T = reference clock period from our own `constraints__clocks__details`: 0.25 ns nangate45, 1.1 ns sky130hd. Paddings are the ones
in `genRuleFile.py`; the area/count ones are read from the rules-base ratios where the generator pads by 15 %.)

## Tolerance (fixed now)
`matches_published` is **true** iff, for each of these metrics, our value lies inside the **two-sided band
`implied_reference ± margin`**, the margin being exactly the one ORFS itself grants in the table above:

* `finish__timing__setup__ws` (± 0.05 T), `finish__timing__setup__tns` (± 0.20 T)
* `finish__design__instance__area`, `placeopt__design__instance__area` (± 15 % of implied reference)
* `placeopt__design__instance__count__stdcell` (± 15 %)
* `detailedroute__route__wirelength` (± 15 % if the rules-base padding is 15; else the padding in the file)

Hold ws/tns are checked **one-sided only** (ours must not be worse than the implied reference): the generator clips them at 0
so the implied reference is uninformative. Metrics with no published value (power, runtime, utilization) are listed as
`no_published_value`, not compared. Beyond the band, a metric is reported honestly as outside (it stays a recorded finding;
the tolerance is not widened after seeing numbers). Being *better* than the reference by more than the margin counts as
outside the band for the two-sided metrics; that is stated in the result.

Separately, ORFS's own threshold check (limits as written) is the existing `thresholds_pass` criterion.
