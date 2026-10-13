#!/usr/bin/env python3
"""P2.4 (stage 63_sram_cacti): run CACTI for the lab's scratchpad sizes. Criteria are in results/p2_63_sram_cacti.json (committed before the first run).
  scripts/p2_sram_run.py gen     write the configs into results/sram/cfg/ (from the unmodified bundled cache.cfg copy results/sram/cache.cfg.base)
  scripts/p2_sram_run.py run     one lock hold (a few seconds each): every config run twice in the CACTI container -> results/sram/out/
  scripts/p2_sram_run.py parse   parse outputs -> results/sram_cacti.json
"""
import json
import os
import re
import subprocess
import sys

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(LAB, "results/sram")
CFG, OUT = os.path.join(R, "cfg"), os.path.join(R, "out")
SIZES_KB = [16, 64, 1024, 2048, 6144]
TEMP = 350
BLOCK = 128


def points():
    p = [(f"s{kb}k_45nm", kb, 0.045) for kb in SIZES_KB]
    p += [("s4096k_45nm", 4096, 0.045), ("s64k_90nm", 64, 0.090), ("s64k_45nm_rep", 64, 0.045)]  # 4096 = part of the 6144 fallback; rep = determinism repeat of s64k_45nm
    return p


def make_cfg(size_kb, tech):
    base = open(os.path.join(R, "cache.cfg.base")).read().splitlines()
    sub = [(r"^-size \(bytes\).*", f"-size (bytes) {size_kb * 1024}"),
           (r"^-block size \(bytes\) \d+", f"-block size (bytes) {BLOCK}"),
           (r"^-associativity \d+", "-associativity 1"),
           (r"^-technology \(u\).*", f"-technology (u) {tech:.3f}"),
           (r"^-output/input bus width \d+", f"-output/input bus width {BLOCK * 8}"),
           (r"^-operating temperature \(K\) \d+", f"-operating temperature (K) {TEMP}"),
           (r'^-cache type "cache"', '-cache type "ram"'),
           (r'^-Add ECC - "true"', '-Add ECC - "false"')]
    out = []
    for l in base:
        for pat, rep in sub:
            if re.match(pat, l):
                l = rep
        out.append(l)
    return "\n".join(out) + "\n"


def gen():
    os.makedirs(CFG, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    for name, kb, tech in points():
        open(os.path.join(CFG, name + ".cfg"), "w").write(make_cfg(kb, tech))
    print("configs:", [n for n, _, _ in points()])


def run():
    names = [n for n, _, _ in points()]
    loop = "cd /opt/cacti; for c in %s; do ./cacti -infile /lab/results/sram/cfg/$c.cfg > /lab/results/sram/out/$c.txt 2>&1; echo $c rc=$?; done; " % " ".join(names)
    loop += "for c in s64k_45nm; do ./cacti -infile /lab/results/sram/cfg/$c.cfg > /lab/results/sram/out/${c}_run2.txt 2>&1; done"
    env = dict(os.environ)
    img = [l.split("=")[1].strip() for l in open(os.path.join(LAB, "coord/images_cacti.env")) if l.startswith("CACTI_IMAGE=")][0]
    r = subprocess.run([os.path.join(LAB, "scripts/with_lock.sh"), "arch", "docker", "run", "--rm", "--platform", "linux/amd64",
                        "-v", f"{LAB}:/lab", "-w", "/opt/cacti", img, "bash", "-c", loop], capture_output=True, text=True, env=env)
    print(r.stdout, r.stderr[-500:])
    return r.returncode


KEYS = {"access_ns": r"Access time \(ns\):\s*([\d.eE+-]+)", "cycle_ns": r"Cycle time \(ns\):\s*([\d.eE+-]+)",
        "read_nJ": r"Total dynamic read energy per access \(nJ\):\s*([\d.eE+-]+)",
        "write_nJ": r"Total dynamic write energy per access \(nJ\):\s*([\d.eE+-]+)",
        "leak_mW": r"Total leakage power of a bank \(mW\):\s*([\d.eE+-]+)",
        "area_mm2": r"Cache height x width \(mm\):\s*([\d.eE+-]+) x ([\d.eE+-]+)"}


def parse_one(path):
    t = open(path).read()
    d = {}
    for k, pat in KEYS.items():
        m = re.search(pat, t)
        if m:
            d[k] = float(m.group(1)) * float(m.group(2)) if k == "area_mm2" else float(m.group(1))
            if k == "area_mm2":
                d["height_mm"], d["width_mm"] = float(m.group(1)), float(m.group(2))
    d["ok"] = all(k in d for k in ("access_ns", "read_nJ", "leak_mW", "area_mm2"))
    if not d["ok"]:
        d["raw_tail"] = t[-400:]
    return d


def parse():
    res = {}
    for name, kb, tech in points():
        p = os.path.join(OUT, name + ".txt")
        res[name] = dict(size_kB=kb, tech_um=tech, **(parse_one(p) if os.path.exists(p) else dict(ok=False, raw_tail="no output")))
    p2 = os.path.join(OUT, "s64k_45nm_run2.txt")
    det = None
    if os.path.exists(p2) and os.path.exists(os.path.join(OUT, "s64k_45nm.txt")):
        det = parse_one(p2) == parse_one(os.path.join(OUT, "s64k_45nm.txt"))
    json.dump(dict(model="CACTI 7 @ 1ffd8dfb10303d306ecd8d215320aea07651e878 (lab-cacti:20261012)", settings=dict(type="ram", block_bytes=BLOCK, ports="1 rw", banks=1, temp_K=TEMP, cells="itrs-hp"),
                   points=res, deterministic_two_runs_s64k_45nm=det), open(os.path.join(LAB, "results/sram_cacti.json"), "w"), indent=1, sort_keys=True)
    for n, v in res.items():
        print(n, {k: (round(x, 5) if isinstance(x, float) else x) for k, x in v.items() if k != "raw_tail"})
    print("deterministic:", det)


if __name__ == "__main__":
    {"gen": gen, "run": run, "parse": parse}[sys.argv[1]]()
