#!/bin/bash
# Test harness for scripts/with_lock.sh. Usage: locktest.sh <with_lock.sh> <empty test root dir>
L="$1"; T="$2"
export LAB_LOCK_ROOT="$T" LOCK_SKIP_BUSY_CHECK=1 LOCK_POLL=1
cat > "$T/job.sh" <<'EOF'
#!/bin/bash
echo "S $1" >> "$2/trace"; sleep 0.4; echo "E $1" >> "$2/trace"
EOF
cat > "$T/overlap.py" <<'EOF'
import sys
ls = [l.split() for l in open(sys.argv[1])]
depth = 0; bad = False
for l in ls:
    depth += 1 if l[0] == 'S' else -1
    bad |= depth > 1
print("OK" if (not bad and len(ls) == int(sys.argv[2])) else "FAIL", "(%d trace lines)" % len(ls))
EOF
echo "1 mutual exclusion, 12 concurrent jobs:"
for i in $(seq 1 12); do "$L" t$i bash "$T/job.sh" j$i "$T" & done; wait
python3 "$T/overlap.py" "$T/trace" 24

echo hello | "$L" t bash -c 'read x; [ "$x" = hello ] && exit 7'; echo "2 exit code + stdin: rc=$? (want 7)"

: > "$T/order"; "$L" hold sleep 3 & sleep 0.5
LOCK_PRIO=low "$L" L1 bash -c "echo L1 >> $T/order" & sleep 0.3
"$L" H1 bash -c "echo H1 >> $T/order; sleep 1.5" & sleep 1.2
"$L" H2 bash -c "echo H2 >> $T/order" & wait
echo "3 priority + FIFO order: $(tr '\n' ' ' < "$T/order")(want H1 H2 L1)"

perl -e 'alarm 20; exec @ARGV' "$L" outer "$L" inner echo nested-ok; echo "4 re-entrant rc=$? (want 0)"

"$L" dead sleep 300 & hp=$!; sleep 1.5; cp=$(cat "$T/coord/heavy.lock.d/child"); kill -9 $hp $cp; sleep 0.5
t0=$(date +%s); "$L" next echo took-stale-lock; echo "5 stale lock (holder and job dead) recovered in $(( $(date +%s) - t0 ))s"

"$L" orphan sleep 6 & hp=$!; sleep 1.5; kill -9 $hp; t0=$(date +%s); "$L" after true
echo "6 holder killed, job alive: next job waited $(( $(date +%s) - t0 ))s (want about 4-5, not 0)"

"$L" sig sleep 300 & hp=$!; sleep 1.5; kill -TERM $hp; wait $hp
echo "7 TERM forwarded to job: rc=$? (want 143); lock dir left: $([ -d "$T/coord/heavy.lock.d" ] && echo yes || echo no)"

"$L" hold sleep 3 & sleep 0.5; "$L" w echo never & wp=$!; sleep 1; kill -TERM $wp; wait $wp
echo "8 TERM while waiting: rc=$? (want 143); queue markers left: $(ls "$T/coord/heavy.waiting.d" | wc -l | tr -d ' ')"; wait

mkdir "$T/coord/heavy.lock.d"; echo 99999 > "$T/coord/heavy.lock.d/pid"; : > "$T/trace"
echo "9 six waiters racing to break one stale lock:"
for i in $(seq 1 6); do "$L" r$i bash "$T/job.sh" j$i "$T" & done; wait
python3 "$T/overlap.py" "$T/trace" 12

perl -e 'alarm 3; exec @ARGV' "$L" alrm sleep 300; echo "10 ALRM (lab_timeout around with_lock): rc=$? ; lock dir left: $([ -d "$T/coord/heavy.lock.d" ] && echo yes || echo no)"
echo "leftovers in coord: $(ls "$T/coord" | tr '\n' ' ') / waiting: $(ls "$T/coord/heavy.waiting.d" "$T/coord/heavy.waiting.low.d" | grep -c '^[0-9]')"
grep -c . "$T/logs/part2/lock.log" | sed 's/^/lock.log lines: /'
grep -E 'STALE|SIGNAL|NEST' "$T/logs/part2/lock.log" | cut -c1-150
cat > "$T/nest.sh" <<'EON'
#!/bin/bash
unset LAB_LOCK_HELD LAB_LOCK_HOLDER
exec "$1" inner echo nested-by-ancestry-ok
EON
perl -e 'alarm 20; exec @ARGV' "$L" outer bash "$T/nest.sh" "$L"; echo "11 nested without env (ancestry): rc=$? (want 0)"
LAB_LOCK_HELD=1 perl -e 'alarm 20; exec @ARGV' "$L" x echo stale-held-queued; echo "12 stale LAB_LOCK_HELD=1 queues normally: rc=$?"
grep -E 'WARN' "$T/logs/part2/lock.log" | cut -c1-150
