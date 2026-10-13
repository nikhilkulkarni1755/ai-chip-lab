#!/usr/bin/env python3
"""P2.3 finalize: run the summary, evaluate the registered criteria (results/p2_62_pdk_compare.json, committed before the run),
write plan_change, evidence, plot, marker."""
import json, os, subprocess, sys, time
LAB = os.path.expanduser("~/ai-chip-lab")
subprocess.check_call([sys.executable, os.path.join(LAB, "scripts", "p2_pdk_compare.py"), "summary"], stdout=subprocess.DEVNULL)
D = json.load(open(os.path.join(LAB, "results/pdk_compare/pdk_compare.json")))
sp = os.path.join(LAB, "results/p2_62_pdk_compare.json"); S = json.load(open(sp))
R = D["points"]; planned = [8.0, 5.5, 4.0, 6.75]
by = {r["clock_period_ns"]: r for r in R}
closing = [r for r in R if r.get("status") == "ok" and r["closed"]]
best = min(closing, key=lambda r: r["clock_period_ns"]) if closing else None
fails_below = [r for r in R if r.get("status") == "ok" and not r["closed"] and best and r["clock_period_ns"] < best["clock_period_ns"]]
C = D["comparison_at_each_pdks_fastest_closing_period"]
res = {}
res["accounting_complete"] = (all(p in by for p in planned) and all(by[p]["status"] in ("ok",) or by[p].get("stage_reached") or by[p].get("errors") for p in planned),
    "; ".join(f"{p} ns: {by[p]['status']} WNS {by[p].get('wns_setup_ns')} hold {by[p].get('lock_hold_s')} s" for p in planned if p in by))
gds = best and os.path.exists(os.path.join(LAB, "orfs/work/results/sky130hd/systolic_os", best["variant"], "6_final.gds"))
res["sky130hd_closes_timing_somewhere"] = (bool(best and best.get("drc_errors") == 0 and gds), f"fastest closing {best['clock_period_ns'] if best else None} ns, WNS {best and best.get('wns_setup_ns')}, DRC {best and best.get('drc_errors')}, GDS {bool(gds)}")
res["frontier_claim_matches_evidence"] = (("bracket" in D["label"]) == bool(fails_below), D["label"])
shas = {open(os.path.join(LAB, "orfs/work/reports/sky130hd/systolic_os", r["variant"], "t2_run.json")).read().split('"rtl_sha256":"')[1][:12] for r in R if r.get("status") == "ok"}
res["both_pdks_compared_on_same_design"] = (bool(C) and all(C[k]["nangate45"] is not None and C[k]["sky130hd"] is not None for k in ("area_um2", "stdcell_count", "power_total_w", "clock_period_ns")) and len(shas) == 1,
    f"RTL sha256 prefix(es) of sky130hd runs: {sorted(shas)}; " + (", ".join(f"{k}: nangate45 {v['nangate45']} vs sky130hd {v['sky130hd']}" for k, v in C.items() if isinstance(v, dict)) if C else "no comparison"))
res["expected_direction"] = (bool(C) and C["clock_period_ns"]["ratio_sky_over_nangate"] > 1 and C["area_um2"]["ratio_sky_over_nangate"] > 1,
    f"period ratio {C and C['clock_period_ns']['ratio_sky_over_nangate']}, area ratio {C and C['area_um2']['ratio_sky_over_nangate']}")
for c in S["criteria"]:
    c["pass"], c["measured"] = bool(res[c["name"]][0]), res[c["name"]][1]
S["pass"] = all(c["pass"] for c in S["criteria"]); S.pop("state", None)
S["plan_change"] = {"when": "18:42", "decision": "P2-11a, amended 19:08", "what": "Planned 8.0 / 5.5 / 4.0 ns. After 8.0 closed and 5.5 failed, a refinement point at 6.75 ns (midpoint of the bracket) was added. 4.0 ns was first to be cut (a faster clock cannot close), but its job already held the lock and ran to its end; it is recorded as a normal planned point with its real result. Criteria and thresholds untouched."}
S["finding"] = D["label"]
S["summary"] = D["comparison_at_each_pdks_fastest_closing_period"]
S["evidence"] = ["results/evidence/62_pdk_compare.txt", "results/pdk_compare/pdk_compare.json", "results/pdk_compare/sky130hd_points.jsonl", "demo/assets/pdk_compare.png", "docs/pdk_compare_explained.md"]
json.dump(S, open(sp, "w"), indent=2)
L = [D["label"], "", "points (sky130hd systolic_os, 30 % utilization):"]
for r in R:
    L.append(f"  {r['clock_period_ns']:>5} ns  {r['status']:6} closed={r.get('closed')} WNS={r.get('wns_setup_ns')} area={r.get('area_um2')} stdcells={r.get('stdcell_count')} power={r.get('power_total_w')} W lock_hold={r.get('lock_hold_s')} s wait={r.get('lock_wait_s')} s")
L += ["", "nangate45 reference: " + json.dumps(D["nangate45_reference_point"]), "", "comparison: " + json.dumps(C, indent=1), "", json.dumps({c["name"]: c["pass"] for c in S["criteria"]})]
os.makedirs(os.path.join(LAB, "results/evidence"), exist_ok=True)
open(os.path.join(LAB, "results/evidence/62_pdk_compare.txt"), "w").write("\n".join(L) + "\n")
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
R2 = sorted(R, key=lambda r: r["clock_period_ns"])
ax[0].plot([r["clock_period_ns"] for r in R2], [r["wns_setup_ns"] for r in R2], "o-", color="#1f77b4", label="sky130hd")
ng = D["nangate45_reference_point"]; ax[0].plot([ng["clock_period_ns"]], [ng["wns_setup_ns"]], "s", color="#ff7f0e", label="nangate45 (closing point)")
ax[0].axhline(0, color="k", lw=.8); ax[0].set_xlabel("clock period (ns)"); ax[0].set_ylabel("setup WNS (ns)"); ax[0].set_title("systolic_os: WNS vs clock"); ax[0].legend(); ax[0].grid(alpha=.3)
if C:
    ks = ["area_um2", "stdcell_count", "power_total_w", "clock_period_ns"]; v = [C[k]["ratio_sky_over_nangate"] for k in ks]
    ax[1].bar(["area", "std cells", "power", "period"], v, color="#1f77b4"); ax[1].axhline(1, color="k", lw=.8)
    for i, x in enumerate(v): ax[1].text(i, x, f"{x:.1f}x", ha="center", va="bottom", fontsize=8)
    ax[1].set_title("sky130hd / nangate45 at each PDK's fastest tested closing clock"); ax[1].set_ylabel("ratio")
fig.tight_layout(); fig.savefig(os.path.join(LAB, "demo/assets/pdk_compare.png"), dpi=130)
open(os.path.join(LAB, "results/.stages/62_pdk_compare.done"), "w").write(f"sky130hd systolic_os coarse search {time.strftime('%F %T')}; pass={S['pass']}; {D['label']}\n")
print(json.dumps({c["name"]: c["pass"] for c in S["criteria"]}), S["pass"])
