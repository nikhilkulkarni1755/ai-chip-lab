#!/bin/bash
# `make t2` / `make t2-stretch`: Task 2 (stage 20_pnr_ref) end to end, the way the pnr agent ran it by hand.
#   scripts/make_t2.sh ref       nangate45/gcd and sky130hd/gcd, each TWICE from clean, then checks + summary
#   scripts/make_t2.sh stretch   nangate45/systolic_os once (the Task 1 array as an ORFS design), then summary
# Per reference design (pnr's convention, read by scripts/t2_summary.py):
#   t2_run.sh <p> <d> base            first clean run
#   move orfs/work/{logs,reports,results}/<p>/<d>/base -> .../run1
#   t2_run.sh <p> <d> base            second clean run (same image digest, same NUM_CORES)
#   t2_check.sh <p> <d> base          ORFS's own checkMetadata.py against the shipped rules-base.json
#   t2_extract.py <p> <d> base        metrics -> results/t2/<p>_<d>_base.json
#   t2_render.sh <p> <d> base         GDS -> demo/assets/t2_<p>_<d>.png (KLayout in the ORFS image)
# then t2_summary.py -> results/t2_summary.json (pass = nangate45/gcd gates; sky130hd and stretch recorded).
# Each ORFS run takes the heavy-job lock inside t2_run.sh (it WAITS if a sweep holds it) and DELETES the
# previous outputs of that design/variant. Rough cost on this machine: gcd ng45 2x5 min, sky130hd 2x12 min,
# systolic_os ~30 min.
# Env: DRY_RUN=1 prints the commands without running anything. T2_DESIGNS="nangate45/gcd sky130hd/gcd" (ref only).
set -u
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 2
MODE="${1:-ref}"
PY=python3; [ -x .venv-pnr/bin/python ] && PY=.venv-pnr/bin/python
run() { echo "+ $*"; [ "${DRY_RUN:-0}" = 1 ] && return 0; "$@"; }
# helpers that start a container themselves run under the heavy-job lock (it is re-entrant, so this stays
# correct when the helper also takes it); t2_run.sh takes the lock itself, per ORFS run.
LK="scripts/with_lock.sh infra"
W=orfs/work; rc=0
case "$MODE" in
  ref)
    for pd in ${T2_DESIGNS:-nangate45/gcd sky130hd/gcd}; do
      P=${pd%/*}; D=${pd#*/}
      run scripts/t2_run.sh "$P" "$D" base || { echo "t2: first run of $pd failed"; rc=1; continue; }
      for d in logs reports results; do
        run rm -rf "$W/$d/$P/$D/run1"; run mv "$W/$d/$P/$D/base" "$W/$d/$P/$D/run1"
      done
      run scripts/t2_run.sh "$P" "$D" base || { echo "t2: second run of $pd failed"; rc=1; continue; }
      run $LK scripts/t2_check.sh "$P" "$D" base || { echo "t2: $pd violates shipped thresholds (recorded in the summary)"; rc=1; }
      if [ "${DRY_RUN:-0}" = 1 ]; then echo "+ $PY scripts/t2_extract.py $P $D base > /dev/null"; else $PY scripts/t2_extract.py "$P" "$D" base > /dev/null || rc=1; fi
      run $LK scripts/t2_render.sh "$P" "$D" base || rc=1
    done ;;
  stretch)
    run scripts/t2_run.sh nangate45 systolic_os base || rc=1
    if [ "${DRY_RUN:-0}" = 1 ]; then echo "+ $PY scripts/t2_extract.py nangate45 systolic_os base > /dev/null"; else $PY scripts/t2_extract.py nangate45 systolic_os base > /dev/null || rc=1; fi
    run $LK scripts/t2_render.sh nangate45 systolic_os base demo/assets/t2_nangate45_systolic_os.png || rc=1 ;;
  *) echo "usage: $0 ref|stretch"; exit 2 ;;
esac
run $LK $PY scripts/t2_summary.py || rc=1
[ "${DRY_RUN:-0}" = 1 ] && { echo "t2 ($MODE): dry run only, nothing executed"; exit 0; }
verdict=$(python3 -c 'import json;print(json.load(open("results/t2_summary.json")).get("pass"))' 2>/dev/null)
echo "t2 ($MODE): results/t2_summary.json pass=$verdict (flow/check exit status: $rc)"
if [ "$MODE" = ref ]; then
  S=results/.stages/20_pnr_ref
  if ls $S.done $S.failed >/dev/null 2>&1; then echo "t2: existing stage marker left untouched ($(ls $S.* | tr '\n' ' '))"
  elif [ "$verdict" = True ] && [ $rc = 0 ]; then : > $S.done
  else echo "make t2: pass=$verdict rc=$rc; see results/t2_summary.json and logs/20_pnr_ref/" > $S.failed; fi
  [ "$verdict" = True ] && [ $rc = 0 ]; exit $?
fi
exit $rc
