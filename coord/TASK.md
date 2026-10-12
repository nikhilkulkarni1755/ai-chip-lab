# Task spec (owner's text, sections 0–10). Budget overridden to 6 h — see COORDINATION.md.

## 0. Context and ground rules

Running **unattended** on an old **Intel (x86_64) MacBook Pro**. The owner comes back later and looks only at the final demo. Job:
1. Build a reproducible, open-source AI-chip-design lab.
2. Run three baseline checks proving the toolchain is correct and its results repeat.
3. Run long design-space sweeps.
4. Package everything into a clear, self-explanatory demo.

The three checks are deliberately **non-innovative**: they establish *objective truth* — answers checkable against math, a second independent tool, or published reference values.

### Hard constraints
- **Homebrew is NOT supported.** Do not install, use, or suggest `brew`, or work around that. Installs come from official release binaries, tarballs, DMGs, or container images.
- **Docker was not installed.** Prefer **Colima** (headless, no GUI, no sudo). Docker Desktop only as fallback.
- **Never block on an interactive prompt.** `-y` / `--yes` / `--accept-license` / `DEBIAN_FRONTEND=noninteractive`; every long command under a timeout. If a step needs `sudo` (`sudo -n true` fails on this machine) log it as BLOCKED with the exact command for the owner and continue.
- **Stay inside `~/ai-chip-lab/`.** No system settings, no shell profiles. Never `rm -rf` outside the lab.
- **Keep the Mac awake** (`caffeinate -dimsu` is already running).
- **Fail soft.** After 2 retries: record error, last 50 log lines, diagnosis; move to the next independent stage.
- **Be resumable.** `.done` markers + outputs; sweep points keyed by parameters in JSONL; skip completed work on restart.
- **Pin and record everything.** Resolve versions at run time (not from memory). Exact versions, git SHAs, image **digests**, download URLs + SHA256 → `versions.lock`. Fixed seeds, `PYTHONHASHSEED=0`, fixed thread counts.

## 2. Container runtime (stage `01_runtime`)

### Route A: Colima (macOS ≥ 13) — this machine
Colima uses Lima; on macOS 13+ it can use Virtualization.framework (`--vm-type vz`), no QEMU. Everything into `~/ai-chip-lab/bin`, no brew, no sudo:
1. **Lima:** latest `lima-<ver>-Darwin-x86_64.tar.gz` from `github.com/lima-vm/lima/releases` → `~/ai-chip-lab/opt/lima`.
2. **Colima:** `colima-Darwin-x86_64` from `github.com/abiosoft/colima/releases` → `~/ai-chip-lab/bin/colima`.
3. **Docker CLI:** static client `docker-<ver>.tgz` from `download.docker.com/mac/static/stable/x86_64/` → `~/ai-chip-lab/bin/docker`. Optionally `docker-buildx` (darwin-amd64) under `$DOCKER_CONFIG/cli-plugins/` with `DOCKER_CONFIG=~/ai-chip-lab/docker-config`.
4. Check SHA256 against published checksums where they exist; record them.
5. `env.sh` exports PATH; source it in **every** script.
6. `colima start --vm-type vz --cpu <N> --memory <GB> --disk 80 --arch x86_64`, then `docker run --rm hello-world`.

### Route B: Docker Desktop (fallback if Route A fails twice) — needs sudo → would be BLOCKED here; give exact commands:
```
hdiutil attach Docker.dmg -nobrowse
sudo /Volumes/Docker/Docker.app/Contents/MacOS/install --accept-license --user=$USER
hdiutil detach /Volumes/Docker
```
### Route C: last resort, native-only
OSS CAD Suite `darwin-x64` tarball from `github.com/YosysHQ/oss-cad-suite-build/releases` + Python venv (python3 or `uv`). Do Sections 4 and 6 natively; Section 5 BLOCKED.

Record route + why in `versions.lock` and the final report.

## 3. Lab images (stage `02_images`)
Everything runs in **linux/amd64 containers**.

### `lab-sim` image — `docker/lab-sim/Dockerfile`, base `ubuntu:22.04` pinned by digest
- **OSS CAD Suite** (`linux-x64` release tarball, pinned by date tag): Yosys, ABC, **Verilator**, **Icarus Verilog**, **SymbiYosys (sby)**, **EQY**, yosys-smtbmc, Boolector, Bitwuzla, Yices, Z3, GHDL, nextpnr, GTKWave.
- **Verible** (GitHub release binary).
- Python 3.11+ with **uv**; `uv pip install` from committed `requirements.lock`: `cocotb`, `cocotb-coverage`, `pytest`, `numpy`, `ml_dtypes`, `pandas`, `matplotlib`, `scalesim` (or SCALE-Sim from `github.com/scalesim-project/scale-sim-v2` at a pinned SHA, whichever installs cleanly), `vcdvcd`, `pyyaml`.
- `klayout` (headless, GDS → PNG) if available as Ubuntu package/AppImage; otherwise use KLayout in the ORFS image.

### ORFS image
Official `openroad/orfs`; newest stable tag, **pinned by digest**. Use `flow/` inside the image or clone ORFS at the matching commit.

### Timeloop image (optional, if time allows) — skip if large / time short.

### Smoke test
`docker/smoke.sh` prints the version of every tool above, output saved into `versions.lock`. Stage passes only if all required tools report a version.

## 4. Task 1: INT8 systolic array, bit-exact against NumPy (stage `10_rtl_verify`)

Concepts to state in the report: MAC is `acc += a*b`; PE = MAC + registers; systolic array = grid of PEs passing operands to neighbours; output-stationary: each PE owns one output element; oracle = integer math (NumPy int32 is exact).

### Build
- `rtl/mac_int8.sv`: signed INT8 × INT8, INT32 accumulator, synchronous `clear`/`valid`.
- `rtl/systolic_os.sv`: parameterized `R×C` output-stationary array (default 4×4), skewed input feeding, simple readout. Short and readable.
- Lint with `verilator --lint-only -Wall` and `verible-verilog-lint`; warnings zero or justified.

### Test
cocotb testbench `tb/test_systolic.py` (Makefile or runner flow):
- Random INT8 `A (M×K)`, `B (K×N)` from **fixed seed 1234**.
- Tile onto the array, compare with `A.astype(int32) @ B.astype(int32)`.
- N = 10,000 random cases + directed: all −128 (at max K), all 127, zeros, identity, reset/clear mid-stream, K=1, non-multiple-of-array-size shapes.
- Functional coverage of operand sign combinations and corner values with `cocotb-coverage`, reported.
Run the full suite on **both Verilator and Icarus**. Each writes `results/t1_<sim>.csv` listing every case and its output.

### Formal
`formal/mac.sby`: MAC satisfies `acc_next == acc + sext(a)*sext(b)` when valid, holds otherwise. BMC ≥ 20 steps, plus `prove` mode if it closes.

### Equivalence
Yosys (`synth -top systolic_os; abc; opt`) → gate-level netlist; prove **RTL ≡ netlist** with **EQY**. If full-design EQY is too slow, prove per PE and say so.

### Pass criteria → `results/t1_summary.json`
- 0 mismatches vs NumPy on both simulators.
- `sha256(t1_verilator.csv) == sha256(t1_icarus.csv)`.
- Formal proof passes. EQY passes.
Also save a VCD of one small case, rendered to `demo/assets/t1_waveform.png` with matplotlib + `vcdvcd`.

## 5. Task 2: OpenROAD reference flow within published thresholds (stage `20_pnr_ref`)

Concepts to state: RTL → synthesis (Yosys/ABC) → floorplan → placement (global + detailed) → CTS (TritonCTS) → routing (TritonRoute) → STA (OpenSTA) → GDSII. Define WNS/TNS, utilization, dynamic vs leakage power, what a PDK is.

### Run (pinned ORFS container, `NUM_CORES` fixed at VM CPU count)
- `make DESIGN_CONFIG=./designs/nangate45/gcd/config.mk`
- `make DESIGN_CONFIG=./designs/sky130hd/gcd/config.mk` (only if disk/time allows)

### Extract and check
- Generate ORFS metadata (`metadata` make target or equivalent at this version).
- Compare against per-design `rules*.json` thresholds shipped with ORFS, using ORFS's own checker under `flow/util/`.
- Extract design area, utilization, WNS/TNS, total power, cell count, DRC count, runtime.

### Determinism
Each design **twice from clean** with the same digest and `NUM_CORES`; diff metrics. Identical = PASS; any difference = recorded determinism finding (still valid).

### Pass criteria
Metrics within shipped thresholds; final DRC = 0; GDS exists; the two runs agree.

### Render
KLayout batch (`klayout -zz -r render.py` → PNG) → `demo/assets/t2_<platform>_gcd.png`.

### Stretch
Wrap Task 1's `systolic_os` (4×4) as an ORFS design on nangate45 (`config.mk`, `constraint.sdc`, conservative clock); run flow, record PPA.

## 6. Task 3: SCALE-Sim against an analytical model (stage `30_arch_model`)

Concepts to state: ws/os/is dataflows; fold/tiling; fill/drain latency; roofline (arithmetic intensity FLOPs/byte vs peak compute and memory bandwidth).

### Run
SCALE-Sim with its **bundled** TPU-like config and a **bundled** topology (ResNet-18 or AlexNet), once each for **ws, os, is**. Save `COMPUTE_REPORT.csv` + bandwidth/detail reports to `results/t3/`.

### Analytical model — `model/analytic.py`
Pure GEMM M×K×N on R×C array: folds = ⌈M/R⌉·⌈N/C⌉ (adjust per dataflow); cycles ≈ folds × (K + fill/drain). Run SCALE-Sim on synthetic GEMM topologies; fit the fill/drain constant; check the residual is small and **stable** when doubling R, C, or K.

### Roofline
Per-layer arithmetic intensity vs SCALE-Sim's reported stalls or bandwidth demand. Low-intensity layers should be the bandwidth-bound ones.

### Pass criteria
Two reruns byte-identical; analytic model matches within the fitted constant with stable residuals; roofline classification agrees with stalls.
Plots: `demo/assets/t3_cycles_vs_analytic.png`, `demo/assets/t3_roofline.png`.

### Optional
Timeloop + Accelergy on one conv layer; order-of-magnitude comparison only.

## 7. Sweeps (stage `40_sweeps`, remaining budget)
One JSON line per point in `results/sweeps/*.jsonl`, keyed by parameters, resumable, per-point timeout. In order, then cycle:

### A. Architecture sweep (SCALE-Sim)
Array sizes {8,16,32,64,128} square + a few rectangular; dataflows {ws,os,is}; 2–3 bundled topologies; SRAM sizes {small, default, large}. Output: cycles, utilization, DRAM bandwidth. Heatmaps.

### B. Physical sweep (ORFS)
nangate45 `gcd` (+ `systolic_os` if the stretch worked). Clock period: start at reference, tighten in 5–10 % steps until WNS < 0, then a few steps beyond. `CORE_UTILIZATION` ∈ {30,40,50,60} %. Output: WNS, TNS, area, power, DRC, runtime. Find the **timing-closure frontier** (fastest clock with WNS ≥ 0) per utilization.

Rules: stop at the reserve time; breadth first (coarse grid, then refine); STATUS every 10 points (automatic via heartbeat).

## 8. Final determinism rerun (stage `50_repro`)
From a clean output directory rerun Tasks 1–3 with pinned versions; compare hashes/metrics to the first run → `results/repro_report.json` with identical/different verdict per check.

## 9. Demo (stage `60_demo`, must always run, even after failures) → `~/ai-chip-lab/demo/`

### `demo/index.html` — single self-contained file (inline CSS, images embedded or relative to `demo/assets`), opens by double-click, no server. Sections:
1. **One-screen summary.** Big PASS/FAIL/BLOCKED table: runtime install, each task, formal, equivalence, repro, sweeps. Total runtime, runtime route, machine specs.
2. **What was created.** Annotated directory tree, one line per important file.
3. **Concepts, from basics.** MAC → PE → systolic array → dataflow → memory hierarchy/roofline → RTL → verification → synthesis → place-and-route → STA → GDS. A few sentences each, each linked to the lab artifact that demonstrates it.
4. **Tool map.** Tool, chip-design stage, commercial equivalent: Verilator/Icarus ↔ VCS/Xcelium/Questa; cocotb ↔ UVM; SBY/EQY ↔ JasperGold/Formality/Conformal; Yosys ↔ Design Compiler/Genus; OpenROAD ↔ Innovus/ICC2; OpenSTA ↔ PrimeTime/Tempus; KLayout/Magic ↔ Calibre; SCALE-Sim/Timeloop ↔ in-house architecture models.
5. **How each thing was tested.** Per task: oracle (math / cross-tool / published thresholds), exact commands, inputs and seeds, pass criteria, actual results, links to logs.
6. **Results.** Waveform PNG, layout renders, cycles-vs-analytic, roofline, sweep heatmaps, timing-closure frontier plot, PPA table for `gcd` (and `systolic_os` if done).
7. **Repeatability.** Repro report, versions, image digests.
8. **Problems and honest caveats.** Everything failed/BLOCKED/cut for time, with the exact command to fix or finish.
9. **Where to go next.** Ordered list with a one-line why each: bfloat16/FP8 PEs (check vs `ml_dtypes`); double-buffered SRAM modelled with CACTI; `systolic_os` through sky130, PPA across PDKs; VCD/SAIF activity from cocotb for real power; Gemmini/Chipyard or TVM/VTA or MLIR/CIRCT; DREAMPlace; LLM-written RTL vs VerilogEval.

### `demo/run_demo.sh`
Re-runs a **5-minute** cut with cached images, no downloads: 200-case Task 1 on both simulators; the formal MAC proof; one SCALE-Sim run; a metadata check on existing ORFS outputs. Prints a PASS/FAIL table.

### `demo/README.md`
Plain-text summary + how to start/stop the VM (`source ~/ai-chip-lab/env.sh && colima start` / `colima stop`), how to free disk afterwards (which images/dirs are safe to delete).

### Last steps
Stop sweep jobs. Leave the VM running only if the demo script needs it, else `colima stop` and say so in the README. Final STATUS says **DONE** and points to `demo/index.html`.

## 10. Layout
```
~/ai-chip-lab/
  env.sh  env.json  budget.json  versions.lock  STATUS.md
  bin/  opt/                 # colima, docker CLI, lima (no brew)
  docker/lab-sim/Dockerfile  docker/smoke.sh  requirements.lock
  rtl/  tb/  formal/  eqy/   # Task 1
  orfs/designs/...           # Task 2 (+ systolic_os wrapper)
  model/  arch/              # Task 3
  sweeps/                    # sweep drivers
  results/  logs/
  demo/index.html  demo/run_demo.sh  demo/README.md  demo/assets/
  Makefile                   # make preflight runtime images t1 t2 t3 sweeps repro demo all
```
