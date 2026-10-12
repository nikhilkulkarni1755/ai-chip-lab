# AI chip design lab

An open-source, reproducible lab that takes a small AI accelerator from a multiply-accumulate unit to a laid-out chip using only open tools, run unattended on an old 2-core Intel MacBook with 8 GB of RAM (no Homebrew, no sudo; a Colima VM runs the containers). Three baseline checks establish objective truth (answers checked against math, a second independent tool, or published reference values); sweeps then explore the design space.

Open [`demo/index.html`](demo/index.html) for the full walk-through: concepts, tool map, how each result was tested, plots, and honest caveats.

## Status

Generated from the files in this repository by `python3 scripts/demo_build.py` (elapsed at generation: 5h 04m since start (2026-10-12 02:48:36 PDT), budget 6h).

| Check | Status | Detail |
|---|---|---|
| Container runtime install | **PASS** | route A (Colima + Lima, macOS Virtualization.framework) |
| Lab images (lab-sim, ORFS) | **PASS** | both images referenced in coord/images.env |
| Task 1: INT8 systolic array vs NumPy | **PASS** | t1_summary.json: pass=true |
| Task 1: formal MAC proof (SBY) | **PASS** | checks: formal_bmc_pass=true, formal_prove_pass=true |
| Task 1: RTL = netlist equivalence (EQY) | **PASS** | checks: eqy_array_pass=true, eqy_mac_pass=true, eqy_pass=true; scope: split proof (1) mac_int8 incl. multiplier, (2) full 4x4 array with mac_int8 black-boxed; compared against the generic-gate Yosys netlist (synth; abc; opt), NOT the placed-and-routed nangate45 netlist (the ORFS logic-equivalence step is disabled, see caveats) |
| Task 2: OpenROAD gcd flows within ORFS's shipped regression thresholds | **PASS** | t2_summary.json: pass=true; NOT timing-closed: nangate45/gcd misses timing at its 0.25 ns reference clock (WNS -0.161583 ns, TNS -7.08646 ns, 51 violating endpoints); sky130hd/gcd misses timing at its 1.1 ns reference clock (WNS -1.45954 ns, TNS -64.9417 ns, 63 violating endpoints) |
| Task 3: SCALE-Sim vs analytical model | **FAIL** | marker .failed: 30_arch_model: 1 of 6 criteria FAILED (honest result, not a crash). Run: scripts/t3_run.sh (container lab-sim, 2 passes).; criteria that fail: roofline_agreement_is, roofline_agreement_os, roofline_agreement_ws, roofline_agrees, roofline_rank_corr_is, roofline_rank_corr_ws (the roofline-vs-stalls agreement; the analytic cycle model and byte-identity checks pass) |
| Sweep A: architecture (SCALE-Sim) | **DONE** | sweep stopped (marker .done); this is a completion status, not a pass/fail verdict; 165 ok of 264 planned points (1 error, 1 skipped after timeout, 97 never reached before the deadline) |
| Sweep B: physical (ORFS) | **DONE** | sweep stopped (marker .done); this is a completion status, not a pass/fail verdict; gcd frontier 0.42 ns (fastest closing period over utilizations 30-60 %), 1 failed point(s) |
| Repeatability rerun (repro) | **PASS** | repro_report.json: pass=true; 10 of 10 checks identical. Scope: Tasks 1 and 3 were re-run from clean directories; Task 2 reuses the two original clean runs (nangate45/gcd and sky130hd/gcd, not a third run); systolic_os has a single run, so it has no determinism verdict |

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
| `demo/run_demo.sh` | The 5-minute re-run: Task 1 (200 cases, both simulators), formal proof, one SCALE-Sim run, ORFS check. |
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
make repro                    # reruns Tasks 1 and 3 clean and compares; Task 2 reuses its own two-run check
make demo                     # plots + evidence PNGs + demo/index.html + this README
make all                      # fail-soft loop over the above, always builds the demo, exits non-zero listing failed stages
bash demo/run_demo.sh         # short cut (cached images, scratch output dir); needs the VM running
```

Honesty note on the recipes: in the original run the stages were executed through their scripts; of the `make` recipes only `make preflight` was executed as such, the others (`t2`, `t2-stretch`, `t3`, `sweeps`, `all`) were dry-run verified.

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

![20_determinism_nangate45_gcd](demo/assets/evidence/20_determinism_nangate45_gcd.png)

![20_determinism_sky130hd_gcd](demo/assets/evidence/20_determinism_sky130hd_gcd.png)

![20_orfs_flow_nangate45_gcd](demo/assets/evidence/20_orfs_flow_nangate45_gcd.png)

![20_systolic_os_ppa](demo/assets/evidence/20_systolic_os_ppa.png)

![20_threshold_check_nangate45_gcd](demo/assets/evidence/20_threshold_check_nangate45_gcd.png)

![20_threshold_check_sky130hd_gcd](demo/assets/evidence/20_threshold_check_sky130hd_gcd.png)

![30_analytic_fit](demo/assets/evidence/30_analytic_fit.png)

![30_byte_identity](demo/assets/evidence/30_byte_identity.png)

![30_roofline](demo/assets/evidence/30_roofline.png)

![30_scalesim_run](demo/assets/evidence/30_scalesim_run.png)

![30_sweepA_progress](demo/assets/evidence/30_sweepA_progress.png)

![40_sweepA_summary](demo/assets/evidence/40_sweepA_summary.png)

![40_sweepB_frontier](demo/assets/evidence/40_sweepB_frontier.png)

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
- The Colima VM is left RUNNING at the end of the run because demo/run_demo.sh needs it. Stop it with: source ~/ai-chip-lab/env.sh && colima stop
- No personal paths, hostnames or credentials are stored in this repository; a pre-commit hook and `scripts/evidence_privacy.py` enforce that.

