#!/bin/bash
# Usage: scripts/with_lock.sh <owner> <cmd...>   Serializes HEAVY container jobs (image builds, ORFS runs)
# on this 2-core/8GB machine. Light jobs (sims, scale-sim) do not need it.
LAB="$HOME/ai-chip-lab"; D="$LAB/coord/heavy.lock.d"; owner="$1"; shift
while ! mkdir "$D" 2>/dev/null; do
  pid=$(cat "$D/pid" 2>/dev/null); if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then rm -rf "$D"; continue; fi
  sleep 10
done
echo $$ > "$D/pid"; echo "$owner $(date '+%F %T') $*" > "$D/owner"
trap 'rm -rf "$D"' EXIT
"$@"
