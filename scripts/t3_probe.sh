#!/usr/bin/env bash
# P2-8 probe: wait for `make t3` (t3_run.sh) to end, then run exactly ONE criterion-A lock hold (rl2_user_ws_high).
set -u
LAB="${LAB:-$HOME/ai-chip-lab}"; cd "$LAB" || exit 2; source "$LAB/env.sh"
L="$LAB/coord/t3_probe.lock.d"; mkdir "$L" 2>/dev/null || { echo "probe already started"; exit 0; }
while pgrep -f "scripts/t3_run.sh" >/dev/null; do sleep 20; done
mkdir -p logs/part2/31_roofline_fix
T3_HOLD_BUDGET_S=480 "$LAB/scripts/with_lock.sh" arch "$LAB/scripts/t3_dk.sh" python3 model/t3_stage.py job rl2_user_ws_high --out results/t3 >> logs/part2/31_roofline_fix/probe_rl2_user_ws_high.log 2>&1
echo "rc=$? $(date +%T)" >> logs/part2/31_roofline_fix/probe_rl2_user_ws_high.log
