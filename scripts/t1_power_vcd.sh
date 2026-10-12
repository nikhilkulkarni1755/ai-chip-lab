#!/usr/bin/env bash
# Part 2, P2.1 support: switching-activity VCDs of systolic_os for power analysis.
#
#   scripts/t1_power_vcd.sh [OUTDIR=results/power_vcd]
#
# Runs tb/test_power_vcd.py three times (workloads random, sparse50, allmax; seed 1234,
# identical schedule) and writes <OUTDIR>/<workload>.vcd + <workload>.json.
# Default design = the ROUTED netlist (gate-level, zero-delay) so that every net name in
# the VCD is a net of the netlist OpenROAD analyses; T1P_DESIGN=rtl dumps the RTL instead.
#   T1P_SIM      icarus (default for the routed netlist) | verilator (default for T1P_DESIGN=rtl).
#                Verilator did not finish building a model of the routed netlist within a
#                10-minute lock hold (stage 11_eqy_routed: stopped at 760 s and 544 s), Icarus
#                simulates it directly (229 test cases in 67 s there).
#   T1P_NETLIST  routed netlist (default results/part1_snapshot/systolic_os_routed/6_final.v)
#   T1P_CLK_PS   clock period in the VCD, ps (default 4000 = the 4.0 ns routed constraint)
#   T1P_TILES / T1P_K   workload length (default 16 tiles x 32 steps)
# VCD scope of the design: TOP.systolic_os (Verilator) / systolic_os (Icarus).
# Zero-delay simulation: glitches are not modelled, so this is functional switching activity.
# Takes scripts/with_lock.sh unless LAB_LOCK_HELD=1: one hold for the three workloads, each
# limited to T1P_WL_TIMEOUT (default 170 s) so the hold stays under 10 minutes.
set -u -o pipefail
OUT_ARG="${1:-results/power_vcd}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; LAB_DIR="$(cd "$SELF_DIR/.." && pwd)"
LIB_IN_IMAGE=/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
if [ -z "${T1P_INSIDE:-}" ]; then
  cd "$LAB_DIR" || exit 2
  # shellcheck disable=SC1091
  source ./env.sh; source coord/images.env
  if [ -z "${T1P_SIM:-}" ]; then
    if [ "${T1P_DESIGN:-routed}" = routed ]; then T1P_SIM=icarus; else T1P_SIM=verilator; fi
  fi
  export T1P_SIM
  if [ "${LAB_LOCK_HELD:-0}" != 1 ]; then
    exec bash scripts/with_lock.sh rtl env LAB_LOCK_HELD=1 bash scripts/t1_power_vcd.sh "$OUT_ARG"
  fi
  OUT_REL="${OUT_ARG#"$LAB_DIR"/}"; mkdir -p "$OUT_REL/work/cells"; echo '*' > "$OUT_REL/work/.gitignore"
  if [ "${T1P_DESIGN:-routed}" = routed ]; then
    docker run --rm --platform linux/amd64 -v "$LAB_DIR":/lab "$ORFS_IMAGE" \
      cp "$LIB_IN_IMAGE" "/lab/$OUT_REL/work/cells/NangateOpenCellLibrary_typical.lib" || exit 3
  fi
  exec docker run --rm --platform linux/amd64 --cpus 2 -v "$LAB_DIR":/lab -w /lab \
    -e T1P_INSIDE=1 -e PYTHONHASHSEED=0 -e T1P_SIM="$T1P_SIM" -e T1P_DESIGN="${T1P_DESIGN:-routed}" \
    -e T1P_NETLIST="${T1P_NETLIST:-results/part1_snapshot/systolic_os_routed/6_final.v}" \
    -e T1P_CLK_PS="${T1P_CLK_PS:-4000}" -e T1P_TILES="${T1P_TILES:-16}" -e T1P_K="${T1P_K:-32}" \
    "$LAB_SIM_IMAGE" bash scripts/t1_power_vcd.sh "$OUT_REL"
fi
cd "$LAB_DIR" || exit 2
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1
OUT="$OUT_ARG"; WORK="$OUT/work"; mkdir -p "$WORK"
OUT_ABS="$(cd "$OUT" && pwd)"; WORK_ABS="$(cd "$WORK" && pwd)"
GATE=()
if [ "$T1P_DESIGN" = routed ]; then
  yosys -q -p "read_liberty -ignore_miss_func $WORK/cells/NangateOpenCellLibrary_typical.lib; proc; opt_clean; write_verilog -noattr $WORK/cells/nangate45_cells_from_liberty.v" || exit 4
  GATE=(T1_GATE_NETLIST="$LAB_DIR/$T1P_NETLIST" T1_GATE_CELLS="$WORK_ABS/cells/nangate45_cells_from_liberty.v")
fi
rc=0
for wl in random sparse50 allmax; do
  rm -f "$OUT/$wl.vcd" "$OUT/$wl.json" tb/dump.vcd
  if [ "$T1P_SIM" = verilator ]; then
    T1P_WORKLOAD=$wl T1P_JSON="$OUT_ABS/$wl.json" timeout "${T1P_WL_TIMEOUT:-170}" make -C tb SIM=verilator T1_TRACE=1 \
      SIM_BUILD="$WORK_ABS/sim_verilator" COCOTB_TEST_MODULES=test_power_vcd \
      COCOTB_RESULTS_FILE="$WORK_ABS/results_$wl.xml" "${GATE[@]}" > "$WORK/$wl.log" 2>&1 || rc=1
    [ -f tb/dump.vcd ] && mv tb/dump.vcd "$OUT/$wl.vcd"
  else
    T1P_WORKLOAD=$wl T1P_JSON="$OUT_ABS/$wl.json" timeout "${T1P_WL_TIMEOUT:-170}" make -C tb SIM=icarus T1_VCD="$OUT_ABS/$wl.vcd" \
      SIM_BUILD="$WORK_ABS/sim_icarus" COCOTB_TEST_MODULES=test_power_vcd \
      COCOTB_RESULTS_FILE="$WORK_ABS/results_$wl.xml" "${GATE[@]}" > "$WORK/$wl.log" 2>&1 || rc=1
  fi
  if [ -s "$OUT/$wl.vcd" ] && [ -s "$OUT/$wl.json" ]; then
    echo "[t1p] $wl: $(du -h "$OUT/$wl.vcd" | cut -f1) vcd, sha256 $(sha256sum "$OUT/$wl.vcd" | cut -c1-16)…, $(tr -d '\n' < "$OUT/$wl.json" | cut -c1-200)"
  else
    echo "[t1p] $wl: FAILED (see $WORK/$wl.log)"; rc=1
  fi
done
exit $rc
