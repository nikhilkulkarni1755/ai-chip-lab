#!/usr/bin/env python3
"""Sweep B plots from results/sweeps/phys.jsonl (re-runnable on partial data).
  demo/assets/sweepB_frontier_<design>.png : fastest closing clock period per CORE_UTILIZATION (+ WNS vs period)
  demo/assets/sweepB_wns_heatmap_<design>.png : WNS (ns) over period x utilization
Run with ~/ai-chip-lab/.venv-pnr/bin/python sweeps/phys_plots.py
"""
import json, os, collections
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

LAB = os.path.expanduser("~/ai-chip-lab")
rows = [json.loads(l) for l in open(os.path.join(LAB, "results/sweeps/phys.jsonl")) if l.strip()]
rows = [r for r in rows if r.get("status") == "ok" and r.get("wns_setup_ns") is not None]
os.makedirs(os.path.join(LAB, "demo/assets"), exist_ok=True)
for des in sorted({r["design"] for r in rows}):
    R = [r for r in rows if r["design"] == des]
    utils = sorted({r["core_utilization"] for r in R}); periods = sorted({r["clock_period_ns"] for r in R})
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
    cmap = plt.get_cmap("viridis")
    front = {}
    for i, u in enumerate(utils):
        P = sorted((r["clock_period_ns"], r["wns_setup_ns"]) for r in R if r["core_utilization"] == u)
        ax[1].plot([p for p, _ in P], [w for _, w in P], "o-", color=cmap(i / max(1, len(utils) - 1)), label=f"util {u}%")
        ok = [p for p, w in P if w >= 0]
        if ok: front[u] = min(ok)
    ax[1].axhline(0, color="k", lw=.8); ax[1].set_xlabel("clock period (ns)"); ax[1].set_ylabel("setup WNS (ns)")
    ax[1].set_title("WNS vs clock period"); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
    if front:
        us = sorted(front); ax[0].plot(us, [front[u] for u in us], "s-", color="#1f77b4")
        ax[0].set_xlabel("CORE_UTILIZATION (%)"); ax[0].set_ylabel("fastest closing period (ns)")
        ax[0].set_title(f"Timing-closure frontier ({des})"); ax[0].grid(alpha=.3)
    else:
        ax[0].text(.5, .5, "no closing point yet", ha="center"); ax[0].set_axis_off()
    fig.tight_layout(); fig.savefig(os.path.join(LAB, f"demo/assets/sweepB_frontier_{des}.png"), dpi=130); plt.close(fig)
    M = np.full((len(utils), len(periods)), np.nan)
    for r in R: M[utils.index(r["core_utilization"]), periods.index(r["clock_period_ns"])] = r["wns_setup_ns"]
    fig, ax = plt.subplots(figsize=(1.1 * len(periods) + 3, 0.8 * len(utils) + 2))
    v = np.nanmax(np.abs(M)) or 1
    im = ax.imshow(M, cmap="RdYlGn", vmin=-v, vmax=v, aspect="auto", origin="lower")
    ax.set_xticks(range(len(periods))); ax.set_xticklabels([f"{p:g}" for p in periods], rotation=45)
    ax.set_yticks(range(len(utils))); ax.set_yticklabels(utils)
    for i in range(len(utils)):
        for j in range(len(periods)):
            if not np.isnan(M[i, j]): ax.text(j, i, f"{M[i,j]:.3f}", ha="center", va="center", fontsize=7)
    ax.set_xlabel("clock period (ns)"); ax.set_ylabel("CORE_UTILIZATION (%)"); ax.set_title(f"Setup WNS (ns), {des}; green = closes")
    fig.colorbar(im, label="WNS (ns)"); fig.tight_layout()
    fig.savefig(os.path.join(LAB, f"demo/assets/sweepB_wns_heatmap_{des}.png"), dpi=130); plt.close(fig)
    print("plots for", des, len(R), "points")
