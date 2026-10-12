#!/usr/bin/env bash
# demo/run_demo.sh - the 5-minute cut. Cached images only (no pull, no download); everything is written to a
# scratch directory (.cache/demo_run) and never touches results/ or the official markers.
#   bash demo/run_demo.sh [NCASES=200]
# Steps: (1) Task 1, N cases on Verilator + Icarus, (2) formal MAC proof (SymbiYosys),
#        (3) one SCALE-Sim run (bundled TPU-like config, 6 GEMM layers) vs the analytic model,
#        (4) ORFS's own threshold checker on the existing nangate45/gcd metadata.
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
t=$(date +%s)
echo "== Task 1: $N cases, Verilator + Icarus"
T1_STEPS="sim" bash scripts/t1_run.sh "$N" "$SCR/t1_sim" > "$SCR/t1_sim.log" 2>&1
r=$(pyget "$SCR/t1_sim/t1_summary.json" "all(c.get(k) is True for k in ['zero_mismatches_verilator','zero_mismatches_icarus','csv_sha256_identical'])")
record "Task 1: $N cases vs NumPy, Verilator+Icarus, CSVs identical" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" $(( $(date +%s) - t ))

t=$(date +%s)
echo "== Task 1: formal MAC proof (sby tasks: prove + cover; the full bmc-20 runs in 'make t1')"
mkdir -p "$SCR/formal"
docker run --rm --pull never --platform linux/amd64 -v "$LAB":/lab -w /lab/formal "$LAB_SIM_IMAGE" \
  sby -f -j 1 --prefix "/lab/$SCR/formal/mac" mac.sby prove cover > "$SCR/t1_formal.log" 2>&1
if [ $? -eq 0 ] && [ -f "$SCR/formal/mac_prove/PASS" ] && [ -f "$SCR/formal/mac_cover/PASS" ]; then r=PASS; else r=FAIL; fi
record "Task 1: formal MAC proof, sby tasks prove (induction) + cover" "$r" $(( $(date +%s) - t ))

# ---- 3: one SCALE-Sim invocation (bundled TPU-like config, os dataflow, 6 GEMMs) vs the closed-form model
t=$(date +%s)
echo "== Task 3: one SCALE-Sim run vs analytic model"
docker run --rm --pull never --platform linux/amd64 -e PYTHONHASHSEED=0 -e LAB=/lab -v "$LAB":/lab -w /lab "$LAB_SIM_IMAGE" \
  python3 demo/demo_scalesim.py "$SCR/t3_demo.json" > "$SCR/t3.log" 2>&1
r=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print('PASS' if d['rows'] and d['max_abs_residual']==0 else 'NO')" "$SCR/t3_demo.json" 2>/dev/null)
record "Task 3: SCALE-Sim cycles == analytic model on 6 GEMMs (1 run; full ws/os/is stage is 'make t3')" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" $(( $(date +%s) - t ))

# ---- 4: ORFS threshold check on existing outputs (ORFS's own checkMetadata.py)
t=$(date +%s)
echo "== Task 2: ORFS shipped-threshold check on existing nangate45/gcd metadata"
REP=orfs/work/reports/nangate45/gcd/base
if [ -f "$REP/metadata.json" ]; then
  docker run --rm --pull never --platform linux/amd64 -v "$LAB:/lab" -w /OpenROAD-flow-scripts/flow "$ORFS_IMAGE" \
    python3 util/checkMetadata.py -m "/lab/$REP/metadata.json" -r designs/nangate45/gcd/rules-base.json > "$SCR/t2_check.log" 2>&1
  grep -q "All metadata rules passed" "$SCR/t2_check.log" && r=PASS || r=FAIL
else
  echo "no $REP/metadata.json (official Task 2 outputs not present; ORFS work dir was deleted?)" > "$SCR/t2_check.log"; r=FAIL
fi
record "Task 2: nangate45/gcd metadata within ORFS shipped thresholds" "$r" $(( $(date +%s) - t ))

# ---- table
echo
echo "================ demo summary ================"
fail=0
for i in "${!NAMES[@]}"; do
  printf "%-5s %4ss  %s\n" "${RES[$i]}" "${TIMES[$i]}" "${NAMES[$i]}"
  [ "${RES[$i]}" = PASS ] || fail=1
done
TOT=$(( $(date +%s) - T0 ))
echo "total: $TOT s   load average: $(uptime | sed 's/.*load averages*: //')   logs: $SCR/*.log"
python3 - "$SCR/timing.json" "$TOT" "$N" "$(uptime | sed 's/.*load averages*: //')" "$(date '+%F %T')" <<'PY'
import json,sys
json.dump({"total_s":int(sys.argv[2]),"cases":int(sys.argv[3]),"load_average":sys.argv[4],"finished":sys.argv[5]},open(sys.argv[1],"w"))
PY
[ $fail -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL (see logs in $SCR)"
exit $fail
