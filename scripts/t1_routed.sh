#!/usr/bin/env bash
# Stage 11_eqy_routed: the Task 1 design checked against the ROUTED nangate45 netlist.
#
#   scripts/t1_routed.sh [NCASES=200] [OUTDIR=results]
#
# LOGICAL checks only (zero-delay cell functions).  Nothing here checks timing.
#
#  gls : post-route gate-level simulation -- routed netlist + nangate45 cell models
#        through the unchanged Task 1 cocotb test (seed 1234) on Icarus and Verilator,
#        0 mismatches vs NumPy, and the CSV must equal the first rows of the official
#        RTL CSV (results/t1_icarus.csv).  Plus a negative control: a netlist with two
#        register inputs swapped must produce mismatches.
#  eqy : EQY RTL == routed netlist (eqy/systolic_os_routed.eqy.in), plus negative
#        controls (bug injected into the RTL MAC, into an RTL operand register and
#        into the routed netlist: each must be rejected).
#
# Inputs
#  * routed netlist: $T1_ROUTED_NETLIST, default the snapshot of the final-RTL ORFS
#    run, results/part1_snapshot/systolic_os_routed/6_final.v (sha256 recorded).
#  * cell models: NangateOpenCellLibrary_typical.lib copied at run time out of the
#    pinned ORFS image ($ORFS_IMAGE in coord/images.env).  The ORFS nangate45 platform
#    ships no Verilog simulation library, so the Verilog cell models used for the
#    gate-level simulation are generated from that Liberty file with Yosys.
#
# Environment: T1R_STEPS = subset of "gls eqy" (default both), or "gls_icarus" = only
# the Icarus gate-level simulation (the quick demo check; with NCASES=50 about half a
# minute).
#
# Lock use: every step is its own short container job under its own
# scripts/with_lock.sh acquisition (cell models, Icarus GLS, Verilator GLS, GLS negative
# control, EQY in resumable chunks of at most T1R_CHUNK_SECONDS = 540 s -- `eqy -c`
# continues with the partitions that have no result yet --, each EQY negative control,
# summary), so other stages' short jobs interleave.  The lock is re-entrant: a caller
# that already holds it (LAB_LOCK_HELD=1) gets the same steps without re-locking.
# T1R_RESUME=1 continues an interrupted or partly failed run: steps that already
# succeeded (rc 0 in <work>/steps.tsv) are skipped, the others run again, proven EQY
# partitions are kept.  T1R_SKIP="<step names>" leaves those steps as they are.
# T1R_EQY_BUDGET_SECONDS caps the EQY solver lock time of one invocation.
set -u -o pipefail

NCASES="${1:-200}"
OUT_ARG="${2:-results}"
STEPS="${T1R_STEPS:-gls eqy}"
case "$NCASES" in ''|*[!0-9]*) echo "NCASES must be a non-negative integer" >&2; exit 2 ;; esac
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SELF_DIR/.." && pwd)"
LIB_IN_IMAGE=/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# ------------------------------------------------------------------ host side
if [ -z "${T1R_INSIDE:-}" ]; then
  cd "$LAB_DIR" || exit 2
  # shellcheck disable=SC1091
  [ -f env.sh ] && source ./env.sh
  case "$OUT_ARG" in
    "$LAB_DIR"/*) OUT_REL="${OUT_ARG#"$LAB_DIR"/}" ;;
    /*) echo "OUTDIR must be inside the lab directory" >&2; exit 2 ;;
    *) OUT_REL="${OUT_ARG%/}" ;;
  esac
  # shellcheck disable=SC1091
  source coord/images.env
  : "${LAB_SIM_IMAGE:?not set in coord/images.env}" "${ORFS_IMAGE:?not set in coord/images.env}"
  WORK="$OUT_REL/t1_routed_work"
  mkdir -p "$WORK/cells"; echo '*' > "$WORK/.gitignore"
  LOCK=()
  [ "${LAB_LOCK_HELD:-0}" = 1 ] || LOCK=(bash scripts/with_lock.sh rtl env LAB_LOCK_HELD=1)
  IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$LAB_SIM_IMAGE" 2>/dev/null || true)"
  phase() {  # phase <name>: one container job = one lock acquisition
    "${LOCK[@]}" docker run --rm --platform linux/amd64 --cpus 2 \
      -v "$LAB_DIR":/lab -w /lab \
      -e T1R_INSIDE=1 -e T1R_PHASE="$1" -e T1R_STEPS="$STEPS" -e PYTHONHASHSEED=0 \
      -e T1R_CHUNK_SECONDS="${T1R_CHUNK_SECONDS:-540}" -e T1R_RESUME="${T1R_RESUME:-0}" \
      -e T1R_EQY_TARGETS="${T1R_EQY_TARGETS:-}" -e T1R_SKIP="${T1R_SKIP:-}" \
      -e T1_ROUTED_NETLIST="${T1_ROUTED_NETLIST:-}" \
      -e T1R_IMAGE_REF="$LAB_SIM_IMAGE" -e T1R_ORFS_IMAGE="$ORFS_IMAGE" -e T1R_LIB_IN_IMAGE="$LIB_IN_IMAGE" \
      -e T1R_IMAGE_ID="$IMAGE_ID" \
      "$LAB_SIM_IMAGE" bash scripts/t1_routed.sh "$NCASES" "$OUT_REL"
  }
  # Cell library straight out of the pinned ORFS image (nothing is downloaded), and
  # step 1 of the task: can ORFS's built-in LEC (Kepler-Formal) run on this CPU?
  "${LOCK[@]}" docker run --rm --platform linux/amd64 -v "$LAB_DIR":/lab "$ORFS_IMAGE" bash -c '
    cp "$0" "/lab/$1/cells/NangateOpenCellLibrary_typical.lib" || exit 3
    K=/OpenROAD-flow-scripts/tools/install/kepler-formal/bin/kepler-formal
    {
      echo "# ORFS built-in LEC = Kepler-Formal ($K), enabled by LEC_CHECK=1 (flow/scripts/formal_check.tcl):"
      echo "# it compares 1_synth_lec.v with 6_final_lec.v (netlist vs netlist, never the RTL)."
      echo "\$ $K --version"
      "$K" --version 2>&1 | head -5
      echo "kepler-formal exit code: ${PIPESTATUS[0]}   (132 = 128 + SIGILL, illegal instruction)"
      echo "zmm instructions: $(objdump -d "$K" 2>/dev/null | grep -c zmm)   (AVX-512 register operands in the binary)"
      echo "cpu: $(grep -m1 "model name" /proc/cpuinfo | cut -d: -f2-)"
      if grep -m1 flags /proc/cpuinfo | grep -qw avx512f; then echo "cpu avx512f: yes"; else echo "cpu avx512f: no"; fi
    } > "/lab/$1/kepler_check.txt" 2>&1
  ' "$LIB_IN_IMAGE" "$WORK" || { echo "cannot copy Liberty from ORFS image" >&2; exit 3; }
  phase prep || true
  if [[ " $STEPS " == *" gls "* ]]; then
    for st in gls_icarus gls_verilator gls_neg; do phase "$st" || true; done
  elif [[ " $STEPS " == *" gls_icarus "* ]]; then
    phase gls_icarus || true
  fi
  if [[ " $STEPS " == *" eqy "* ]]; then
    # EQY holds: the first one sets the proof up (and starts solving); after that every
    # hold gets explicit partitions -- all cheap wrapper partitions at once, then the
    # per-PE MAC partitions two at a time (they run in parallel and take ~5 min each),
    # so no hold is cut off in the middle of a proof.  T1R_EQY_BUDGET_SECONDS caps the
    # total lock time spent on EQY solving in this invocation (default: no cap).
    spent=0; budget="${T1R_EQY_BUDGET_SECONDS:-0}"
    held() { awk -F'\t' '$1 ~ /^eqy_routed_(hold|chunk)/ {s += $3} END {print s + 0}' "$WORK/steps.tsv" 2>/dev/null || echo 0; }
    held0=$(held)
    hold() {  # hold <partitions...>   (lock time = solver step time, queue waits not counted)
      T1R_EQY_TARGETS="$*" phase eqy || true
      spent=$(( $(held) - held0 ))
      echo "[t1r] EQY lock time used in this invocation: ${spent} s"
    }
    todo() {  # todo <grep -E arguments on partition names>: partitions without a PASS/FAIL status
      local p
      cut -d' ' -f2 "$WORK/eqy_routed/partition.list" 2>/dev/null | grep -E "$@" | sort -t. -k3 -n | while read -r p; do
        grep -qE '^(PASS|FAIL)' "$WORK/eqy_routed/strategies/$p/smt/status" 2>/dev/null || echo "$p"
      done
    }
    [ -s "$WORK/eqy_routed/strategies.mk" ] || hold
    w="$(todo -v '\.acc_o\.' | tr '\n' ' ')"
    [ -n "${w// /}" ] && hold $w
    while :; do
      m="$(todo '\.acc_o\.' | head -n "${T1R_EQY_PARALLEL:-2}" | tr '\n' ' ')"
      [ -n "${m// /}" ] || break
      if [ "$budget" -gt 0 ] && [ $(( spent + ${T1R_CHUNK_SECONDS:-540} )) -gt "$budget" ]; then
        echo "[t1r] EQY lock budget ($budget s) reached with partitions still open: $(todo '.' | tr '\n' ' ')"; break
      fi
      hold $m
    done
    for st in eqy_neg_rtl_mac eqy_neg_rtl_reg eqy_neg_netlist; do phase "$st" || true; done
  fi
  phase finish
  exit $?
fi

# --------------------------------------------------------- inside (container)
cd "$LAB_DIR" || exit 2
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 LC_ALL=C.UTF-8
OUT="$OUT_ARG"
WORK="$OUT/t1_routed_work"
NETLIST="${T1_ROUTED_NETLIST:-results/part1_snapshot/systolic_os_routed/6_final.v}"
LIB="$WORK/cells/NangateOpenCellLibrary_typical.lib"
CELLS_V="$WORK/cells/nangate45_cells_from_liberty.v"
OFFICIAL=0
[ "$OUT" = "results" ] && [ "$NCASES" -ge 200 ] && [ "$STEPS" = "gls eqy" ] && [ -z "${T1_ROUTED_NETLIST:-}" ] && OFFICIAL=1
if [ "$OUT" = "results" ]; then LOGS="logs/part2/11_eqy_routed"; else LOGS="$WORK/logs"; fi
STAGE="results/.stages/11_eqy_routed"
[ -f "$NETLIST" ] || { echo "routed netlist not found: $NETLIST" >&2; exit 3; }

PHASE="${T1R_PHASE:-all}"
mkdir -p "$OUT" "$WORK" "$LOGS"
OUT_ABS="$(cd "$OUT" && pwd)"; WORK_ABS="$(cd "$WORK" && pwd)"
NETLIST_ABS="$(cd "$(dirname "$NETLIST")" && pwd)/$(basename "$NETLIST")"
RESUME=0; [ "${T1R_RESUME:-0}" = 1 ] && [ -s "$WORK/steps.tsv" ] && RESUME=1
if { [ "$PHASE" = prep ] || [ "$PHASE" = all ]; } && [ "$RESUME" = 0 ]; then   # new run: clean slate
  find "$WORK" -mindepth 1 -maxdepth 1 ! -name cells ! -name .gitignore ! -name kepler_check.txt -exec rm -rf {} +
  rm -f "$OUT"/t1_routed_gls_*.csv "$OUT"/t1_routed_summary.json "$CELLS_V" "$LOGS"/step_*.log
  : > "$WORK/steps.tsv"; date +%s > "$WORK/t_start"
  if [ "$OFFICIAL" = 1 ]; then
    rm -f "$STAGE.done" "$STAGE.failed"; : > "$STAGE.running"
    echo "$(date +%H:%M:%S) rtl: 11_eqy_routed started (N=$NCASES)" >> logs/run.log
  fi
fi
in_phase() { [ "$PHASE" = all ] || [ "$PHASE" = "$1" ]; }

tmo() { local secs="$1"; shift; timeout "$secs" "$@"; }
want() { case " $STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
step() {  # step <name> <timeout-seconds> <function> [args]
  local name="$1" secs="$2" t0 rc; shift 2
  case " ${T1R_SKIP:-} " in *" $name "*)
    echo "[t1r] $name: skipped on request (T1R_SKIP), earlier result kept"; return 0 ;; esac
  if [ "$RESUME" = 1 ] && grep -q "^$name	0	" "$WORK/steps.tsv"; then
    echo "[t1r] $name: already done in this run (resume), skipped"; return 0
  fi
  grep -v "^$name	" "$WORK/steps.tsv" > "$WORK/steps.tsv.tmp" 2>/dev/null; mv "$WORK/steps.tsv.tmp" "$WORK/steps.tsv"
  t0=$(date +%s); echo "[t1r] $name ..."
  TMO="$secs"
  "$@" > "$LOGS/step_$name.log" 2>&1
  rc=$?
  printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" >> "$WORK/steps.tsv"
  echo "[t1r] $name: rc=$rc, $(( $(date +%s) - t0 )) s"
  return $rc
}
T_START=$(cat "$WORK/t_start" 2>/dev/null || date +%s)

# ------------------------------------------------------- 0. cell models
# Verilog cell models generated from the Liberty functions, and a check that every
# cell instantiated by the routed netlist has a function (none is a black box).
cells() {
  tmo "$TMO" yosys -q -l "$WORK/cells_from_liberty.log" -p "read_liberty -ignore_miss_func $LIB; proc; opt_clean; write_verilog -noattr $CELLS_V" || return 1
  tmo "$TMO" yosys -q -l "$WORK/netlist_cells.log" -p "read_liberty -ignore_miss_func $LIB; read_verilog $NETLIST; hierarchy -check -top systolic_os; tee -q -o $WORK/netlist_stat.json stat -json; flatten; select -assert-none t:* t:\$* %d; proc; opt_merge; opt_clean; tee -q -o $WORK/netlist_flat_stat.json stat -json"
}
in_phase prep && { step cells 600 cells || echo "[t1r] cell models failed; later steps will fail too"; }

# -------------------------------------------------- 1. gate-level simulation
gls() {  # gls <sim> <netlist> <csv tag> <ncases>
  T1_NCASES="$4" T1_SEED=1234 \
  T1_CSV="$OUT_ABS/t1_routed_gls_$3.csv" T1_COV="$WORK_ABS/coverage_gls_$3.json" \
    tmo "$TMO" make -C tb SIM="$1" SIM_BUILD="$WORK_ABS/sim_$3" COCOTB_RESULTS_FILE="$WORK_ABS/results_$3.xml" \
      T1_GATE_NETLIST="$2" T1_GATE_CELLS="$WORK_ABS/cells/nangate45_cells_from_liberty.v"
}
# Verilator: with one module instance per standard cell (27k scopes, all public for
# cocotb) the generated C++ takes over half an hour to compile on this machine, so
# Verilator simulates the same netlist after Yosys has inlined the cell functions
# (flatten only: every gate and flop is kept, nothing is optimised).  Icarus simulates
# the netlist exactly as OpenROAD wrote it, with one cell module per instance.
gls_verilator() {
  tmo 300 yosys -q -l "$WORK/netlist_flat_for_verilator.log" -p "read_liberty -ignore_miss_func $LIB; read_verilog $NETLIST; hierarchy -check -top systolic_os; flatten; select -assert-none t:* t:\$* %d; proc; clean; write_verilog -noattr $WORK/netlist_flat_for_verilator.v" || return 1
  T1_NCASES="$NCASES" T1_SEED=1234 \
  T1_CSV="$OUT_ABS/t1_routed_gls_verilator.csv" T1_COV="$WORK_ABS/coverage_gls_verilator.json" \
    tmo "$TMO" make -C tb SIM=verilator SIM_BUILD="$WORK_ABS/sim_verilator" COCOTB_RESULTS_FILE="$WORK_ABS/results_verilator.xml" \
      T1_GATE_NETLIST="$WORK_ABS/netlist_flat_for_verilator.v" T1_GATE_CELLS=
}
# Negative control: swap the D inputs of two operand-register flops in a copy of the
# netlist; the simulation must then report mismatches (make exits non-zero).
gls_neg() {
  python3 scripts/t1_routed_summary.py mutate "$NETLIST" "$WORK/netlist_swapped_d.v" || return 90
  T1_NCASES=20 T1_SEED=1234 \
  T1_CSV="$WORK_ABS/gls_neg.csv" T1_COV="$WORK_ABS/coverage_gls_neg.json" \
    tmo "$TMO" make -C tb SIM=icarus SIM_BUILD="$WORK_ABS/sim_neg" COCOTB_RESULTS_FILE="$WORK_ABS/results_neg.xml" \
      T1_GATE_NETLIST="$WORK_ABS/netlist_swapped_d.v" T1_GATE_CELLS="$WORK_ABS/cells/nangate45_cells_from_liberty.v"
  local rc=$?
  echo "make exit code: $rc (non-zero expected: the testbench must report mismatches)"
  [ $rc -ne 0 ] && [ $rc -ne 124 ]
}
if { want gls || want gls_icarus; } && in_phase gls_icarus; then
  step gls_icarus 540 gls icarus "$NETLIST_ABS" icarus "$NCASES"
fi
if want gls; then
  in_phase gls_verilator && { rm -rf "$WORK/sim_verilator"; step gls_verilator 540 gls_verilator; }
  in_phase gls_neg && step gls_neg 540 gls_neg
fi

# ------------------------------------------------------------------- 2. EQY
mkeqy() {  # mkeqy <rtl dir> <netlist> <out file>
  sed -e "s#@RTL@#$1#g" -e "s#@LIB@#$WORK_ABS/cells/NangateOpenCellLibrary_typical.lib#g" -e "s#@NETLIST@#$2#g" \
    eqy/systolic_os_routed.eqy.in > "$3"
}
# One hold of EQY work.  Without a set-up proof directory: `eqy -f` (partitions the
# design, writes one make target per partition and starts solving) for at most
# T1R_CHUNK_SECONDS.  Afterwards: exactly the partitions named in T1R_EQY_TARGETS, through
# the make targets EQY generated (strategies.mk), so finished partitions are never redone.
equiv() {
  local rc p targets=()
  if [ ! -s "$WORK/eqy_routed/strategies.mk" ]; then
    mkeqy "$LAB_DIR/rtl" "$NETLIST_ABS" "$WORK/routed.eqy"
    timeout "${T1R_CHUNK_SECONDS:-540}" eqy -f -j 2 -d "$WORK/eqy_routed" "$WORK/routed.eqy"; rc=$?
  else
    for p in ${T1R_EQY_TARGETS:-}; do targets+=("strategies/$p/smt/status"); done
    [ ${#targets[@]} -gt 0 ] || { echo "no partitions requested"; return 0; }
    echo "partitions in this hold: ${T1R_EQY_TARGETS}"
    timeout "${T1R_CHUNK_SECONDS:-540}" make -j 2 -C "$WORK/eqy_routed" -f strategies.mk "${targets[@]}"; rc=$?
  fi
  echo "hold exit code: $rc (124 = time limit of this hold)"
  for p in ${T1R_EQY_TARGETS:-}; do echo "status $p: $(cat "$WORK/eqy_routed/strategies/$p/smt/status" 2>/dev/null || echo none)"; done
  return 0
}
# EQY's own verdict over all partition results (nothing is solved here: finished
# partitions are skipped; it is only run when every partition has a result).
equiv_verdict() {
  local p
  while read -r _ p _; do
    grep -qE '^(PASS|FAIL)' "$WORK/eqy_routed/strategies/$p/smt/status" 2>/dev/null || { echo "open partition: $p"; return 3; }
  done < "$WORK/eqy_routed/partition.list"
  timeout "$TMO" eqy -c -j 2 -d "$WORK/eqy_routed" "$WORK/routed.eqy"
}
# Negative controls: one injected bug, only the partition that contains it is solved
# (apply <partition>, the rest goes to a dummy strategy); EQY must not prove it.
equiv_neg() {  # equiv_neg <tag> <partition> rtl <file> <sed expr> | netlist
  local d="$WORK_ABS/neg_$1" net="$NETLIST_ABS" rc
  rm -rf "$d"; mkdir -p "$d/rtl"
  cp rtl/mac_int8.sv rtl/systolic_os.sv "$d/rtl/"
  if [ "$3" = rtl ]; then
    sed -e "$5" "rtl/$4" > "$d/rtl/$4"
    if cmp -s "rtl/$4" "$d/rtl/$4"; then echo "mutation did not apply to $4"; return 90; fi
    echo "injected bug (RTL):"; diff "rtl/$4" "$d/rtl/$4"
  else
    python3 scripts/t1_routed_summary.py mutate "$NETLIST" "$d/netlist_swapped_d.v" || return 90
    net="$d/netlist_swapped_d.v"
  fi
  mkeqy "$d/rtl" "$net" "$d/routed.eqy"
  printf 'apply %s\n\n[strategy skip]\nuse dummy\n' "$2" >> "$d/routed.eqy"
  tmo "$TMO" eqy -f -j 2 -d "$d/eqy" "$d/routed.eqy"
  rc=$?
  echo "eqy exit code: $rc (non-zero expected)"
  [ $rc -ne 0 ] && [ $rc -ne 124 ]
}
if want eqy && in_phase eqy; then
  n=$(grep -c '^eqy_routed_hold' "$WORK/steps.tsv" 2>/dev/null || true)
  n=$(( ${n:-0} + $(grep -c '^eqy_routed_chunk' "$WORK/steps.tsv" 2>/dev/null || true) ))
  RESUME=0 step "eqy_routed_hold$(( n + 1 ))" 600 equiv
fi
if want eqy && in_phase finish; then
  RESUME=0 step eqy_routed_verdict 300 equiv_verdict || true
fi
# Clock tree: the equivalence proof models every flop as clocked by one global clock, so
# it does not look at the clock nets.  Checked separately and structurally: after the
# Liberty functions are applied (clock buffers are identity functions), the clock pin of
# every one of the 806 flops must be the net `clk` itself.
clock_check() {
  tmo "$TMO" yosys -q -l "$WORK/clock_check.log" -p "read_liberty -ignore_miss_func $LIB; read_verilog $NETLIST; hierarchy -check -top systolic_os; flatten; proc; opt_merge; opt_clean; select -assert-count 806 t:\$_DFF_P_; select -assert-count 806 w:clk %co1:+\$_DFF_P_[C] t:\$_DFF_P_ %i; select -assert-none t:\$_DFF_P_ w:clk %co1:+\$_DFF_P_[C] %d"
}
in_phase finish && { RESUME=0 step clock_check 300 clock_check || true; }
if want eqy; then
  in_phase eqy_neg_rtl_mac && step eqy_neg_rtl_mac 540 equiv_neg rtl_mac systolic_os.acc_o.0 rtl mac_int8.sv \
    "s/acc <= acc + 32'(prod);/acc <= acc + 32'(prod) + 32'sd1;/"
  in_phase eqy_neg_rtl_reg && step eqy_neg_rtl_reg 300 equiv_neg rtl_reg systolic_os.g_row.0.g_col.0.g_east.a_q.0 rtl systolic_os.sv \
    "s/a_q <= a_w\\[i\\]\\[j\\];/a_q <= a_w[i][j] ^ 8'd1;/"
  in_phase eqy_neg_netlist && step eqy_neg_netlist 300 equiv_neg netlist systolic_os.g_row.0.g_col.0.g_east.a_q.0 netlist
fi

in_phase finish || exit 0
python3 scripts/t1_routed_summary.py summary --out "$OUT" --work "$WORK" --logs "$LOGS" \
  --ncases "$NCASES" --steps "$STEPS" --netlist "$NETLIST" --wall "$(( $(date +%s) - T_START ))"
RC=$?
if [ "$OFFICIAL" = 1 ]; then
  rm -f "$STAGE.running" "$STAGE.done" "$STAGE.failed"
  python3 - > "$STAGE.$([ $RC -eq 0 ] && echo done || echo failed)" <<'PY'
import json
d = json.load(open("results/t1_routed_summary.json"))
e = d["values"].get("eqy_routed", {})
print("pass", d["pass"], "eqy_routed_pass", d["eqy_routed_pass"], "gls_routed_pass", d["gls_routed_pass"])
print("gls by simulator:", json.dumps(d["values"].get("gls_routed_by_simulator")))
print("eqy partitions proven:", e.get("partitions_proved"), "of", e.get("partitions"))
if not d["pass"]:
    print("failed checks:", ", ".join(k for k, v in sorted(d["checks"].items()) if not v))
    print("open partitions:", ", ".join(sorted(e.get("partitions_not_proved", {}))) or "none")
    print("diagnosis: a partition without a solver result was not attempted or its lock hold ended first; "
          "no partition has a counterexample unless listed as 'solver status FAIL' in results/t1_routed_summary.json")
    print("continue with: T1R_RESUME=1 T1R_SKIP=gls_verilator scripts/t1_routed.sh 200 results")
PY
  echo "$(date +%H:%M:%S) rtl: 11_eqy_routed finished rc=$RC ($(( $(date +%s) - T_START )) s incl. lock waits)" >> logs/run.log
fi
exit $RC
