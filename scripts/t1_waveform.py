#!/usr/bin/env python3
"""Render the VCD of the small Task-1 case to a PNG (matplotlib + vcdvcd).

usage: t1_waveform.py <in.vcd> <case.json> <out.png>
"""
import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from vcdvcd import VCDVCD  # noqa: E402

INK, MUTED, GRID = "#1f2933", "#6b7785", "#d9dee4"
C_CTRL, C_A, C_B, C_ACC = "#3d5a80", "#2a7f62", "#b5651d", "#7b3fa0"


def s8(v):
    return v - 256 if v >= 128 else v


def s32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def main(vcd_path, json_path, png_path):
    case = json.load(open(json_path))
    vcd = VCDVCD(vcd_path, store_tvs=True)
    names = {n.split(".")[-1].split("[")[0]: n for n in vcd.signals if n.count(".") == 1}
    ts = vcd.timescale["timescale"]            # seconds per VCD tick
    period = round(10e-9 / float(ts))          # 10 ns clock

    def at(sig, t):
        v = vcd[names[sig]][t]
        return None if set(v) & set("xXzZ") else int(v, 2)

    end = vcd.endtime
    ncyc = int(end // period)
    # sample in the second half of each clock-high phase: after the falling
    # edge where the testbench drives, just before the next rising edge
    mid = [c * period + period - 1 for c in range(ncyc)]
    clear = [at("clear", t) for t in mid]
    start = max(0, max(i for i, v in enumerate(clear) if v) - 1)   # last clear pulse
    cyc = list(range(start, ncyc))
    R, C = len(case["A"]), len(case["B"][0])

    rows = [("clk", "clk"), ("clear", "bit"), ("in_valid", "bit")]
    rows += [(f"a_i[{i}]", "a") for i in range(R)]
    rows += [(f"b_i[{j}]", "b") for j in range(C)]
    rows += [("busy", "bit")]
    rows += [(f"acc[{i}][{j}]", "acc") for i, j in ((0, 0), (0, C - 1), (R - 1, 0), (R - 1, C - 1))]

    fig, ax = plt.subplots(figsize=(13, 0.42 * len(rows) + 1.6), dpi=130)
    n = len(rows)
    for r, (label, kind) in enumerate(rows):
        y = n - 1 - r
        ax.text(-0.15, y + 0.3, label, ha="right", va="center", fontsize=9, color=INK,
                family="monospace")
        for x, c in enumerate(cyc):
            t = mid[c]
            if kind == "clk":
                ax.plot([x, x, x + 0.5, x + 0.5, x + 1], [y + 0.05, y + 0.6, y + 0.6, y + 0.05, y + 0.05],
                        color=MUTED, lw=1)
                continue
            if kind == "bit":
                v = at(label, t)
                h = 0.6 if v else 0.05
                ax.fill_between([x, x + 1], y + 0.05, y + h, color=C_CTRL, alpha=0.25, lw=0)
                ax.plot([x, x + 1], [y + h, y + h], color=C_CTRL, lw=1.4)
                continue
            if kind in ("a", "b"):
                idx = int(label.split("[")[1][:-1])
                word = at(kind + "_i", t)
                valid = at("in_valid", t)
                v = None if word is None else s8((word >> (8 * idx)) & 0xFF)
                color = C_A if kind == "a" else C_B
                live = bool(valid)
            else:
                i, j = (int(p[:-1]) for p in label.split("[")[1:])
                word = at("acc_o", t)
                v = None if word is None else s32((word >> (32 * (i * C + j))) & 0xFFFFFFFF)
                color, live = C_ACC, True
            ax.add_patch(plt.Rectangle((x + 0.04, y + 0.05), 0.92, 0.55, fill=live, lw=0.8,
                                       facecolor=color if live else "none", alpha=1.0,
                                       edgecolor=color if live else GRID))
            ax.text(x + 0.5, y + 0.32, "x" if v is None else str(v), ha="center", va="center",
                    fontsize=8, color="white" if live else MUTED, family="monospace")
    for x in range(len(cyc) + 1):
        ax.axvline(x, color=GRID, lw=0.5, zorder=0)
    ax.set_xlim(-0.1, len(cyc))
    ax.set_ylim(-0.3, n)
    ax.set_xticks([x + 0.5 for x in range(len(cyc))])
    ax.set_xticklabels([str(x) for x in range(len(cyc))], fontsize=8, color=MUTED)
    ax.set_xlabel("clock cycle (starts at a rising edge; values shown are those sampled by the next rising edge)", fontsize=9, color=MUTED)
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ok = "match" if case["match"] else "MISMATCH"
    ax.set_title(
        f"systolic_os {R}x{C}: one tile, K={len(case['B'])} steps (Icarus Verilog VCD). "
        f"Skewed operands meet in PE(i,j) i+j clocks after entering; "
        f"acc[{R-1}][{C-1}] = {case['rtl'][R-1][C-1]} (NumPy {case['numpy'][R-1][C-1]}, {ok})",
        fontsize=9.5, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(png_path, metadata={"Software": None})
    print(f"wrote {png_path}: {len(cyc)} cycles, {n} rows")


if __name__ == "__main__":
    main(*sys.argv[1:4])
