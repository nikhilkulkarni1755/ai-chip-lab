# AI chip design lab

An open-source, reproducible lab that takes a small AI accelerator from a multiply-accumulate unit to a laid-out chip using only open tools, run unattended on an old 2-core Intel MacBook with 8 GB of RAM (no Homebrew, no sudo; a Colima VM runs the containers). Three baseline checks establish objective truth (answers checked against math, a second independent tool, or published reference values); sweeps then explore the design space.

Open [`demo/index.html`](demo/index.html) for the full walk-through: concepts, tool map, how each result was tested, plots, and honest caveats.

## Status

Generated from the files in this repository by `python3 scripts/demo_build.py` (Total runtime: 5h 08m, from 2026-10-12 02:48:36 PDT to 07:57, budget 6h).

| Check | Status | Detail |
|---|---|---|
| Container runtime install | **PASS** | route A (Colima + Lima, macOS Virtualization.framework) |
| Lab images (lab-sim, ORFS) | **PASS** | both images referenced in coord/images.env |
| Task 1: INT8 systolic array vs NumPy | **RUNNING** | re-verification in progress: inputs changed after the recorded result (inputs last committed 09:49:22, summary last committed 06:10:17); the previous result (pass=True) is not shown as current |
| Task 1: formal MAC proof (SBY) | **RUNNING** | re-verification in progress (see Task 1 row); the earlier values are withheld |
| Task 1: RTL = netlist equivalence (EQY) | **RUNNING** | re-verification in progress (see Task 1 row); the earlier values are withheld |
| Task 2: OpenROAD gcd flows within ORFS's shipped regression thresholds | **PASS** | t2_summary.json: pass=true; NOT timing-closed: nangate45/gcd misses timing at its 0.25 ns reference clock (WNS -0.161583 ns, TNS -7.08646 ns, 51 violating endpoints); sky130hd/gcd misses timing at its 1.1 ns reference clock (WNS -1.45954 ns, TNS -64.9417 ns, 63 violating endpoints) |
| Task 3: SCALE-Sim vs analytical model | **INCOMPLETE** | INCOMPLETE (not PASS, not a bare FAIL): the re-specified roofline check is in progress and results/t3_summary.json is still the Part 1 result (marker .failed: 30_arch_model: 1 of 6 criteria FAILED (honest result, not a crash). Run: scripts/t3_run.sh (container lab-sim, 2 passes).; criteria that fail: roofline_agreement_is, roofline_agreement_os, roofline_agreement_ws, roofline_agrees, roofline_rank_corr_is, roofline_rank_corr_ws (the roofline-vs-stalls agreement; the analytic cycle model and byte-identity checks pass)). Roofline runs finished so far: rl2_calc_is, rl2_calc_os, rl2_calc_ws; criterion B (CALC mode, rho(intensity, required bandwidth) <= -0.6 required): ws 0.37 (fails), os -0.56 (fails), is -0.51 (fails); criterion A (stalls at fixed user bandwidth) started for: rl2_user_ws_high, no layer-complete run reported yet. Pre-registered in model/t3_roofline2_criteria.json, cost-only amendment P2-A2, plan P2-7 (COORDINATION.md). The Part 2 hypothesis was wrong: the bundled google.cfg already uses USER bandwidth and its stalls are all zero (results/evidence/31_original_stalls.txt) |
| Sweep A: architecture (SCALE-Sim) | **DONE** | sweep stopped (marker .done); this is a completion status, not a pass/fail verdict; 165 ok of 264 planned points (1 error, 1 skipped after timeout, 97 never reached before the deadline) |
| Sweep B: physical (ORFS) | **DONE** | sweep stopped (marker .done); this is a completion status, not a pass/fail verdict; gcd closes at 0.42-0.425 ns depending on utilization (about zero margin at 0.42 ns, u50); systolic_os at 30 % utilization: closes at 1.25 ns (WNS 0.0132117 ns), fails at 1.2 ns (WNS -0.00730405 ns), 6 points; 1 failed point(s) |
| Repeatability rerun (repro) | **RUNNING** | summary says pass=true but a re-run is in progress; 10 of 10 checks identical in the Part 1 report (results/repro_report.json predates the Part 2 repro: its scope was Tasks 1 and 3 re-run once, Task 2 from its two original runs, systolic_os a single run). The Part 2 report with every design's run count (gcd 4 runs on both PDKs, systolic_os 3, from results/t2_reruns.json) replaces it when `make repro` finishes |
| Task 1: RTL = ROUTED netlist equivalence (EQY) | **FAIL** | eqy_routed_pass = false in t1_summary.json; EQY partitions proved: 9 of 27 (the rest were not proved; see the diagnosis in the not-green list) |
| Task 1: routed gate-level simulation vs NumPy | **FAIL** | gls_routed_pass = false in t1_summary.json; per simulator (0 mismatches against NumPy): Icarus True, Verilator False; negative control detected: True |
| Task 2: matches ORFS's published reference results | **PASS** | matches_published = true in t2_summary.json |
| Make recipes executed for real | **RUNNING** | 5 recipe(s) recorded in results/make_recipes.json; non-zero exit: t3 |

### What is not green yet, why, and the next action

State is computed from the files; diagnosis and next action are explanations written from the decisions in COORDINATION.md.

| Row | State now | Diagnosis | Next action |
|---|---|---|---|
| Task 1: INT8 systolic array vs NumPy | **RUNNING** | Part 2 changed inputs of the Task 1 recipe (the routed-netlist runner and shared scripts) after the recorded result, so the page refuses to show the old PASS as current. | The real `make t1` recipe (infra) re-runs the stage and rewrites results/t1_summary.json; the row turns PASS or FAIL from that file. Nothing to do by hand. |
| Task 1: formal MAC proof (SBY) | **RUNNING** | Same as the Task 1 row. | Same as the Task 1 row (`make t1`). |
| Task 1: RTL = netlist equivalence (EQY) | **RUNNING** | Same as the Task 1 row. | Same as the Task 1 row (`make t1`). |
| Task 3: SCALE-Sim vs analytical model | **INCOMPLETE** | Criterion B (CALC mode) and criterion A (stalls at a fixed user bandwidth) were pre-registered; the cells that have not been evaluated keep the row open, and criterion B's measured correlations are shown in the row and in section 6. The hypothesis that the default bandwidth mode hid the stalls was wrong: the bundled config uses user bandwidth and its stalls are all zero. | The arch agent makes the fixed-bandwidth jobs resumable and bounded per lock hold, then infra re-runs `make t3`. Whatever the pre-registered thresholds say is final: if criterion B or A fails the row becomes FAIL with the diagnosis, it is not retuned. |
| Sweep A: architecture (SCALE-Sim) | **DONE** | A completion status: points never reached before the sweep deadline (cut because sweeps run at low priority behind stage jobs in the one-job-at-a-time queue; cheapest points ran first). | `make sweeps` resumes where it stopped; each unreached point is accounted for in the sweep section of the page. |
| Sweep B: physical (ORFS) | **DONE** | A completion status. The systolic_os frontier at 30 % utilization is bracketed by a failing and a closing period (see the row); 40 and 50 % utilization points are listed with their state in section 12. | `make sweeps` (or `python3 sweeps/phys_sweep.py --plan part2`) runs the remaining planned points. |
| Repeatability rerun (repro) | **RUNNING** | The Part 2 repro (Task 1 in full, Task 3 cheap set, Task 2 from the extra clean runs) is still running or has not been summarised; the user-bandwidth Task 3 runs are not rerun because of their cost and are reported as such, never as identical. | `make repro`; results/repro_report.json then shows every check with its run count. |
| Task 1: RTL = ROUTED netlist equivalence (EQY) | **FAIL** | The routed netlist is flat, so the Part 1 split is applied by name: 16 per-PE partitions plus wrapper partitions. The partitions proved are counted in the row; the stage marker text on the page says which were not proved and why. The per-PE multiplier/accumulator partitions are the hard ones for the solver on 8 GB. | The rtl agent re-runs the missing wrapper partitions (`T1R_STEPS=eqy scripts/t1_routed.sh`, under the lock). The row stays FAIL until every partition is proved; the scope is stated exactly, never widened. |
| Task 1: routed gate-level simulation vs NumPy | **FAIL** | The gate-level result is per simulator: the row detail shows Icarus and Verilator separately. Icarus having 0 mismatches against NumPy and the negative control being caught are shown as true/false in the row; a false Verilator value means that step did not pass or did not complete (see the evidence text on the page). | The rtl agent re-runs the Verilator gate-level step (`T1R_STEPS=gls scripts/t1_routed.sh`). The combined criterion needs both simulators and an identical CSV; a Verilator-only gap is reported as exactly that. |
| Make recipes executed for real | **RUNNING** | Each recipe is executed for real by the recorder in queue order; the ones still running or not run yet are listed in the note on the page. | `make all` (fail-soft, always builds the demo, exits non-zero naming failed stages). |

## Part 2: before and after

| Check | At the start of Part 2 | Now |
|---|---|---|
| Runtime | PASS | **PASS** |
| Images | PASS | **PASS** |
| Task 1: sim vs NumPy, SBY, EQY | PASS | **FAIL** |
| Task 2: ORFS gcd within thresholds | PASS | **PASS** |
| Task 3: SCALE-Sim vs analytic | FAIL | **INCOMPLETE** |
| Sweep A | Incomplete | **DONE** |
| Sweep B | Coarse | **DONE** |
| Repro | PASS | **RUNNING** |
| Make recipes | Untested | **RUNNING** |

Part 2 elapsed so far (not finished): 4h 16m, from 2026-10-12 09:03:34 PDT to now, budget 14h (Part 1's total runtime stays as recorded in its own section)

Part 2 stage states:

| Stage | State |
|---|---|
| `31_roofline_fix` P1.1 Task 3 roofline check | INCOMPLETE |
| `32_make_recipes` P1.2 every make recipe run for real | RUNNING |
| `11_eqy_routed` P1.3 equivalence and gate-level simulation of the routed netlist | FAIL |
| `51_repro_full` P1.4 complete determinism story | RUNNING |
| `21_orfs_crosscheck` P1.5 Task 2 against ORFS's published results | PASS |
| `41_sweeps_finish` P1.6 finish and refine the sweeps | INCOMPLETE |
| `60_power_activity` P2.1 activity-based power | PENDING |
| `61_pe_bf16` P2.2 bf16 processing element | PENDING |
| `62_pdk_compare` P2.3 systolic_os on sky130hd | PENDING |
| `63_sram_cacti` P2.4 SRAM modelling (CACTI) | PENDING |
| `64_roadmap` P2.5 roadmap | PENDING |


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
| `demo/run_demo.sh` | The 5-minute re-run: Task 1 (200 cases, both simulators), formal proof, one SCALE-Sim run, ORFS check, and the Task 3 roofline criterion B recomputed from saved reports. The routed-netlist gate-level simulation is left out (67 s, over the 1-minute-per-step rule). |
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

![31_neutrality_and_intensity_tests](demo/assets/evidence/31_neutrality_and_intensity_tests.png)

![31_original_stalls](demo/assets/evidence/31_original_stalls.png)

![40_sweepA_summary](demo/assets/evidence/40_sweepA_summary.png)

![40_sweepB_frontier](demo/assets/evidence/40_sweepB_frontier.png)

![51_determinism_reruns](demo/assets/evidence/51_determinism_reruns.png)

## Results

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

