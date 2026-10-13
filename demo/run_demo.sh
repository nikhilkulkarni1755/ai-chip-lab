#!/usr/bin/env bash
# demo/run_demo.sh - the 5-minute cut. Cached images only (no pull, no download); everything is written to a
# scratch directory (.cache/demo_run) and never touches results/ or the official markers.
#   bash demo/run_demo.sh [NCASES=200]
# Steps: (1) Task 1, N cases on Verilator + Icarus, (2) formal MAC proof (SymbiYosys),
#        (3) one SCALE-Sim run (bundled TPU-like config, 6 GEMM layers) vs the analytic model,
#        (4) ORFS's own threshold checker on the existing nangate45/gcd metadata,
#        (5) Part 2: the Task 3 roofline criterion B verdict recomputed from the saved reports (seconds, no container).
# The routed-netlist gate-level step uses 20 random cases (+29 directed), Icarus only; the 229-case run takes 67 s and is not used here.
# Part 2: every container job takes the lab-wide lock (scripts/with_lock.sh), so it may wait behind other jobs; the wait is
# reported separately and excluded from the per-step times. LAB_LOCK_HELD=1 (set inside the lock) prevents a nested re-lock.
# Prints a PASS/FAIL table; exit 0 only if every step passed.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB="$(cd "$HERE/.." && pwd)"
cd "$LAB" || exit 2
source ./env.sh >/dev/null 2>&1
source coord/images.env
N="${1:-200}"
SCR=".cache/demo_run"
rm -rf "$SCR"; mkdir -p "$SCR"
T0=$(date +%s)
declare -a NAMES RES TIMES

if ! docker info >/dev/null 2>&1; then
  echo "Container runtime not reachable; starting the VM (no downloads)..."
  colima start >/dev/null 2>&1 || { echo "Could not start the VM. Try: source env.sh && colima start"; exit 3; }
fi
for img in "$LAB_SIM_IMAGE" "$ORFS_IMAGE"; do
  docker image inspect "$img" >/dev/null 2>&1 || { echo "image $img is not cached locally; this demo does not download. Run: make images"; exit 3; }
done

WAIT=0; LAST_START=0
lk() {  # lk <cmd...>: run under the lock (skipped if already inside it); sets LAST_START (epoch the job really started)
  local before; before=$(date +%s)
  if [ "${LAB_LOCK_HELD:-0}" = 1 ]; then LAST_START=$before; "$@"; return; fi
  bash scripts/with_lock.sh demo bash -c 'date +%s > "$1"; shift; LAB_LOCK_HELD=1 exec "$@"' _ "$SCR/.start" "$@"
  local rc=$?
  LAST_START=$(cat "$SCR/.start" 2>/dev/null || echo "$before"); WAIT=$(( WAIT + LAST_START - before ))
  return $rc
}
step_secs() { echo $(( $(date +%s) - LAST_START )); }
record() { NAMES+=("$1"); RES+=("$2"); TIMES+=("$3"); }
# pyget <json> <python expression over c (checks) and v (values)>  -> prints PASS or NO
pyget() { python3 -c "
import json,sys
try:
    d=json.load(open(sys.argv[1])); c=d.get('checks',{}); v=d.get('values',{})
    print('PASS' if eval(sys.argv[2]) else 'NO')
except Exception:
    print('NO')
" "$1" "$2"; }

# ---- 1+2: Task 1 on both simulators, then the formal proof (partial run of the official script)
echo "== Task 1: $N cases, Verilator + Icarus"
lk env T1_STEPS="sim" bash scripts/t1_run.sh "$N" "$SCR/t1_sim" > "$SCR/t1_sim.log" 2>&1
r=$(pyget "$SCR/t1_sim/t1_summary.json" "all(c.get(k) is True for k in ['zero_mismatches_verilator','zero_mismatches_icarus','csv_sha256_identical'])")
record "Task 1: $N cases vs NumPy, Verilator+Icarus, CSVs identical" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" "$(step_secs)"

echo "== Task 1: formal MAC proof (sby tasks: prove + cover; the full bmc-20 runs in 'make t1')"
mkdir -p "$SCR/formal"
lk docker run --rm --pull never --platform linux/amd64 -v "$LAB":/lab -w /lab/formal "$LAB_SIM_IMAGE" \
  sby -f -j 1 --prefix "/lab/$SCR/formal/mac" mac.sby prove cover > "$SCR/t1_formal.log" 2>&1
if [ $? -eq 0 ] && [ -f "$SCR/formal/mac_prove/PASS" ] && [ -f "$SCR/formal/mac_cover/PASS" ]; then r=PASS; else r=FAIL; fi
record "Task 1: formal MAC proof, sby tasks prove (induction) + cover" "$r" "$(step_secs)"

# ---- 3: one SCALE-Sim invocation (bundled TPU-like config, os dataflow, 6 GEMMs) vs the closed-form model
echo "== Task 3: one SCALE-Sim run vs analytic model"
lk docker run --rm --pull never --platform linux/amd64 -e PYTHONHASHSEED=0 -e LAB=/lab -v "$LAB":/lab -w /lab "$LAB_SIM_IMAGE" \
  python3 demo/demo_scalesim.py "$SCR/t3_demo.json" > "$SCR/t3.log" 2>&1
r=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print('PASS' if d['rows'] and d['max_abs_residual']==0 else 'NO')" "$SCR/t3_demo.json" 2>/dev/null)
record "Task 3: SCALE-Sim cycles == analytic model on 6 GEMMs (1 run; full ws/os/is stage is 'make t3')" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" "$(step_secs)"

# ---- 4: ORFS's own threshold checker on existing metadata (scripts/t2_check.sh; by default the committed copy
#         results/t2/metadata_nangate45_gcd.json, so it also works on a fresh clone; T2_USE_COMMITTED=0 uses orfs/work)
echo "== Task 2: ORFS shipped-threshold check on existing nangate45/gcd metadata"
lk env T2_USE_COMMITTED="${T2_USE_COMMITTED:-1}" bash scripts/t2_check.sh nangate45 gcd > "$SCR/t2_check.log" 2>&1
if grep -q "All metadata rules passed" "$SCR/t2_check.log"; then r=PASS; else r=FAIL; fi
record "Task 2: nangate45/gcd metadata within ORFS shipped thresholds (checkMetadata.py)" "$r" "$(step_secs)"

# ---- 4b (Part 2): routed-netlist gate-level simulation, Icarus only, 20 random + 29 directed cases (rtl measured about 40 s; the 229-case run is 67 s and is NOT used here).
#      Zero-delay logical check against the routed nangate45 netlist, not a timing check. PASS = the cocotb run reports no failure and the CSV equals the first rows of the official RTL CSV.
echo "== Task 1: routed-netlist gate-level simulation (Icarus, 20 random + 29 directed cases)"
mkdir -p "$SCR/t1_routed"
lk env T1R_STEPS=gls_icarus bash scripts/t1_routed.sh 20 "$SCR/t1_routed" > "$SCR/t1_routed.log" 2>&1
rg=$?
gcsv="$SCR/t1_routed/t1_routed_gls_icarus.csv"
if [ $rg -eq 0 ] && [ -s "$gcsv" ] && [ "$(head -n "$(wc -l < "$gcsv")" results/t1_icarus.csv | shasum -a 256 | cut -d' ' -f1)" = "$(shasum -a 256 < "$gcsv" | cut -d' ' -f1)" ]; then r=PASS; else r=FAIL; fi
record "Task 1: routed-netlist gate-level sim, Icarus, 49 cases vs NumPy (CSV = first rows of the official CSV; Verilator not run)" "$r" "$(step_secs)"

# ---- 5 (Part 2): the fixed roofline check, criterion B - recompute the verdict from the saved CALC-mode SCALE-Sim reports (native python, no simulation, seconds).
#      PASS = the recomputed verdict equals the one recorded in results/t3_summary.json (or none is recorded yet); the verdict itself (met / NOT met) is printed, never hidden.
#      Criterion A (stalls at a fixed user bandwidth) needs SCALE-Sim runs of minutes each and is not part of this cut.
echo "== Task 3: roofline criterion B recomputed from saved reports"
T5=$(date +%s)
python3 scripts/t3_criterion_b_recheck.py --lab "$LAB" > "$SCR/t3_critB.log" 2>&1; rcb=$?
cat "$SCR/t3_critB.log"
if [ $rcb -eq 0 ]; then r=PASS; elif [ $rcb -eq 2 ]; then r=SKIP; else r=FAIL; fi
record "Task 3: recorded verdict is consistent with saved reports (criterion B itself: NOT met)" "$r" "$(( $(date +%s) - T5 ))"

# ---- table
echo
echo "================ demo summary ================"
fail=0
for i in "${!NAMES[@]}"; do
  printf "%-5s %4ss  %s\n" "${RES[$i]}" "${TIMES[$i]}" "${NAMES[$i]}"
  [ "${RES[$i]}" = PASS ] || [ "${RES[$i]}" = SKIP ] || fail=1
done
TOT=$(( $(date +%s) - T0 ))
echo "total: $TOT s (of which $WAIT s waiting for the lock; steps above exclude that wait)   load average: $(uptime | sed 's/.*load averages*: //')   logs: $SCR/*.log"
python3 - "$SCR/timing.json" "$TOT" "$N" "$WAIT" "$(uptime | sed 's/.*load averages*: //')" "$(date '+%F %T')" <<'PY'
import json,sys
json.dump({"total_s":int(sys.argv[2]),"cases":int(sys.argv[3]),"lock_wait_s":int(sys.argv[4]),"load_average":sys.argv[5],"finished":sys.argv[6]},open(sys.argv[1],"w"))
PY
[ $fail -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL (see logs in $SCR)"
exit $fail
