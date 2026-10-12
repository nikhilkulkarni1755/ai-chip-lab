#!/usr/bin/env python3
"""Task 3 stage body (runs inside the lab-sim container; see scripts/t3_run.sh).

  t3_stage.py pass    --out DIR    SCALE-Sim bundled runs (+fit, +roofline) into DIR
  t3_stage.py summary --out DIR --rerun DIR2   compare passes, write summary JSON + plots
"""
import argparse
import datetime
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


CHEAP_JOBS = [f"bundled_{df}" for df in DATAFLOWS] + ["fit"] + [f"rl2_calc_{df}" for df in DATAFLOWS]   # re-run in-stage for byte identity


def job_list(only=None):
    import t3_roofline2
    if only == "cheap":
        return list(CHEAP_JOBS)
    return CHEAP_JOBS[:4] + ["roofline_synthetic"] + t3_roofline2.jobs()


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
        r = t3_roofline2.run_job(job, out)
        if r == "blocked":
            print(f"job {job}: blocked (see roofline2/{job}/blocked.json); not retried")
            sys.exit(76)
        if not r:
            print(f"job {job}: partial (time budget for this lock hold used); call again")
            sys.exit(75)
    else:
        raise SystemExit("unknown job " + job)
    os.makedirs(os.path.dirname(mk), exist_ok=True)
    open(mk, "w").write("done\n")


def do_pass(out, only=None):
    """All jobs sequentially in this process tree (single container)."""
    for j in job_list(only):
        do_job(j, out)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def deterministic_files(root):
    out = []
    for dp, dn, fs in os.walk(root):
        dn[:] = [x for x in dn if not x.startswith(".rerun")]     # kept pass-2 copy lives in <final>/.rerun
        for f in fs:
            if f.endswith((".csv", ".json", ".cfg")) and "summary" not in f and f not in ("roofline2.json", "attempts.json"):   # attempts.json: scheduling bookkeeping, not a result
                out.append(os.path.relpath(os.path.join(dp, f), root))
    return sorted(out)


def do_summary(out, rerun, prev_summary=None):
    import t3_roofline2
    missing = [j for j in job_list() if not os.path.exists(os.path.join(out, ".jobs", j + ".done"))
               and not j.startswith("rl2_user_") and not (os.environ.get("T3_JOBS") == "cheap" and j == "roofline_synthetic")]     # criterion-A runs may be unfinished (Decision P2-7): reported as such
    if missing:
        raise SystemExit("jobs not finished: %s" % missing)
    a = deterministic_files(out)
    prev_id = None
    if not os.path.isdir(rerun) and prev_summary and os.path.exists(prev_summary):
        prev_id = json.load(open(prev_summary)).get("identity", {})      # resumed from a finished run: pass 2 not repeated
    if prev_id and prev_id.get("compared_in_stage"):
        b = [x for x in prev_id["compared_in_stage"] if not x.endswith("attempts.json")]
    else:
        b = deterministic_files(rerun)
    # Per decision P2-6 the second in-stage pass covers only the cheap jobs; every other file is compared by
    # `make repro` (pending_repro here).
    pending = [x for x in a if x not in b]
    extra = [x for x in b if x not in a]
    if prev_id and prev_id.get("compared_in_stage"):
        # carried over: valid only while every compared file still has the hash recorded when pass 2 compared it
        mism = list(prev_id.get("mismatches", [])) + [x for x in b if x in a and sha(os.path.join(out, x)) != prev_id.get("sha256", {}).get(x)]
    else:
        mism = [x for x in b if x in a and sha(os.path.join(out, x)) != sha(os.path.join(rerun, x))]
    ident = bool(b and not extra and not mism)
    hashes = {x: sha(os.path.join(out, x)) for x in a}
    jobs_info = {}
    for j in job_list():
        mk = os.path.join(out, ".jobs", j + ".done")
        if not os.path.exists(mk):
            jobs_info[j] = dict(completed=None, state=t3_roofline2._status(out, j))
            bpj = os.path.join(out, "roofline2", j, "blocked.json")
            if os.path.exists(bpj):
                jobs_info[j]["blocked"] = json.load(open(bpj))
            continue
        jobs_info[j] = dict(completed=datetime.datetime.fromtimestamp(os.path.getmtime(mk)).isoformat(timespec="seconds"),
                            rerun_in_stage=os.path.exists(os.path.join(rerun, ".jobs", j + ".done")))
    fit = json.load(open(os.path.join(out, "fit.json")))
    runs = {df: json.load(open(os.path.join(out, "scalesim", df, "layers.json"))) for df in DATAFLOWS}
    chk = {}
    chk["bundled_runs_ok"] = all(len(runs[df]) > 0 and all(r["total_cycles"] > 0 for r in runs[df]) for df in DATAFLOWS)
    chk["reports_saved"] = all(os.path.exists(os.path.join(out, "scalesim", df, r)) for df in DATAFLOWS for r in REPORTS)
    chk["reruns_byte_identical"] = ident   # scope: in-stage files only; see identity.pending_repro
    chk["analytic_constants_match_derivation"] = all(v["constants_match_derivation"] for v in fit["dataflows"].values())
    chk["analytic_residuals_stable"] = all(v["residuals_ok"] for v in fit["dataflows"].values())
    summ = dict(
        stage="30_arch_model", scalesim_version="3.0.0",
        bundled=dict(config=BUNDLED_CFG, topology=BUNDLED_TOPO, array="256x256", dataflows=DATAFLOWS),
        identity=dict(state="in_stage_ok_pending_repro" if ident and pending else ("complete" if ident else "mismatch"),
                      scope_in_stage="bundled ws/os/is runs + analytic fit + 3 CALC-mode roofline runs, pass 2 in the same stage; user-bandwidth runs: not rerun in-stage (cost)",
                      files_compared_in_stage=len(b), compared_in_stage=sorted(b), mismatches=mism,
                      pending_repro=pending, pending_repro_note="compared by make repro (51_repro_full), not yet in this summary",
                      sha256=hashes),
        jobs=jobs_info,
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
        passed=r2["passed"], complete=r2["complete"], cell_status=r2["cell_status"], per_dataflow=r2["per_dataflow"], checks=r2["checks"], criteria=r2["criteria"])
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
    summ["pass"] = bool(all(chk.values()) and r2["complete"])
    summ["complete"] = bool(not pending and r2["complete"])
    summ["state"] = ("A_incomplete(" + ",".join(k.replace("rl2_user_", "") + "=" + v for k, v in r2["cell_status"].items() if k.startswith("rl2_user_") and v != "evaluated") + ")") if not r2["complete"] else summ["identity"]["state"]
    evaluated_fail = [k for k, v in r2["checks"].items() if not v and (
        (k.startswith("calc_required_bw") and r2["cell_status"].get("rl2_calc_" + k.rsplit("_", 1)[1]) == "evaluated") or
        (k.startswith(("user_bw_stalls_vs_ai_", "stall_cycles_monotone_in_B_")) and r2["per_dataflow"][k.rsplit("_", 1)[1]]["user_all_levels_evaluated"]))]
    other_fail = [k for k in ("bundled_runs_ok", "reports_saved", "reruns_byte_identical", "analytic_constants_match_derivation", "analytic_residuals_stable") if not chk[k]]
    summ["verdict"] = "PASS" if summ["pass"] else ("FAIL" if evaluated_fail or other_fail else "INCOMPLETE")
    summ["verdict_failed_criteria"] = evaluated_fail + other_fail
    summ["pending"] = ["repro byte-identity of %d result files" % len(pending)] if pending else []
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pass", "summary", "job", "list"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--out", default=".")
    ap.add_argument("--rerun")
    ap.add_argument("--only", choices=["cheap"])
    ap.add_argument("--summary-json")
    ap.add_argument("--prev-summary")
    a = ap.parse_args()
    if a.cmd == "list":
        print("\n".join(job_list()))
        sys.exit(0)
    if a.cmd == "job":
        do_job(a.name, a.out)
    elif a.cmd == "pass":
        do_pass(a.out, a.only)
    else:
        s = do_summary(a.out, a.rerun, a.prev_summary)
        json.dump(s, open(a.summary_json, "w"), indent=1, sort_keys=True)
        print(json.dumps({"pass": s["pass"], "checks": s["checks"]}, indent=1))
