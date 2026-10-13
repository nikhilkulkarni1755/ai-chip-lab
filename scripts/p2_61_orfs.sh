#!/usr/bin/env bash
# Stage 61_pe_bf16, ORFS part: the INT8 MAC and the bf16 MAC alone, nangate45, same flow
# settings, same clock (1.25 ns = closure clock of the INT8 MAC array, fixed in the SDC files
# before the first run).  One clean ORFS run per design through scripts/t2_run.sh (which takes
# the lab lock; T2_TIMEOUT keeps each hold under 10 minutes), then scripts/p2_61_finish.py.
#   scripts/p2_61_orfs.sh [mac_int8 mac_bf16]
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
[ $# -gt 0 ] || set -- mac_int8 mac_bf16
rc=0
for d in "$@"; do
  T2_TIMEOUT="${T2_TIMEOUT:-560}" scripts/t2_run.sh nangate45 "$d" p2_61 --config "/lab/orfs/p2_designs/nangate45/$d/config.mk"
  r=$?; echo "[t61-orfs] $d: flow exit code $r"; [ $r -eq 0 ] || rc=1
done
exit $rc
