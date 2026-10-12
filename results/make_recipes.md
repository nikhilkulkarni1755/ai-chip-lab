### Make recipes: what was actually run

Each recipe below was executed for real as `make <recipe>` from the repo root (recorded by `scripts/make_record.py`, raw data in `results/make_recipes.json`). Wall time includes waiting in the one-job-at-a-time queue of this machine; the time without that wait is shown separately.

| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |
|---|---|---|---|---|---|---|
| `make runtime` | 0 | 9 min 47 s | 9 min 41 s | 6 s | 09:17:53 | `logs/part2/32_make_recipes/runtime_091753.log` |
| `make images` | 0 | 53 min 59 s | 52 min 58 s | 1 min 01 s | 09:27:41 | `logs/part2/32_make_recipes/images_092741.log` |
| `make t1` | not run yet | – | – | – | – | – |
| `make t2` | 0 | 69 min 08 s | 60 min 01 s | 9 min 07 s | 10:27:19 | `logs/part2/32_make_recipes/t2_102719.log` |
| `make t2-stretch` | 0 | 38 min 12 s | 19 min 49 s | 18 min 23 s | 11:36:27 | `logs/part2/32_make_recipes/t2-stretch_113627.log` |
| `make t3` | still running | – | – | – | 12:17:29 | `logs/part2/32_make_recipes/t3_121729.log` |
| `make repro` | not run yet | – | – | – | – | – |
| `make demo` | not run yet | – | – | – | – | – |

**Not run as a recipe yet:** `make t1`, `make t3`, `make repro`, `make demo`.

Notes: `make t2`: one fresh clean ORFS run per reference design (run 4 for gcd on both platforms, after the two Part 1 runs and pnr's P1.4 rerun), compared against all earlier runs by scripts/t2_repro.sh; `make t2-stretch`: systolic_os on nangate45, a further clean run compared against the earlier ones.

**`make all` fail-soft test:** not run yet.
