# AI chip design lab

An open-source, reproducible lab that takes a small AI accelerator from a multiply-accumulate unit to a laid-out chip using only open tools, run unattended on an old 2-core Intel MacBook with 8 GB of RAM (no Homebrew, no sudo; a Colima VM runs the containers). Three baseline checks establish objective truth (answers checked against math, a second independent tool, or published reference values); sweeps then explore the design space.

Open [`demo/index.html`](demo/index.html) for the full walk-through: concepts, tool map, how each result was tested, plots, and honest caveats.

## Status

Generated from the files in this repository by `python3 scripts/demo_build.py` (Part 1: Total runtime: 5h 08m, from 2026-10-12 02:48:36 PDT to 07:57, budget 6h; Part 2 runtime is in the Part 2 section).

| Check | Status | Detail |
|---|---|---|
| Container runtime install | **PASS** | route A (Colima + Lima, macOS Virtualization.framework) |
| Lab images (lab-sim, ORFS) | **PASS** | both images referenced in coord/images.env |
| Task 1: INT8 systolic array vs NumPy | **PASS** | t1_summary.json: pass=true |
| Task 1: formal MAC proof (SBY) | **PASS** | checks: formal_bmc_pass=true, formal_prove_pass=true |
| Task 1: RTL = netlist equivalence (EQY) | **PASS** | checks: eqy_array_pass=true, eqy_mac_pass=true, eqy_pass=true; scope: split proof (1) mac_int8 incl. multiplier, (2) full 4x4 array with mac_int8 black-boxed; compared against the generic-gate Yosys netlist (synth; abc; opt), NOT the placed-and-routed nangate45 netlist (the ORFS logic-equivalence step is disabled, see caveats) |
| Task 2: OpenROAD gcd flows within ORFS's shipped regression thresholds | **PASS** | t2_summary.json: pass=true; NOT timing-closed: nangate45/gcd misses timing at its 0.25 ns reference clock (WNS -0.161583 ns, TNS -7.08646 ns, 51 violating endpoints); sky130hd/gcd misses timing at its 1.1 ns reference clock (WNS -1.45954 ns, TNS -64.9417 ns, 63 violating endpoints) |
| Task 3: SCALE-Sim vs analytical model | **FAIL** | FAIL: criteria that fail: calc_required_bw_inverse_to_ai_ws, calc_required_bw_inverse_to_ai_os, calc_required_bw_inverse_to_ai_is; reruns_byte_identical also appears in the file's failed list but is a bookkeeping state, not a failed criterion (repro compared the files byte-identical; see the known presentation defects in section 6) (criterion B, CALC mode: rho(intensity, required bandwidth) must be <= -0.6 for every dataflow). Criterion A (stalls at a fixed user bandwidth) is NOT EVALUATED (cost), neither pass nor fail: A_incomplete(ws_mid=not_run,ws_high=not_run,os_mid=not_run,os_high=not_run,is_mid=not_run,is_high=not_run); the probe showed the largest layer alone needs more than 481 s, over the 10-minute lock-hold rule (results/evidence/31_a_probe.txt). Pre-registered thresholds were not changed (model/t3_roofline2_criteria.json, P2-A1/P2-A2/P2-7); the Part 2 hypothesis was wrong in its mechanism (the bundled google.cfg already uses USER bandwidth and its stalls are all zero, results/evidence/31_original_stalls.txt). Explainer: docs/t3_roofline_explained.md |
| Sweep A: architecture (SCALE-Sim) | **CUT** | cut at gate (Part 2 stage 41_sweeps_finish_A): all planned points accounted for (not 'complete'); 173 of 264 done, 0 errored or timed out, 91 cut (reason: sweep driver stops at the Phase 1 gate (budget_part2.json deadline_sweeps_stop_epoch); points run cheapest-estimated-first at low lock priority behind stage jobs, so the most expensive points were not reached); live from results/sweeps/arch.jsonl: 173 ok of 264 planned points (0 error, 0 skipped after timeout, 91 not reached) |
| Sweep B: physical (ORFS) | **CUT** | cut at gate (Part 2 stage 41_sweeps_finish_B): all planned points accounted for (not 'complete'); Part 2 refinement plan: 26 points, 16 done, 0 failed or timed out, 6 cut deliberately (the 30 % frontier was already bracketed by 1.20 ns failing / 1.25 ns closing), 4 not reached before the gate (each listed with its state and reason in section 12); gcd closes at 0.42-0.425 ns depending on utilization (about zero margin at 0.42 ns, u50); systolic_os at 30 % utilization: closes at 1.25 ns (WNS 0.0132117 ns), fails at 1.2 ns (WNS -0.00730405 ns), 6 points; systolic_os at 40 % utilization: closes at 1.25 ns (WNS 0.0168722 ns), fails at null ns (WNS null ns), 1 points; systolic_os at 50 % utilization: closes at 1.25 ns (WNS 0.0172729 ns), fails at null ns (WNS null ns), 1 points; 1 failed point(s) |
| Repeatability rerun (repro) | **PASS** | repro_report.json: pass=true; 13 checks, each with its run count and verdict in section 7: 11 identical, 2 not_rerun_cost; NOT complete: at least one check was not rerun (cost) and is not counted as identical; excluded: run-time measurements (3 files) (file class timing.timing, per-layer wall time and memory, not results); hidden files excluded: 0; PASS with a stated scope: complete=False because 2 check(s) were not rerun (cost): the criterion-A user-bandwidth Task 3 runs are NOT claimed identical; Task 1 (full), Task 2 (4/4/3 clean runs) and the Task 3 cheap set (bundled, fit, CALC-mode runs) were compared |
| Task 1: RTL = ROUTED netlist equivalence (EQY) | **PASS** | eqy_routed_pass = true in t1_summary.json; EQY partitions proved: 27 of 27 |
| Task 1: routed gate-level simulation vs NumPy | **PARTIAL** | Icarus PASS; Verilator not run (partial against the task, not counted as a PASS). Pass on Icarus only; Verilator gate-level simulation not run (partial vs TASK2 P1.3 item 4); gls_routed_pass = true in t1_summary.json; Icarus 0 mismatches against NumPy: True; negative control detected: True; Verilator: not run: the verilator model build of the routed netlist did not finish within the lock hold (stopped after 544 s, exit code 124); no simulation result exists |
| Task 2: matches ORFS's published reference results | **PASS** | matches_published = true in t2_summary.json |
| P2.1 Activity-based power | **PASS** | 8 of 8 evaluated criteria pass. Total power (active-window VCD analysis, 4.0 ns clock): random 7.84 mW, sparse50 5.16 mW (0.66x), allmax 4.31 mW (0.55x); ORFS default vectorless estimate 28.51 mW, i.e. 3.6x / 5.5x / 6.6x higher. Vectorless assumes 0.1 transitions per cycle on every input and propagates it; the real array switches far less. Leakage 0.41-0.43 mW across workloads (6 % spread; Liberty leakage is state dependent). Zero-delay simulation: no glitch power, so the VCD numbers are a lower bound on switching power. Zero-delay gate-level simulation has no glitch power, so the simulated switching power is a lower bound. The vectorless figure is OpenROAD's default-activity assumption (0.1 transitions per cycle on every input), not a measurement (docs/power_explained.md). |
| P2.2 bf16 processing element | **FAIL** | 9 of 10 evaluated criteria pass; failing checks: lint_clean; bit-exact checks over 10042 cases: Verilator True, Icarus True. INT8 vs bf16 MAC PPA table in section 16: bf16 power is at a clock it does not meet and fmax comes from one run per design, not a frontier; failing: lint_clean |
| P2.3 systolic_os on sky130hd | **PASS** | 4 sky130hd points recorded (planned 8.0 / 5.5 / 4.0 ns plus one refinement, Decision P2-11a); result label by the file's rule: coarse frontier bracket: fails at 5.5 ns, closes at 6.75 ns; 5 of 5 evaluated criteria pass. Clock ratio is an upper bound on the slowdown; power is at clocks 5.4x apart, so energy per cycle is shown too |
| P2.4 SRAM modelling (CACTI) | **PASS** | 7 of 7 evaluated criteria pass; 1 reported only or not evaluated yet (neither pass nor fail). CACTI is an analytical model: 45 nm matches nangate45 in feature size only and no SRAM macro exists in any ORFS run, so absolute numbers are unchecked; the energy model is order-of-magnitude (SRAM read energy only, DRAM and MAC energy not modelled); the non-monotone cycle time is an unregistered observation (docs/sram_explained.md) |
| Make recipes executed for real | **FAIL** | 12 recipe(s) recorded in results/make_recipes.json; non-zero exit: t3, all |

### What is not green yet, why, and the next action

State is computed from the files; diagnosis and next action are explanations written from the decisions in COORDINATION.md.

| Row | State now | Diagnosis | Next action |
|---|---|---|---|
| Task 3: SCALE-Sim vs analytical model | **FAIL** | FAIL on the pre-registered criterion B: in CALC mode the intensity versus required-bandwidth rank correlation does not reach -0.6 for ws, os or is (values in the row and section 6). Criterion A (stalls at a fixed user bandwidth) is NOT EVALUATED, neither pass nor fail: a probe showed the largest ResNet-18 layer alone needs more than 481 s, over the 10-minute lock-hold rule, and SCALE-Sim cannot checkpoint inside a layer. The original hypothesis (default bandwidth mode hides stalls) was wrong: the bundled config uses user bandwidth and its stalls are all zero. | Thresholds are final and were not retuned. To finish criterion A the owner can approve long holds (several hours of exclusive machine time) or a smaller layer set registered as a new amendment before running; criterion B's failure needs a diagnosis of the analytic intensity (see docs/t3_roofline_explained.md). |
| Sweep A: architecture (SCALE-Sim) | **CUT** | Accounted for, not complete: every planned point is done, errored, or cut with a stated reason, but the cut points were not run; points never reached before the sweep deadline (cut because sweeps run at low priority behind stage jobs in the one-job-at-a-time queue; cheapest points ran first). | Nothing is hidden: the cut points are listed in the sweep section with the reason. A later `make sweeps` with a later deadline would run them. |
| Sweep B: physical (ORFS) | **CUT** | Accounted for, not complete: every planned point is done, failed, or cut at the gate with its state listed in section 12; the cut points were not run. The systolic_os frontier at 30 % utilization is bracketed by a failing and a closing period (see the row). | Running the cut points (`python3 sweeps/phys_sweep.py --plan part2`, low priority) would extend the plan; nothing is claimed for them now. |
| Task 1: routed gate-level simulation vs NumPy | **PARTIAL** | PASS on Icarus only: the task also asks for Verilator if the cell models parse (they do). The Verilator model build of the routed netlist did not finish within the 10-minute lock hold, so no Verilator gate-level result exists; every check that needs one is listed as NOT EVALUATED, neither pass nor fail. This is partial against the task, not a pass of the full item. | Build the Verilator gate-level model in a bounded way (a smaller or pre-built model, or a longer hold approved by the owner), then `T1R_STEPS=gls scripts/t1_routed.sh`. Until then the page keeps saying Icarus only. |
| P2.2 bf16 processing element | **FAIL** | Verification is bit-exact on both simulators; the stage fails on the single check `lint_clean` (one comment line over the 100-character limit). The PPA table is from one flow run per design at a clock the bf16 MAC does not meet. | `git cherry-pick e21fd3b` (from branch p2/rtl; shortens one comment line, no logic change), then `scripts/t61_run.sh 10000 results && python3 scripts/p2_61_finish.py` (about 4 minutes of lock). Decision P2-12 deferred it because rtl/ is an input of the t1 stages. Search the bf16 frontier clock before quoting its power. |
| Make recipes executed for real | **FAIL** | Each recipe is executed for real by the recorder in queue order. `make t3` exits non-zero because the Task 3 stage verdict is FAIL (criterion B; criterion A not evaluated), so `make all` exits non-zero and lists t3 as the failed stage; the fail-soft test of that behaviour ran in the reduced form its note describes. The row reads RUNNING while the real `make all` is still running. | No fix for the exit code is intended: it is the honest result of the Task 3 verdict. It changes only if Task 3's criteria are re-registered or criterion A is evaluated and criterion B passes. |

**Owner actions**

- Review and merge branch `part2-green` yourself. Nothing was pushed and `main` was not touched.
- Keep branch `p2/rtl`: it holds the one-line bf16 lint fix (commit e21fd3b) that was deliberately not merged (Decision P2-12).
- Optional bf16 lint fix: `git cherry-pick e21fd3b`, then `scripts/t61_run.sh 10000 results && python3 scripts/p2_61_finish.py`. rtl/ is an input of the t1, t1-routed and repro stages, so those re-run afterwards.
- Optional: decide whether Task 3 criterion A should be evaluated at all (several hours of exclusive machine time) or re-registered; criterion B's failure is a finding, not a bug.
- Stop the VM when done: `source env.sh && colima stop` (the demo needs it running).

## Part 2: before and after

| Check | At the start of Part 2 | Now |
|---|---|---|
| Runtime | PASS | **PASS** |
| Images | PASS | **PASS** |
| Task 1: sim vs NumPy, SBY, EQY | PASS | **PASS** |
| Task 2: ORFS gcd within thresholds | PASS | **PASS** |
| Task 3: SCALE-Sim vs analytic | FAIL | **FAIL** |
| Sweep A | Incomplete | **CUT** Incomplete → 173 of 264 done, 91 cut at gate |
| Sweep B | Coarse | **CUT** Coarse → 16 of 26 refinement points done, 6 cut deliberately, 4 not reached |
| Repro | PASS | **PASS** |
| Make recipes | Untested | **FAIL** |
| Task 1: routed netlist equivalence (new in Part 2) | - | **PASS** |
| Task 1: routed gate-level simulation (new in Part 2) | - | **PARTIAL** |
| Task 2: matches ORFS's published results (new in Part 2) | - | **PASS** |
| P2.1 activity-based power (new) | - | **PASS** |
| P2.2 bf16 processing element (new) | - | **FAIL** |
| P2.3 systolic_os on sky130hd (new) | - | **PASS** |
| P2.4 SRAM modelling with CACTI (new) | - | **PASS** |

Part 2 is in progress or its end has not been recorded (the end time is read from results/.stages/99_part2.done, which does not exist yet); started 2026-10-12 09:03:34 PDT, budget 14h. Part 1's runtime stays as recorded in its own section.

Part 2 stage states:

| Stage | State |
|---|---|
| `31_roofline_fix` P1.1 Task 3 roofline check | FAIL |
| `32_make_recipes` P1.2 every make recipe run for real | FAIL |
| `11_eqy_routed` P1.3 equivalence and gate-level simulation of the routed netlist | PASS |
| `51_repro_full` P1.4 complete determinism story | DONE |
| `21_orfs_crosscheck` P1.5 Task 2 against ORFS's published results | PASS |
| `41_sweeps_finish` P1.6 finish and refine the sweeps | DONE |
| `60_power_activity` P2.1 activity-based power | PASS |
| `61_pe_bf16` P2.2 bf16 processing element | FAIL |
| `62_pdk_compare` P2.3 systolic_os on sky130hd | PASS |
| `63_sram_cacti` P2.4 SRAM modelling (CACTI) | PASS |
| `64_roadmap` P2.5 roadmap | DONE |


PASS means the stage's `.done` marker exists and its summary JSON says `"pass": true`. Anything unfinished is shown as PENDING/RUNNING/BLOCKED/UNKNOWN and not assumed.

## What is in it

| Path | What |
|---|---|
| `env.sh` | Puts the lab-local tools (colima, docker) on PATH and redirects all VM/Docker state into this directory. |
| `env.json` | Measured machine facts (CPU, RAM, macOS, free disk) captured at preflight. |
| `budget.json` | The time budget and its milestones; the build elapsed time is computed from it. |
| `versions.lock` | Every pinned version, git SHA, image digest, download URL and SHA256 the lab used. |
| `coord/images.env` | The two container images (lab-sim build, ORFS pinned by digest) that every script sources. |
| `COORDINATION.md` | How the agents divided the work: rules, decisions with evidence, requests between agents. |
| `docker/lab-sim/Dockerfile` | Recipe for the simulation image (OSS CAD Suite, Verible, Python venv). |
| `docker/requirements.lock` | Hash-locked Python dependencies installed in the lab-sim image (it lives under docker/, not at the repo root). |
| `rtl/mac_int8.sv` | The multiply-accumulate unit: signed INT8 x INT8 into an INT32 accumulator. |
| `rtl/systolic_os.sv` | R x C output-stationary systolic array built from MAC processing elements. |
| `tb/test_systolic.py` | cocotb testbench: random + directed cases checked against NumPy, with functional coverage. |
| `formal/` | SymbiYosys property proofs for the MAC (Task 1). |
| `eqy/` | Equivalence check: RTL versus the Yosys gate-level netlist (Task 1). |
| `orfs/designs/` | Design configs for the OpenROAD flow (gcd reference and the systolic_os stretch design). |
| `orfs/render.py` | KLayout batch script that turns a GDS layout into a PNG. |
| `model/` | analytic.py: the closed-form cycle/roofline model that SCALE-Sim is checked against (Task 3). |
| `arch/` | SCALE-Sim configs and topologies used in Task 3 and sweep A. |
| `sweeps/` | Sweep drivers: architecture (SCALE-Sim) and physical (ORFS clock x utilization). |
| `scripts/` | Entry points: with_lock.sh (one heavy job at a time), t1/t2/t3 runners, repro.sh, demo_build.py. |
| `results/t1_summary.json` | Task 1 verdict and measured values. |
| `results/t2_summary.json` | Task 2 verdict and PPA metrics. |
| `results/t3_summary.json` | Task 3 verdict and fit residuals. |
| `results/repro_report.json` | Per-check identical/different verdicts from the clean rerun. |
| `results/sweeps/` | One JSON line per sweep point, keyed by its parameters. |
| `results/evidence/` | Scrubbed real terminal output of each stage's key command; rendered to PNG for the README. |
| `results/.stages/` | Stage markers (.done/.failed/.blocked/.running) that this page reads for its status. |
| `demo/index.html` | This page, generated by scripts/demo_build.py from whatever exists on disk. |
| `demo/run_demo.sh` | The 5-minute re-run: Task 1 (200 cases, both simulators), formal proof, one SCALE-Sim run, ORFS check, and the Task 3 roofline criterion B recomputed from saved reports., plus the routed-netlist gate-level simulation on Icarus with 20 random + 29 directed cases (Verilator not run). |
| `demo/assets/` | Waveform, layout, plots and evidence PNGs referenced by this page. |
| `Makefile` | make preflight runtime images t1 t2 t3 sweeps repro demo all. |

## Reproduce

```sh
source env.sh                 # lab-local PATH; all VM/Docker state stays inside this directory
make preflight                # machine facts
make runtime images           # Colima VM + pinned images (digests in coord/images.env, versions.lock)
make t1                       # Task 1: RTL vs NumPy on 2 simulators, formal, equivalence (full run incl. BMC-20)
make t2                       # Task 2: gcd on nangate45 + sky130hd, twice from clean (about 35 min of ORFS)
make t2-stretch               # systolic_os through ORFS (about 30 min)
make t3                       # Task 3: SCALE-Sim vs analytic model + roofline (exits non-zero while the roofline criterion fails)
make sweeps                   # architecture + physical sweeps; they start no new point after the sweep deadline in budget.json
make repro                    # reruns Task 1 in full and the cheap Task 3 set clean and compares; Task 2 runs come from results/t2_reruns.json
make demo                     # plots + evidence PNGs + demo/index.html + this README
make all                      # fail-soft loop over the above, always builds the demo, exits non-zero listing failed stages
bash demo/run_demo.sh         # short cut (cached images, scratch output dir); needs the VM running
```

Timed run of `bash demo/run_demo.sh` (results/run_demo_last.json, results/evidence/final_run_demo.txt): **PASS** in 117 s (2 s of lock wait), 6 of 6 steps PASS. The Task 3 criterion-B step's PASS only means the recomputed verdict equals the recorded one; the criterion itself is **not met**. The routed gate-level step is Icarus only (Verilator not run).

### Make recipes: what was actually run

Each row is one recorded invocation of `make` from the repo root with exactly the command shown (recorded by `scripts/make_record.py`, raw data in `results/make_recipes.json`). Not every recipe re-executed all of its work: `make t3 T3_USER_DEADLINE=1` ran in resume mode (8 step/job results kept from earlier runs of the same day by the identical commands, 0 executed under the recipe); `make t3-clean-first` ran in resume mode (0 step/job results kept from earlier runs of the same day by the identical commands, 8 executed under the recipe); `make t1-routed T1R_RESUME=1 T1R_SKIP=gls_verilator` ran in resume mode (46 step/job results kept from earlier runs of the same day by the identical commands, 2 executed under the recipe). Variables on a command line restrict what ran (`T3_USER_DEADLINE=1`: Task 3 criterion-A jobs not started; `T1R_SKIP=gls_verilator`: Verilator gate-level simulation not run; `REPRO_PART=t3`: Task 3 rerun only). Wall time includes waiting in the one-job-at-a-time queue of this machine; the time without that wait is shown separately. The recipes were not run in the order of the task text; all recorded invocations by start time: 09:17 runtime (exit 0), 09:27 images (exit 0), 10:27 t2 (exit 0), 11:36 t2-stretch (exit 0), 12:17 t3 (exit 2), 13:10 t3 (exit 2), 13:56 t1 (exit 0), 14:06 repro (exit 2), 15:18 t1-routed (exit 0), 15:40 preflight (exit 0), 15:40 demo (exit 0), 16:40 t3-clean-first (exit 0), 17:01 repro (exit 0), 19:07 t1-routed (exit 0), 19:08 demo (exit 0), 19:11 all (exit 2), 19:58 demo (exit 0), 20:02 demo (exit 0).

| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |
|---|---|---|---|---|---|---|
| `make runtime` | 0 | 9 min 47 s | 9 min 41 s | 6 s | 09:17:53 | `logs/part2/32_make_recipes/runtime_091753.log` |
| `make images` | 0 | 53 min 59 s | 52 min 58 s | 1 min 01 s | 09:27:41 | `logs/part2/32_make_recipes/images_092741.log` |
| `make t1` | 0 | 82 min 16 s | 63 min 11 s | 19 min 05 s | 13:56:30 | `logs/part2/32_make_recipes/t1_135630.log` |
| `make t2` | 0 | 69 min 08 s | 60 min 01 s | 9 min 07 s | 10:27:19 | `logs/part2/32_make_recipes/t2_102719.log` |
| `make t2-stretch` | 0 | 38 min 12 s | 19 min 49 s | 18 min 23 s | 11:36:27 | `logs/part2/32_make_recipes/t2-stretch_113627.log` |
| `make t3 T3_USER_DEADLINE=1` | 2 | 55 min 39 s | 31 min 05 s | 24 min 34 s | 13:10:40 | `logs/part2/32_make_recipes/t3_131040.log` |
| `make repro REPRO_PART=t3` | 0 | 125 min 36 s | 95 min 43 s | 29 min 53 s | 17:01:51 | `logs/part2/32_make_recipes/repro_170151.log` |
| `make demo` | 0 | 20 s | 0 s | 20 s | 20:02:37 | `logs/part2/32_make_recipes/demo_200237.log` |
| `make preflight` | 0 | 1 s | 0 s | 1 s | 15:40:37 | `logs/part2/32_make_recipes/preflight_154037.log` |
| `make t3-clean-first` | 0 | 21 min 37 s | 6 min 11 s | 15 min 26 s | 16:40:13 | `logs/part2/32_make_recipes/t3-clean-first_164013.log` |
| `make t1-routed T1R_RESUME=1 T1R_SKIP=gls_verilator` | 0 | 31 s | 0 s | 31 s | 19:07:27 | `logs/part2/32_make_recipes/t1-routed_190727.log` |
| `make all RESUME=1` | 2 | 46 min 38 s | 0 s | 46 min 38 s | 19:11:43 | `logs/part2/32_make_recipes/all_191142.log` |

**Recipes that exited non-zero:** `make t3` (exit 2) — see the log of each.

Notes:

- `make t2`: one fresh clean ORFS run per reference design (run 4 for gcd on both platforms, after the two Part 1 runs and pnr's P1.4 rerun), compared against all earlier runs by scripts/t2_repro.sh
- `make t2-stretch`: systolic_os on nangate45, a further clean run compared against the earlier ones
- `make t3`: attempt 2 (P2-7): criterion-A user-bandwidth jobs not started (T3_USER_DEADLINE=1) because the first one made no progress in a 769 s hold; this attempt runs the cheap second pass (bundled x3, fit, 3 CALC) and the summary; earlier jobs kept Reclassified by finish time (the recipe renamed results/t3.partial to results/t3 at its end). Under this attempt the recipe executed the second-pass jobs bundled_ws/os/is, fit, rl2_calc_ws/os/is (in results/t3.rerun.tmp, removed by the script after the byte-identity compare) and the summary + plots; see the '== t3 pass 2 job' lines in the log. Verdict printed by the recipe: pass=False, state=A_incomplete (criterion A: ws_high in_progress, the other five cells not_run); criterion B (calc_required_bw_inverse_to_ai_ws/os/is) False.
- `make t1`: official 10,000-case run of the per-step-lock script (rtl GO 13:47, inputs final at commit aea7f62)
- `make t3-clean-first`: Decision P2-10: clean Task 3 cheap-set first pass on frozen inputs (t3 inputs at commit 26ea3e5): bundled x3, fit, 3 CALC runs, single pass, no criterion-A job, every file incl. roofline2.json and the summary written in the container; the superseded synthetic roofline is carried over
- `make repro`: Decision P2-10: Task-3-only rerun on frozen inputs; repro.sh keeps the Task 1 full rerun of 15:20-15:40 only if the Task 1 input object SHAs are unchanged; timing.timing excluded and reported by repro_compare.py
- `make t1-routed`: post-gate rerun (gate audit G4) so that the recorded run is the one that wrote the final routed summary; resume mode, gls_verilator not run
- `make all`: TASK2 P1.7 / Final steps: the real make all in resume mode under the input-aware rule (Decision P2-1), no exclusions; stages whose git-tracked inputs are unchanged since their last successful run are skipped with the reason logged
- earlier attempts of `make t3`: attempt started 12:17:29: exit 2 after 52 min 42 s — Stopped on purpose at 13:11 (loop killed, container of the current job killed): job rl2_user_ws_high held the lock 769 s (12:55:47-13:08:36, exit 75 'partial') without finishing a single layer (its layers/ dir is empty; log: 'parallel failed: BrokenProcessPool' for Conv5_1b/Conv5_2a) and had re-queued itself for an identical hold. Rule from main: no stage lock hold > 10 min. The three CALC jobs finished under this attempt (see executed_under_this_recipe). Next attempt runs with T3_USER_DEADLINE=1 (criterion-A user-bandwidth jobs not started) so the cheap second pass and the summary can complete; criterion A stays incomplete until arch fixes the job.
- earlier attempts of `make t1-routed`: attempt started 15:18:53: exit 0 after 1 min 01 s
- earlier attempts of `make repro`: attempt started 14:06:34: exit 2 after 93 min 53 s — Failed on Task 3 bookkeeping and provenance only (arch's diagnosis: results/evidence/51_repro_t3_diagnosis.txt, Decision P2-10): all SCALE-Sim reports and fit/CALC results byte-identical; differing files were scheduler bookkeeping (attempts.json), per-layer timing measurements (timing.timing) and roofline2.json, which had been regenerated natively (Python 3.11) during the rerun while the rerun's was written in the container (Python 3.12, 1-ulp difference in a float sum); a t3 input commit (8cd5d98) also landed during the rerun. The Task 1 full rerun inside this recipe ran 15:20-15:40.
- earlier attempts of `make demo`: attempt started 15:40:38: exit 0 after 23 s | attempt started 19:08:50: exit 0 after 20 s | attempt started 19:58:43: exit 0 after 18 s

**`make all` fail-soft test: PASS.** Command: `MAKE_ALL_FAIL=preflight RESUME=markers SWEEPS_DETACH=1 T3_USER_DEADLINE=1 make all   (then marker restored and `make demo` rerun)`. `make all` exited 2 and listed the failed stage; the demo was built after the failure. In this test the forced stage's recipe was not run (preflight); executed for real: t3, demo; skipped because they had already succeeded (marker-only resume of the test, see each reason): runtime, images, t1, t2, t2-stretch, t1-routed, sweeps, repro; excluded from the test: none. The marker was restored and the demo rebuilt afterwards. Details: `results/make_all_failsoft.json`.

**How this test differs from the test as first specified, and why.** The specification (TASK2 P1.2 item 3) was: run `make all`, temporarily force one stage marker to fail, confirm that all stages still run, the demo is built and the exit status is non-zero listing the failed stage, then restore. What was executed differs in these points:

1. *The failure is injected by a hook, not by a failing recipe.* `MAKE_ALL_FAIL=preflight` makes `scripts/make_all.py` skip that stage's recipe, switch its marker from `.done` to `.failed` and count the stage as failed. This matches the specification ("forcing a stage marker to fail"); it does not show a recipe that fails by itself.
2. *Most later stages were skipped, not executed.* The run used the marker-only resume (`RESUME=markers`): the 8 stages that already had a `.done` marker or a recorded successful run (runtime, images, t1, t2, t2-stretch, t1-routed, sweeps, repro) were skipped without checking whether their inputs had changed (the input-aware rule of `RESUME=1` would have rerun: images, t1, t2, t2-stretch). Reason: a full pass costs about 3 hours of the single heavy-job queue (Decision P2-1). Consequence: the test shows the control flow continuing past the failure and reaching the end; it does **not** show a heavy stage being executed after a failure. Executed for real after the forced failure: t3, demo.
3. *Sweeps were started but not waited for* (`SWEEPS_DETACH=1`), and Task 3's criterion-A jobs were disabled (`T3_USER_DEADLINE=1`).
4. *One assertion was changed while the test was written:* from "only the forced stage failed" to "the forced stage is first in the failed list", so that a stage failing for its own reasons is listed instead of failing the test. Failed list of this run besides the forced stage: t3.

It is therefore a weaker check than a full `make all` with one stage really failing: it verifies the fail-soft bookkeeping and exit status on the real Makefile and markers, with 2 of 11 stages actually executed. Execution of real recipes after a real failure is covered separately by (a) the unit test `scripts/tests/make_all_test.sh` on a scratch repository (cases A and J: every later recipe runs after one or two failing recipes) and (b) the recorded `make all` run below, when present, in which a stage fails with its own exit code.

Earlier fail-soft test runs (kept for the record):

- 15:42: PASS; executed for real: sweeps, demo; excluded: t3. Correction after the reviewer's gate audit (G2): in this 15:41 run `repro` was skipped as 'succeeded before' although its report said pass=False — its marker was still .done (the marker followed the verdict only after a fix at 15:58) — and `t3`, which fails, was excluded. So the failed list contained only the forced stage because the two stages that really fail were kept out of the run, not because nothing else fails; the stricter assertion 'only the forced stage failed' would not hold in a run that includes them.

**`make all` (resume):** exit 1; failed stages: t3; per stage: preflight skipped — inputs (2 git-tracked files) byte-identical to the last successful `make preflight` at 2026-10-12 15:40:37; runtime skipped — inputs (3 git-tracked files) byte-identical to the last successful `make runtime` at 2026-10-12 09:27:41; images ran 1093 s, of which lock wait 1012 s; t1 ran 750 s, of which lock wait 1 s; t2 ran 474 s, of which lock wait 0 s; t2-stretch ran 454 s, of which lock wait 0 s; t1-routed skipped — inputs (23 git-tracked files) byte-identical to the last successful `make t1-routed` at 2026-10-12 19:07:59; t3 ran 8 s, of which lock wait 0 s exit 2; sweeps skipped — inputs (8 git-tracked files) byte-identical to the last successful `make sweeps` at 2026-10-12 15:41:01; repro skipped — inputs (65 git-tracked files) byte-identical to the last successful `make repro` at 2026-10-12 19:07:27; demo ran 20 s, of which lock wait 0 s.

What two of these entries mean: the `t3` entry was a resume of jobs already finished, lasting 8 s (`T3_RESUME=1`: no SCALE-Sim job was re-executed, only the verdict was recomputed and the summary rewritten); Task 3's real executions are the recorded `make t3`, `make t3-clean-first` and `make repro` runs above; `sweeps` was skipped because its inputs are unchanged since its last recorded success, and that success is only the detached start inside the first fail-soft test (`SWEEPS_DETACH=1`: `scripts/make_sweeps.sh` found both drivers already running, started nothing and returned in a fraction of a second, at 15:42); the sweep work itself was done by the drivers the agents started directly, stage `41_sweeps_finish`.

**Why the repro verdict still covers the files on HEAD.** `make all` re-executed stages whose first-run files `make repro` had already compared. Checked afterwards by `scripts/post_repro_identity_check.py`: Task 1 files on HEAD vs the rerun copies repro compared — `t1_icarus.csv` identical; `t1_verilator.csv` identical; `t1_coverage_icarus.json` identical; `t1_coverage_verilator.json` identical; `t1_waveform_case.json` identical; summary check booleans equal to the rerun's (16 compared): yes; Task 2 (the stage's own comparison against every earlier run): nangate45/gcd run 5 identical; nangate45/systolic_os run 4 identical; sky130hd/gcd run 5 identical; Task 3: 42 of 42 files that repro compared have, on HEAD, the sha256 recorded in the repro report for both the first run and the rerun (newest file time on HEAD 2026-10-12 19:57:54, i.e. after the last resume of the stage; excluded: run-time measurements (3 files)). Overall: **identical**.

**Image pins.** `coord/images.env` holds the two images every baseline stage uses (lab-sim, ORFS) and is an input of those stages. The CACTI image of stage 63 (`lab-cacti:20261012`) is pinned separately in `coord/images_cacti.env` and in the `cacti:` section of `versions.lock`, on purpose: adding it to `coord/images.env` would change an input of Task 1 and of the repro stage and force their rerun (Decision P2-12).

## Evidence that it builds and runs

Terminal output saved by each stage, rendered to images from the saved text (not OS screenshots).

![01_runtime_docker](demo/assets/evidence/01_runtime_docker.png)

![02_images_scalesim_numpy_fix](demo/assets/evidence/02_images_scalesim_numpy_fix.png)

![02_images_smoke](demo/assets/evidence/02_images_smoke.png)

![10_cocotb_icarus](demo/assets/evidence/10_cocotb_icarus.png)

![10_cocotb_verilator](demo/assets/evidence/10_cocotb_verilator.png)

![10_eqy](demo/assets/evidence/10_eqy.png)

![10_lint](demo/assets/evidence/10_lint.png)

![10_sby](demo/assets/evidence/10_sby.png)

![10_sha256](demo/assets/evidence/10_sha256.png)

![11_eqy_routed](demo/assets/evidence/11_eqy_routed.png)

![11_gls_routed](demo/assets/evidence/11_gls_routed.png)

![11_orfs_lec_kepler](demo/assets/evidence/11_orfs_lec_kepler.png)

![20_determinism_nangate45_gcd](demo/assets/evidence/20_determinism_nangate45_gcd.png)

![20_determinism_sky130hd_gcd](demo/assets/evidence/20_determinism_sky130hd_gcd.png)

![20_orfs_flow_nangate45_gcd](demo/assets/evidence/20_orfs_flow_nangate45_gcd.png)

![20_systolic_os_ppa](demo/assets/evidence/20_systolic_os_ppa.png)

![20_threshold_check_nangate45_gcd](demo/assets/evidence/20_threshold_check_nangate45_gcd.png)

![20_threshold_check_sky130hd_gcd](demo/assets/evidence/20_threshold_check_sky130hd_gcd.png)

![21_orfs_crosscheck](demo/assets/evidence/21_orfs_crosscheck.png)

![21_orfs_crosscheck_implied_superseded](demo/assets/evidence/21_orfs_crosscheck_implied_superseded.png)

![30_analytic_fit](demo/assets/evidence/30_analytic_fit.png)

![30_byte_identity](demo/assets/evidence/30_byte_identity.png)

![30_roofline](demo/assets/evidence/30_roofline.png)

![30_scalesim_run](demo/assets/evidence/30_scalesim_run.png)

![30_sweepA_progress](demo/assets/evidence/30_sweepA_progress.png)

![31_a_probe](demo/assets/evidence/31_a_probe.png)

![31_neutrality_and_intensity_tests](demo/assets/evidence/31_neutrality_and_intensity_tests.png)

![31_original_stalls](demo/assets/evidence/31_original_stalls.png)

![40_sweepA_summary](demo/assets/evidence/40_sweepA_summary.png)

![40_sweepB_frontier](demo/assets/evidence/40_sweepB_frontier.png)

![41_sweepB_frontier](demo/assets/evidence/41_sweepB_frontier.png)

![41_sweepB_lock_accounting](demo/assets/evidence/41_sweepB_lock_accounting.png)

![41_sweepB_plan_accounting](demo/assets/evidence/41_sweepB_plan_accounting.png)

![41_sweep_A_accounting](demo/assets/evidence/41_sweep_A_accounting.png)

![51_determinism_reruns](demo/assets/evidence/51_determinism_reruns.png)

![51_repro_t3_diagnosis](demo/assets/evidence/51_repro_t3_diagnosis.png)

![60_power_activity](demo/assets/evidence/60_power_activity.png)

![61_bit_exact](demo/assets/evidence/61_bit_exact.png)

![61_cocotb_icarus](demo/assets/evidence/61_cocotb_icarus.png)

![61_cocotb_verilator](demo/assets/evidence/61_cocotb_verilator.png)

![61_lint](demo/assets/evidence/61_lint.png)

![61_ppa](demo/assets/evidence/61_ppa.png)

![62_pdk_compare](demo/assets/evidence/62_pdk_compare.png)

![63_cacti_image_smoke](demo/assets/evidence/63_cacti_image_smoke.png)

![63_sram_cacti_results](demo/assets/evidence/63_sram_cacti_results.png)

![final_run_demo](demo/assets/evidence/final_run_demo.png)

## Results

![pdk compare](demo/assets/pdk_compare.png)

![power activity](demo/assets/power_activity.png)

![sram cacti](demo/assets/sram_cacti.png)

![sweepA best dataflow](demo/assets/sweepA_best_dataflow.png)

![sweepA cycles alexnet](demo/assets/sweepA_cycles_alexnet.png)

![sweepA cycles alexnet part](demo/assets/sweepA_cycles_alexnet_part.png)

![sweepA cycles gemm test](demo/assets/sweepA_cycles_gemm_test.png)

![sweepA cycles ncf](demo/assets/sweepA_cycles_ncf.png)

![sweepA cycles vit s](demo/assets/sweepA_cycles_vit_s.png)

![sweepA dram bw alexnet](demo/assets/sweepA_dram_bw_alexnet.png)

![sweepA dram bw alexnet part](demo/assets/sweepA_dram_bw_alexnet_part.png)

![sweepA dram bw gemm test](demo/assets/sweepA_dram_bw_gemm_test.png)

![sweepA dram bw ncf](demo/assets/sweepA_dram_bw_ncf.png)

![sweepA dram bw vit s](demo/assets/sweepA_dram_bw_vit_s.png)

![sweepA sram alexnet part](demo/assets/sweepA_sram_alexnet_part.png)

![sweepA sram gemm test](demo/assets/sweepA_sram_gemm_test.png)

![sweepA sram ncf](demo/assets/sweepA_sram_ncf.png)

![sweepA sram vit s](demo/assets/sweepA_sram_vit_s.png)

![sweepA util alexnet](demo/assets/sweepA_util_alexnet.png)

![sweepA util alexnet part](demo/assets/sweepA_util_alexnet_part.png)

![sweepA util gemm test](demo/assets/sweepA_util_gemm_test.png)

![sweepA util ncf](demo/assets/sweepA_util_ncf.png)

![sweepA util vit s](demo/assets/sweepA_util_vit_s.png)

![sweepB frontier gcd](demo/assets/sweepB_frontier_gcd.png)

![sweepB frontier systolic os](demo/assets/sweepB_frontier_systolic_os.png)

![sweepB wns heatmap gcd](demo/assets/sweepB_wns_heatmap_gcd.png)

![sweepB wns heatmap systolic os](demo/assets/sweepB_wns_heatmap_systolic_os.png)

![t1 waveform](demo/assets/t1_waveform.png)

![t2 nangate45 gcd](demo/assets/t2_nangate45_gcd.png)

![t2 nangate45 systolic os](demo/assets/t2_nangate45_systolic_os.png)

![t2 sky130hd gcd](demo/assets/t2_sky130hd_gcd.png)

![t3 cycles vs analytic](demo/assets/t3_cycles_vs_analytic.png)

![t3 roofline](demo/assets/t3_roofline.png)

## Notes

- Versions, image digests, URLs and SHA256s: `versions.lock`, `coord/images.env`.
- VM end-state is stated at final packaging; start/stop commands are in `demo/README.md`.
- No personal paths, hostnames or credentials are stored in this repository; a pre-commit hook and `scripts/evidence_privacy.py` enforce that.

