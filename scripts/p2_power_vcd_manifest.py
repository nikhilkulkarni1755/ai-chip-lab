#!/usr/bin/env python3
"""Manifest of the power-analysis VCDs written by scripts/t1_power_vcd.sh (Part 2, P2.1).

usage: p2_power_vcd_manifest.py [DIR=results/power_vcd]  -> DIR/manifest.json
Everything is read from the files in DIR and from the simulated netlist; the VCDs themselves
are not committed (large, git-ignored), their sha256 is.
"""
import hashlib
import json
import os
import re
import sys

EXPECTED_NETLIST_SHA256 = "f4976d1a6b34a19700dfb0e6246cb8221cf9792255f28f48e41a69dcbd06e293"
NETLIST = "results/part1_snapshot/systolic_os_routed/6_final.v"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "results/power_vcd"
    nsha = sha(NETLIST)
    man = {"stage": "60_power_activity (input)", "generator": "scripts/t1_power_vcd.sh " + d,
           "simulator": "Icarus Verilog, zero-delay gate-level simulation (functional switching only, no glitches)",
           "design": "routed nangate45 systolic_os, one cell module per instance, cell models generated from the pinned Liberty",
           "simulated_netlist": NETLIST, "simulated_netlist_sha256": nsha,
           "simulated_netlist_sha256_is_expected": nsha == EXPECTED_NETLIST_SHA256,
           "vcd_scope": "systolic_os", "testbench": "tb/test_power_vcd.py (results checked against NumPy in the same run)",
           "seed_rule": "numpy default_rng([1234, 2000000000]), the same stream and schedule for every workload",
           "note": "each VCD starts with a $date header written by the simulator, so vcd_sha256 identifies these files; "
                   "a rerun gives the same value changes but a different file hash",
           "workloads": {}}
    ok = man["simulated_netlist_sha256_is_expected"]
    for wl, what in (("random", "uniform INT8 operands"), ("sparse50", "uniform INT8, each element zeroed with p = 0.5"),
                     ("allmax", "every operand 127")):
        j = json.load(open(os.path.join(d, wl + ".json")))
        v = os.path.join(d, wl + ".vcd")
        with open(v, errors="replace") as f:
            head = f.read(4000)
        ts = re.search(r"\$timescale\s+(\S+)\s*\$end", head)
        e = {"data": what, "seed": j["seed"], "cases": {"tiles": j["tiles"], "K": j["K"],
                                                        "matrix_products": j["tiles"], "mac_steps_per_tile": j["K"]},
             "clock_period_ps": j["clock_period_ps"], "clock_cycles": j["clock_cycles"],
             "active_window_ps": j["active_window_ps"], "operand_zero_fraction": j["operand_zero_fraction"],
             "mismatching_elements_vs_numpy": j["mismatching_elements_vs_numpy"],
             "vcd": wl + ".vcd", "vcd_bytes": os.path.getsize(v), "vcd_sha256": sha(v),
             "vcd_timescale": ts.group(1) if ts else None, "json": wl + ".json"}
        ok = ok and e["mismatching_elements_vs_numpy"] == 0
        man["workloads"][wl] = e
    man["ok"] = bool(ok)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(man, f, indent=1)
        f.write("\n")
    print(json.dumps(man, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
