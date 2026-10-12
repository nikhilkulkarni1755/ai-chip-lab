#!/usr/bin/env python3
"""t2_repro_compare.py <platform> <design> [variant=base] -- compare a fresh ORFS run against every earlier run.
Earlier runs = results/part1_snapshot/<plat>_<design>_*/ (metadata.json + hashes.json). Fields compared: all of
metadata.json except wall-clock/CPU/memory/profiling/uuid (t2_extract.NONDET); GDS compared by sha256 with GDSII
timestamp records zeroed. Writes results/repro/t2_<plat>_<design>.json:
  {runs, identical, comparisons:[{vs, identical, differing_fields, localized_stages, gds_identical}], ...}
Any difference is a determinism finding (verdict stays DIFFERENT) and is localized by flow stage (key prefix) and
NUM_CORES of both runs."""
import glob, json, os, sys
LAB = os.path.expanduser("~/ai-chip-lab"); sys.path.insert(0, os.path.join(LAB, "scripts"))
import t2_extract as X
plat, des = sys.argv[1], sys.argv[2]; var = sys.argv[3] if len(sys.argv) > 3 else "base"
P = X.paths(plat, des, var); new = X.rd(P["meta"])
newrun = X.rd(P["run"]) if os.path.exists(P["run"]) else {}
ngds = X.gds_norm_sha256(P["gds"]) if os.path.exists(P["gds"]) else None
comps = []
for d in sorted(glob.glob(os.path.join(LAB, "results", "part1_snapshot", f"{plat}_{des}_*"))):
    old = X.rd(os.path.join(d, "metadata.json")); h = X.rd(os.path.join(d, "hashes.json"))
    oldrun = X.rd(os.path.join(d, "t2_run.json")) if os.path.exists(os.path.join(d, "t2_run.json")) else {}
    diffs = {k: [old.get(k), new.get(k)] for k in sorted(set(old) | set(new)) if not X.NONDET.search(k) and old.get(k) != new.get(k)}
    gi = ngds is not None and ngds == h.get("gds_sha256_timestamps_zeroed")
    comps.append({"vs": os.path.basename(d), "identical": (not diffs) and gi, "differing_fields": diffs,
                  "localized_stages": sorted({k.split("__")[0] for k in diffs}), "gds_identical_ignoring_timestamps": gi,
                  "num_cores": [oldrun.get("num_cores"), newrun.get("num_cores")]})
out = {"platform": plat, "design": des, "new_run_variant": var, "runs": len(comps) + 1,
       "identical": bool(comps) and all(c["identical"] for c in comps),
       "verdict": "IDENTICAL" if comps and all(c["identical"] for c in comps) else "DIFFERENT",
       "new_gds_sha256_timestamps_zeroed": ngds, "comparisons": comps,
       "compare_rule": "all metadata.json fields except wall-clock/cpu/memory/profiling(_s)/uuid; GDS with GDSII BGNLIB/BGNSTR timestamps zeroed"}
os.makedirs(os.path.join(LAB, "results", "repro"), exist_ok=True)
json.dump(out, open(os.path.join(LAB, "results", "repro", f"t2_{plat}_{des}.json"), "w"), indent=2)
print(json.dumps({k: out[k] for k in ("platform", "design", "runs", "verdict")}), [ (c["vs"], c["identical"], len(c["differing_fields"])) for c in comps])
sys.exit(0 if out["identical"] else 1)
