#!/usr/bin/env python3
"""Evidence: the Part 1 bundled Task 3 runs have zero stalls. Reads committed results/t3."""
import configparser, csv, os, sys
LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print("$ scripts/t3_orig_stall_evidence.py   # Part 1 bundled runs: google.cfg 256x256, alexnet.csv")
for df in ("ws", "os", "is"):
    d = os.path.join(LAB, "results/t3/scalesim", df)
    cp = configparser.ConfigParser(); cp.optionxform = str; cp.read(os.path.join(d, "config.cfg"))
    a = cp["architecture_presets"]
    print(f"== {df}: InterfaceBandwidth={cp['run_presets']['InterfaceBandwidth']} Bandwidth={a['Bandwidth']} "
          f"SRAM kB ifmap/filter/ofmap={a['IfmapSramSzkB']}/{a['FilterSramSzkB']}/{a['OfmapSramSzkB']}")
    rows = list(csv.reader(open(os.path.join(d, "COMPUTE_REPORT.csv"))))[1:]
    print("   Stall Cycles per layer:", [int(float(r[3])) for r in rows if r])
    bw = list(csv.reader(open(os.path.join(d, "BANDWIDTH_REPORT.csv"))))[1:]
    print("   Avg IFMAP/FILTER DRAM BW per layer:", [(round(float(r[4]), 2), round(float(r[5]), 2)) for r in bw if r])
