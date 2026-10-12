#!/usr/bin/env bash
# Task 3 (stage 30_arch_model + 31_roofline_fix): SCALE-Sim vs analytic model + pre-registered roofline check.
#   scripts/t3_run.sh [OUTDIR]        default OUTDIR=results/t3   (relative to the lab / main checkout)
# Jobs (model/t3_stage.py list): bundled ws/os/is runs, analytic fit, superseded synthetic roofline, 3 CALC-mode
# + 6 USER-bandwidth (B=256 then 64) ResNet-18 runs (amended design P2-A2). Pass 2 re-runs only the cheap jobs (bundled ws/os/is + fit + CALC runs) for in-stage byte identity;
# the 12 roofline2 runs are compared by `make repro` (decision P2-6); summary says which files were compared where.  Env:
#   T3_SUMMARY=path   summary JSON (default results/t3_summary.json)     T3_PLOTS=1|0 (default 1)
#   T3_PASSES=1       single pass (quick/repro mode; identity then trivially true and flagged)
#   T3_LOCK=1         host mode: every job is its own container run under scripts/with_lock.sh (the CALLER must NOT
#                     hold the lock); default: one container, the caller is responsible for the lock.
#   T3_RESUME=1       keep OUTDIR.partial / OUTDIR.rerun.tmp from an interrupted run and skip finished jobs
set -euo pipefail
LAB="${LAB:-$HOME/ai-chip-lab}"
CHEAP="bundled_ws bundled_os bundled_is fit rl2_calc_ws rl2_calc_os rl2_calc_is"
JOBS="bundled_ws bundled_os bundled_is fit roofline_synthetic rl2_calc_ws rl2_calc_os rl2_calc_is rl2_user_ws_high rl2_user_os_high rl2_user_is_high rl2_user_ws_mid rl2_user_os_mid rl2_user_is_mid"
OUT_ARG="${1:-results/t3}"; SUMMARY="${T3_SUMMARY:-results/t3_summary.json}"
FINAL="$OUT_ARG"; OUT="${FINAL}.partial"; RERUN="${FINAL}.rerun.tmp"
if [ ! -f /.dockerenv ]; then
  source "$LAB/env.sh"; source "$LAB/coord/images.env"
  dk="$LAB/scripts/t3_dk.sh"
  if [ "${T3_LOCK:-0}" != "1" ]; then "$dk" bash scripts/t3_run.sh "$@"; exit $?; fi
  LK="$LAB/scripts/with_lock.sh arch"
  cd "$LAB"; mkdir -p logs/part2/31_roofline_fix
  if [ "${T3_RESUME:-0}" != "1" ]; then rm -rf "$OUT" "$RERUN"; fi
  for pass in 1 2; do
    [ "$pass" = 2 ] && [ "${T3_PASSES:-2}" -lt 2 ] && break
    D="$OUT"; JL="$JOBS"; [ "$pass" = 2 ] && { D="$RERUN"; JL="$CHEAP"; }
    for j in $JL; do
      if [ -e "$D/.jobs/$j.done" ]; then continue; fi
      # criterion-A (user-bandwidth) runs stop being started at the Phase 1 deadline (Decision P2-7); the summary reports them unfinished
      case "$j" in rl2_user_*) if [ "$(date +%s)" -ge "${T3_USER_DEADLINE:-$(python3 -c "import json;print(json.load(open('$LAB/budget_part2.json'))['deadline_phase1_epoch'])")}" ]; then echo "== skip $j (past Phase 1 deadline)"; continue; fi;; esac
      while [ ! -e "$D/.jobs/$j.done" ]; do
        echo "== t3 pass $pass job $j $(date +%T)"
        rc=0
        $LK "$dk" python3 model/t3_stage.py job "$j" --out "$D" >> "logs/part2/31_roofline_fix/pass${pass}_$j.log" 2>&1 || rc=$?
        # rc 75 = partial: the job used its time budget for this lock hold; call it again (lock released in between)
        if [ "$rc" != 0 ] && [ "$rc" != 75 ]; then
          echo "JOB FAILED: $j rc=$rc (see logs/part2/31_roofline_fix/pass${pass}_$j.log)"; tail -20 "logs/part2/31_roofline_fix/pass${pass}_$j.log"; exit 1
        fi
      done
    done
  done
  if [ "${T3_PASSES:-2}" -lt 2 ]; then rm -rf "$RERUN"; cp -r "$OUT" "$RERUN"; fi   # quick mode: identity trivially true
  $LK "$dk" bash -c "python3 model/t3_stage.py summary --out '$OUT' --rerun '$RERUN' --summary-json '$SUMMARY' && { [ \"\${T3_PLOTS:-1}\" != 1 ] || python3 model/t3_plots.py '$OUT' '$SUMMARY'; }"
  rm -rf "$RERUN"; rm -rf "$FINAL"; mv "$OUT" "$FINAL"
  exit 0
fi
# ---- inside the container (single-container mode) ----
cd /lab
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 MPLBACKEND=Agg
if [ "${T3_RESUME:-0}" != "1" ]; then rm -rf "$OUT" "$RERUN"; fi
mkdir -p logs/part2/31_roofline_fix
echo "== t3 pass 1 -> $OUT"
python3 model/t3_stage.py pass --out "$OUT" 2>&1 | tee logs/part2/31_roofline_fix/pass1.log
if [ "${T3_PASSES:-2}" -ge 2 ]; then
  echo "== t3 pass 2 (rerun) -> $RERUN"
  python3 model/t3_stage.py pass --only cheap --out "$RERUN" > logs/part2/31_roofline_fix/pass2.log 2>&1
else
  rm -rf "$RERUN"; cp -r "$OUT" "$RERUN"   # quick mode: identity trivially true; flagged in summary
fi
python3 model/t3_stage.py summary --out "$OUT" --rerun "$RERUN" --summary-json "$SUMMARY"
if [ "${T3_PLOTS:-1}" = "1" ] && [ -f model/t3_plots.py ]; then python3 model/t3_plots.py "$OUT" "$SUMMARY"; fi
rm -rf "$RERUN"
# publish only a fully finished run (set -e: any failure above leaves only *.partial, never a half-written $FINAL)
rm -rf "$FINAL"; mv "$OUT" "$FINAL"
