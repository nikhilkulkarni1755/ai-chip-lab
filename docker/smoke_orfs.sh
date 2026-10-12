#!/bin/bash
# Runs INSIDE the ORFS image. Prints "<status> <tool> <version>"; exit 1 if any required item is missing.
fail=0
[ -f /OpenROAD-flow-scripts/env.sh ] && . /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1
v() { local name="$1"; shift; local out; out=$("$@" 2>&1 | grep -v '^[[:space:]]*$' | head -1)
  if [ -n "$out" ] && command -v "$1" >/dev/null 2>&1; then printf 'OK    %-22s %s\n' "$name" "$out"; else printf 'MISS  %-22s %s\n' "$name" "${out:-not found}"; fail=1; fi; }
p() { if [ -e "$2" ]; then printf 'OK    %-22s %s\n' "$1" "$2"; else printf 'MISS  %-22s %s\n' "$1" "$2"; fail=1; fi; }
v orfs:openroad    openroad -version
v orfs:yosys       yosys -V
v orfs:opensta     sh -c 'echo "puts \"OpenSTA [sta::version] (embedded in openroad)\"" > /tmp/v.tcl; openroad -no_init -exit /tmp/v.tcl 2>&1 | grep OpenSTA'
v orfs:klayout     klayout -v
v orfs:make        make --version
v orfs:python3     python3 --version
p orfs:flow        /OpenROAD-flow-scripts/flow/Makefile
p orfs:gcd-ng45    /OpenROAD-flow-scripts/flow/designs/nangate45/gcd/config.mk
p orfs:gcd-rules   /OpenROAD-flow-scripts/flow/designs/nangate45/gcd/rules-base.json
p orfs:gcd-sky130  /OpenROAD-flow-scripts/flow/designs/sky130hd/gcd/config.mk
p orfs:checker     /OpenROAD-flow-scripts/flow/util/checkMetadata.py
p orfs:qor-checker /OpenROAD-flow-scripts/flow/util/checkQorMetrics.py
exit $fail
