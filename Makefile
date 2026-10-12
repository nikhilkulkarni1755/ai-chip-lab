# AI-chip lab — top-level entry points.  make preflight runtime images t1 t2 t3 sweeps repro demo all
# Append-by-section: each agent owns the recipe of its own target(s) and edits only that section.
# Every recipe runs from the repo root and sources env.sh itself (scripts do `source ~/ai-chip-lab/env.sh`).
# Cheap/safe to try: make preflight, make smoke, DRY_RUN=1 make t2 t2-stretch sweeps, make -n all.
SHELL := /bin/bash
.PHONY: preflight runtime images t1 t1-routed t2 t2-stretch t3 sweeps repro demo all smoke failsoft-test
STAGES := results/.stages

# `make all` (scripts/make_all.py) runs every stage in order: preflight runtime images t1 t2 t2-stretch t1-routed t3
# sweeps repro demo. Fail-soft: a failing stage (including an honest scientific FAIL verdict) never stops the later ones,
# the demo is ALWAYS built last, and the exit status is non-zero with the failed stages listed.
#   make all            real run of everything          RESUME=1 make all   skip stages whose git-tracked inputs
#   FORCE=1 make all    rerun everything                                    (scripts/stage_inputs.json) are unchanged
#   DRY_RUN=1 make all  print what has a dry mode                           since they last succeeded; skips are logged
# Per-stage outcome of the last run: results/make_all_last.json. Fail-soft self-test: scripts/make_all_failsoft_test.sh.
# Only container steps take the heavy-job lock (inside the stage scripts); a recipe is never wrapped in one lock.
all:
	@MAKE="$(MAKE)" python3 scripts/make_all.py

# ---- main: 00_preflight ---------------------------------------------------------------------
preflight:
	scripts/preflight.sh

# ---- infra: 01_runtime (Lima + Colima + Docker CLI, no brew / no sudo) ------------------------
runtime:
	@if [ ! -x bin/colima ] || [ ! -x bin/docker ] || [ ! -x opt/lima/bin/limactl ]; then scripts/infra_runtime_install.sh; fi
	scripts/infra_runtime_start.sh

# ---- infra: 02_images (pull pinned ORFS, build lab-sim, smoke test, record versions) ----------
images: runtime
	scripts/infra_images.sh

smoke:
	docker/smoke.sh

# ---- rtl: 10_rtl_verify (Task 1) --------------------------------------------------------------
t1:
	scripts/t1_run.sh $(or $(T1_CASES),10000) $(or $(T1_OUT),results)

# ---- rtl: 11_eqy_routed (EQY against the routed nangate45 netlist + gate-level simulation) -----
# Takes its own lock per step; T1R_RESUME=1 continues a partly finished run; T1R_STEPS=gls = simulation only.
t1-routed:
	scripts/t1_routed.sh $(or $(T1R_CASES),200) $(or $(T1R_OUT),results)

# ---- pnr: 20_pnr_ref (Task 2) -----------------------------------------------------------------
# t2: nangate45/gcd and sky130hd/gcd: one clean ORFS run each via pnr's scripts/t2_repro.sh (compared against all
#     earlier runs; two runs if no earlier run exists or T2_FRESH=1), threshold check, extract, render, summary.
#     Each ORFS run takes the heavy-job lock by itself and REPLACES orfs/work/.../base of that design.
# t2-stretch: systolic_os 4x4 on nangate45 (~30 min), kept separate so `make t2` stays the baseline.
# DRY_RUN=1 make t2 prints the exact command sequence (scripts/make_t2.sh).
t2:
	scripts/make_t2.sh ref

t2-stretch:
	scripts/make_t2.sh stretch

# ---- arch: 30_arch_model (Task 3) -------------------------------------------------------------
# Job-based (model/t3_stage.py job <name>): every job is its own lab-sim container under the heavy-job lock
# (T3_LOCK=1), so other work interleaves; resumable (T3_RESUME=1, default here): jobs already finished in
# OUT.partial are kept, not rerun. T3_RESUME=0 make t3 starts from scratch. T3_PASSES/T3_PLOTS/T3_OUT/T3_SUMMARY
# as documented in scripts/t3_run.sh. The target fails if the run breaks OR if the summary's verdict "pass" is
# false (verdict, state and per-check booleans are printed) — it exits 0 only on a legitimate pass.
t3:
	T3_LOCK=1 T3_RESUME=$(or $(T3_RESUME),1) scripts/t3_run.sh $(or $(T3_OUT),results/t3)
	@python3 -c 'import json,os;s=json.load(open(os.environ.get("T3_SUMMARY") or "results/t3_summary.json"));print("t3: pass =",s["pass"],"| state =",s.get("state","-"),"|",s.get("checks"));raise SystemExit(0 if s["pass"] is True else 1)'

# ---- arch + pnr: 40_sweeps ---------------------------------------------------------------------
# Starts the two sweep drivers as host processes (every point takes the lock itself at LOCK_PRIO=low), both
# resumable and stopping at budget_part2.json:deadline_sweeps_stop_epoch, then waits for them. Never starts a
# second copy of a running sweep. DRY_RUN=1 prints the commands; SWEEPS_DETACH=1 does not wait.
sweeps:
	scripts/make_sweeps.sh

# ---- demo: 50_repro / 60_demo -----------------------------------------------------------------
repro:
	scripts/repro.sh

demo:
	@if [ -x .venv-arch/bin/python ]; then .venv-arch/bin/python sweeps/arch_plots.py || true; fi
	@if [ -x .venv-pnr/bin/python ]; then .venv-pnr/bin/python sweeps/phys_plots.py || true; fi
	python3 scripts/demo_build.py
	@if [ -x .venv-demo/bin/python ]; then .venv-demo/bin/python scripts/evidence_render.py && python3 scripts/demo_build.py; else echo "evidence PNGs not re-rendered: no .venv-demo (uv venv .venv-demo && uv pip install pillow)"; fi
	python3 scripts/demo_check.py
	@echo "demo: open demo/index.html ; 5-minute cut: bash demo/run_demo.sh"

# ---- infra: self-test of `make all` (forces one cheap stage to fail, resumes the rest, restores) --------
failsoft-test:
	scripts/make_all_failsoft_test.sh
