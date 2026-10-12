# P1.5b: comparison with ORFS's public QoR dashboard measurement of the pinned commit (pre-registered)

**Reference (real measurement, not implied).** The ORFS QoR dashboard (https://dashboard.precisioninno.com, public read API,
`GET /api/commits/25781/metrics`) holds the CI build of **exactly commit 3a964e13f11a4e435aac01ffa14db0a7d2853720** (branch master/nightly,
2026-09-20), the commit our pinned image tag `26Q3-600-g3a964e13f` was built from. The raw per-design entries for nangate45/gcd and sky130hd/gcd
were fetched first (`results/t2/published/`, retrieval time in `retrieved_utc.txt`; the raw files are committed right after this document, still before any comparison was computed).
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

## Notes added before the verdict was recorded (review feedback, 10:19)
* Provenance order: the raw payload was fetched 31 s before the tolerance commit and the tolerance document was written after it; I had looked only at the
  first floorplan-stage values (core/die area) while checking the file structure. The raw files are committed in the commit right after the tolerance document, still before
  any comparison was computed. Because the match turned out exact (every compared metric equal to every printed digit), no choice of tolerance could change the verdict.
* Reproducibility: `scripts/t2_dashboard_fetch.sh` re-fetches the payload (read-only GETs) and records sha256 values in `results/t2/published/sha256.txt`; an independent
  re-fetch by the reviewer (2026-10-12 ~17:16Z) returned a byte-identical payload.
* Limit: the dashboard API exposes only the ORFS commit sha of that CI build, not the version of the OpenROAD binary used in it. An exact match with the image built from the same ORFS commit
  makes a different binary unlikely but this is not independently verifiable.
