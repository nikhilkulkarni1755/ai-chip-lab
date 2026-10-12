#!/usr/bin/env bash
# repro.sh (stage 50_repro) - rerun Tasks 1 and 3 from a clean output directory with the pinned images and
# compare with the first (official) run -> results/repro_report.json (identical/different per check).
# Task 2 is NOT re-run a third time: pnr's t2_summary.json already holds a two-run-from-clean determinism
# verdict with the same image digest and core count; it is reused (set REPRO_T2=1 only to force a note, not a run).
#   scripts/repro.sh [--dry]      env: REPRO_NCASES (default 10000, must equal the first run)
# Run from the main checkout, after the official Task 1 and Task 3 runs are .done. Takes the heavy lock around
# each stage so it never overlaps ORFS jobs.
set -u
LAB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LAB" || exit 2
source ./env.sh >/dev/null 2>&1
RUN=".cache/repro_run"
N="${REPRO_NCASES:-10000}"
DRY=0; [ "${1:-}" = "--dry" ] && DRY=1
S=results/.stages
say() { echo "$(date +%H:%M:%S) repro: $*" | tee -a logs/run.log; }
if [ $DRY = 1 ]; then
  echo "would run: with_lock.sh demo scripts/t1_run.sh $N $RUN/t1"
  echo "would run: with_lock.sh demo env T3_PASSES=2 T3_PLOTS=0 T3_SUMMARY=$RUN/t3_summary.json scripts/t3_run.sh $RUN/t3"
  echo "would run: python3 scripts/repro_compare.py --lab $LAB --run $RUN"
  exit 0
fi
for st in 10_rtl_verify 30_arch_model; do
  [ -f "$S/$st.done" ] || { echo "first run of $st is not .done yet; refusing to start repro"; exit 4; }
done
rm -rf "$RUN"; mkdir -p "$RUN" logs/50_repro; rm -f "$S/50_repro.done" "$S/50_repro.failed"; : > "$S/50_repro.running"
say "started (N=$N)"
rc=0
scripts/with_lock.sh demo bash scripts/t1_run.sh "$N" "$RUN/t1" > logs/50_repro/t1.log 2>&1; say "t1 rerun rc=$?"
scripts/with_lock.sh demo env T3_PASSES=2 T3_PLOTS=0 T3_SUMMARY="$RUN/t3_summary.json" bash scripts/t3_run.sh "$RUN/t3" > logs/50_repro/t3.log 2>&1; say "t3 rerun rc=$?"
python3 scripts/repro_compare.py --lab "$LAB" --run "$RUN" | tee logs/50_repro/compare.log; rc=${PIPESTATUS[0]}
rm -f "$S/50_repro.running"
if [ -f results/repro_report.json ]; then
  echo "report written; pass=$(python3 -c "import json;print(json.load(open('results/repro_report.json'))['pass'])")" > "$S/50_repro.done"
else
  { echo "repro_report.json not produced"; tail -50 logs/50_repro/compare.log; } > "$S/50_repro.failed"
fi
say "finished compare rc=$rc"
exit $rc
