#!/usr/bin/env python3
"""t2_reruns.py -- build results/t2_reruns.json (P1.4) from the Part 1 snapshot + every later run stored by
t2_repro_compare.py (results/repro/runs/*). Append-friendly: each new run (e.g. infra's `make t2`) goes through
t2_repro.sh, which stores it; rerun this script to regenerate. All pairwise comparisons use t2_extract.NONDET exclusion and
GDS with timestamps zeroed. Also writes results/evidence/51_determinism_reruns.txt."""
import glob, itertools, json, os, sys
LAB = os.path.expanduser("~/ai-chip-lab"); sys.path.insert(0, os.path.join(LAB, "scripts"))
import t2_extract as X
image = dict(l.strip().split("=", 1) for l in open(os.path.join(LAB, "coord", "images.env")) if "=" in l and not l.startswith("#"))["ORFS_IMAGE"]
designs = {}; lines = []
for plat, des in [("nangate45", "gcd"), ("sky130hd", "gcd"), ("nangate45", "systolic_os")]:
    dirs = sorted(glob.glob(os.path.join(LAB, "results", "part1_snapshot", f"{plat}_{des}_*"))) + \
           sorted(glob.glob(os.path.join(LAB, "results", "repro", "runs", f"{plat}_{des}_p2_*")), key=lambda d: int(d.rsplit("_", 1)[1]))
    runs = []
    for d in dirs:
        h = X.rd(os.path.join(d, "hashes.json")); md = X.rd(os.path.join(d, "metadata.json"))
        rj = X.rd(os.path.join(d, "t2_run.json")) if os.path.exists(os.path.join(d, "t2_run.json")) else {}
        runs.append({"run_id": os.path.basename(d).replace(f"{plat}_{des}_", ""), "origin": "part1" if "part1" in d else "part2",
                     "gds_sha256_timestamps_zeroed": h["gds_sha256_timestamps_zeroed"], "num_cores": rj.get("num_cores"),
                     "image": rj.get("image"), "rtl_sha256": rj.get("rtl_sha256"), "_md": md})
    pairs = []; allfields = {}
    for a, b in itertools.combinations(runs, 2):
        diffs = {k: [a["_md"].get(k), b["_md"].get(k)] for k in sorted(set(a["_md"]) | set(b["_md"])) if not X.NONDET.search(k) and a["_md"].get(k) != b["_md"].get(k)}
        n = len([k for k in set(a["_md"]) | set(b["_md"]) if not X.NONDET.search(k)])
        gi = a["gds_sha256_timestamps_zeroed"] == b["gds_sha256_timestamps_zeroed"]
        pairs.append({"a": a["run_id"], "b": b["run_id"], "compared_fields": n, "identical_fields": n - len(diffs), "differing_fields": diffs,
                      "gds_identical_ignoring_timestamps": gi, "identical": (not diffs) and gi})
        allfields.update(diffs)
    for r in runs: r.pop("_md")
    ident = bool(pairs) and all(p["identical"] for p in pairs)
    designs[f"{plat}/{des}"] = {"runs": runs, "run_count": len(runs), "pairs": pairs, "verdict": "identical" if ident else "different",
        "differing_fields": allfields, "image": image,
        "compare_rule": "all metadata.json fields except wall-clock/cpu/memory/profiling(_s)/uuid; GDS with GDSII timestamp records zeroed",
        "note": "run1/run2 = Part 1 (first/second clean run; systolic_os: the single final-RTL run); p2_<epoch> = Part 2 clean reruns, same image digest, NUM_CORES=3"
                + ("" if ident else " -- DIFFERENCE FOUND, localized by stage prefix in differing_fields (FAIL, not hidden)")}
    lines.append(f"{plat}/{des}: {len(runs)} runs, verdict {designs[f'{plat}/{des}']['verdict']}")
    for p in pairs: lines.append(f"   {p['a']} vs {p['b']}: {p['identical_fields']}/{p['compared_fields']} fields identical, GDS(ts-zeroed) identical={p['gds_identical_ignoring_timestamps']}")
    for r in runs: lines.append(f"   run {r['run_id']}: gds {r['gds_sha256_timestamps_zeroed'][:16]}… cores={r['num_cores']}")
json.dump({"designs": designs, "image": image}, open(os.path.join(LAB, "results", "t2_reruns.json"), "w"), indent=2)
open(os.path.join(LAB, "results", "evidence", "51_determinism_reruns.txt"), "w").write("\n".join(lines[-60:]) + "\n")
print("\n".join(lines))
