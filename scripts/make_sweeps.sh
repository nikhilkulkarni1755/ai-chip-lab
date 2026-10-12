#!/bin/bash
# `make sweeps`: start both design-space sweep drivers, then (by default) wait until both have stopped.
# Part 2 rules this wrapper enforces:
#   * every sweep POINT takes the heavy-job lock by itself with LOCK_PRIO=low (exported here, inherited by
#     scripts/with_lock.sh inside the drivers), so stage work is never starved and no container outlives
#     its point. The Part 1 way of running sweep A (one long-lived detached container `arch-sweep`) is
#     therefore refused: it would hold the VM for hours outside the lock.
#   * the stop deadline is budget_part2.json:deadline_sweeps_stop_epoch (LAB_BUDGET, exported). budget.json
#     is Part 1's frozen record. A driver that still reads budget.json itself is not started.
#   * both drivers are resumable (JSONL keyed by parameters); a driver that is already running is left alone.
#   A (arch): python3 sweeps/arch_sweep.py $ARCH_SWEEP_ARGS      -> results/sweeps/arch.jsonl, logs/part2/41_sweeps_finish/arch_sweep.log
#   B (pnr):  python3 sweeps/phys_sweep.py $PHYS_SWEEP_ARGS      -> results/sweeps/phys.jsonl, logs/part2/41_sweeps_finish/phys.log
#             (pid in results/sweeps/phys.pid; stop early: touch results/sweeps/phys.stop)
# Env: DRY_RUN=1 print only | SWEEPS_DETACH=1 do not wait | SWEEPS="A B" | ARCH_SWEEP_ARGS | PHYS_SWEEP_ARGS
set -u
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 2
source "$LAB/env.sh"
export LOCK_PRIO=low LAB_BUDGET="${LAB_BUDGET:-$LAB/budget_part2.json}"
LOGD=logs/part2/41_sweeps_finish; mkdir -p "$LOGD" results/sweeps
DRY="${DRY_RUN:-0}"; SW="${SWEEPS:-A B}"; AARGS="${ARCH_SWEEP_ARGS:-}"; PARGS="${PHYS_SWEEP_ARGS:-}"
left=$(python3 -c 'import json,os,time;print(int(json.load(open(os.environ["LAB_BUDGET"]))["deadline_sweeps_stop_epoch"]-time.time()))')
if [ "$left" -le 0 ]; then echo "sweeps: the sweep deadline in $(basename "$LAB_BUDGET") passed $(( -left / 60 )) min ago -> drivers start no new point (results so far are kept)"
else echo "sweeps: $(( left / 60 )) min until the sweep stop deadline in $(basename "$LAB_BUDGET")"; fi
reads_part2() { grep -q -E 'budget_part2|LAB_BUDGET' "$1"; }
locks_points() { grep -q 'with_lock' "$1"; }
pid_running() { p=$(cat "$1" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null && ps -p "$p" -o command= | grep -q "$2"; }
a_running() { pid_running results/sweeps/arch.pid arch_sweep || pgrep -f 'sweeps/arch_sweep.py' >/dev/null; }
b_running() { pid_running results/sweeps/phys.pid phys_sweep || pgrep -f 'sweeps/phys_sweep.py' >/dev/null; }
rc=0
start() {  # start <A|B> <driver.py> <args> <log> <pidfile>
  echo "+ LOCK_PRIO=low LAB_BUDGET=$(basename "$LAB_BUDGET") nohup python3 $2 $3 >> $4 2>&1 &"
  [ "$DRY" = 1 ] && return 0
  nohup python3 "$2" $3 >> "$4" 2>&1 </dev/null &
  echo $! > "$5.launcher"
}
case " $SW " in *" A "*)
  if a_running; then echo "sweep A: arch_sweep.py already running -> left alone"
  elif ! locks_points sweeps/arch_sweep.py; then echo "sweep A: NOT started — sweeps/arch_sweep.py does not take scripts/with_lock.sh per point yet (Part 2 rule; owner: arch)"; rc=1
  elif ! reads_part2 sweeps/arch_sweep.py; then echo "sweep A: NOT started — sweeps/arch_sweep.py does not read budget_part2.json / \$LAB_BUDGET yet (owner: arch)"; rc=1
  else start A sweeps/arch_sweep.py "$AARGS" "$LOGD/arch_sweep.log" results/sweeps/arch.pid; fi ;; esac
case " $SW " in *" B "*)
  if b_running; then echo "sweep B: phys_sweep.py already running -> left alone"
  elif ! reads_part2 sweeps/phys_sweep.py; then echo "sweep B: NOT started — sweeps/phys_sweep.py does not read budget_part2.json / \$LAB_BUDGET yet (owner: pnr)"; rc=1
  else [ "$DRY" = 1 ] || rm -f results/sweeps/phys.stop; start B sweeps/phys_sweep.py "$PARGS" "$LOGD/phys.log" results/sweeps/phys.pid; fi ;; esac
[ "$DRY" = 1 ] && { echo "sweeps: dry run only, nothing started"; exit $rc; }
[ "${SWEEPS_DETACH:-0}" = 1 ] && { echo "sweeps: started/detached; follow $LOGD/*.log and scripts/queue.sh"; exit $rc; }
echo "sweeps: waiting for the drivers to stop (they stop themselves at the deadline)…"
sleep 5; while a_running || b_running; do sleep 30; done
for f in results/sweeps/arch.jsonl results/sweeps/phys.jsonl; do [ -f "$f" ] && echo "sweeps: $(wc -l < "$f" | tr -d ' ') points in $f"; done
exit $rc
