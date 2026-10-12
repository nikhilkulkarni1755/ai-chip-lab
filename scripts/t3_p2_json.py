#!/usr/bin/env python3
"""Write results/p2_31_roofline_fix.json (common Part 2 schema) from results/t3_summary.json.
usage: t3_p2_json.py [summary.json] [out.json]  -- reports exactly what the summary holds; nothing is re-judged."""
import json
import os
import sys

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(LAB, "results/t3_summary.json")))
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(LAB, "results/p2_31_roofline_fix.json")
rf = S["roofline"]
crit = []
for df, v in rf["per_dataflow"].items():
    ok = rf["checks"][f"calc_required_bw_inverse_to_ai_{df}"]
    evaluated = v.get("calc_status") == "evaluated"
    crit.append(dict(name=f"B_calc_required_bw_inverse_to_AI_{df}", threshold="Spearman rho(AI, required DRAM bandwidth) <= -0.6, 21 ResNet-18 layers, 128x128",
                     written_before_run="6d2fc2f", measured=("rho = %+.3f" % v["calc_rho_ai_vs_required_bw"]) if evaluated else v.get("calc_status"),
                     pass_=bool(ok) if evaluated else None))
for df, v in rf["per_dataflow"].items():
    for b, c in v["user"].items():
        if c["status"] == "evaluated":
            crit.append(dict(name=f"A_user_bw_stall_frac_vs_AI_{df}_B{c['B']}", threshold="rho(AI, stall fraction) <= -0.6 and < +0.3, >= 5 layers with stalls",
                             written_before_run="69183b1", measured="rho = %+.3f, layers with stalls %d" % (c["rho"], c["n_layers_with_stalls"]), pass_=bool(c["satisfies"])))
        else:
            crit.append(dict(name=f"A_user_bw_stall_frac_vs_AI_{df}_B{c['B']}", threshold="rho(AI, stall fraction) <= -0.6 and < +0.3, >= 5 layers with stalls",
                             written_before_run="69183b1", measured="not evaluated (cost): " + c["status"], pass_=None))
crit.append(dict(name="analytic_model_matches_scalesim", threshold="held-out residuals stable; constants match derivation",
                 written_before_run="Part 1", measured="pass" if S["checks"]["analytic_residuals_stable"] and S["checks"]["analytic_constants_match_derivation"] else "fail",
                 pass_=bool(S["checks"]["analytic_residuals_stable"] and S["checks"]["analytic_constants_match_derivation"])))
crit.append(dict(name="reruns_byte_identical_in_stage", threshold="bundled + fit + CALC reruns identical", written_before_run="Part 1",
                 measured="%s; pending repro: %s" % (S["identity"]["state"], len(S["identity"]["pending_repro"])), pass_=bool(S["checks"]["reruns_byte_identical"])))
for c in crit:
    c["pass"] = c.pop("pass_")
sup = []
old = S.get("superseded", {}).get("roofline_part1")
if old:
    sup.append(dict(name="Part 1 synthetic roofline (16 GEMMs, 16x16, 5 % stall threshold)", threshold="agreement >= 80 %, rho <= -0.5",
                    measured=json.dumps(old.get("checks")), pass_=False, reason=old["reason"] + " See COORDINATION.md Decisions P2-A1, P2-7."))
for c in sup:
    c["pass"] = c.pop("pass_")
res = dict(stage="31_roofline_fix", **{"pass": bool(S["pass"])}, verdict=S.get("verdict"), complete=S["complete"], state=S["state"],
           oracle="SCALE-Sim's own reports (COMPUTE_REPORT stall cycles, BANDWIDTH_REPORT required DRAM bandwidth) against arithmetic intensity computed from the layer shapes alone (2MNK / compulsory bytes); the two sides share no code.",
           criteria=crit, superseded=sup,
           commands=["make t3", "python3 scripts/t3_p2_json.py"], seeds="none (SCALE-Sim is deterministic; PYTHONHASHSEED=0)",
           evidence=["results/t3_summary.json", "results/evidence/31_original_stalls.txt", "results/evidence/31_neutrality_and_intensity_tests.txt",
                     "results/evidence/31_a_probe.txt", "demo/assets/t3_roofline.png", "docs/t3_roofline_explained.md"])
json.dump(res, open(OUT, "w"), indent=1)
print("wrote", OUT, "verdict", res["verdict"])
