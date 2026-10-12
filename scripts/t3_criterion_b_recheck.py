#!/usr/bin/env python3
"""t3_criterion_b_recheck.py - recompute the Task 3 roofline criterion B verdict from the saved SCALE-Sim reports (no simulation, a few seconds).

Criterion B (pre-registered in model/t3_roofline2_criteria.json): in CALC bandwidth mode, Spearman rho between a layer's arithmetic intensity
and the DRAM bandwidth SCALE-Sim reports it requires must be <= -0.6, per dataflow. The saved per-layer data are results/t3/roofline2/rl2_calc_<df>.json.
Output: one line per dataflow with the recomputed rho and verdict, and whether it equals the verdict recorded in results/t3_summary.json.
Exit 0 when every recomputed verdict equals the recorded one (or nothing is recorded yet: then the verdict is printed as unrecorded); 1 on a disagreement;
2 when no saved report exists (the demo then reports SKIP, never PASS).
Usage: t3_criterion_b_recheck.py [--lab DIR]"""
import argparse, json, os, sys

THRESHOLD = -0.6


def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(x, y):
    a, b = ranks(x), ranks(y)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = (sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** 0.5
    return num / den if den else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    a = ap.parse_args()
    summ = {}
    try:
        summ = json.load(open(os.path.join(a.lab, "results/t3_summary.json")))
    except (OSError, ValueError):
        pass
    rec = summ.get("checks") or {}
    seen, bad = 0, 0
    for df in ("ws", "os", "is"):
        f = None
        for base in ("results/t3", "results/t3.partial"):
            p = os.path.join(a.lab, base, "roofline2", "rl2_calc_%s.json" % df)
            if os.path.exists(p):
                f = p
                break
        if f is None:
            print("%s: no saved CALC-mode report" % df)
            continue
        try:
            ls = json.load(open(f))["layers"]
            rho = spearman([x["ai"] for x in ls], [x["required_bw_words_per_cycle"] for x in ls])
        except (OSError, ValueError, KeyError):
            print("%s: saved report unreadable" % df)
            continue
        seen += 1
        verdict = rho <= THRESHOLD
        key = "calc_required_bw_inverse_to_ai_%s" % df
        if key in rec:
            same = bool(rec[key]) == verdict
            bad += 0 if same else 1
            note = "recorded verdict %s, %s" % (rec[key], "equal" if same else "DIFFERENT")
        else:
            note = "no recorded verdict yet"
        print("%s: %d layers, rho(intensity, required bandwidth) = %.3f, threshold <= %.1f -> %s (%s)" % (df, len(ls), rho, THRESHOLD, "criterion met" if verdict else "criterion NOT met", note))
    if not seen:
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
