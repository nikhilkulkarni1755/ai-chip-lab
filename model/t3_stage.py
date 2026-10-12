#!/usr/bin/env python3
"""Task 3 stage body (runs inside the lab-sim container; see scripts/t3_run.sh).

  t3_stage.py pass    --out DIR    SCALE-Sim bundled runs (+fit, +roofline) into DIR
  t3_stage.py summary --out DIR --rerun DIR2   compare passes, write summary JSON + plots
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

BUNDLED_CFG = "configs/google.cfg"           # TPU-v1-like: 256x256, os, 6 MiB/6 MiB/2 MiB SRAM
BUNDLED_TOPO = "topologies/conv_nets/alexnet.csv"
DATAFLOWS = ["ws", "os", "is"]
REPORTS = ["COMPUTE_REPORT.csv", "BANDWIDTH_REPORT.csv", "DETAILED_ACCESS_REPORT.csv"]


def _bundled_one(args):
    df, out = args
    d = os.path.join(out, "scalesim", df)
    os.makedirs(d, exist_ok=True)
    cfg = sim.make_config(os.path.join(d, "config.cfg"), os.path.join(sim.SCALESIM_SRC, BUNDLED_CFG),
                          256, 256, df, run_name=f"tpu_{df}")
    # make_config rewrites only ArrayHeight/Width (same values) and Dataflow; nothing else changes.
    res, rd = sim.run(cfg, os.path.join(sim.SCALESIM_SRC, BUNDLED_TOPO), os.path.join(d, "raw"))
    for r in REPORTS:
        shutil.copy(os.path.join(rd, r), os.path.join(d, r))
    shutil.rmtree(os.path.join(d, "raw"))
    return df, res


def do_pass(out):
    os.makedirs(out, exist_ok=True)
    runs = dict(_bundled_one((df, out)) for df in DATAFLOWS)   # sequential: 1 worker (8 GB machine)
    json.dump(runs, open(os.path.join(out, "bundled_runs.json"), "w"), indent=1, sort_keys=True)
    import t3_fit
    fit = t3_fit.run_fit()
    json.dump(fit, open(os.path.join(out, "fit.json"), "w"), indent=1, sort_keys=True)
    print(t3_fit.table(fit))
    try:
        import t3_roofline
    except ImportError:
        t3_roofline = None
    if t3_roofline:
        t3_roofline.run(out)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def deterministic_files(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith((".csv", ".json", ".cfg")) and "summary" not in f:
                out.append(os.path.relpath(os.path.join(dp, f), root))
    return sorted(out)


def do_summary(out, rerun):
    a, b = deterministic_files(out), deterministic_files(rerun)
    a = [x for x in a if not x.startswith("_rerun")]
    same_set = a == b
    mism = [x for x in a if x in b and sha(os.path.join(out, x)) != sha(os.path.join(rerun, x))]
    ident = bool(same_set and not mism and a)
    hashes = {x: sha(os.path.join(out, x)) for x in a}
    fit = json.load(open(os.path.join(out, "fit.json")))
    runs = json.load(open(os.path.join(out, "bundled_runs.json")))
    chk = {}
    chk["bundled_runs_ok"] = all(len(runs[df]) > 0 and all(r["total_cycles"] > 0 for r in runs[df]) for df in DATAFLOWS)
    chk["reports_saved"] = all(os.path.exists(os.path.join(out, "scalesim", df, r)) for df in DATAFLOWS for r in REPORTS)
    chk["reruns_byte_identical"] = ident
    chk["analytic_constants_match_derivation"] = all(v["constants_match_derivation"] for v in fit["dataflows"].values())
    chk["analytic_residuals_stable"] = all(v["residuals_ok"] for v in fit["dataflows"].values())
    summ = dict(
        stage="30_arch_model", scalesim_version="3.0.0",
        bundled=dict(config=BUNDLED_CFG, topology=BUNDLED_TOPO, array="256x256", dataflows=DATAFLOWS),
        identity=dict(files_compared=len(a), mismatches=mism, same_file_set=same_set, sha256=hashes),
        bundled_summary={df: dict(total_cycles=sum(r["total_cycles"] for r in runs[df]),
                                  stall_cycles=sum(r["stall_cycles"] for r in runs[df]))
                         for df in DATAFLOWS},
        fit={df: dict(fitted=v["fitted"], derived=v["derived"],
                      heldout_max_abs_residual=v["heldout_max_abs_residual"],
                      heldout_max_rel_residual=v["heldout_max_rel_residual"],
                      naive_single_constant_k=v["naive_k_fit"],
                      naive_heldout_max_rel_residual=v["naive_heldout_max_rel_residual"])
             for df, v in fit["dataflows"].items()},
    )
    rf = os.path.join(out, "roofline.json")
    if os.path.exists(rf):
        r = json.load(open(rf))
        summ["roofline"] = r["summary"]
        chk.update(r["checks"])
    summ["checks"] = chk
    summ["pass"] = bool(all(chk.values()))
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pass", "summary"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--rerun")
    ap.add_argument("--summary-json")
    a = ap.parse_args()
    if a.cmd == "pass":
        do_pass(a.out)
    else:
        s = do_summary(a.out, a.rerun)
        json.dump(s, open(a.summary_json, "w"), indent=1, sort_keys=True)
        print(json.dumps({"pass": s["pass"], "checks": s["checks"]}, indent=1))
