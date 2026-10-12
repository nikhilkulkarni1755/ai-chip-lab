#!/bin/bash
# t2_check.sh -- ORFS's own threshold checker (flow/util/checkMetadata.py) against the design's shipped
# rules-base.json, run on existing outputs (metadata.json from a previous t2_run.sh).
# Usage: scripts/t2_check.sh <platform> <design> [variant=base]   -> exit 0 iff all rules pass
# Writes orfs/work/reports/<p>/<d>/<v>/t2_check.log. No heavy lock needed (a second of CPU).
set -u
LAB="$HOME/ai-chip-lab"; source "$LAB/env.sh"; source "$LAB/coord/images.env"
PLAT="$1"; DES="$2"; VAR="${3:-base}"
REP="orfs/work/reports/$PLAT/$DES/$VAR"
[ -f "$LAB/$REP/metadata.json" ] || { echo "no $REP/metadata.json (run scripts/t2_run.sh first)"; exit 2; }
FLOW=/OpenROAD-flow-scripts/flow
docker run --rm --platform linux/amd64 -v "$LAB:/lab" -w "$FLOW" "$ORFS_IMAGE" \
  python3 util/checkMetadata.py -m "/lab/$REP/metadata.json" -r "designs/$PLAT/$DES/rules-base.json" 2>&1 \
  | tee "$LAB/$REP/t2_check.log"
exit ${PIPESTATUS[0]}
