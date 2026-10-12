#!/usr/bin/env python3
"""Plots for Task 3: t3_cycles_vs_analytic.png, t3_roofline.png (into demo/assets/).
usage: t3_plots.py OUTDIR SUMMARY_JSON"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

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
    p = os.path.join(out, "roofline.json")
    if not os.path.exists(p):
        return
    r = json.load(open(p))
    fig, axes = plt.subplots(1, len(r["runs"]), figsize=(6 * len(r["runs"]), 4.8), squeeze=False)
    for ax, (name, run) in zip(axes[0], r["runs"].items()):
        peak, bw = run["peak_flops_per_cycle"], run["dram_words_per_cycle"]
        xs = [10 ** (i / 20) for i in range(-10, 80)]
        ax.plot(xs, [min(peak, bw * x) for x in xs], "k-", lw=1.5, label="roofline")
        for L in run["layers"]:
            c = "#d1495b" if L["obs_bandwidth_bound"] else "#2a9d8f"
            ax.scatter(L["ai"], L["achieved_flops_per_cycle"], color=c, s=40, zorder=3)
            ax.annotate(L["name"], (L["ai"], L["achieved_flops_per_cycle"]), fontsize=6, xytext=(3, 3),
                        textcoords="offset points")
        ax.axvline(run["ridge_ai"], color="gray", ls=":", label=f"ridge AI = {run['ridge_ai']:.1f}")
        ax.scatter([], [], color="#d1495b", label="stalls > threshold (SCALE-Sim)")
        ax.scatter([], [], color="#2a9d8f", label="no/low stalls")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("arithmetic intensity (FLOP / DRAM byte)"); ax.set_ylabel("achieved FLOP / cycle")
        ax.set_title(f"{name}: agreement {run['agreement']:.0%}, rho(AI, stall) = {run['spearman_ai_stallfrac']:.2f}",
                     fontsize=9)
        ax.legend(frameon=False, fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, "t3_roofline.png"), dpi=130)


if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    cycles_plot(sys.argv[1])
    roofline_plot(sys.argv[1])
    print("plots written to demo/assets")
