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


def job_list():
    import t3_roofline2
    return [f"bundled_{df}" for df in DATAFLOWS] + ["fit", "roofline_synthetic"] + t3_roofline2.jobs()


def do_job(job, out):
    os.makedirs(out, exist_ok=True)
    mk = os.path.join(out, ".jobs", job + ".done")
    if os.path.exists(mk):
        print(f"job {job}: already done, skipped")
        return
    if job.startswith("bundled_"):
        df, res = _bundled_one((job.split("_")[1], out))
        json.dump(res, open(os.path.join(out, "scalesim", df, "layers.json"), "w"), indent=1, sort_keys=True)
    elif job == "fit":
        import t3_fit
        fit = t3_fit.run_fit()
        json.dump(fit, open(os.path.join(out, "fit.json"), "w"), indent=1, sort_keys=True)
        print(t3_fit.table(fit))
    elif job == "roofline_synthetic":      # Part 1 study, kept only as 'superseded' evidence
        import t3_roofline
        t3_roofline.run(out)
    elif job.startswith("rl2_"):
        import t3_roofline2
        t3_roofline2.run_job(job, out)
    else:
        raise SystemExit("unknown job " + job)
    os.makedirs(os.path.dirname(mk), exist_ok=True)
    open(mk, "w").write("done\n")


def do_pass(out):
    """All jobs sequentially in this process tree (single container)."""
    for j in job_list():
        do_job(j, out)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def deterministic_files(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith((".csv", ".json", ".cfg")) and "summary" not in f and f != "roofline2.json":
                out.append(os.path.relpath(os.path.join(dp, f), root))
    return sorted(out)


def do_summary(out, rerun):
    missing = [j for j in job_list() if not os.path.exists(os.path.join(out, ".jobs", j + ".done"))]
    if missing:
        raise SystemExit("jobs not finished: %s" % missing)
    a, b = deterministic_files(out), deterministic_files(rerun)
    a = [x for x in a if not x.startswith("_rerun")]
    same_set = a == b
    mism = [x for x in a if x in b and sha(os.path.join(out, x)) != sha(os.path.join(rerun, x))]
    ident = bool(same_set and not mism and a)
    hashes = {x: sha(os.path.join(out, x)) for x in a}
    fit = json.load(open(os.path.join(out, "fit.json")))
    runs = {df: json.load(open(os.path.join(out, "scalesim", df, "layers.json"))) for df in DATAFLOWS}
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
    import t3_roofline2
    r2 = t3_roofline2.assemble(out)
    summ["roofline"] = dict(
        summary="Pre-registered (model/t3_roofline2_criteria.json) re-specification: ResNet-18 real layers, "
                "USER-bandwidth stalls and CALC-mode required bandwidth vs arithmetic intensity.",
        passed=r2["passed"], per_dataflow=r2["per_dataflow"], checks=r2["checks"], criteria=r2["criteria"])
    chk.update(r2["checks"])
    chk["roofline_agrees"] = bool(r2["passed"])
    rf = os.path.join(out, "roofline.json")
    if os.path.exists(rf):
        old = json.load(open(rf))
        summ["superseded"] = dict(
            roofline_part1=dict(
                reason="Measured the wrong thing: (1) the TASK 3 bundled run had Stall Cycles = 0 (results/evidence/31_original_stalls.txt), "
                       "so there was nothing to correlate against; (2) the substitute study used 16 hand-picked synthetic GEMMs on a 16x16 "
                       "array and a binary agreement gate on a 5 % stall threshold, a metric that depends on the arbitrary threshold and class balance, "
                       "and was not a real layer set. Replaced by rank correlations (threshold-free) on the real ResNet-18 layers.",
                checks=old["checks"], summary=old["summary"]))
    summ["bundled_config_zero_stalls"] = all(summ["bundled_summary"][df]["stall_cycles"] == 0 for df in DATAFLOWS)
    summ["checks"] = chk
    summ["pass"] = bool(all(chk.values()))
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pass", "summary", "job", "list"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--out", default=".")
    ap.add_argument("--rerun")
    ap.add_argument("--summary-json")
    a = ap.parse_args()
    if a.cmd == "list":
        print("\n".join(job_list()))
        sys.exit(0)
    if a.cmd == "job":
        do_job(a.name, a.out)
    elif a.cmd == "pass":
        do_pass(a.out)
    else:
        s = do_summary(a.out, a.rerun)
        json.dump(s, open(a.summary_json, "w"), indent=1, sort_keys=True)
        print(json.dumps({"pass": s["pass"], "checks": s["checks"]}, indent=1))
