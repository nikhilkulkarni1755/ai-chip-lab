#!/bin/bash
# `make sweeps` (stage 40_sweeps): start both design-space sweeps exactly as their owners run them, then
# (by default) wait until both have stopped. Both drivers are resumable (JSONL keyed by parameters, existing
# keys skipped) and deadline-aware: they read budget.json:deadline_sweeps_stop_epoch and start no new point
# after it. If that deadline has already passed they exit at once without running anything.
#   A (arch): detached lab-sim container `arch-sweep` running sweeps/arch_sweep.py --workers 1 --timeout 1200
#             -> results/sweeps/arch.jsonl, log logs/40_sweeps/arch_sweep.log        (light: no heavy lock)
#   B (pnr):  host process sweeps/phys_sweep.py (nangate45/gcd, period x utilization, then bisection); every
#             point is one scripts/t2_run.sh ORFS run under the heavy-job lock
#             -> results/sweeps/phys.jsonl, log logs/40_sweeps/phys.log, pid results/sweeps/phys.pid
#             stop early: touch results/sweeps/phys.stop
# A sweep that is already running is left alone (never a second copy).
# Env: DRY_RUN=1          print the commands, start nothing
#      SWEEPS_DETACH=1    return right after starting instead of waiting
#      SWEEPS="A B"       which sweeps (default both)
#      ARCH_SWEEP_ARGS    default "--workers 1 --timeout 1200";  PHYS_SWEEP_ARGS default "" (driver defaults)
#      SWEEP_SYSTOLIC=1   after B's gcd grid, also run pnr's 3-point systolic_os slice (~30+ min per point)
set -u
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 2
source "$LAB/env.sh"; source "$LAB/coord/images.env"
mkdir -p logs/40_sweeps results/sweeps
DRY="${DRY_RUN:-0}"; SW="${SWEEPS:-A B}"
AARGS="${ARCH_SWEEP_ARGS:---workers 1 --timeout 1200}"; PARGS="${PHYS_SWEEP_ARGS:-}"
left=$(python3 -c 'import json,time;print(int(json.load(open("budget.json"))["deadline_sweeps_stop_epoch"]-time.time()))')
if [ "$left" -le 0 ]; then echo "sweeps: budget.json sweep deadline passed $(( -left / 60 )) min ago -> the drivers will start no new point (results so far are kept)"
else echo "sweeps: $(( left / 60 )) min until the sweep stop deadline in budget.json"; fi
a_running() { [ "$(docker inspect -f '{{.State.Running}}' arch-sweep 2>/dev/null)" = true ]; }
b_running() { p=$(cat results/sweeps/phys.pid 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && ps -p "$p" -o command= | grep -q phys_sweep; }
case " $SW " in *" A "*)
  if a_running; then echo "sweep A: container arch-sweep already running -> left alone"
  else
    ACMD="nice -n 10 python3 sweeps/arch_sweep.py $AARGS >> logs/40_sweeps/arch_sweep.log 2>&1"
    echo "+ docker rm -f arch-sweep; docker run -d --name arch-sweep --platform linux/amd64 -e PYTHONHASHSEED=0 -v \$LAB:/lab -w /lab $LAB_SIM_IMAGE bash -c '$ACMD'"
    if [ "$DRY" != 1 ]; then
      docker rm -f arch-sweep >/dev/null 2>&1
      docker run -d --name arch-sweep --platform linux/amd64 -e PYTHONHASHSEED=0 -v "$LAB:/lab" -w /lab "$LAB_SIM_IMAGE" bash -c "$ACMD" >/dev/null || exit 1
    fi
  fi ;; esac
case " $SW " in *" B "*)
  if b_running; then echo "sweep B: phys_sweep.py already running (pid $(cat results/sweeps/phys.pid)) -> left alone"
  elif [ -d coord/heavy.lock.d ] && grep -q phys_sweep <(ps -ax -o command= | grep -v grep); then echo "sweep B: another phys_sweep.py process is active (systolic slice) -> left alone"
  else
    echo "+ nohup python3 sweeps/phys_sweep.py $PARGS >> logs/40_sweeps/phys.log 2>&1 &"
    [ "${SWEEP_SYSTOLIC:-0}" = 1 ] && echo "+ then: python3 sweeps/phys_sweep.py --design systolic_os --periods 2.4,2.0,1.6 --utils 30 --timeout 3600 --max-points 3 >> logs/40_sweeps/phys.log 2>&1"
    if [ "$DRY" != 1 ]; then
      rm -f results/sweeps/phys.stop
      ( python3 sweeps/phys_sweep.py $PARGS >> logs/40_sweeps/phys.log 2>&1
        [ "${SWEEP_SYSTOLIC:-0}" = 1 ] && python3 sweeps/phys_sweep.py --design systolic_os --periods 2.4,2.0,1.6 --utils 30 --timeout 3600 --max-points 3 >> logs/40_sweeps/phys.log 2>&1 ) </dev/null >/dev/null 2>&1 &
      echo $! > logs/40_sweeps/phys_chain.pid
    fi
  fi ;; esac
[ "$DRY" = 1 ] && { echo "sweeps: dry run only, nothing started"; exit 0; }
[ "${SWEEPS_DETACH:-0}" = 1 ] && { echo "sweeps: started/detached; follow logs/40_sweeps/*.log"; exit 0; }
echo "sweeps: waiting for the drivers to stop (they stop themselves at the deadline)…"
while a_running || b_running || { [ -f logs/40_sweeps/phys_chain.pid ] && kill -0 "$(cat logs/40_sweeps/phys_chain.pid)" 2>/dev/null; }; do sleep 30; done
for f in results/sweeps/arch.jsonl results/sweeps/phys.jsonl; do [ -f "$f" ] && echo "sweeps: $(wc -l < "$f" | tr -d ' ') points in $f"; done
exit 0
