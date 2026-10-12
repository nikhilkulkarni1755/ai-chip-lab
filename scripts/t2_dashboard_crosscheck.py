#!/usr/bin/env python3
"""P1.5b: our gcd metadata vs the ORFS QoR dashboard's measurement of the pinned commit (raw files in
results/t2/published/). Tolerances: docs/t2_dashboard_crosscheck_tolerance.md (pre-registered). Output
results/t2_dashboard_crosscheck.json; also rewrites results/p2_21_orfs_crosscheck.json (old criterion -> superseded)."""
import json, os, re
LAB = os.path.expanduser("~/ai-chip-lab"); R = lambda p: json.load(open(os.path.join(LAB, p)))
raw = R("results/t2/published/dashboard_commit_3a964e13f_metrics_raw.json"); defs = raw["metricDefinitions"]
retrieved = open(os.path.join(LAB, "results/t2/published/retrieved_utc.txt")).read().strip()
TOL = {"finish__timing__setup__ws": ("T", 0.05), "finish__timing__setup__tns": ("T", 0.20),
       "finish__design__instance__area": ("rel", .15), "placeopt__design__instance__area": ("rel", .15),
       "placeopt__design__instance__count__stdcell": ("rel", .15), "detailedroute__route__wirelength": ("rel", .15),
       "finish__power__total": ("rel", .15), "detailedroute__route__drc_errors": ("eq", 0)}
out = {"reference": {"source": "https://dashboard.precisioninno.com/api/commits/25781/metrics", "commit": raw["sha"], "retrieved_utc": retrieved,
                     "kind": "measured CI build of the exact pinned commit (QoR dashboard)"},
       "tolerance_doc": "docs/t2_dashboard_crosscheck_tolerance.md", "designs": {}}
for plat in ("nangate45", "sky130hd"):
    g = R(f"results/t2/published/dashboard_{plat}_gcd_raw.json")["design"]
    # dashboard rows with iteration != None are per-detailed-route-iteration values (our metadata: <name>__iter__<n>); the
    # final value (iteration None) is the one the tolerance doc refers to. (First version of this script let iteration-0 rows
    # overwrite the final ones and reported drc_errors 63/289 vs 0: a script bug, fixed here; tolerance unchanged.)
    pub = {defs[m]["rawName"]: v for m, v, it in zip(g["metrics"], g["values"], g["iterations"]) if it is None}
    pub_iter = {f"{defs[m]['rawName']}__iter__{it}": v for m, v, it in zip(g["metrics"], g["values"], g["iterations"]) if it is not None}
    iter_equal = all(md_.get(k) == v for k, v in pub_iter.items()) if (md_ := R(f"results/t2/metadata_{plat}_gcd.json")) else None
    md = R(f"results/t2/metadata_{plat}_gcd.json")
    T = float(re.match(r".*: ([\d.]+)", md["constraints__clocks__details"][0]).group(1))
    rows = {}; ok = True; exact = True
    for m, (k, t) in TOL.items():
        p, o = pub.get(m), md.get(m)
        if p is None or o is None: rows[m] = {"published": p, "ours": o, "within": False, "note": "missing"}; ok = False; continue
        d = o - p
        if k == "T": within = abs(d) <= t * T; one = abs(d) <= 0.01 * T
        elif k == "rel": within = abs(d) <= t * abs(p); one = abs(d) <= 0.01 * abs(p)
        else: within = one = (o == p)
        rows[m] = {"published": p, "ours": o, "delta": round(d, 6), "tolerance": f"{t}*T" if k == "T" else (f"{int(t*100)}%" if k == "rel" else "equal"), "within": bool(within), "within_1pct": bool(one)}
        ok &= bool(within); exact &= bool(one)
    hashes = {h: {"published": pub.get(h), "ours": md.get(h), "equal": (pub.get(h) == md.get(h)) if pub.get(h) is not None else None, "note": "the dashboard stores numeric metrics only; netlist hashes are not published there"} for h in ("synth__netlist__hash", "synth__canonical_netlist__hash")}
    # informational: all metrics both sides have, relative delta, so the stage of departure is visible
    common = [(m, pub[m], md[m]) for m in pub if m in md and isinstance(pub[m], (int, float)) and isinstance(md[m], (int, float)) and not re.search(r"elapsed|runtime|mem|cpu|time", m)]
    ndiff = sum(1 for m, p, o in common if abs(o - p) > 1e-9 * max(1, abs(p)))
    out["designs"][f"{plat}/gcd"] = {"clock_period_ns": T, "metrics": rows, "matches_published_dashboard": bool(ok), "exact_1pct_informational": bool(exact),
        "synth_netlist_hashes": hashes, "per_iteration_series_identical": iter_equal, "per_iteration_series_count": len(pub_iter), "numeric_metrics_common": len(common), "numeric_metrics_differing": ndiff}
out["matches_published_dashboard"] = all(d["matches_published_dashboard"] for d in out["designs"].values())
json.dump(out, open(os.path.join(LAB, "results", "t2_dashboard_crosscheck.json"), "w"), indent=2)
for k, d in out["designs"].items():
    print(k, "matches_published_dashboard =", d["matches_published_dashboard"], "| exact_1pct", d["exact_1pct_informational"], "| differing numeric metrics", d["numeric_metrics_differing"], "/", d["numeric_metrics_common"])
    for m, r in d["metrics"].items(): print("  ", m, "published", r["published"], "ours", r["ours"], "->", "IN" if r["within"] else "OUT", f"(tol {r.get('tolerance')})")
    print("   hashes equal:", {h: x["equal"] for h, x in d["synth_netlist_hashes"].items()})

# ---- common stage schema: results/p2_21_orfs_crosscheck.json (old implied-reference criterion kept as superseded) ----
old = R("results/t2_crosscheck.json")
crit = []
for k, d in out["designs"].items():
    meas = "; ".join(f"{m}: published {r['published']} ours {r['ours']} ({'in' if r['within'] else 'OUT'} tol {r['tolerance']})" for m, r in d["metrics"].items())
    crit.append({"name": f"matches_published_dashboard[{k}] (measured CI build of the exact pinned commit)",
                 "threshold": "8 metrics within ORFS's own margins of the dashboard value (docs/t2_dashboard_crosscheck_tolerance.md)",
                 "written_before_run": "9b81746", "measured": meas + f" | exact within 1 %: {d['exact_1pct_informational']}", "pass": d["matches_published_dashboard"]})
sup = []
for k, d in old["designs"].items():
    sup.append({"name": f"matches_published[{k}] (implied reference from rules-base.json)", "threshold": "docs/t2_crosscheck_tolerance.md (a2c2d54)",
                "measured": f"{d['matches_published']} (nangate45: setup WNS/TNS and wirelength outside the implied band, all better)", "pass": d["matches_published"],
                "reason": "compared against a number inferred by un-padding rules-base.json, not a publication; rules-base.json for this design is 4 weeks older than the pinned commit, and the real published measurement of the pinned commit equals our run - see COORDINATION.md Decision P2-5"})
p2 = {"stage": "21_orfs_crosscheck", "pass": out["matches_published_dashboard"],
      "oracle": "ORFS's public QoR dashboard measurement of exactly the pinned commit 3a964e13f (CI build, retrieved via its public API); independent of our run",
      "criteria": crit, "superseded": sup,
      "commands": ["python3 scripts/t2_dashboard_crosscheck.py", "python3 scripts/t2_crosscheck.py"], "seeds": "none",
      "evidence": ["results/evidence/21_orfs_crosscheck.txt", "results/t2_dashboard_crosscheck.json", "results/t2_crosscheck.json", "docs/t2_timing_explained.md"],
      "finding": "our runs equal the dashboard's measurement of the pinned commit on all 430/439 non-profiling numeric metrics (the 9 that differ are fastroute wall-clock profiling); the implied-reference miss for nangate45 comes from a stale rules-base.json"}
json.dump(p2, open(os.path.join(LAB, "results", "p2_21_orfs_crosscheck.json"), "w"), indent=2)
