#!/usr/bin/env bash
# Task 3 (stage 30_arch_model): SCALE-Sim (bundled TPU-like config, bundled topology, ws/os/is)
# vs analytic model + roofline.  Runs inside the lab-sim container; two full passes; byte-identity check.
#   scripts/t3_run.sh [OUTDIR]        default OUTDIR=results/t3   (relative to the lab / main checkout)
#   env: T3_SUMMARY=path   summary JSON (default results/t3_summary.json); T3_PLOTS=1|0 (default 1)
#        T3_PASSES=1 skips the rerun (demo quick mode; then reruns_byte_identical is not evaluated)
set -euo pipefail
LAB="${LAB:-$HOME/ai-chip-lab}"
if [ ! -f /.dockerenv ]; then
  # host: re-exec inside the container
  source "$LAB/env.sh"; source "$LAB/coord/images.env"
  exec docker run --rm --platform linux/amd64 -e PYTHONHASHSEED=0 -e T3_SUMMARY -e T3_PLOTS -e T3_PASSES \
    -v "$LAB":/lab -w /lab "$LAB_SIM_IMAGE" bash scripts/t3_run.sh "$@"
fi
cd /lab
export PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 MPLBACKEND=Agg
OUT="${1:-results/t3}"; SUMMARY="${T3_SUMMARY:-results/t3_summary.json}"
RERUN="${OUT}.rerun.tmp"
rm -rf "$OUT" "$RERUN"; mkdir -p logs/30_arch_model
echo "== t3 pass 1 -> $OUT"
python3 model/t3_stage.py pass --out "$OUT" 2>&1 | tee logs/30_arch_model/pass1.log
if [ "${T3_PASSES:-2}" -ge 2 ]; then
  echo "== t3 pass 2 (rerun) -> $RERUN"
  python3 model/t3_stage.py pass --out "$RERUN" > logs/30_arch_model/pass2.log 2>&1
else
  cp -r "$OUT" "$RERUN"   # quick mode: identity trivially true; flagged in summary
fi
python3 model/t3_stage.py summary --out "$OUT" --rerun "$RERUN" --summary-json "$SUMMARY"
if [ "${T3_PLOTS:-1}" = "1" ] && [ -f model/t3_plots.py ]; then python3 model/t3_plots.py "$OUT" "$SUMMARY"; fi
rm -rf "$RERUN"
