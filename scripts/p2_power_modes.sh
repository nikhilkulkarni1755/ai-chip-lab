#!/bin/bash
# Runs INSIDE the pinned ORFS image (called by scripts/p2_power_activity.sh under the heavy-job lock).
# One openroad process per analysis (activity annotations accumulate within a process, so never reuse one):
#   vectorless                       ORFS default (input activity 0.1, duty 0.5) with our own load of the routed design
#   <wl>.window  / <wl>.whole        VCD of workload <wl>, restricted to the active window / whole file
#   random.window.repeat             determinism check (second identical analysis)
# Usage: p2_power_modes.sh <step>   step = vectorless | random | sparse50 | allmax | repeat   (one lock hold per step)
# VCD scope: `systolic_os` (Icarus, per rtl's manifest) first, `TOP/systolic_os` (Verilator) as fallback; the one used is recorded in <wl>.scope.
set -u
source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1 || true
OUT=/lab/results/power_activity/raw; mkdir -p "$OUT"
run() {  # run <tag> <mode> [vcd scope t0 t1]
  local tag=$1; shift
  P2P_MODE=$1 P2P_VCD=${2:-} P2P_SCOPE=${3:-} P2P_T0=${4:-} P2P_T1=${5:-} \
    openroad -no_splash -exit /lab/scripts/p2_power.tcl > "$OUT/$tag.log" 2>&1
  return $?
}
STEP=${1:?step}
win() { python3 -c "import json;print(int(json.load(open('/lab/results/power_vcd/$1.json'))['active_window_ps'][$2]))"; }
wl_run() {  # wl_run <wl> <tag-suffix> <with-window 1|0> <scope-list...>
  local wl=$1 suf=$2 w=$3; shift 3
  for scope in "$@"; do
    if [ "$w" = 1 ]; then run $wl.$suf vcd /lab/results/power_vcd/$wl.vcd $scope "$(win $wl 0)" "$(win $wl 1)"
    else run $wl.$suf vcd /lab/results/power_vcd/$wl.vcd $scope; fi
    grep -q "@@POWER-END" "$OUT/$wl.$suf.log" && { echo "$scope" > "$OUT/$wl.scope"; return 0; }
  done
  return 1
}
case $STEP in
  vectorless) run vectorless vectorless ;;
  random|sparse50|allmax) wl_run $STEP window 1 systolic_os TOP/systolic_os && wl_run $STEP whole 0 "$(cat $OUT/$STEP.scope)" ;;
  repeat) wl_run random window.repeat 1 "$(cat $OUT/random.scope)" ;;
esac
echo "step $STEP done"
