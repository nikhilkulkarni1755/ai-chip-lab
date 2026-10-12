### Make recipes: what was actually run

Each recipe below was executed for real as `make <recipe>` from the repo root (recorded by `scripts/make_record.py`, raw data in `results/make_recipes.json`). Wall time includes waiting in the one-job-at-a-time queue of this machine; the time without that wait is shown separately.

| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |
|---|---|---|---|---|---|---|
| `make runtime` | 0 | 9 min 47 s | 9 min 41 s | 6 s | 09:17:53 | `logs/part2/32_make_recipes/runtime_091753.log` |
| `make images` | 0 | 53 min 59 s | 52 min 58 s | 1 min 01 s | 09:27:41 | `logs/part2/32_make_recipes/images_092741.log` |
| `make t1` | not run yet | – | – | – | – | – |
| `make t2` | 0 | 69 min 08 s | 60 min 01 s | 9 min 07 s | 10:27:19 | `logs/part2/32_make_recipes/t2_102719.log` |
| `make t2-stretch` | not run yet | – | – | – | – | – |
| `make t3` | not run yet | – | – | – | – | – |
| `make repro` | not run yet | – | – | – | – | – |
| `make demo` | not run yet | – | – | – | – | – |

**Not run as a recipe yet:** `make t1`, `make t2-stretch`, `make t3`, `make repro`, `make demo`.

Notes: `make t2`: one fresh clean ORFS run per reference design (run 4 for gcd on both platforms, after the two Part 1 runs and pnr's P1.4 rerun), compared against all earlier runs by scripts/t2_repro.sh.

**`make all` fail-soft test:** not run yet.
