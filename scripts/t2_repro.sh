#!/bin/bash
# t2_repro.sh <platform> <design> [variant=base] -- fresh clean ORFS run (through the lock), then compare against all
# earlier runs (Part 1 snapshot). This is what `make t2` / `make t2-stretch` call (Decision P2-1), so nothing runs twice.
# Reference designs: stock config; systolic_os: orfs/designs/nangate45/systolic_os (4.0 ns, CORE_UTILIZATION 30).
set -u
LAB="$HOME/ai-chip-lab"; source "$LAB/env.sh"
PLAT="$1"; DES="$2"; VAR="${3:-base}"
mkdir -p "$LAB/logs/part2/51_repro_full"
"$LAB/scripts/t2_run.sh" "$PLAT" "$DES" "$VAR" || exit $?
"$LAB/.venv-pnr/bin/python" "$LAB/scripts/t2_repro_compare.py" "$PLAT" "$DES" "$VAR"
