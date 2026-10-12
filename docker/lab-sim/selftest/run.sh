#!/bin/bash
# Runs INSIDE lab-sim: proves cocotb drives both simulators and lint/formal entry points start.
set -uo pipefail
cd "$(dirname "$0")"; rc=0
for sim in icarus verilator; do
  log=/tmp/selftest_$sim.log
  make SIM=$sim > "$log" 2>&1
  if grep -q 'TESTS=1 PASS=1 FAIL=0' "$log"; then echo "OK    cocotb+$sim   $(grep -o 'PROBE sim.*' "$log" | head -1)"; else echo "FAIL  cocotb+$sim"; tail -25 "$log"; rc=1; fi
done
verilator --lint-only -Wall mac_probe.sv >/tmp/selftest_lint.log 2>&1 && echo "OK    verilator --lint-only -Wall (0 warnings)" || { cat /tmp/selftest_lint.log; rc=1; }
verible-verilog-lint mac_probe.sv && echo "OK    verible-verilog-lint" || rc=1
cells=$(yosys -p 'read_verilog -sv mac_probe.sv; synth -top mac_probe; abc; opt; stat' 2>&1 | grep -E '^ +[0-9]+ +cells$|Number of cells' | tail -1 | tr -s ' ')
[ -n "$cells" ] && echo "OK    yosys synth+abc+opt   $cells" || { echo "FAIL  yosys synth"; rc=1; }
exit $rc
