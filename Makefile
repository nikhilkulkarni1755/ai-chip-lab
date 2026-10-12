# AI-chip lab — top-level entry points.  make preflight runtime images t1 t2 t3 sweeps repro demo all
# Append-by-section: each agent owns the recipe of its own target(s) and edits only that section.
# Every recipe runs from the repo root and sources env.sh itself (scripts do `source ~/ai-chip-lab/env.sh`).
# Cheap/safe to try: make preflight, make smoke, DRY_RUN=1 make t2 t2-stretch sweeps, make -n all.
SHELL := /bin/bash
.PHONY: preflight runtime images t1 t2 t2-stretch t3 sweeps repro demo all smoke
STAGES := results/.stages

# `make all` runs every stage in order. A stage that fails (including an honest scientific FAIL verdict)
# does not stop the later independent stages, and the demo is always built; exit status is non-zero if
# any stage failed. Heavy stages wait for the heavy-job lock. DRY_RUN=1 make all prints the t2/sweeps
# commands instead of running them (t1, t3, repro have no dry-run mode and are skipped then).
all:
	@failed=""; for t in preflight runtime images t1 t2 t3 sweeps repro demo; do \
	  if [ "$${DRY_RUN:-0}" = 1 ] && case $$t in t1|t3|repro|runtime|images) true;; *) false;; esac; then echo "== make $$t: skipped in DRY_RUN (no dry-run mode)"; continue; fi; \
	  echo "== make $$t"; $(MAKE) --no-print-directory $$t || failed="$$failed $$t"; \
	done; \
	if [ -n "$$failed" ]; then echo "make all: stages that failed:$$failed"; exit 1; else echo "make all: every stage passed"; fi

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

# ---- pnr: 20_pnr_ref (Task 2) -----------------------------------------------------------------
# t2: nangate45/gcd and sky130hd/gcd, each twice from clean, threshold check, extract, render, summary.
#     ~35 min of ORFS under the heavy-job lock; DELETES and regenerates the previous reference outputs.
# t2-stretch: systolic_os 4x4 on nangate45 (~30 min more), kept separate so `make t2` stays the baseline.
# DRY_RUN=1 make t2 prints the exact command sequence (scripts/make_t2.sh).
t2:
	scripts/make_t2.sh ref

t2-stretch:
	scripts/make_t2.sh stretch

# ---- arch: 30_arch_model (Task 3) -------------------------------------------------------------
# Two full SCALE-Sim passes (ws/os/is) + fit + roofline in lab-sim, ~15-20 min, light (no heavy lock).
# Rewrites results/t3/ and results/t3_summary.json; T3_PASSES=1 skips the rerun, T3_PLOTS=0 skips plots,
# T3_OUT/T3_SUMMARY redirect the outputs. The target fails if the run breaks OR if the summary's
# scientific verdict "pass" is false (the verdict and per-check booleans are printed).
t3:
	scripts/t3_run.sh $(or $(T3_OUT),results/t3)
	@python3 -c 'import json,os;s=json.load(open(os.environ.get("T3_SUMMARY") or "results/t3_summary.json"));print("t3: pass =",s["pass"],s.get("checks"));raise SystemExit(0 if s["pass"] else 1)'

# ---- arch + pnr: 40_sweeps ---------------------------------------------------------------------
# Starts sweep A (detached lab-sim container) and sweep B (ORFS, heavy-job lock), both resumable and
# stopping themselves at budget.json:deadline_sweeps_stop_epoch, then waits for them. Never starts a
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
