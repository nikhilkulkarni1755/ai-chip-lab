#!/usr/bin/env python3
"""Plots for Task 3: t3_cycles_vs_analytic.png, t3_roofline.png (into demo/assets/).
usage: t3_plots.py OUTDIR SUMMARY_JSON"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(LAB, "demo/assets")
COL = {"os": "#1b6ca8", "ws": "#d1495b", "is": "#2a9d8f"}


def cycles_plot(out):
    fit = json.load(open(os.path.join(out, "fit.json")))
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.5), gridspec_kw={"width_ratios": [1.2, 1]})
    allv = []
    for df, v in fit["dataflows"].items():
        xs, ys, rs = [], [], []
        for g, gv in v["groups"].items():
            for p in gv["points"]:
                xs.append(p["model_cycles"]); ys.append(p["sim_cycles"]); rs.append(p["residual"])
        allv += xs + ys
        ax.scatter(xs, ys, s=28, color=COL[df], alpha=.8, label=f"{df} (held-out, n={len(xs)})")
        ax2.scatter(range(len(rs)), rs, s=28, color=COL[df], label=df)
    lo, hi = min(allv) * .8, max(allv) * 1.25
    ax.plot([lo, hi], [lo, hi], "k--", lw=1, label="y = x")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("analytic model cycles"); ax.set_ylabel("SCALE-Sim total cycles")
    ax.set_title("Held-out GEMMs (2R, 2C, 2R+2C, 2K, 2M, 2N)"); ax.legend(frameon=False, fontsize=8)
    ax2.axhline(0, color="k", lw=1); ax2.set_ylim(-2, 2)
    ax2.set_xlabel("held-out point index"); ax2.set_ylabel("residual (sim - model), cycles")
    mx = max(v["heldout_max_abs_residual"] for v in fit["dataflows"].values())
    ax2.set_title(f"Residuals (max |res| = {mx:g} cycles)"); ax2.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "t3_cycles_vs_analytic.png"), dpi=130)


def roofline_plot(out):
    d2 = os.path.join(out, "roofline2")
    if not os.path.isdir(d2):
        return
    import t3_roofline2 as R2
    dfs = R2.DFS
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    cols = {"mid": "#e9a03b", "high": "#1b6ca8"}
    r2 = json.load(open(os.path.join(out, "roofline2.json")))
    for k, df in enumerate(dfs):
        ax = axes[0][k]
        for b, B in R2.BW.items():
            fp = os.path.join(d2, f"rl2_user_{df}_{b}.json")
            if not os.path.exists(fp):
                ax.text(0.5, 0.5 - 0.1 * list(R2.BW).index(b), f"B={B}: {r2['cell_status'].get('rl2_user_'+df+'_'+b, 'not_run')}", transform=ax.transAxes, ha="center", color=cols[b])
                continue
            r = json.load(open(fp))
            ax.scatter([l["ai"] for l in r["layers"]], [max(l["stall_frac"], 1e-4) for l in r["layers"]],
                       s=26, color=cols[b], alpha=.85,
                       label=f"B={B} w/cyc, rho={r2['per_dataflow'][df]['user'][b]['rho']:+.2f}")
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_ylim(8e-5, 1.5)
        ax.set_title(f"{df}: stall fraction vs arithmetic intensity (USER bandwidth)", fontsize=9)
        ax.set_xlabel("arithmetic intensity (FLOP / compulsory DRAM byte)")
        ax.set_ylabel("stall cycles / total cycles (0 drawn at 1e-4)")
        ax.legend(frameon=False, fontsize=7)
        ax = axes[1][k]
        fp = os.path.join(d2, f"rl2_calc_{df}.json")
        if not os.path.exists(fp):
            ax.text(0.5, 0.5, "CALC run: " + r2["cell_status"].get("rl2_calc_" + df, "not_run"), transform=ax.transAxes, ha="center")
            continue
        r = json.load(open(fp))
        ax.scatter([l["ai"] for l in r["layers"]], [l["required_bw_words_per_cycle"] for l in r["layers"]], s=26, color="#2a9d8f")
        for l in r["layers"]:
            if l["name"] in ("FC", "Conv1", "Conv5_1b", "Conv3_s"):
                ax.annotate(l["name"], (l["ai"], l["required_bw_words_per_cycle"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(f"{df}: CALC mode, required DRAM bandwidth, rho = {r2['per_dataflow'][df].get('calc_rho_ai_vs_required_bw', float('nan')):+.2f}", fontsize=9)
        ax.set_xlabel("arithmetic intensity (FLOP / compulsory DRAM byte)")
        ax.set_ylabel("SCALE-Sim required DRAM BW (words/cycle)")
    fig.suptitle("Task 3 roofline check (pre-registered): ResNet-18, 21 layers, 128x128 array. "
                 f"{'PASS' if r2['passed'] else ('FAIL' if r2['complete'] or any(not v for k, v in r2['checks'].items() if k.startswith('calc_')) else 'INCOMPLETE')}"
                 f"{'' if r2['complete'] else ' (criterion B evaluated; criterion A not evaluated: cost)'}: criteria rho <= -0.6 (amended design P2-A2: B = 64, 256)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "t3_roofline.png"), dpi=130)


if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    cycles_plot(sys.argv[1])
    roofline_plot(sys.argv[1])
    print("plots written to demo/assets")
