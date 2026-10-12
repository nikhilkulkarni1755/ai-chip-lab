#!/usr/bin/env bash
# demo/run_demo.sh - the 5-minute cut. Cached images only (no pull, no download); everything is written to a
# scratch directory (.cache/demo_run) and never touches results/ or the official markers.
#   bash demo/run_demo.sh [NCASES=200]
# Steps: (1) Task 1, N cases on Verilator + Icarus, (2) formal MAC proof (SymbiYosys),
#        (3) one SCALE-Sim pass (bundled config + topology, ws/os/is) vs the analytic model,
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
pyget() { python3 -c "
import json,sys
try:
    d=json.load(open('$1')); c=d.get('checks',{}); v=d.get('values',{})
    $2
except Exception as e:
    print('NO'); 
"; }

# ---- 1+2: Task 1 on both simulators, then the formal proof (partial run of the official script)
t=$(date +%s)
echo "== Task 1: $N cases, Verilator + Icarus"
T1_STEPS="sim" bash scripts/t1_run.sh "$N" "$SCR/t1_sim" > "$SCR/t1_sim.log" 2>&1
r=$(pyget "$SCR/t1_sim/t1_summary.json" "
ks=['zero_mismatches_verilator','zero_mismatches_icarus','csv_sha256_identical']
print('PASS' if all(c.get(k) is True for k in ks) else 'NO')")
record "Task 1: $N cases vs NumPy, Verilator+Icarus, CSVs identical" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" $(( $(date +%s) - t ))

t=$(date +%s)
echo "== Task 1: formal MAC proof"
T1_STEPS="formal" bash scripts/t1_run.sh "$N" "$SCR/t1_formal" > "$SCR/t1_formal.log" 2>&1
r=$(pyget "$SCR/t1_formal/t1_summary.json" "
ks=[k for k in c if k.startswith('formal_') and k.endswith('pass')]
print('PASS' if ks and all(c[k] is True for k in ks) else 'NO')")
record "Task 1: formal proof of the MAC (SymbiYosys bmc + prove)" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" $(( $(date +%s) - t ))

# ---- 3: SCALE-Sim, one pass, vs the analytic model
t=$(date +%s)
echo "== Task 3: SCALE-Sim ws/os/is, one pass, vs analytic model"
T3_PASSES=1 T3_PLOTS=0 T3_SUMMARY="$SCR/t3_summary.json" bash scripts/t3_run.sh "$SCR/t3" > "$SCR/t3.log" 2>&1
r=$(pyget "$SCR/t3_summary.json" "
chk=[v for k,v in c.items() if isinstance(v,bool) and 'rerun' not in k and 'identical' not in k]
print('PASS' if chk and all(chk) else 'NO')")
record "Task 3: SCALE-Sim vs analytic model (1 pass; rerun identity skipped in the cut)" "$( [ "$r" = PASS ] && echo PASS || echo FAIL )" $(( $(date +%s) - t ))

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
echo "total: $(( $(date +%s) - T0 )) s   logs: $SCR/*.log"
[ $fail -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL (see logs in $SCR)"
exit $fail
