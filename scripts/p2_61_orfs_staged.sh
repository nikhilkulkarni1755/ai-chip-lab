#!/usr/bin/env bash
# Stage 61_pe_bf16, ORFS part, for a design whose whole flow does not fit one 10-minute lock
# hold: the same ORFS flow as scripts/t2_run.sh (same make variables, pinned image), but one
# lock hold per ORFS stage group (synth+floorplan+place | cts | route | finish+metadata).  ORFS's
# make is incremental, so the result is the flow's normal result.  Fresh FLOW_VARIANT, so no
# earlier artefact is reused; a stage group that does not finish in its hold stops the run
# (recorded, no retry).
#   scripts/p2_61_orfs_staged.sh <design> [variant=p2_61s]
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
LAB="$PWD"
# shellcheck disable=SC1091
source ./env.sh; source coord/images.env
DES="$1"; VAR="${2:-p2_61s}"
CFG="/lab/orfs/p2_designs/nangate45/$DES/config.mk"
SUB="nangate45/$DES/$VAR"
if [ -e "orfs/work/logs/$SUB" ] || [ -e "orfs/work/results/$SUB" ]; then
  echo "variant $VAR already has artefacts for $DES; choose a new variant name" >&2; exit 2
fi
mkdir -p logs/part2/61_pe_bf16 "orfs/work/reports/$SUB"
LOGF="logs/part2/61_pe_bf16/orfs_${DES}_${VAR}.log"
T0=$(date +%s); RC=0; HOLDS=""
for grp in "synth floorplan place" "cts" "route" "finish metadata-generate"; do
  h0=$(date +%s)
  echo "$(date '+%F %T') [$DES/$VAR] hold: $grp" | tee -a "$LOGF"
  # shellcheck disable=SC2086
  scripts/with_lock.sh rtl docker run --rm --name "orfs_${DES}_${VAR}" --platform linux/amd64 \
    -v "$LAB:/lab" -w /OpenROAD-flow-scripts/flow -e NUM_CORES="${NUM_CORES:-3}" -e PYTHONHASHSEED=0 \
    "$ORFS_IMAGE" bash -c '
      [ -f /OpenROAD-flow-scripts/env.sh ] && source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1 || true
      cfg="$0"; var="$1"; shift
      t0=$(date +%s)
      timeout 560 make DESIGN_CONFIG="$cfg" WORK_HOME=/lab/orfs/work FLOW_VARIANT="$var" NUM_CORES="$NUM_CORES" LEC_CHECK=0 "$@"
      rc=$?; echo "@@HOLD_SECONDS $(( $(date +%s) - t0 )) rc=$rc targets=$*"; exit $rc
    ' "$CFG" "$VAR" $grp >> "$LOGF" 2>&1
  r=$?
  secs=$(grep '@@HOLD_SECONDS' "$LOGF" | tail -1 | cut -d' ' -f2)
  HOLDS="$HOLDS\"$grp\":${secs:-null},"
  echo "$(date '+%F %T') [$DES/$VAR] hold '$grp': rc=$r, ${secs:-?} s in the container, $(( $(date +%s) - h0 )) s incl. lock wait" | tee -a "$LOGF"
  if [ $r -ne 0 ]; then RC=$r; break; fi
done
printf '{"platform":"nangate45","design":"%s","variant":"%s","rc":%d,"wall_s":%d,"start_epoch":%d,"config":"%s","extra":"","image":"%s","num_cores":%s,"staged_holds_s":{%s},"runner":"scripts/p2_61_orfs_staged.sh"}\n' \
  "$DES" "$VAR" "$RC" $(( $(date +%s) - T0 )) "$T0" "$CFG" "$ORFS_IMAGE" "${NUM_CORES:-3}" "${HOLDS%,}" > "orfs/work/reports/$SUB/t2_run.json"
echo "[t61-orfs] $DES/$VAR: flow exit code $RC"
exit $RC
