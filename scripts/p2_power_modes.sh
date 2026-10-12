#!/bin/bash
# Runs INSIDE the pinned ORFS image (called by scripts/p2_power_activity.sh under the heavy-job lock).
# One openroad process per analysis (activity annotations accumulate within a process, so never reuse one):
#   vectorless                       ORFS default (input activity 0.1, duty 0.5) with our own load of the routed design
#   <wl>.window  / <wl>.whole        VCD of workload <wl>, restricted to the active window / whole file
#   random.window.repeat             determinism check (second identical analysis)
# VCD scope candidates are tried in order; the first for which read_vcd succeeds is used (recorded in the log).
set -u
source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1 || true
OUT=/lab/results/power_activity/raw; mkdir -p "$OUT"
run() {  # run <tag> <mode> [vcd scope t0 t1]
  local tag=$1; shift
  P2P_MODE=$1 P2P_VCD=${2:-} P2P_SCOPE=${3:-} P2P_T0=${4:-} P2P_T1=${5:-} \
    openroad -no_splash -exit /lab/scripts/p2_power.tcl > "$OUT/$tag.log" 2>&1
  return $?
}
run vectorless vectorless
for wl in random sparse50 allmax; do
  J=/lab/results/power_vcd/$wl.json
  T0=$(python3 -c "import json;print(json.load(open('$J'))['active_window_ps'][0]*1e-12)")
  T1=$(python3 -c "import json;print(json.load(open('$J'))['active_window_ps'][1]*1e-12)")
  for scope in TOP/systolic_os systolic_os; do
    run $wl.window vcd /lab/results/power_vcd/$wl.vcd $scope $T0 $T1 && grep -q "@@POWER-END" "$OUT/$wl.window.log" && { echo "$scope" > "$OUT/$wl.scope"; break; }
  done
  [ -f "$OUT/$wl.scope" ] || { echo "no usable VCD scope for $wl" >&2; continue; }
  run $wl.whole vcd /lab/results/power_vcd/$wl.vcd "$(cat $OUT/$wl.scope)"
done
[ -f "$OUT/random.scope" ] && run random.window.repeat vcd /lab/results/power_vcd/random.vcd "$(cat $OUT/random.scope)" \
  "$(python3 -c "import json;print(json.load(open('/lab/results/power_vcd/random.json'))['active_window_ps'][0]*1e-12)")" \
  "$(python3 -c "import json;print(json.load(open('/lab/results/power_vcd/random.json'))['active_window_ps'][1]*1e-12)")"
echo done
