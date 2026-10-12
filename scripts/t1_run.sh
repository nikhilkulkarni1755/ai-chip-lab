#!/usr/bin/env bash
# Task 1 (stage 10_rtl_verify): INT8 systolic array, bit-exact against NumPy.
#
#   scripts/t1_run.sh [NCASES=10000] [OUTDIR=results]
#
# Runs the whole stage inside the pinned lab-sim container (image ref read from
# coord/images.env at run time): lint, cocotb regression on Icarus and
# Verilator, waveform, SymbiYosys proof of the MAC, Yosys synthesis and EQY
# RTL == netlist (per-PE MAC proof + full-array proof with the MAC black-boxed,
# each with a negative control that must be rejected), then writes <OUTDIR>/t1_summary.json.  Exit code 0 = pass.
#
# * Idempotent and deterministic: every output is rebuilt from scratch, seed
#   1234, PYTHONHASHSEED=0, the CSVs contain no timestamps or paths.
# * OUTDIR may be relative to the lab root or absolute inside it.  Scratch data
#   goes to <OUTDIR>/t1_work (self-ignoring), logs to logs/10_rtl_verify when
#   OUTDIR is the official results/, else to <OUTDIR>/t1_work/logs.
# * Stage markers in results/.stages and demo/assets/t1_waveform.png are only
#   touched by the official configuration (OUTDIR=results, NCASES>=10000, all steps).
#
# Lock use (Part 2): every step (lint, each simulator, waveform, formal, synthesis+EQY MAC,
# EQY array, negative controls, summary) is its own container job under its own
# scripts/with_lock.sh acquisition, so other stages' short jobs interleave; a caller that
# already holds the lock (LAB_LOCK_HELD=1) gets the same steps without re-locking.
# What is computed is unchanged.
#
# Environment knobs:
#   T1_STEPS   space-separated subset of "lint sim wave formal eqy" (default: all).
#              A partial run reports "complete": false and never writes a stage marker.
#   T1_NATIVE  =1: run with a native toolchain on PATH instead of the container
#              (development only; never used for official results).
set -u -o pipefail

NCASES="${1:-10000}"
OUT_ARG="${2:-results}"
STEPS="${T1_STEPS:-lint sim wave formal eqy}"
case "$NCASES" in ''|*[!0-9]*) echo "NCASES must be a non-negative integer" >&2; exit 2 ;; esac

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(cd "$SELF_DIR/.." && pwd)"

# ------------------------------------------------------------------ host side
if [ -z "${T1_INSIDE:-}" ]; then
  cd "$LAB_DIR" || exit 2
  # shellcheck disable=SC1091
  [ -f env.sh ] && source ./env.sh
  case "$OUT_ARG" in
    "$LAB_DIR"/*) OUT_REL="${OUT_ARG#"$LAB_DIR"/}" ;;
    /*) echo "OUTDIR must be inside the lab directory" >&2; exit 2 ;;
    *) OUT_REL="${OUT_ARG%/}" ;;
  esac
  if [ "${T1_NATIVE:-0}" = "1" ]; then
    T1_INSIDE=1 T1_IMAGE_REF="native-dev-toolchain" T1_IMAGE_ID="" \
      exec bash "$LAB_DIR/scripts/t1_run.sh" "$NCASES" "$OUT_REL"
  fi
  # shellcheck disable=SC1091
  [ -f coord/images.env ] && source coord/images.env
  if [ -z "${LAB_SIM_IMAGE:-}" ]; then
    echo "LAB_SIM_IMAGE is not set in coord/images.env (stage 02_images not done?)" >&2
    exit 3
  fi
  IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$LAB_SIM_IMAGE" 2>/dev/null || true)"
  # Part 2 rule: every container job takes the lab-wide lock (one heavy job at a
  # time).  A caller that already holds it says so with LAB_LOCK_HELD=1.
  LOCK=()
  [ "${LAB_LOCK_HELD:-0}" = 1 ] || LOCK=(bash scripts/with_lock.sh rtl env LAB_LOCK_HELD=1)
  phase() {  # phase <name>: one container job = one lock acquisition
    ${LOCK[@]+"${LOCK[@]}"} docker run --rm --platform linux/amd64 --cpus 2 \
      -v "$LAB_DIR":/lab -w /lab \
      -e T1_INSIDE=1 -e T1_PHASE="$1" -e T1_STEPS="$STEPS" -e PYTHONHASHSEED=0 \
      -e T1_IMAGE_REF="$LAB_SIM_IMAGE" -e T1_IMAGE_ID="$IMAGE_ID" \
      "$LAB_SIM_IMAGE" bash scripts/t1_run.sh "$NCASES" "$OUT_REL"
  }
  phase prep || exit $?
  for st in lint:lint sim:sim_verilator sim:sim_icarus wave:waveform formal:formal \
            eqy:eqy_mac eqy:eqy_array eqy:eqy_neg; do
    [[ " $STEPS " == *" ${st%%:*} "* ]] && { phase "${st#*:}" || true; }
  done
  phase finish
  exit $?
fi

# --------------------------------------------------------- inside (container)
cd "$LAB_DIR" || exit 2
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg LC_ALL=C.UTF-8
OUT="$OUT_ARG"
OFFICIAL=0
[ "$OUT" = "results" ] && [ "$NCASES" -ge 10000 ] && [ "$STEPS" = "lint sim wave formal eqy" ] && OFFICIAL=1
WORK="$OUT/t1_work"
if [ "$OUT" = "results" ]; then LOGS="logs/10_rtl_verify"; else LOGS="$WORK/logs"; fi
STAGE="results/.stages/10_rtl_verify"

PHASE="${T1_PHASE:-all}"
in_phase() { [ "$PHASE" = all ] || [ "$PHASE" = "$1" ]; }
if in_phase prep; then                                   # a new run starts here: clean slate
  rm -rf "$WORK"
  rm -f "$OUT"/t1_icarus.csv "$OUT"/t1_verilator.csv "$OUT"/t1_coverage_*.json "$OUT"/t1_lint.txt \
        "$OUT"/t1_summary.json "$OUT"/t1_waveform.png "$OUT"/t1_waveform_case.json
  mkdir -p "$OUT" "$WORK" "$LOGS"
  rm -f "$LOGS"/*.log
  echo '*' > "$WORK/.gitignore"
  : > "$WORK/steps.tsv"; date +%s > "$WORK/t_start"
  if [ "$OFFICIAL" = 1 ]; then
    mkdir -p results/.stages
    rm -f "$STAGE.done" "$STAGE.failed"
    : > "$STAGE.running"
    echo "$(date +%H:%M:%S) rtl: 10_rtl_verify official run started (N=$NCASES, image $T1_IMAGE_REF)" >> logs/run.log
  fi
fi
mkdir -p "$OUT" "$WORK" "$LOGS"
OUT_ABS="$(cd "$OUT" && pwd)"
WORK_ABS="$(cd "$WORK" && pwd)"

tmo() {  # tmo <seconds> <cmd...>
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@"
  else perl -e 'alarm shift; exec @ARGV' "$secs" "$@"; fi
}
want() { case " $STEPS " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
step() {  # step <name> <timeout-seconds> <function> [args]   (records rc + wall seconds;
          # the function wraps its tool calls in: tmo "$TMO" ...)
  local name="$1" secs="$2" t0 rc; shift 2
  t0=$(date +%s)
  echo "[t1] $name ..."
  TMO="$secs"
  "$@" > "$LOGS/$name.log" 2>&1
  rc=$?
  printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" >> "$WORK/steps.tsv"
  echo "[t1] $name: rc=$rc, $(( $(date +%s) - t0 )) s"
  return $rc
}
T_START=$(cat "$WORK/t_start" 2>/dev/null || date +%s)

# The OSS CAD Suite launchers export PYTHONHOME for the suite's private Python.
# cocotb embeds the lab's own Python (venv with numpy, cocotb-coverage) into
# vvp, so Icarus is started through copies of the launchers without those lines.
if grep -q PYTHONHOME "$(command -v vvp)" 2>/dev/null; then
  SUITE_BIN="$(cd "$(dirname "$(command -v vvp)")" && pwd)"
  mkdir -p "$WORK/icarus-shim"
  for t in iverilog vvp; do
    sed -e "s#^release_bindir=.*#release_bindir=\"$SUITE_BIN\"#" \
        -e '/PYTHONHOME/d' -e '/PYTHONEXECUTABLE/d' "$SUITE_BIN/$t" > "$WORK/icarus-shim/$t"
    chmod +x "$WORK/icarus-shim/$t"
  done
  export PATH="$WORK_ABS/icarus-shim:$PATH"
fi
# Apple clang needs <cstddef> for Verilator's headers (native development only).
[ "$(uname)" = "Darwin" ] && export T1_VERILATOR_EXTRA='-CFLAGS "-include cstddef -std=gnu++20"'

RTL="rtl/mac_int8.sv rtl/systolic_os.sv"

# ------------------------------------------------------------------- 1. lint
lint() {
  local rc=0 n
  run() { echo "\$ $*"; tmo "$TMO" "$@" 2>&1; n=$?; echo "[exit code $n]"; echo; [ $n -eq 0 ] || rc=1; }
  # shellcheck disable=SC2086
  {
    run verilator --lint-only -Wall --top-module systolic_os $RTL
    run verilator --lint-only -Wall --top-module systolic_os -GR=1 -GC=1 $RTL
    run verilator --lint-only -Wall --top-module systolic_os -GR=3 -GC=5 $RTL
    run verible-verilog-lint --rules_config rtl/.rules.verible_lint $RTL
    echo "# verible rule configuration and justifications (rtl/.rules.verible_lint):"
    cat rtl/.rules.verible_lint
  } > "$OUT/t1_lint.txt"
  cat "$OUT/t1_lint.txt"
  return $rc
}
want lint && in_phase lint && step lint 300 lint

# -------------------------------------------------------------------- 2. sim
sim() {  # sim <icarus|verilator>
  T1_NCASES="$NCASES" T1_SEED=1234 \
  T1_CSV="$OUT_ABS/t1_$1.csv" T1_COV="$OUT_ABS/t1_coverage_$1.json" \
    tmo "$TMO" make -C tb SIM="$1" SIM_BUILD="$WORK_ABS/sim_$1" COCOTB_RESULTS_FILE="$WORK_ABS/results_$1.xml"
}
if want sim; then
  in_phase sim_verilator && step sim_verilator 1800 sim verilator
  in_phase sim_icarus && step sim_icarus 3000 sim icarus
fi

# --------------------------------------------------------------- 3. waveform
wave() {
  T1_WAVE_JSON="$OUT_ABS/t1_waveform_case.json" \
    tmo "$TMO" make -C tb SIM=icarus SIM_BUILD="$WORK_ABS/sim_wave" COCOTB_TEST_MODULES=test_waveform \
      T1_VCD="$WORK_ABS/t1_small_case.vcd" COCOTB_RESULTS_FILE="$WORK_ABS/results_wave.xml" || return 1
  python3 scripts/t1_waveform.py "$WORK/t1_small_case.vcd" "$OUT/t1_waveform_case.json" \
    "$OUT/t1_waveform.png"
}
want wave && in_phase waveform && step waveform 600 wave

# ----------------------------------------------------------------- 4. formal
formal() { (cd formal && tmo "$TMO" sby -f -j 2 --prefix "$WORK_ABS/formal/mac" mac.sby); }
# Negative control: the same properties must FAIL on a MAC with an injected bug.
formal_neg() {
  local d="$WORK_ABS/neg_formal" rc
  rm -rf "$d"; mkdir -p "$d"
  sed -e "s/acc <= acc + 32'(prod);/acc <= acc + 32'(prod) + 32'sd1;/" rtl/mac_int8.sv > "$d/mac_int8.sv"
  if cmp -s rtl/mac_int8.sv "$d/mac_int8.sv"; then echo "mutation did not apply"; return 90; fi
  echo "injected bug:"; diff rtl/mac_int8.sv "$d/mac_int8.sv"
  sed -e "s#^\.\./rtl/mac_int8\.sv#$d/mac_int8.sv#" -e "s#^mac_formal\.sv#$LAB_DIR/formal/mac_formal.sv#" \
    formal/mac.sby > "$d/mac.sby"
  (cd "$d" && tmo "$TMO" sby -f mac.sby bmc)
  rc=$?
  echo "sby exit code: $rc (non-zero expected)"
  [ $rc -ne 0 ] && [ $rc -ne 124 ]
}
if want formal && in_phase formal; then
  step formal 2400 formal
  step formal_neg 600 formal_neg
fi

# ---------------------------------------------------------- 5. synth + EQY
synth() {
  tmo "$TMO" yosys -q -l "$WORK/synth.log" -p "script eqy/synth.ys; tee -q -o $WORK/synth_stat.json stat -json; write_verilog -noattr $WORK/systolic_os_netlist.v"
}
equiv() {  # equiv <mac_int8|systolic_os>
  sed -e "s#@RTL@#$LAB_DIR/rtl#g" -e "s#@NETLIST@#$WORK_ABS/systolic_os_netlist.v#g" \
    "eqy/$1.eqy.in" > "$WORK/$1.eqy"
  tmo "$TMO" eqy -f -j 2 -d "$WORK/eqy_$1" "$WORK/$1.eqy"
}
# Negative controls: the same EQY flow must REJECT a deliberately broken RTL.
# One bug is injected into a copy of the RTL and only the partition that
# contains it is checked (apply <partition>); the expected outcome is
# "Could not prove equivalence" for that partition (verified by t1_summary.py).
equiv_neg() {  # equiv_neg <mac_int8|systolic_os> <file to mutate> <sed expr> <partition>
  local d="$WORK_ABS/neg_$1"
  rm -rf "$d"; mkdir -p "$d/rtl"
  cp rtl/mac_int8.sv rtl/systolic_os.sv "$d/rtl/"
  sed -e "$3" "rtl/$2" > "$d/rtl/$2"
  if cmp -s "rtl/$2" "$d/rtl/$2"; then echo "mutation did not apply to $2"; return 90; fi
  echo "injected bug:"; diff "rtl/$2" "$d/rtl/$2"
  sed -e "s#@RTL@#$d/rtl#g" -e "s#@NETLIST@#$WORK_ABS/systolic_os_netlist.v#g" \
    "eqy/$1.eqy.in" > "$d/$1.eqy"
  printf 'apply %s\n\n[strategy skip]\nuse dummy\n' "$4" >> "$d/$1.eqy"
  tmo "$TMO" eqy -f -j 2 -d "$d/eqy" "$d/$1.eqy"
  local rc=$?
  echo "eqy exit code: $rc (non-zero expected)"
  [ $rc -ne 0 ] && [ $rc -ne 124 ]
}
if want eqy; then
  if in_phase eqy_mac; then
    step synth 900 synth && step eqy_mac 1800 equiv mac_int8
  fi
  if [ -s "$WORK/systolic_os_netlist.v" ]; then
    in_phase eqy_array && step eqy_array 2400 equiv systolic_os
    if in_phase eqy_neg; then
      step eqy_neg_mac 900 equiv_neg mac_int8 mac_int8.sv \
        "s/acc <= acc + 32'(prod);/acc <= acc + 32'(prod) + 32'sd1;/" mac_int8.acc
      step eqy_neg_array 900 equiv_neg systolic_os systolic_os.sv \
        "s/a_q <= a_w\\[i\\]\\[j\\];/a_q <= a_w[i][j] ^ 8'd1;/" systolic_os.g_row.0.g_col.0.g_east.a_q
    fi
  fi
fi

# ---------------------------------------------------------------- 6. summary
in_phase finish || exit 0
python3 scripts/t1_summary.py --out "$OUT" --work "$WORK" --logs "$LOGS" --ncases "$NCASES" \
  --steps "$STEPS" --wall "$(( $(date +%s) - T_START ))"
RC=$?
if [ "$OFFICIAL" = 1 ]; then
  rm -f "$STAGE.running"
  if [ $RC -eq 0 ]; then
    mkdir -p demo/assets && cp "$OUT/t1_waveform.png" demo/assets/t1_waveform.png
    python3 -c "import json;d=json.load(open('results/t1_summary.json'));print('pass', d['pass'], 'cases', d['values']['cases_total'], 'csv_sha256', d['values']['csv_sha256_icarus'])" > "$STAGE.done"
  fi
  echo "$(date +%H:%M:%S) rtl: 10_rtl_verify official run finished rc=$RC ($(( $(date +%s) - T_START )) s)" >> logs/run.log
fi
exit $RC
