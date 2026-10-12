#!/bin/bash
# scripts/queue.sh — who holds the heavy-job lock, since when, who is waiting (read-only).
#   scripts/queue.sh        one snapshot          scripts/queue.sh -l [N]   plus the last N lock.log lines (default 10)
LAB="$HOME/ai-chip-lab"; R="${LAB_LOCK_ROOT:-$LAB}"; C="$R/coord"; D="$C/heavy.lock.d"
now=$(date +%s)
age() { local m; m=$(stat -f %m "$1" 2>/dev/null) || { echo "?"; return; }; local s=$((now - m)); printf '%dm%02ds' $((s / 60)) $((s % 60)); }
alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }
echo "== heavy-job lock @ $(date '+%F %T')"
if [ -d "$D" ]; then
  pid=$(cat "$D/pid" 2>/dev/null); ch=$(cat "$D/child" 2>/dev/null)
  st="LIVE"; alive "$pid" || { alive "$ch" && st="wrapper dead, job $ch still running" || st="STALE (holder and job dead; the next waiter removes it)"; }
  set -- $(cat "$D/owner" 2>/dev/null)
  echo "HELD by ${1:-?} (prio ${2:-?}) for $(age "$D/owner")  since ${3:-?} ${4:-?}  pid ${pid:-?} job ${ch:-not started}  [$st]"
  echo "     cmd: $(tr '\n' ' ' < "$D/owner" 2>/dev/null | cut -d' ' -f5- | sed "s#$HOME#~#g" | cut -c1-150)"
  [ -f "$D/busy" ] && echo "     NOT STARTED YET: waiting for container(s) still running in the VM: $(cat "$D/busy")"
else
  echo "FREE"
fi
n=0
for q in high:"$C/heavy.waiting.d" low:"$C/heavy.waiting.low.d"; do
  pr=${q%%:*}; dir=${q#*:}
  for f in $(ls -tr "$dir" 2>/dev/null); do
    p=${f%%.*}; alive "$p" || continue
    n=$((n + 1)); echo "WAIT #$n $pr ${f#*.} for $(age "$dir/$f")  pid $p  cmd: $(head -1 "$dir/$f" | cut -d' ' -f3- | sed "s#$HOME#~#g" | cut -c1-110)"
  done
done
[ $n = 0 ] && echo "nobody waiting"
if [ -x "$LAB/bin/docker" ]; then
  c=$(DOCKER_HOST="${DOCKER_HOST:-unix://$LAB/.colima/default/docker.sock}" perl -e 'alarm 15; exec @ARGV' "$LAB/bin/docker" ps --format '{{.Names}} ({{.Status}})' 2>/dev/null | tr '\n' ';')
  echo "containers running in the VM: ${c:-none}"
fi
if [ "${1:-}" = -l ]; then echo "== last ${2:-10} lock.log lines"; tail -n "${2:-10}" "$R/logs/part2/lock.log" 2>/dev/null | sed "s#$HOME#~#g" | cut -c1-170; fi
