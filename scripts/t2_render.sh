#!/bin/bash
# t2_render.sh <platform> <design> [variant=base] [out.png]  -- GDS -> PNG with KLayout (-zz) in the ORFS image.
set -u
LAB="$HOME/ai-chip-lab"; source "$LAB/env.sh"; source "$LAB/coord/images.env"
PLAT="$1"; DES="$2"; VAR="${3:-base}"; OUT="${4:-demo/assets/t2_${PLAT}_${DES}.png}"
GDS="orfs/work/results/$PLAT/$DES/$VAR/6_final.gds"
[ -f "$LAB/$GDS" ] || { echo "missing $GDS"; exit 2; }
mkdir -p "$LAB/$(dirname "$OUT")"
case "$PLAT" in nangate45) LYP=FreePDK45.lyp;; sky130hd) LYP=sky130hd.lyp;; *) LYP=;; esac
FLOW=/OpenROAD-flow-scripts/flow
docker run --rm --platform linux/amd64 -v "$LAB:/lab" -w "$FLOW" "$ORFS_IMAGE" bash -c '
  [ -f /OpenROAD-flow-scripts/env.sh ] && source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1
  K=$(command -v klayout || ls /OpenROAD-flow-scripts/tools/install/*/bin/klayout 2>/dev/null | head -1)
  QT_QPA_PLATFORM=offscreen "$K" -zz -r /lab/orfs/render.py -rd gds=/lab/'"$GDS"' -rd lyp='"/OpenROAD-flow-scripts/flow/platforms/$PLAT/$LYP"' -rd out=/lab/'"$OUT"
