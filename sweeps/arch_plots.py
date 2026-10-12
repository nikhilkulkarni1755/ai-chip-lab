#!/usr/bin/env python3
"""Heatmaps for sweep A -> demo/assets/sweepA_*.png.  Safe to re-run on partial data.
usage: arch_plots.py [results/sweeps/arch.jsonl]"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(LAB, "demo/assets")
DFS = ["ws", "os", "is"]
METRICS = [("cycles", "total_cycles", "total cycles (log colour)", True),
           ("util", "util_pct", "PE utilisation %", False),
           ("dram_bw", "dram_bw_avg_words_per_cycle", "avg DRAM traffic, words/cycle", True)]


def load(path):
    rows = []
    for line in open(path):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("status") == "ok":
            rows.append(r)
    return rows


def heat(rows, topo, key, label, logc, fname, sram="default"):
    rs = [r for r in rows if r["topo"] == topo and r["sram"] == sram]
    if not rs:
        return False
    dims_r = sorted({r["rows"] for r in rs}); dims_c = sorted({r["cols"] for r in rs})
    vals = [r[key] for r in rs]
    norm = LogNorm(min(vals), max(vals)) if logc and min(vals) > 0 else None
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    for ax, df in zip(axes, DFS):
        grid = [[None] * len(dims_c) for _ in dims_r]
        for r in rs:
            if r["dataflow"] == df:
                grid[dims_r.index(r["rows"])][dims_c.index(r["cols"])] = r[key]
        import numpy as np
        a = np.array([[np.nan if v is None else v for v in row] for row in grid], float)
        im = ax.imshow(a, origin="lower", cmap="viridis", norm=norm if norm else None, aspect="auto")
        for i in range(len(dims_r)):
            for j in range(len(dims_c)):
                if not np.isnan(a[i, j]):
                    ax.text(j, i, f"{a[i, j]:.3g}", ha="center", va="center", color="w", fontsize=7)
        ax.set_xticks(range(len(dims_c))); ax.set_xticklabels(dims_c)
        ax.set_yticks(range(len(dims_r))); ax.set_yticklabels(dims_r)
        ax.set_xlabel("array columns C"); ax.set_ylabel("array rows R"); ax.set_title(df)
        fig.colorbar(im, ax=ax, fraction=.046)
    fig.suptitle(f"SCALE-Sim sweep A: {topo}, SRAM {sram}: {label}   ({len(rs)} points)", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(ASSETS, fname), dpi=120)
    plt.close(fig)
    return True


def sram_plot(rows, topo):
    rs = [r for r in rows if r["topo"] == topo and r["rows"] == r["cols"]]
    if len({r["sram"] for r in rs}) < 2:
        return False
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    sty = {"small": "--", "default": "-", "large": ":"}
    for ax, df in zip(axes, DFS):
        for s in ("small", "default", "large"):
            pts = sorted((r["rows"], r["dram_bw_avg_words_per_cycle"]) for r in rs if r["dataflow"] == df and r["sram"] == s)
            if pts:
                ax.plot(*zip(*pts), sty[s], marker="o", label=f"SRAM {s}")
        ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_title(df); ax.set_xlabel("array size N (NxN)")
        ax.legend(frameon=False, fontsize=7)
    axes[0].set_ylabel("avg DRAM traffic, words/cycle")
    fig.suptitle(f"SRAM size vs DRAM traffic: {topo}", fontsize=10)
    fig.tight_layout(); fig.savefig(os.path.join(ASSETS, f"sweepA_sram_{topo}.png"), dpi=120); plt.close(fig)
    return True


def best_df(rows):
    pts = {}
    for r in rows:
        if r["sram"] == "default":
            pts.setdefault((r["topo"], r["rows"], r["cols"]), {})[r["dataflow"]] = r["total_cycles"]
    full = {k: v for k, v in pts.items() if len(v) == 3}
    if not full:
        return False
    topos = sorted({k[0] for k in full})
    fig, axes = plt.subplots(1, len(topos), figsize=(4.5 * len(topos), 3.8), squeeze=False)
    cmap = {"ws": "#d1495b", "os": "#1b6ca8", "is": "#2a9d8f"}
    for ax, t in zip(axes[0], topos):
        for (tt, R, C), v in full.items():
            if tt != t:
                continue
            b = min(v, key=v.get)
            ax.scatter(C, R, s=420, color=cmap[b], marker="s")
            ax.text(C, R, b, ha="center", va="center", color="w", fontsize=8)
        ax.set_xscale("log", base=2); ax.set_yscale("log", base=2)
        ax.set_xlabel("C"); ax.set_ylabel("R"); ax.set_title(f"{t}: fastest dataflow")
    fig.tight_layout(); fig.savefig(os.path.join(ASSETS, "sweepA_best_dataflow.png"), dpi=120); plt.close(fig)
    return True


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LAB, "results/sweeps/arch.jsonl")
    os.makedirs(ASSETS, exist_ok=True)
    rows = load(path)
    made = []
    for topo in sorted({r["topo"] for r in rows}):
        for name, key, label, logc in METRICS:
            if heat(rows, topo, key, label, logc, f"sweepA_{name}_{topo}.png"):
                made.append(f"sweepA_{name}_{topo}.png")
        if sram_plot(rows, topo):
            made.append(f"sweepA_sram_{topo}.png")
    if best_df(rows):
        made.append("sweepA_best_dataflow.png")
    print(f"[arch_plots] {len(rows)} ok points -> {len(made)} plots")


if __name__ == "__main__":
    main()
