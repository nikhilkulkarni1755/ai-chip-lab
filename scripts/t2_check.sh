#!/bin/bash
# t2_check.sh -- ORFS's own threshold checker (flow/util/checkMetadata.py, run from the pinned image) against the
# design's shipped rules-base.json (which lives inside the image).
# Usage: scripts/t2_check.sh <platform> <design> [variant=base]   -> exit 0 iff all rules pass
# Metadata source: orfs/work/reports/<p>/<d>/<v>/metadata.json (from t2_run.sh); if that is absent (fresh clone, or
# T2_USE_COMMITTED=1 to force it) the committed copy results/t2/metadata_<p>_<d>.json (variant base) is used.
# Writes orfs/work/.../t2_check.log when using the work copy. No heavy lock needed.
set -u
LAB="$HOME/ai-chip-lab"; source "$LAB/env.sh"; source "$LAB/coord/images.env"
PLAT="$1"; DES="$2"; VAR="${3:-base}"
REP="orfs/work/reports/$PLAT/$DES/$VAR"; COMMITTED="results/t2/metadata_${PLAT}_${DES}.json"
if [ -f "$LAB/$REP/metadata.json" ] && [ "${T2_USE_COMMITTED:-0}" != 1 ]; then
  MD="$REP/metadata.json"; LOG="$LAB/$REP/t2_check.log"; echo "[t2_check] metadata: $MD"
elif [ "$VAR" = base ] && [ -f "$LAB/$COMMITTED" ]; then
  MD="$COMMITTED"; LOG=/dev/null; echo "[t2_check] metadata: committed copy $COMMITTED (no orfs/work outputs)"
else
  echo "no $REP/metadata.json and no committed copy (run scripts/t2_run.sh first)"; exit 2
fi
FLOW=/OpenROAD-flow-scripts/flow
docker run --rm --platform linux/amd64 -v "$LAB:/lab" -w "$FLOW" "$ORFS_IMAGE" \
  python3 util/checkMetadata.py -m "/lab/$MD" -r "designs/$PLAT/$DES/rules-base.json" 2>&1 | tee "$LOG"
exit ${PIPESTATUS[0]}
