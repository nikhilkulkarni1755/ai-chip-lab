#!/bin/bash
# Runs INSIDE lab-sim. Prints "<status> <tool> <version>" per required tool; exit 1 if any is missing.
fail=0
v() { # name, command...
  local name="$1"; shift
  local out; out=$("$@" 2>&1 | grep -v '^[[:space:]]*$' | head -1)
  if [ -n "$out" ] && command -v "$1" >/dev/null 2>&1 && ! echo "$out" | grep -qiE 'not found|could not|error|no such'; then printf 'OK    %-22s %s\n' "$name" "$out"; else printf 'MISS  %-22s %s\n' "$name" "${out:-not found}"; fail=1; fi
}
v yosys            yosys -V
v abc              sh -c 'yosys-abc -q "version" 2>&1 || true; command -v yosys-abc'
v verilator        verilator --version
v iverilog         iverilog -V
v vvp              vvp -V
v sby              sby --version
v eqy              eqy --version
v yosys-smtbmc     sh -c 'yosys-smtbmc --help 2>&1 | grep -q yosys_smt2_output && echo "present (no --version flag; ships with $(yosys -V | cut -d" " -f1-2))"'
v boolector        boolector --version
v bitwuzla         bitwuzla --version
v yices            yices --version
v yices-smt2       yices-smt2 --version
v z3               z3 --version
v ghdl             ghdl --version
v nextpnr-ice40    nextpnr-ice40 --version
v nextpnr-ecp5     nextpnr-ecp5 --version
# gtkwave is a GUI: it cannot print a version without a display, so report the binary + suite build instead (optional tool)
v gtkwave          sh -c 'command -v gtkwave >/dev/null && echo "present (GUI, no headless --version); OSS CAD Suite build $(cat /opt/oss-cad-suite/VERSION)"'
v oss-cad-suite    cat /opt/oss-cad-suite/VERSION
v which-vvp        sh -c 'command -v vvp'
v verible-lint     verible-verilog-lint --version
v verible-format   verible-verilog-format --version
v make             make --version
v g++              g++ --version
v git              git --version
v uv               uv --version
v python3          python3 --version
v cocotb-config    cocotb-config --version
python3 - <<'PY' || fail=1
import importlib.metadata as md, sys
bad = 0
for dist, mod in [("cocotb","cocotb"),("cocotb-coverage","cocotb_coverage"),("pytest","pytest"),("numpy","numpy"),
                  ("ml_dtypes","ml_dtypes"),("pandas","pandas"),("matplotlib","matplotlib"),("scalesim","scalesim"),
                  ("vcdvcd","vcdvcd"),("pyyaml","yaml"),("numba","numba")]:
    try:
        __import__(mod); print("OK    %-22s %s" % ("py:" + dist, md.version(dist)))
    except Exception as e:
        bad = 1; print("MISS  %-22s %r" % ("py:" + dist, e))
sys.exit(bad)
PY
# functional self-test: cocotb on both simulators, lint, synthesis
bash "$(dirname "$0")/lab-sim/selftest/run.sh" || fail=1
bash "$(dirname "$0")/lab-sim/selftest/scalesim_probe.sh" || fail=1
exit $fail
