# P1.5b: comparison with ORFS's public QoR dashboard measurement of the pinned commit (pre-registered)

**Reference (real measurement, not implied).** The ORFS QoR dashboard (https://dashboard.precisioninno.com, public read API,
`GET /api/commits/25781/metrics`) holds the CI build of **exactly commit 3a964e13f11a4e435aac01ffa14db0a7d2853720** (branch master/nightly,
2026-09-20), the commit our pinned image tag `26Q3-600-g3a964e13f` was built from. The raw per-design entries for nangate45/gcd and sky130hd/gcd
were fetched and stored first (`results/t2/published/`, retrieval time in `retrieved_utc.txt`) in the commit that precedes the commit evaluating this criterion.
Caveats stated up front: the CI machine, thread count and OpenROAD binary build need not equal ours; and I saw the first ~15 values of each
metric vector (floorplan-stage numbers, e.g. core/die area) while checking the file structure, before writing this tolerance; none of the metrics below
at later stages were looked at.

**Criterion `matches_published_dashboard`** (per design) is true iff every metric below lies within the tolerance of the dashboard value:

| metric (ORFS name) | tolerance (fixed now) | justification |
|---|---|---|
| `finish__timing__setup__ws` | abs diff <= 0.05 x clock period | the margin ORFS's own rules grant on setup WNS |
| `finish__timing__setup__tns` | abs diff <= 0.20 x clock period | the margin ORFS's own rules grant on TNS |
| `finish__design__instance__area`, `placeopt__design__instance__area`, `placeopt__design__instance__count__stdcell`, `detailedroute__route__wirelength` | relative diff <= 15 % | the padding ORFS's own rules use |
| `finish__power__total` | relative diff <= 15 % | no ORFS rule exists for power; the same 15 % as the largest numeric padding |
| `detailedroute__route__drc_errors` | equal (0) | ORFS rule `== 0` |
| `synth__netlist__hash`, `synth__canonical_netlist__hash` | informational only (not part of the criterion) | exact identity is a bonus, not a requirement |

Secondary, informational (not part of the pass): `exact_1pct` = all numeric metrics above within 1 % (WNS/TNS within 1 % of the clock period).
The earlier criterion `matches_published` (implied reference from `rules-base.json`) is kept in `results/p2_21_orfs_crosscheck.json` as `superseded`:
it compared against an inferred number, not a publication. Whatever this comparison shows, the tolerance is not changed afterwards.
