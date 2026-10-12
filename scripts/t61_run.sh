#!/usr/bin/env bash
# Stage 61_pe_bf16 (Part 2, P2.2): bf16 x bf16 -> FP32 MAC, bit-exact against the golden model.
#
#   scripts/t61_run.sh [NCASES=10000] [OUTDIR=results]
#
# Runs in the pinned lab-sim container.  Every step (lint + oracle cross-check, each
# simulator, negative control, summary) is its own container job under its own
# scripts/with_lock.sh acquisition (unless LAB_LOCK_HELD=1), like scripts/t1_run.sh:
# lint, oracle cross-check (golden vs exact-rational reference), cocotb on Verilator and
# Icarus, a negative control (tie rule broken in an RTL copy must be detected), then
# scripts/t61_summary.py fills results into <OUTDIR>/p2_61_pe_bf16_summary.json next to the
# pass criteria that were committed before the first run.  The ORFS part of the stage
# (area / power / clock vs the INT8 MAC) is a separate step.
set -u -o pipefail
NCASES="${1:-10000}"; OUT_ARG="${2:-results}"
case "$NCASES" in ''|*[!0-9]*) echo "NCASES must be a non-negative integer" >&2; exit 2 ;; esac
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; LAB_DIR="$(cd "$SELF_DIR/.." && pwd)"
if [ -z "${T61_INSIDE:-}" ]; then
  cd "$LAB_DIR" || exit 2
  # shellcheck disable=SC1091
  source ./env.sh; source coord/images.env
  : "${LAB_SIM_IMAGE:?not set in coord/images.env}"
  case "$OUT_ARG" in "$LAB_DIR"/*) OUT_REL="${OUT_ARG#"$LAB_DIR"/}" ;; /*) echo "OUTDIR must be inside the lab" >&2; exit 2 ;; *) OUT_REL="${OUT_ARG%/}" ;; esac
  LOCK=(); [ "${LAB_LOCK_HELD:-0}" = 1 ] || LOCK=(bash scripts/with_lock.sh rtl env LAB_LOCK_HELD=1)
  IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$LAB_SIM_IMAGE" 2>/dev/null || true)"
  phase() {  # phase <name>: one container job = one lock acquisition
    ${LOCK[@]+"${LOCK[@]}"} docker run --rm --platform linux/amd64 --cpus 2 -v "$LAB_DIR":/lab -w /lab \
      -e T61_INSIDE=1 -e T61_PHASE="$1" -e PYTHONHASHSEED=0 -e T61_IMAGE_REF="$LAB_SIM_IMAGE" -e T61_IMAGE_ID="$IMAGE_ID" \
      "$LAB_SIM_IMAGE" bash scripts/t61_run.sh "$NCASES" "$OUT_REL"
  }
  phase prep || exit $?
  for ph in sim_verilator sim_icarus neg_control; do phase "$ph" || true; done
  phase finish
  exit $?
fi
PHASE="${T61_PHASE:-all}"
in_phase() { [ "$PHASE" = all ] || [ "$PHASE" = "$1" ]; }
cd "$LAB_DIR" || exit 2
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 LC_ALL=C.UTF-8
OUT="$OUT_ARG"; WORK="$OUT/t61_work"
OFFICIAL=0; [ "$OUT" = results ] && [ "$NCASES" -ge 10000 ] && OFFICIAL=1
if [ "$OUT" = results ]; then LOGS="logs/part2/61_pe_bf16"; else LOGS="$WORK/logs"; fi
STAGE="results/.stages/61_pe_bf16"
if in_phase prep; then   # a new run starts here: clean slate
  rm -rf "$WORK"; mkdir -p "$OUT" "$WORK" "$LOGS"; echo '*' > "$WORK/.gitignore"
  rm -f "$OUT"/t61_verilator.csv "$OUT"/t61_icarus.csv "$OUT"/t61_coverage_*.json "$OUT"/t61_lint.txt "$LOGS"/step_*.log
  : > "$WORK/steps.tsv"; date +%s > "$WORK/t_start"
  if [ "$OFFICIAL" = 1 ]; then rm -f "$STAGE.done" "$STAGE.failed"; : > "$STAGE.running"; fi
fi
mkdir -p "$OUT" "$WORK" "$LOGS"
OUT_ABS="$(cd "$OUT" && pwd)"; WORK_ABS="$(cd "$WORK" && pwd)"
step() { local name="$1" secs="$2" t0 rc; shift 2; t0=$(date +%s); echo "[t61] $name ..."; TMO="$secs"
  "$@" > "$LOGS/step_$name.log" 2>&1; rc=$?
  printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - t0 ))" >> "$WORK/steps.tsv"
  echo "[t61] $name: rc=$rc, $(( $(date +%s) - t0 )) s"; return $rc; }
T_START=$(cat "$WORK/t_start" 2>/dev/null || date +%s)

lint() {
  local rc=0 n
  run() { echo "\$ $*"; timeout "$TMO" "$@" 2>&1; n=$?; echo "[exit code $n]"; echo; [ $n -eq 0 ] || rc=1; }
  { run verilator --lint-only -Wall --top-module mac_bf16 rtl/mac_bf16.sv
    run verible-verilog-lint --rules_config rtl/.rules.verible_lint rtl/mac_bf16.sv; } > "$OUT/t61_lint.txt"
  cat "$OUT/t61_lint.txt"; return $rc
}
oracle() { timeout "$TMO" python3 scripts/t61_oracle_check.py 20000 "$WORK/oracle_check.json"; }
sim() {  # sim <simulator> <rtl dir> <tag> <ncases>
  T61_NCASES="$4" T61_CSV="$5/t61_$3.csv" T61_COV="$5/t61_coverage_$3.json" \
    timeout "$TMO" make -C tb SIM="$1" T1_SOURCES=mac_bf16.sv T61_RTL_DIR="$2" COCOTB_TOPLEVEL=mac_bf16 \
      COCOTB_TEST_MODULES=test_mac_bf16 SIM_BUILD="$WORK_ABS/sim_$3" COCOTB_RESULTS_FILE="$WORK_ABS/results_$3.xml"
}
# Negative control: round-half-up instead of round-half-to-even in a copy of the RTL.
neg() {
  mkdir -p "$WORK/neg_rtl"
  sed -e 's/assign round_up = norm\[2\] & (norm\[1\] | norm\[0\] | norm\[3\]);/assign round_up = norm[2];/' rtl/mac_bf16.sv > "$WORK/neg_rtl/mac_bf16.sv"
  if cmp -s rtl/mac_bf16.sv "$WORK/neg_rtl/mac_bf16.sv"; then echo "mutation did not apply"; return 90; fi
  echo "injected bug:"; diff rtl/mac_bf16.sv "$WORK/neg_rtl/mac_bf16.sv"
  sim icarus "$WORK_ABS/neg_rtl" neg 300 "$WORK_ABS"; local rc=$?
  echo "make exit code: $rc (non-zero expected: the testbench must report mismatches)"
  [ $rc -ne 0 ] && [ $rc -ne 124 ]
}
# Step time limits stay under the 10-minute lock-hold rule; a simulator that needs longer
# for NCASES fails its step (reported as such) rather than holding the queue.
in_phase prep && { step lint 120 lint; step oracle 300 oracle; }
in_phase sim_verilator && step sim_verilator 570 sim verilator "" verilator "$NCASES" "$OUT_ABS"
in_phase sim_icarus && step sim_icarus 570 sim icarus "" icarus "$NCASES" "$OUT_ABS"
in_phase neg_control && step neg_control 300 neg
in_phase finish || exit 0
python3 scripts/t61_summary.py --out "$OUT" --work "$WORK" --logs "$LOGS" --ncases "$NCASES" --wall "$(( $(date +%s) - T_START ))"
RC=$?
if [ "$OFFICIAL" = 1 ]; then rm -f "$STAGE.running"; echo "$(date +%H:%M:%S) rtl: 61_pe_bf16 verification finished rc=$RC" >> logs/run.log; fi
exit $RC
