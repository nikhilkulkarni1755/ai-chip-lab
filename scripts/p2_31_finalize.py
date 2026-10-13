#!/usr/bin/env python3
"""Final form of results/p2_31_roofline_fix.json: the generic export (scripts/t3_p2_json.py, a frozen stage input, unchanged) plus the identity
evidence from the repro report. Reads committed files only; writes only results/p2_31_roofline_fix.json."""
import json
import os
import subprocess
import sys

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
subprocess.run([sys.executable, os.path.join(LAB, "scripts/t3_p2_json.py")], check=True, cwd=LAB, stdout=subprocess.DEVNULL)
P = os.path.join(LAB, "results/p2_31_roofline_fix.json")
d = json.load(open(P))
rep = json.load(open(os.path.join(LAB, "results/repro_report.json")))
S = json.load(open(os.path.join(LAB, "results/t3_summary.json")))
t3 = [c for c in rep["checks"] if "t3 cheap-set" in c["check"]][0]
for c in d["criteria"]:
    if c["name"] == "reruns_byte_identical_in_stage":
        c.update(name="reruns_byte_identical (make repro)", written_before_run="Part 1 / P2-6 (identity of the cheap set is decided by make repro)",
                 threshold="bundled ws/os/is + fit + CALC-mode runs byte-identical between the clean first pass and the repro rerun (time measurements excluded and listed)",
                 measured="repro report pass=%s: %s; %s; excluded: %s" % (rep["pass"], t3["check"], t3["verdict"], rep["excluded_file_class"]["label"]),
                 **{"pass": bool(rep["pass"] and t3["verdict"] == "identical")})
d["identity"] = dict(source="results/repro_report.json", repro_pass=rep["pass"], repro_complete=rep["complete"], counts=rep["counts"],
                     cheap_set_verdict=t3["verdict"], excluded=rep["excluded_file_class"]["label"],
                     note="The repro verdict is the identity evidence. The stage summary's own identity block is not (see known_presentation_defects).")
d["known_presentation_defects"] = [
    "results/t3_summary.json lists the unevaluated criterion-A checks (user_bw_stalls_vs_ai_*, stall_cycles_monotone_in_B_*, roofline_agrees) as plain false; they are NOT FAILED, they were not evaluated (cell_status: %s). Render NOT EVALUATED from cell_status. Fix deferred: model/ is frozen (Decision P2-12)." % json.dumps({k: v for k, v in S["roofline"]["cell_status"].items() if k.startswith("rl2_user")}),
    "results/t3_summary.json identity.state reads '%s' with %d files compared in-stage and checks.reruns_byte_identical=%s: the summary was last written by a stage invocation that resumed a finished single-pass run, so no in-stage comparison existed. This is a bookkeeping state, not a mismatch (repro compared 42 files byte-identical). verdict_failed_criteria in the summary therefore also lists reruns_byte_identical; the real failing criteria are the three criterion-B checks. Fix deferred. Any later `make t3` or resumed `make all` rewrites the summary the same way while the stage has a .failed marker, so rerun `python3 scripts/p2_31_finalize.py` after it." % (S["identity"]["state"], S["identity"]["files_compared_in_stage"], S["checks"]["reruns_byte_identical"])]
d["evidence"] = sorted(set(d["evidence"] + ["results/repro_report.json", "results/evidence/51_repro_t3_diagnosis.txt", "results/evidence/31_a_probe.txt"]))
d["commands"] = ["make t3", "make repro", "python3 scripts/p2_31_finalize.py"]
json.dump(d, open(P, "w"), indent=1)
print("verdict", d["verdict"], "pass", d["pass"], [(c["name"], c["pass"]) for c in d["criteria"] if "byte" in c["name"]])
