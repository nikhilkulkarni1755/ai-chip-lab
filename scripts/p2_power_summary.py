#!/usr/bin/env python3
"""P2.1 summary: parse results/power_activity/raw/*.log, evaluate the criteria registered in results/p2_60_power_activity.json
(thresholds below are the registered ones; they were committed before the first run), write
results/power_activity.json, results/p2_60_power_activity.json (filled), evidence, demo/assets/power_activity.png."""
import hashlib, json, os, re, sys

LAB = os.path.expanduser("~/ai-chip-lab")
RAW = os.path.join(LAB, "results", "power_activity", "raw")
WL = ["random", "sparse50", "allmax"]
# ---- registered thresholds (do not tune after seeing results) ----
COVER_MIN = 0.90          # annotated fraction of netlist pins per workload run
ZERO_FRAC = {"sparse50": (0.48, 0.52), "allmax": (0.0, 0.0), "random": (0.0, 0.01)}
LEAK_SPREAD_MAX = 0.10    # (max-min)/mean of leakage over the 3 workloads
VECTORLESS_TOL = 0.01     # our vectorless load vs ORFS finish__power__total
EV = os.path.join(LAB, "results", "evidence")


def parse(tag):
    p = os.path.join(RAW, tag + ".log")
    if not os.path.exists(p):
        return None
    t = open(p, errors="replace").read()
    r = {"log": os.path.relpath(p, LAB)}
    m = re.search(r"@@TOTALPINS (\d+)", t); r["total_pins"] = int(m.group(1)) if m else None
    m = re.search(r"@@POWER-BEGIN(.*?)@@POWER-END", t, re.S)
    if not m:
        r["error"] = "no power report"; return r
    rows = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"\s*(Sequential|Combinational|Macro|Pad|Total)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", line)
        if mm:
            rows[mm.group(1).lower()] = dict(zip(("internal_w", "switching_w", "leakage_w", "total_w"), map(float, mm.groups()[1:5])))
    r["groups"] = rows; r.update(rows.get("total", {}))
    r["dynamic_w"] = r["internal_w"] + r["switching_w"] if "internal_w" in r else None
    m = re.search(r"@@UNANNOT-BEGIN(.*?)@@UNANNOT-END", t, re.S)
    if m:
        un = [l.strip() for l in m.group(1).splitlines() if "/" in l and " " not in l.strip()]
        r["unannotated_pins"] = len(un)
        if r["total_pins"]:
            r["annotated_fraction"] = round(1 - len(un) / r["total_pins"], 4)
    m = re.search(r"@@ANNOT-BEGIN(.*?)@@ANNOT-END", t, re.S)
    r["annotation_report"] = m.group(1).strip()[:600] if m else None
    return r


def main():
    res = {"vectorless": parse("vectorless"), "repeat": parse("random.window.repeat"), "workloads": {}}
    meta = {w: json.load(open(os.path.join(LAB, "results", "power_vcd", w + ".json"))) for w in WL if os.path.exists(os.path.join(LAB, "results", "power_vcd", w + ".json"))}
    for w in WL:
        win, whole = parse(w + ".window"), parse(w + ".whole")
        use, how = (win, "active window") if win and win.get("dynamic_w") and (win.get("annotated_fraction") or 0) >= 0.5 else (whole, "whole file (window run unusable)")
        res["workloads"][w] = {"used": how, "scope": open(os.path.join(RAW, w + ".scope")).read().strip() if os.path.exists(os.path.join(RAW, w + ".scope")) else None,
                               "window_run": win, "whole_run": whole, "result": use, "vcd_meta": meta.get(w)}
    base = json.load(open(os.path.join(LAB, "orfs", "work", "reports", "nangate45", "systolic_os", "base", "metadata.json")))
    ref = base["finish__power__total"]
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    n_live = sha(os.path.join(LAB, "orfs/work/results/nangate45/systolic_os/base/6_final.v"))
    n_snap = sha(os.path.join(LAB, "results/part1_snapshot/systolic_os_routed/6_final.v"))
    C = []
    def crit(name, thr, measured, ok):
        C.append({"name": name, "threshold": thr, "measured": measured, "pass": bool(ok)})
    vl = res["vectorless"] or {}
    dv = abs(vl.get("total_w", 0) - ref) / ref if vl.get("total_w") else None
    crit("setup_reproduces_orfs_vectorless", f"our vectorless report_power on the routed design within {VECTORLESS_TOL:.0%} of ORFS finish__power__total",
         f"ours {vl.get('total_w')} W, ORFS {ref} W, deviation {dv}", dv is not None and dv <= VECTORLESS_TOL)
    cov = {w: (res["workloads"][w]["result"] or {}).get("annotated_fraction") for w in WL}
    crit("vcd_annotation_coverage", f"annotated fraction of netlist pins >= {COVER_MIN} for every workload (VCD names map onto the routed flat netlist)",
         json.dumps(cov), all(c is not None and c >= COVER_MIN for c in cov.values()))
    zf = {w: (meta.get(w) or {}).get("operand_zero_fraction") for w in WL}
    mm = {w: (meta.get(w) or {}).get("mismatching_elements_vs_numpy") for w in WL}
    crit("workloads_valid", "0 mismatches vs NumPy per workload; operand zero fraction sparse50 in [0.48,0.52], allmax = 0, random < 0.01",
         f"zero fractions {json.dumps(zf)}, mismatches {json.dumps(mm)}",
         all(mm[w] == 0 for w in WL) and all(zf[w] is not None and ZERO_FRAC[w][0] <= zf[w] <= ZERO_FRAC[w][1] for w in WL))
    dyn = {w: (res["workloads"][w]["result"] or {}).get("dynamic_w") for w in WL}
    leak = {w: (res["workloads"][w]["result"] or {}).get("leakage_w") for w in WL}
    have = all(dyn.values())
    crit("sparse_uses_less_dynamic_power_than_random", "dynamic (internal+switching) power sparse50 < random (spec sanity)",
         f"sparse50 {dyn['sparse50']} W vs random {dyn['random']} W, ratio {dyn['sparse50']/dyn['random'] if have else None}", have and dyn["sparse50"] < dyn["random"])
    crit("allmax_uses_less_dynamic_power_than_random", "additional expected ordering: constant all-max operands do not toggle operand registers, so dynamic power allmax < random",
         f"allmax {dyn['allmax']} W vs random {dyn['random']} W, ratio {dyn['allmax']/dyn['random'] if have else None}", have and dyn["allmax"] < dyn["random"])
    if all(leak.values()):
        mean = sum(leak.values()) / 3; spread = (max(leak.values()) - min(leak.values())) / mean
    else:
        spread = None
    crit("leakage_roughly_constant", f"(max-min)/mean of leakage over the three workloads <= {LEAK_SPREAD_MAX}", f"leakage {json.dumps(leak)}, spread {spread}", spread is not None and spread <= LEAK_SPREAD_MAX)
    rp, r0 = res["repeat"] or {}, (res["workloads"]["random"]["window_run"] or {})
    crit("analysis_deterministic", "second identical analysis of the random workload gives identical internal/switching/leakage/total",
         f"{ {k: (rp.get(k), r0.get(k)) for k in ('internal_w', 'switching_w', 'leakage_w', 'total_w')} }", bool(rp) and all(rp.get(k) == r0.get(k) for k in ("internal_w", "switching_w", "leakage_w", "total_w")))
    crit("netlist_identity", "sha256 of the netlist OpenROAD analysed equals the one the VCD simulation used (results/part1_snapshot/systolic_os_routed/6_final.v)",
         f"analysed {n_live[:12]}, simulated {n_snap[:12]}", n_live == n_snap)
    out = {"design": "nangate45/systolic_os (routed, base run, clock 4.0 ns)", "openroad": "pinned ORFS image (coord/images.env)", "orfs_vectorless_total_w": ref,
           "ratios_to_orfs_vectorless": {w: ((res["workloads"][w]["result"] or {}).get("total_w") or 0) / ref for w in WL},
           "criteria": C, "pass": all(c["pass"] for c in C), "raw": res}
    json.dump(out, open(os.path.join(LAB, "results", "power_activity.json"), "w"), indent=1)
    # stage json: keep registered criteria text/commit, fill measurements
    sp = os.path.join(LAB, "results", "p2_60_power_activity.json"); S = json.load(open(sp))
    byname = {c["name"]: c for c in C}
    for c in S["criteria"]:
        if c["name"] in byname:
            c["measured"] = byname[c["name"]]["measured"]; c["pass"] = byname[c["name"]]["pass"]
    S["pass"] = out["pass"]; S.pop("state", None)
    S["finding"] = "total power / ORFS vectorless: " + json.dumps({w: round(v, 3) for w, v in out["ratios_to_orfs_vectorless"].items()})
    json.dump(S, open(sp, "w"), indent=2)
    os.makedirs(EV, exist_ok=True)
    open(os.path.join(EV, "60_power_activity.txt"), "w").write(json.dumps({k: out[k] for k in ("design", "orfs_vectorless_total_w", "ratios_to_orfs_vectorless", "criteria", "pass")}, indent=1) + "\n")
    plot(out)
    print(json.dumps({c["name"]: c["pass"] for c in C}, indent=1), "pass:", out["pass"])


def plot(out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    labs = ["ORFS default\n(vectorless)"] + WL
    rows = [out["raw"]["vectorless"]] + [out["raw"]["workloads"][w]["result"] for w in WL]
    comp = [("internal_w", "internal", "#1f77b4"), ("switching_w", "switching", "#ff7f0e"), ("leakage_w", "leakage", "#2ca02c")]
    fig, ax = plt.subplots(figsize=(7, 4.2)); bot = [0] * 4
    for k, n, c in comp:
        v = [(r or {}).get(k, 0) * 1e3 for r in rows]
        ax.bar(labs, v, bottom=bot, label=n, color=c); bot = [a + b for a, b in zip(bot, v)]
    for i, t in enumerate(bot): ax.text(i, t, f"{t:.2f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("power (mW)"); ax.set_title("systolic_os (routed, nangate45, 4.0 ns): power by workload"); ax.legend(); ax.grid(axis="y", alpha=.3)
    fig.tight_layout(); os.makedirs(os.path.join(LAB, "demo/assets"), exist_ok=True)
    fig.savefig(os.path.join(LAB, "demo/assets/power_activity.png"), dpi=130)


if __name__ == "__main__":
    main()
