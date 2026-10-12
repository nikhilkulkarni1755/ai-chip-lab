#!/bin/bash
# t2_run.sh -- ONE ORFS run (one design, one FLOW_VARIANT), clean, inside the pinned ORFS image.
# Usage: scripts/t2_run.sh <platform> <design> <variant> [--config <path-in-container>] [KEY=VAL ...]
#   <design>   = DESIGN_NICKNAME (dir name under flow/designs/<platform>/ or orfs/designs/<platform>/)
#   --config   = container path of config.mk. Default: stock ORFS config inside the image,
#                /OpenROAD-flow-scripts/flow/designs/<platform>/<design>/config.mk
#                (custom designs: /lab/orfs/designs/<platform>/<design>/config.mk, chosen automatically if it exists)
#   KEY=VAL    = extra make variables (e.g. CORE_UTILIZATION=40 SDC_FILE=/lab/orfs/sdc_gen/x.sdc)
# Outputs (host): $LAB/orfs/work/{logs,objects,reports,results}/<platform>/<design>/<variant>/
# The image stays read-only: WORK_HOME points at the bind-mounted lab dir. Takes the heavy-job lock.
# LEC_CHECK=0: optional Kepler-Formal equivalence step SIGILLs on this CPU (no AVX-512 in VM); it does not affect PPA.
# Exit code = flow exit code (metadata checking is a separate step: t2_check.sh).
set -u
LAB="$HOME/ai-chip-lab"; source "$LAB/env.sh"; source "$LAB/coord/images.env"
PLAT="$1"; DES="$2"; VAR="$3"; shift 3
CFG=""; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in --config) CFG="$2"; shift 2;; *) EXTRA+=("$1"); shift;; esac
done
FLOW=/OpenROAD-flow-scripts/flow
if [ -z "$CFG" ]; then
  if [ -f "$LAB/orfs/designs/$PLAT/$DES/config.mk" ]; then CFG="/lab/orfs/designs/$PLAT/$DES/config.mk"
  else CFG="$FLOW/designs/$PLAT/$DES/config.mk"; fi
fi
W="$LAB/orfs/work"; SUB="$PLAT/$DES/$VAR"
TMO="${T2_TIMEOUT:-5400}"   # seconds, whole run
mkdir -p "$W" "$LAB/logs/20_pnr_ref"
# clean run: remove every previous artefact of this (platform, design, variant)
for d in logs objects reports results; do rm -rf "$W/$d/$SUB"; done
LOGF="$LAB/logs/20_pnr_ref/${PLAT}_${DES}_${VAR}.log"
echo "$(date '+%F %T') t2_run start $SUB cfg=$CFG extra=${EXTRA[*]:-} image=$ORFS_IMAGE" | tee -a "$LAB/logs/run.log" > "$LOGF"
T0=$(date +%s)
CONT="orfs_${PLAT}_${DES}_${VAR}"
docker rm -f "$CONT" >/dev/null 2>&1
# watchdog: kill container after timeout
( sleep "$TMO"; docker kill "$CONT" >/dev/null 2>&1 ) & WD=$!
"$LAB/scripts/with_lock.sh" pnr docker run --rm --name "$CONT" --platform linux/amd64 \
  -v "$LAB:/lab" -w "$FLOW" \
  -e NUM_CORES="${NUM_CORES:-3}" -e PYTHONHASHSEED=0 \
  "$ORFS_IMAGE" bash -c '
    set -e
    [ -f /OpenROAD-flow-scripts/env.sh ] && source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1 || true
    make DESIGN_CONFIG="$0" WORK_HOME=/lab/orfs/work FLOW_VARIANT="$1" NUM_CORES="$NUM_CORES" LEC_CHECK=0 "${@:2}" finish metadata-generate
  ' "$CFG" "$VAR" "${EXTRA[@]+"${EXTRA[@]}"}" >> "$LOGF" 2>&1
RC=$?
kill $WD 2>/dev/null; wait $WD 2>/dev/null
T1=$(date +%s)
mkdir -p "$W/reports/$SUB"
printf '{"platform":"%s","design":"%s","variant":"%s","rc":%d,"wall_s":%d,"start_epoch":%d,"config":"%s","extra":"%s","image":"%s","num_cores":%s}\n' \
  "$PLAT" "$DES" "$VAR" "$RC" $((T1-T0)) "$T0" "$CFG" "${EXTRA[*]:-}" "$ORFS_IMAGE" "${NUM_CORES:-3}" > "$W/reports/$SUB/t2_run.json"
echo "$(date '+%F %T') t2_run end $SUB rc=$RC wall=$((T1-T0))s" | tee -a "$LAB/logs/run.log" >> "$LOGF"
exit $RC
