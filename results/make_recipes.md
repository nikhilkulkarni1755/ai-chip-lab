### Make recipes: what was actually run

Each recipe below was executed for real as `make <recipe>` from the repo root (recorded by `scripts/make_record.py`, raw data in `results/make_recipes.json`). Wall time includes waiting in the one-job-at-a-time queue of this machine; the time without that wait is shown separately.

| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |
|---|---|---|---|---|---|---|
| `make runtime` | 0 | 9 min 47 s | 9 min 41 s | 6 s | 09:17:53 | `logs/part2/32_make_recipes/runtime_091753.log` |
| `make images` | 0 | 53 min 59 s | 52 min 58 s | 1 min 01 s | 09:27:41 | `logs/part2/32_make_recipes/images_092741.log` |
| `make t1` | 0 | 82 min 16 s | 63 min 11 s | 19 min 05 s | 13:56:30 | `logs/part2/32_make_recipes/t1_135630.log` |
| `make t2` | 0 | 69 min 08 s | 60 min 01 s | 9 min 07 s | 10:27:19 | `logs/part2/32_make_recipes/t2_102719.log` |
| `make t2-stretch` | 0 | 38 min 12 s | 19 min 49 s | 18 min 23 s | 11:36:27 | `logs/part2/32_make_recipes/t2-stretch_113627.log` |
| `make t3` | 2 | 55 min 39 s | 31 min 05 s | 24 min 34 s | 13:10:40 | `logs/part2/32_make_recipes/t3_131040.log` |
| `make repro` | still running | – | – | – | 14:06:34 | `logs/part2/32_make_recipes/repro_140634.log` |
| `make demo` | not run yet | – | – | – | – | – |
| `make t1-routed` | 0 | 1 min 01 s | 10 s | 51 s | 15:18:53 | `logs/part2/32_make_recipes/t1-routed_151853.log` |

**Not run as a recipe yet:** `make repro`, `make demo`.
**Recipes that exited non-zero:** `make t3` (exit 2) — see the log of each.

Notes:

- `make t2`: one fresh clean ORFS run per reference design (run 4 for gcd on both platforms, after the two Part 1 runs and pnr's P1.4 rerun), compared against all earlier runs by scripts/t2_repro.sh
- `make t2-stretch`: systolic_os on nangate45, a further clean run compared against the earlier ones
- `make t3`: attempt 2 (P2-7): criterion-A user-bandwidth jobs not started (T3_USER_DEADLINE=1) because the first one made no progress in a 769 s hold; this attempt runs the cheap second pass (bundled x3, fit, 3 CALC) and the summary; earlier jobs kept Reclassified by finish time (the recipe renamed results/t3.partial to results/t3 at its end). Under this attempt the recipe executed the second-pass jobs bundled_ws/os/is, fit, rl2_calc_ws/os/is (in results/t3.rerun.tmp, removed by the script after the byte-identity compare) and the summary + plots; see the '== t3 pass 2 job' lines in the log. Verdict printed by the recipe: pass=False, state=A_incomplete (criterion A: ws_high in_progress, the other five cells not_run); criterion B (calc_required_bw_inverse_to_ai_ws/os/is) False.
- `make t1`: official 10,000-case run of the per-step-lock script (rtl GO 13:47, inputs final at commit aea7f62)
- `make t1-routed`: resume mode (Decision P2-7 item 2): partitions and steps proven earlier today by the identical commands are kept (listed); only the remaining steps execute. gls_verilator skipped as instructed by rtl (T1R_SKIP)
- earlier attempts of `make t3`: attempt started 12:17:29: exit 2 after 52 min 42 s — Stopped on purpose at 13:11 (loop killed, container of the current job killed): job rl2_user_ws_high held the lock 769 s (12:55:47-13:08:36, exit 75 'partial') without finishing a single layer (its layers/ dir is empty; log: 'parallel failed: BrokenProcessPool' for Conv5_1b/Conv5_2a) and had re-queued itself for an identical hold. Rule from main: no stage lock hold > 10 min. The three CALC jobs finished under this attempt (see executed_under_this_recipe). Next attempt runs with T3_USER_DEADLINE=1 (criterion-A user-bandwidth jobs not started) so the cheap second pass and the summary can complete; criterion A stays incomplete until arch fixes the job.

**`make all` fail-soft test:** not run yet.
