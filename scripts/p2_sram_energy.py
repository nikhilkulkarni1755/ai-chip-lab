#!/usr/bin/env python3
"""P2.4: order-of-magnitude SRAM energy per inference for 3 sweep A configurations, plot, evidence.
SRAM energy = SRAM word traffic (sweep A sram_bw_avg_words_per_cycle x total_cycles) x CACTI 45 nm read energy per word
(read energy of one 128-byte access / 128 words). Every SRAM access is charged as a read (writes cost 1.2-2x in CACTI): lower bound.
DRAM and MAC energy are NOT modelled; DRAM word traffic is listed, and the break-even DRAM energy per word is computed (no assumed constant)."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = json.load(open(os.path.join(LAB, "results/sram_cacti.json")))["points"]
cur = {}
for l in open(os.path.join(LAB, "results/sweeps/arch.jsonl")):
    d = json.loads(l); cur[d["key"]] = d
KB = {"small": 16, "default": 64, "large": 1024}
rows = []
for sram in ("small", "default", "large"):
    r = cur[f"vit_s|os|128x128|{sram}"]
    e_word_pj = C[f"s{KB[sram]}k_45nm"]["read_nJ"] / 128 * 1000
    words = r["sram_bw_avg_words_per_cycle"] * r["total_cycles"]
    dram = r["dram_reads_ifmap"] + r["dram_reads_filter"] + r["dram_writes_ofmap"]
    rows.append(dict(config=f"vit_s os 128x128, {KB[sram]} kB per buffer", sram=sram, cycles=r["total_cycles"], sram_words=words, dram_words=dram,
                     sram_read_pJ_per_word=e_word_pj, sram_energy_uJ=words * e_word_pj * 1e-6, buffer_area_mm2_x3=3 * C[f"s{KB[sram]}k_45nm"]["area_mm2"],
                     buffer_leakage_mW_x3=3 * C[f"s{KB[sram]}k_45nm"]["leak_mW"]))
for r in rows:   # leakage over the run at an ASSUMED 1 GHz clock (label)
    r["leakage_energy_uJ_at_1GHz"] = r["buffer_leakage_mW_x3"] * 1e-3 * r["cycles"] * 1e-9 * 1e6
a, b, c = rows
be = {}
for lo, hi, nm in ((a, b, "small->default"), (b, c, "default->large")):
    dd = lo["dram_words"] - hi["dram_words"]; ds = hi["sram_energy_uJ"] - lo["sram_energy_uJ"]
    be[nm] = dict(dram_words_saved=dd, sram_energy_added_uJ=ds, break_even_dram_pJ_per_word=(ds * 1e6 / dd) if dd > 0 else None)
out = dict(label="ORDER-OF-MAGNITUDE model, not a prediction: 45 nm ITRS-based CACTI numbers, SRAM read energy only, DRAM and MAC energy not modelled, leakage at an assumed 1 GHz clock",
           workload="ViT-S GEMM list (sweep A topology vit_s), output stationary, 128x128 array", configs=rows, break_even=be)
json.dump(out, open(os.path.join(LAB, "results/sram_energy_model.json"), "w"), indent=1)
fig, ax = plt.subplots(1, 3, figsize=(13, 4))
sz = sorted((v["size_kB"], v) for k, v in C.items() if k.endswith("_45nm") and "rep" not in k)
x = [s for s, _ in sz]
for axx, key, lab in ((ax[0], "area_mm2", "area (mm2)"), (ax[1], "access_ns", "access time (ns)")):
    axx.loglog(x, [v[key] for _, v in sz], "o-", color="#1b6ca8", label="45 nm")
    axx.loglog([64], [C["s64k_90nm"][key]], "s", color="#d1495b", label="64 kB, 90 nm")
    axx.set_xlabel("capacity (kB)"); axx.set_ylabel(lab); axx.legend(frameon=False, fontsize=8)
ax[2].loglog(x, [v["read_nJ"] for _, v in sz], "o-", color="#1b6ca8", label="read energy / 128 B access (nJ)")
ax[2].loglog(x, [v["leak_mW"] / 1000 for _, v in sz], "^-", color="#2a9d8f", label="leakage (W)")
ax[2].set_xlabel("capacity (kB)"); ax[2].legend(frameon=False, fontsize=8)
fig.suptitle("CACTI 7, 45 nm scratchpad SRAM (ram, 128 B block, 1 port): analytical model, trends and order of magnitude only", fontsize=10)
fig.tight_layout(); os.makedirs(os.path.join(LAB, "demo/assets"), exist_ok=True)
fig.savefig(os.path.join(LAB, "demo/assets/sram_cacti.png"), dpi=130)
print(json.dumps(out, indent=1))
