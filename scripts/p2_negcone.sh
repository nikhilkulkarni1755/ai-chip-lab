#!/usr/bin/env bash
# Stage 11_eqy_routed, extra negative control (reviewer caveat): a bug INSIDE a per-PE cone
# of the routed NETLIST.  One standard cell in the fan-in of PE(0,0)'s accumulator is replaced
# by a pin-compatible cell with a different function (scripts/p2_negcone.py mutate); EQY then
# checks only that PE's partition (systolic_os.acc_o.0) with the same template and engine as
# the proof.  One lock hold, at most 9 minutes; no result within the hold is recorded as such.
#
#   scripts/p2_negcone.sh          -> results/p2_11_negcone.json, work in .cache/rtl_negcone
#
# Reads (never writes) the stage's inputs: the routed netlist snapshot, the Liberty copy in
# results/t1_routed_work/cells and eqy/systolic_os_routed.eqy.in.
set -u -o pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; LAB_DIR="$(cd "$SELF_DIR/.." && pwd)"
W=.cache/rtl_negcone
PART=systolic_os.acc_o.0
if [ -z "${NEGCONE_INSIDE:-}" ]; then
  cd "$LAB_DIR" || exit 2
  # shellcheck disable=SC1091
  source ./env.sh; source coord/images.env
  LOCK=(); [ "${LAB_LOCK_HELD:-0}" = 1 ] || LOCK=(bash scripts/with_lock.sh rtl env LAB_LOCK_HELD=1)
  mkdir -p "$W"
  ${LOCK[@]+"${LOCK[@]}"} docker run --rm --platform linux/amd64 --cpus 2 -v "$LAB_DIR":/lab -w /lab \
    -e NEGCONE_INSIDE=1 -e PYTHONHASHSEED=0 "$LAB_SIM_IMAGE" bash scripts/p2_negcone.sh
  exit $?
fi
cd "$LAB_DIR" || exit 2
NET=results/part1_snapshot/systolic_os_routed/6_final.v
LIB="$LAB_DIR/results/t1_routed_work/cells/NangateOpenCellLibrary_typical.lib"
[ -s "$LIB" ] || { echo "Liberty copy missing: $LIB" >&2; exit 3; }
D="$LAB_DIR/$W/run"
mkdir -p "$D"
python3 scripts/p2_negcone.py mutate "$NET" "$D/netlist_cone_bug.v" "$D/mutation.json" 5 || exit 90
sed -e "s#@RTL@#$LAB_DIR/rtl#g" -e "s#@LIB@#$LIB#g" -e "s#@NETLIST@#$D/netlist_cone_bug.v#g" \
  eqy/systolic_os_routed.eqy.in > "$D/routed.eqy"
printf 'apply %s\n\n[strategy skip]\nuse dummy\n' "$PART" >> "$D/routed.eqy"
t0=$(date +%s)
timeout 540 eqy -f -j 2 -d "$D/eqy" "$D/routed.eqy" > "$D/eqy.log" 2>&1
rc=$?
grep -E "Could not prove|Proved equivalence|DONE|Failed to prove" "$D/eqy.log" | grep -v "strategy 'skip'" | tail -5
echo "eqy exit code: $rc (non-zero expected; 124 = hold time limit)"
python3 scripts/p2_negcone.py result "$D/eqy" "$PART" "$D/mutation.json" "$rc" "$(( $(date +%s) - t0 ))" results/p2_11_negcone.json
