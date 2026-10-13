#!/usr/bin/env python3
"""After a stage has regenerated first-run files that `make repro` had already compared: show (by sha256 and by the
compared summary fields) that the files now on HEAD are identical to the rerun copies repro compared, i.e. that the
existing repro verdict still covers them. Writes the block `post_repro_identity_check` into results/make_all_last.json
and prints it. Any difference is reported as a determinism finding (exit 1); nothing is hidden.

Task 1: results/t1_{icarus,verilator}.csv, coverage JSONs and waveform case vs .cache/repro_run/t1/, plus the summary's
        `checks` booleans and the csv hashes recorded in results/repro_report.json.
Task 2: cites the stage's own comparison (scripts/t2_repro.sh -> results/repro/t2_<platform>_<design>.json: run count,
        identical yes/no against every earlier run).
"""
import hashlib, json, os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
RUN = ".cache/repro_run/t1"
files = []
for f in ("t1_icarus.csv", "t1_verilator.csv", "t1_coverage_icarus.json", "t1_coverage_verilator.json", "t1_waveform_case.json"):
    a, b = os.path.join("results", f), os.path.join(RUN, f)
    if not (os.path.exists(a) and os.path.exists(b)):
        files.append({"file": f, "identical": None, "note": "missing on one side"}); continue
    ha, hb = sha(a), sha(b)
    files.append({"file": f, "head_sha256": ha, "repro_rerun_sha256": hb, "identical": ha == hb,
                  "head_mtime": time.strftime("%F %T", time.localtime(os.path.getmtime(a)))})
rep = json.load(open("results/repro_report.json"))
recorded = {c["check"]: c for c in rep.get("checks", [])}
rec_cmp = []
for sim in ("icarus", "verilator"):
    c = recorded.get("t1 csv sha256 (%s)" % sim)
    if c:
        h = sha("results/t1_%s.csv" % sim)
        rec_cmp.append({"check": c["check"], "head_sha256": h, "sha256_repro_compared_first_run": c["first_run"], "sha256_repro_rerun": c["rerun"],
                        "identical": h == c["first_run"] == c["rerun"]})
s_head = json.load(open("results/t1_summary.json")); s_rerun = json.load(open(os.path.join(RUN, "t1_summary.json")))
keys = sorted(set(s_rerun.get("checks", {})))
checks_same = {k: s_head.get("checks", {}).get(k) == s_rerun["checks"][k] for k in keys}
t1 = {"files": files, "against_hashes_recorded_in_repro_report": rec_cmp,
      "summary_check_booleans_equal_to_rerun": all(checks_same.values()), "summary_check_booleans_compared": len(keys),
      "differing_summary_checks": [k for k, v in checks_same.items() if not v],
      "identical": all(f["identical"] for f in files) and all(c["identical"] for c in rec_cmp) and all(checks_same.values())}
t2 = []
for f in sorted(os.listdir("results/repro")) if os.path.isdir("results/repro") else []:
    if f.startswith("t2_") and f.endswith(".json"):
        d = json.load(open(os.path.join("results/repro", f)))
        t2.append({"source": "results/repro/" + f, "design": "%s/%s" % (d.get("platform"), d.get("design")), "runs": d.get("runs"),
                   "new_run_id": d.get("new_run_id"), "identical_to_all_earlier_runs": d.get("identical")})
block = {"generated": time.strftime("%F %T %Z"), "repro_report_generated_epoch": rep.get("generated_epoch"), "repro_pass": rep.get("pass"),
         "why": "make all re-executed stages whose first-run files `make repro` had already compared; this block shows whether the files on HEAD "
                "are byte-identical to what repro compared, which is the reason its verdict still applies",
         "task1": t1, "task2_stage_own_comparison": t2,
         "identical": bool(t1["identical"] and all(x["identical_to_all_earlier_runs"] for x in t2))}
p = "results/make_all_last.json"
if os.path.exists(p):
    d = json.load(open(p)); d["post_repro_identity_check"] = block; json.dump(d, open(p, "w"), indent=1)
print(json.dumps({"identical": block["identical"], "task1_files": [(f["file"], f["identical"]) for f in files],
                  "task1_summary_checks_equal": t1["summary_check_booleans_equal_to_rerun"],
                  "task2": [(x["design"], x["runs"], x["identical_to_all_earlier_runs"]) for x in t2]}, indent=1))
sys.exit(0 if block["identical"] else 1)
