#!/bin/bash
# Usage: [LOCK_PRIO=low] scripts/with_lock.sh <owner> <cmd...>
# Part 2 rule: EVERY container job goes through this lock (2 cores / 8 GB: one heavy job at a time;
# never two ORFS flows, never ORFS + SCALE-Sim together).
# Priority: default "high". Sweep points must use LOCK_PRIO=low: a low-priority job does not take the
# lock while any live high-priority job is waiting, so stage work is never starved by sweeps.
LAB="$HOME/ai-chip-lab"; D="$LAB/coord/heavy.lock.d"; W="$LAB/coord/heavy.waiting.d"
owner="$1"; shift; prio="${LOCK_PRIO:-high}"; mkdir -p "$W"
me="$W/$$.$owner"; [ "$prio" = high ] && echo "$(date '+%F %T') $*" > "$me"
cleanup() { rm -f "$me"; [ "$(cat "$D/pid" 2>/dev/null)" = "$$" ] && rm -rf "$D"; }
trap cleanup EXIT INT TERM
high_waiting() { for f in "$W"/*; do [ -e "$f" ] || continue; p=$(basename "$f" | cut -d. -f1)
    if kill -0 "$p" 2>/dev/null; then return 0; else rm -f "$f"; fi; done; return 1; }
while :; do
  if [ "$prio" = low ] && high_waiting; then sleep 10; continue; fi
  if mkdir "$D" 2>/dev/null; then break; fi
  pid=$(cat "$D/pid" 2>/dev/null); if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$D"; continue; fi
  sleep 10
done
echo $$ > "$D/pid"; echo "$owner $prio $(date '+%F %T') $*" > "$D/owner"; rm -f "$me"
echo "$(date '+%F %T') LOCK $owner $prio $(echo "$*" | cut -c1-120)" >> "$LAB/logs/part2/lock.log"
"$@"; rc=$?
echo "$(date '+%F %T') FREE $owner rc=$rc" >> "$LAB/logs/part2/lock.log"
exit $rc
