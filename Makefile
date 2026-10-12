# AI-chip lab — top-level entry points.  make preflight runtime images t1 t2 t3 sweeps repro demo all
# Append-by-section: each agent owns the recipe of its own target(s) and edits only that section.
# Every recipe runs from the repo root and sources env.sh itself (scripts do `source ~/ai-chip-lab/env.sh`).
SHELL := /bin/bash
.ONESHELL:
.PHONY: preflight runtime images t1 t2 t3 sweeps repro demo all smoke
STAGES := results/.stages

all: preflight runtime images t1 t2 t3 sweeps repro demo

# ---- main: 00_preflight ---------------------------------------------------------------------
preflight:
	@test -f $(STAGES)/00_preflight.done && echo "preflight: done" || { echo "preflight marker missing (owner: main)"; exit 1; }

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
	@echo "t1: recipe owned by the rtl agent (scripts/t1_*)"; exit 1

# ---- pnr: 20_pnr_ref (Task 2) -----------------------------------------------------------------
t2:
	@echo "t2: recipe owned by the pnr agent (scripts/t2_*)"; exit 1

# ---- arch: 30_arch_model (Task 3) -------------------------------------------------------------
t3:
	@echo "t3: recipe owned by the arch agent (scripts/t3_*)"; exit 1

# ---- arch + pnr: 40_sweeps ---------------------------------------------------------------------
sweeps:
	@echo "sweeps: recipe owned by the arch and pnr agents"; exit 1

# ---- demo: 50_repro / 60_demo -----------------------------------------------------------------
repro:
	@echo "repro: recipe owned by the demo agent (scripts/repro*)"; exit 1

demo:
	@echo "demo: recipe owned by the demo agent"; exit 1
