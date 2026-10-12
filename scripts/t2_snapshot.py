#!/usr/bin/env python3
"""Part 2 snapshot of Part 1 ORFS runs, taken BEFORE any rerun overwrites orfs/work.
Writes results/part1_snapshot/<plat>_<design>_<run>/{metadata.json,t2_run.json,hashes.json[,6_final.v]} and
results/part1_snapshot/index.json. Never overwrites an existing snapshot. Big files (GDS/ODB) are not copied: sha256
(raw and GDSII-timestamps-zeroed) are recorded; 6_final.v (routed netlist) is copied if < 8 MB (else gitignored copy
under orfs/work + hash)."""
import hashlib, json, os, shutil, sys
LAB = os.path.expanduser("~/ai-chip-lab"); sys.path.insert(0, os.path.join(LAB, "scripts"))
import t2_extract as X
S = os.path.join(LAB, "results", "part1_snapshot"); os.makedirs(S, exist_ok=True)
runs = [("nangate45", "gcd", "run1", "run1"), ("nangate45", "gcd", "base", "run2"),
        ("sky130hd", "gcd", "run1", "run1"), ("sky130hd", "gcd", "base", "run2"),
        ("nangate45", "systolic_os", "base", "final_rtl_cebd174")]
idx = {}
for plat, des, var, tag in runs:
    d = os.path.join(S, f"{plat}_{des}_{tag}")
    P = X.paths(plat, des, var)
    if not os.path.exists(P["meta"]): print("missing", plat, des, var); continue
    if os.path.exists(os.path.join(d, "hashes.json")): idx[f"{plat}/{des}/{tag}"] = json.load(open(os.path.join(d, "hashes.json"))); continue
    os.makedirs(d)
    shutil.copy(P["meta"], os.path.join(d, "metadata.json"))
    if os.path.exists(P["run"]): shutil.copy(P["run"], os.path.join(d, "t2_run.json"))
    h = {"source_variant": var, "part1_run": tag}
    if os.path.exists(P["gds"]):
        h.update(gds_bytes=os.path.getsize(P["gds"]), gds_sha256_raw=X.sha256(P["gds"]), gds_sha256_timestamps_zeroed=X.gds_norm_sha256(P["gds"]))
    nv = os.path.join(X.WORK, "results", plat, des, var, "6_final.v")
    if os.path.exists(nv):
        h.update(netlist_6_final_v_sha256=X.sha256(nv), netlist_bytes=os.path.getsize(nv))
        if os.path.getsize(nv) < 8 << 20: shutil.copy(nv, os.path.join(d, "6_final.v"))
    json.dump(h, open(os.path.join(d, "hashes.json"), "w"), indent=2)
    idx[f"{plat}/{des}/{tag}"] = h
json.dump(idx, open(os.path.join(S, "index.json"), "w"), indent=2); print(json.dumps(idx, indent=1))
