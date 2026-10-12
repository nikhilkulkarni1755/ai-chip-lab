#!/usr/bin/env python3
"""P1.5: compare our gcd runs with what ORFS publishes (rules-base.json shipped in the pinned image, copied to
results/t2/rules_<plat>_gcd.json). Tolerance and implied-reference formulas: docs/t2_crosscheck_tolerance.md
(committed before this script was run). Output: results/t2_crosscheck.json."""
import json, os, re
LAB = os.path.expanduser("~/ai-chip-lab"); R = lambda p: json.load(open(os.path.join(LAB, p)))
TWO = {  # metric -> (kind, pad)
    "finish__timing__setup__ws": ("period", 5), "finish__timing__setup__tns": ("period", 20),
    "finish__design__instance__area": ("pct", 15), "placeopt__design__instance__area": ("pct", 15),
    "placeopt__design__instance__count__stdcell": ("pct", 15), "detailedroute__route__wirelength": ("pct", 15)}
ONE = ["finish__timing__hold__ws", "finish__timing__hold__tns"]
NOPUB = ["finish__power__total", "finish__design__instance__utilization", "total_elapsed_seconds"]
out = {"tolerance_doc": "docs/t2_crosscheck_tolerance.md", "designs": {}}
for plat in ("nangate45", "sky130hd"):
    rules = R(f"results/t2/rules_{plat}_gcd.json"); md = R(f"results/t2/metadata_{plat}_gcd.json")
    T = float(re.match(r".*: ([\d.]+)", md["constraints__clocks__details"][0]).group(1))
    rows = {}; ok = True
    for m, (kind, pad) in TWO.items():
        lim = rules[m]["value"]; ours = md[m]
        if kind == "period":
            ref = lim + pad / 100 * T; margin = pad / 100 * T
        else:
            ref = lim / (1 + pad / 100); margin = pad / 100 * ref
        inside = abs(ours - ref) <= margin + 1e-12
        ok &= inside
        rows[m] = {"rule_limit": lim, "implied_reference": round(ref, 5), "margin": round(margin, 5), "ours": ours,
                   "delta": round(ours - ref, 5), "within_band": inside,
                   "direction": "better" if (ours > ref if kind == "period" else ours < ref) else "worse"}
    one = {}
    for m in ONE:
        lim = rules[m]["value"]; ref = lim + (0.05 if "ws" in m else 0.20) * T if "ws" in m or "tns" in m else lim
        ref = min(ref, 0)
        one[m] = {"rule_limit": lim, "implied_reference": round(ref, 5), "ours": md[m], "not_worse": md[m] >= ref - 1e-12}
        ok &= one[m]["not_worse"]
    out["designs"][f"{plat}/gcd"] = {"clock_period_ns": T, "two_sided": rows, "one_sided_hold": one,
        "no_published_value": {k: md.get(k) for k in NOPUB}, "matches_published": bool(ok)}
out["matches_published"] = all(d["matches_published"] for d in out["designs"].values())
json.dump(out, open(os.path.join(LAB, "results", "t2_crosscheck.json"), "w"), indent=2)
for k, d in out["designs"].items():
    print(k, "matches_published =", d["matches_published"])
    for m, r in d["two_sided"].items(): print("  ", m, "ours", r["ours"], "ref~", r["implied_reference"], "+-", r["margin"], "->", "IN" if r["within_band"] else "OUT", r["direction"])
    for m, r in d["one_sided_hold"].items(): print("  ", m, "ours", r["ours"], "ref~", r["implied_reference"], "not worse:", r["not_worse"])
