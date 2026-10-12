#!/bin/bash
# Usage: [LOCK_PRIO=low] scripts/with_lock.sh <owner> <cmd...>          (queue view: scripts/queue.sh)
# Part 2 rule: EVERY container job goes through this lock (2 cores / 8 GB: one heavy job at a time;
# never two ORFS flows, never ORFS + SCALE-Sim together).
#
# Priority: default "high". Sweep points must use LOCK_PRIO=low: a low-priority job does not take the
# lock while any live high-priority job is waiting, so stage work is never starved by sweeps.
# Within one priority the queue is first-come-first-served (by registration time).
# A low-priority job also waits LOCK_LOW_GRACE seconds (default 45) after a high-priority job has released the
# lock, so a driver that queues its next high-priority job right after the previous one is not interleaved with
# long sweep points.
#
# Guarantees (each one closes a failure mode found in review, see COORDINATION.md Decision P2-3):
#  * Stale locks are broken only under a second short mutex and re-checked there, so two waiters can no
#    longer both "break" a dead holder's lock and then both hold it.
#  * A holder counts as alive while EITHER the wrapper OR the job it started is alive, and liveness is
#    pid + process start time (a recycled pid cannot keep a lock or a queue slot alive).
#  * INT/TERM/HUP/ALRM to the wrapper are forwarded to the job; the lock is kept until the job has
#    really exited (a second signal sends KILL). While waiting in the queue a signal just leaves it.
#  * After taking the lock the wrapper waits until NO container is running in the VM (orphans of killed
#    docker clients, or jobs started outside the lock), so "one container job at a time" holds even
#    then. Bounded by LOCK_BUSY_MAX seconds (default 3600; then it proceeds with a WARN in the log).
#  * Re-entrant: a command already running under the lock may call with_lock.sh again (no deadlock).
#    Decided by ancestry (the holder is a live ancestor of the caller), not by environment. The job sees
#    LAB_LOCK_HELD=1 (team convention); a stale LAB_LOCK_HELD=1 outside the holder's job is not honoured.
#  * The job keeps stdin and its exit code is returned unchanged.
# Env: LAB_LOCK_TAG=<label> is copied into the LOCK log line (used by scripts/make_record.py to sum queue waits),
#      LOCK_PRIO=high|low, LOCK_POLL (s, default 5), LOCK_BUSY_MAX, LOCK_SKIP_BUSY_CHECK=1 (tests only),
#      LAB_LOCK_ROOT (tests only: directory used instead of the lab for coord/ and logs/).
LAB="$HOME/ai-chip-lab"; R="${LAB_LOCK_ROOT:-$LAB}"
C="$R/coord"; D="$C/heavy.lock.d"; W="$C/heavy.waiting.d"; WL="$C/heavy.waiting.low.d"; BRK="$C/heavy.break.d"
LOG="$R/logs/part2/lock.log"
[ $# -ge 2 ] || { echo "usage: [LOCK_PRIO=low] $0 <owner> <cmd...>" >&2; exit 2; }
owner="$1"; shift
prio="${LOCK_PRIO:-high}"; [ "$prio" = low ] || prio=high
POLL="${LOCK_POLL:-5}"
mkdir -p "$W" "$WL" "$(dirname "$LOG")"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
cmd1=$(printf '%s' "$*" | tr '\n' ' ' | cut -c1-160)
pstart() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' '; }
live() {  # live <pid> [<start time>]
  [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null || return 1
  [ -z "${2:-}" ] && return 0
  [ "$(pstart "$1")" = "$2" ]
}

# ---- re-entrant call from inside the current holder's job ---------------------------------------
# Re-entrant iff the current lock holder is a live ANCESTOR of this process (walk the parent chain). This
# does not depend on environment variables, so it also works for jobs started by the previous version of
# this script, and it cannot be fooled by a stale LAB_LOCK_HELD=1 in a process detached from an old job.
holder_is_ancestor() {
  local h p n=0; h=$(cat "$D/pid" 2>/dev/null); [ -n "$h" ] && kill -0 "$h" 2>/dev/null || return 1
  p=$PPID
  while [ -n "$p" ] && [ "$p" -gt 1 ] && [ $n -lt 64 ]; do
    [ "$p" = "$h" ] && return 0
    p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' '); n=$((n + 1))
  done
  return 1
}
if holder_is_ancestor; then
  log "NEST $owner (inside holder $(cat "$D/pid")) $cmd1"
  export LAB_LOCK_HELD=1
  exec "$@"
fi
if [ "${LAB_LOCK_HELD:-0}" = 1 ]; then log "WARN $owner had LAB_LOCK_HELD=1 but is not inside the current holder's job -> queued normally"; unset LAB_LOCK_HELD; fi

# ---- queue registration ---------------------------------------------------------------------------
if [ "$prio" = high ]; then Q="$W"; else Q="$WL"; fi
me="$Q/$$.$owner"; child=""; nsig=0; sigseen=0; T0=$(date +%s)
printf '%s %s\n%s\n' "$(date '+%F %T')" "$cmd1" "$(pstart $$)" > "$me"
cleanup() { rm -f "$me"; [ "$(cat "$D/pid" 2>/dev/null)" = "$$" ] && rm -rf "$D"; return 0; }
on_signal() {
  sigseen=1; nsig=$((nsig + 1))
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    if [ "$nsig" -ge 2 ]; then s=KILL; elif [ "$1" = ALRM ]; then s=TERM; else s="$1"; fi
    log "SIGNAL $owner got $1 -> sent $s to job $child; lock kept until the job exits"
    kill -"$s" "$child" 2>/dev/null
    return 0
  fi
  log "SIGNAL $owner got $1 while waiting -> left the queue"
  cleanup; trap - EXIT; exit 143
}
trap cleanup EXIT
for s in INT TERM HUP ALRM; do trap "on_signal $s" "$s"; done

marker_live() {  # marker file: line 1 "date time cmd", line 2 process start time (absent for old-format markers)
  local p st; p=$(basename "$1" | cut -d. -f1); st=$(sed -n 2p "$1" 2>/dev/null)
  live "$p" "$st" && return 0
  rm -f "$1"; return 1
}
ahead_of_me() {  # 0 = some live job must go first
  local f
  if [ "$prio" = low ]; then
    for f in "$W"/*; do [ -e "$f" ] || continue; marker_live "$f" && return 0; done
    # grace period: a chain of high-priority jobs (driver loops like `make t3` queue their next job a moment
    # after the previous one ends) must not be split by a 30-minute sweep point slipping into the gap
    if [ -e "$C/heavy.lasthigh" ] && [ $(( $(date +%s) - $(stat -f %m "$C/heavy.lasthigh" 2>/dev/null || echo 0) )) -lt "${LOCK_LOW_GRACE:-45}" ]; then return 0; fi
  fi
  for f in $(ls -tr "$Q" 2>/dev/null); do
    [ "$Q/$f" = "$me" ] && return 1
    marker_live "$Q/$f" && return 0
  done
  return 1
}
holder_state() {  # 0 held by a live job, 1 free, 2 stale
  [ -d "$D" ] || return 1
  local pid st ch age
  pid=$(cat "$D/pid" 2>/dev/null); st=$(cat "$D/start" 2>/dev/null); ch=$(cat "$D/child" 2>/dev/null)
  if [ -z "$pid" ]; then   # holder between mkdir and writing its pid, or it died right there
    age=$(( $(date +%s) - $(stat -f %m "$D" 2>/dev/null || date +%s) ))
    [ "$age" -lt 30 ] && return 0; return 2
  fi
  live "$pid" "$st" && return 0
  live "$ch" && return 0
  return 2
}
break_stale() {
  if ! mkdir "$BRK" 2>/dev/null; then   # someone else is breaking; clear a breaker mutex left by a crash
    [ $(( $(date +%s) - $(stat -f %m "$BRK" 2>/dev/null || date +%s) )) -gt 60 ] && rmdir "$BRK" 2>/dev/null
    return
  fi
  holder_state
  if [ $? = 2 ]; then log "STALE lock of dead holder ($(cut -c1-80 "$D/owner" 2>/dev/null)) removed by $owner"; rm -rf "$D"; fi
  rmdir "$BRK" 2>/dev/null
}

# ---- wait for the lock ----------------------------------------------------------------------------
while :; do
  if ! ahead_of_me; then
    if mkdir "$D" 2>/dev/null; then
      echo $$ > "$D/pid"; pstart $$ > "$D/start"; echo "$owner $prio $(date '+%F %T') $cmd1" > "$D/owner"
      break
    fi
    holder_state; if [ $? = 2 ]; then break_stale; sleep 1; continue; fi
  fi
  sleep "$POLL" & wait $!     # `wait` so that a signal is handled at once, not after the sleep
done
rm -f "$me"
waited=$(( $(date +%s) - T0 ))

# ---- nothing else may be running in the VM --------------------------------------------------------
if [ "${LOCK_SKIP_BUSY_CHECK:-0}" != 1 ] && [ -x "$LAB/bin/docker" ]; then
  export DOCKER_HOST="${DOCKER_HOST:-unix://$LAB/.colima/default/docker.sock}"
  b0=$(date +%s); last=0
  while :; do
    names=$(perl -e 'alarm 20; exec @ARGV' "$LAB/bin/docker" ps --format '{{.Names}}' 2>/dev/null | tr '\n' ' ')
    [ -z "${names// /}" ] && break
    now=$(date +%s); echo "$names" > "$D/busy"
    if [ $((now - b0)) -gt "${LOCK_BUSY_MAX:-3600}" ]; then log "WARN $owner proceeds although containers are still running after $((now - b0))s: $names"; break; fi
    if [ $((now - last)) -ge 60 ]; then log "BUSY $owner holds the lock, waiting for running container(s) to end: $names"; last=$now; fi
    sleep "$POLL" & wait $!
    [ "$nsig" -gt 0 ] && { cleanup; trap - EXIT; exit 143; }
  done
  rm -f "$D/busy"
fi

# ---- run the job ------------------------------------------------------------------------------------
log "LOCK $owner $prio waited=${waited}s${LAB_LOCK_TAG:+ tag=$LAB_LOCK_TAG} $(printf '%s' "$cmd1" | cut -c1-120)"
# LAB_LOCK_HELD=1 is the team convention scripts test to know they already run under the lock
export LAB_LOCK_HELD=1 LAB_LOCK_HOLDER=$$
"$@" <&0 &
child=$!; echo "$child" > "$D/child"
while :; do
  sigseen=0; wait "$child"; rc=$?
  [ "$sigseen" = 0 ] && break            # real exit status; otherwise wait was interrupted by a signal
  kill -0 "$child" 2>/dev/null || { wait "$child" 2>/dev/null; r2=$?; [ "$r2" != 127 ] && rc=$r2; break; }
done
[ "$prio" = high ] && : > "$C/heavy.lasthigh"
log "FREE $owner rc=$rc ran=$(( $(date +%s) - T0 - waited ))s"
exit $rc
