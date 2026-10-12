#!/usr/bin/env python3
"""Sweep A: SCALE-Sim architecture sweep.  Resumable JSONL, per-point timeout, <=2 workers,
stops itself at deadline_sweeps_stop_epoch from budget.json.

  python3 sweeps/arch_sweep.py [--out results/sweeps/arch.jsonl] [--workers 2] [--timeout 900]

One JSON line per point, keyed by "key" = topo|dataflow|RxC|sram.  Re-running skips keys already
present (ok, timeout and error lines all count as done; delete a line to retry it).
Config = bundled scale.cfg (CALC interface-bandwidth mode: SCALE-Sim estimates the DRAM
bandwidth each layer needs; stalls are not modelled in that mode) with array, dataflow and the three SRAM
sizes overridden.  SRAM levels (per operand buffer): small 16 kB, default 64 kB (bundled), large 1024 kB.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LAB, "model"))

SRAM_KB = {"small": 16, "default": 64, "large": 1024}
TOPOS = {  # name -> (path under arch/bundled/topologies, gemm?)
    "alexnet_part": ("conv_nets/alexnet_part.csv", False),
    "alexnet": ("conv_nets/alexnet.csv", False),
    "vit_s": ("GEMM_mnk/vit_s.csv", True),
    "ncf": ("GEMM_mnk/NCF.csv", True),
    "resnet18": ("conv_nets/Resnet18.csv", False),
    "mobilenet": ("conv_nets/mobilenet.csv", False),
}
DFS = ["ws", "os", "is"]
SQUARES = [16, 32, 64, 128]


def est_cost(topo, df, R, C):
    """Rough wall seconds (calibrated: ~1.2e-5 (loaded) s per demand-line per array row on this machine)."""
    import analytic as an
    import sim
    p, g = TOPOS[topo]
    L = an.load_topology(os.path.join(sim.SCALESIM_SRC, "topologies", p), g)
    lines = 0
    for l in L:
        F, T = an.shape_map(df, l["M"], l["N"], l["K"], R, C)
        lines += F * (T + 2 * R + C)
    return lines * max(R, C) * 1.2e-5


def grid():
    """Ordered list of (phase, topo, df, R, C, sram). Coarse first, then refinement."""
    pts = []

    def add(ph, topos, arrays, srams):
        batch = []
        for t in topos:
            for (R, C) in arrays:
                for df in DFS:
                    for s in srams:
                        batch.append((ph, t, df, R, C, s))
        pts.extend(batch)

    sq = [(n, n) for n in SQUARES]
    cheap = ["alexnet_part", "vit_s", "ncf"]
    add(1, cheap, sq, ["default"])
    add(2, cheap, [(16, 64), (64, 16), (32, 128), (128, 32)], ["default"])
    add(3, cheap, sq, ["small", "large"])
    add(4, ["alexnet"], sq, ["default"])
    add(5, cheap, [(8, 8), (24, 24), (48, 48), (96, 96)], ["default"])
    add(6, ["resnet18"], [(32, 32), (64, 64), (128, 128)], ["default"])
    add(7, ["alexnet", "resnet18"], [(16, 64), (64, 16), (32, 128), (128, 32)], ["default"])
    add(8, ["alexnet", "resnet18"], [(64, 64), (128, 128)], ["small", "large"])
    add(9, ["mobilenet"], sq, ["default"])
    # within a phase: cheapest first so a complete coarse grid finishes early
    out, i = [], 0
    while i < len(pts):
        j = i
        while j < len(pts) and pts[j][0] == pts[i][0]:
            j += 1
        out += sorted(pts[i:j], key=lambda p: est_cost(p[1], p[2], p[3], p[4]))
        i = j
    return out


def key_of(t, df, R, C, s):
    return f"{t}|{df}|{R}x{C}|{s}"


def run_one(topo, df, R, C, sram):
    """Child process body: run SCALE-Sim, print one JSON result line."""
    import analytic as an
    import sim
    p, g = TOPOS[topo]
    tpath = os.path.join(sim.SCALESIM_SRC, "topologies", p)
    kb = SRAM_KB[sram]
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        cfg = sim.make_config(os.path.join(td, "c.cfg"), os.path.join(sim.SCALESIM_SRC, "configs/scale.cfg"),
                              R, C, df, kb, kb, kb)
        res, _ = sim.run(cfg, tpath, os.path.join(td, "out"), gemm=g)
    L = an.load_topology(tpath, g)
    macs = sum(l["M"] * l["N"] * l["K"] for l in L)
    cyc = sum(x["total_cycles"] for x in res)
    rec = dict(
        total_cycles=int(cyc),
        total_cycles_incl_prefetch=int(sum(x["total_cycles_incl_prefetch"] for x in res)),
        stall_cycles=int(sum(x["stall_cycles"] for x in res)),
        macs=int(macs),
        util_pct=100.0 * macs / (cyc * R * C),
        mapping_eff_pct=sum(x["mapping_eff"] for x in res) / len(res),
        dram_reads_ifmap=int(sum(x["ifmap_dram_reads"] for x in res)),
        dram_reads_filter=int(sum(x["filter_dram_reads"] for x in res)),
        dram_writes_ofmap=int(sum(x["ofmap_dram_writes"] for x in res)),
        dram_bw_avg_words_per_cycle=sum(x["ifmap_dram_reads"] + x["filter_dram_reads"] + x["ofmap_dram_writes"]
                                        for x in res) / cyc,
        dram_bw_peak_layer_words_per_cycle=max(x["ifmap_dram_bw"] + x["filter_dram_bw"] + x["ofmap_dram_bw"]
                                               for x in res),
        sram_bw_avg_words_per_cycle=sum(x["ifmap_sram_bw"] * x["total_cycles"] + x["filter_sram_bw"] * x["total_cycles"]
                                        + x["ofmap_sram_bw"] * x["total_cycles"] for x in res) / cyc,
        n_layers=len(res),
        sim_wall_s=round(time.time() - t0, 1),
    )
    print("RESULT " + json.dumps(rec, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(LAB, "results/sweeps/arch.jsonl"))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--budget", default=os.path.join(LAB, "budget.json"))
    ap.add_argument("--max-points", type=int, default=0)
    ap.add_argument("--one", help="internal: topo,df,R,C,sram")
    a = ap.parse_args()
    if a.one:
        t, df, R, C, s = a.one.split(",")
        run_one(t, df, int(R), int(C), s)
        return
    workers = min(a.workers, 2)
    deadline = json.load(open(a.budget))["deadline_sweeps_stop_epoch"]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    done = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try:
                done.add(json.loads(line)["key"])
            except Exception:
                pass
    todo = [p for p in grid() if key_of(*p[1:]) not in done]
    if a.max_points:
        todo = todo[:a.max_points]
    print(f"[arch_sweep] {len(done)} done, {len(todo)} to do, workers={workers}, "
          f"{max(0, int(deadline - time.time()))}s until stop deadline", flush=True)
    lock = threading.Lock()
    stop = threading.Event()
    env = dict(os.environ, PYTHONHASHSEED="0", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", NUMBA_NUM_THREADS="1")
    n_done = [0]

    def work(p):
        ph, t, df, R, C, s = p
        if stop.is_set() or time.time() > deadline - 30:
            stop.set()
            return
        key = key_of(t, df, R, C, s)
        rem = deadline - time.time()
        tmo = min(a.timeout, rem)
        rec = dict(key=key, phase=ph, topo=t, dataflow=df, rows=R, cols=C, sram=s, sram_kb=SRAM_KB[s],
                   scalesim="3.0.0")
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", f"{t},{df},{R},{C},{s}"],
                               capture_output=True, text=True, timeout=tmo, env=env, cwd=LAB)
            line = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
            if r.returncode == 0 and line:
                rec.update(json.loads(line[-1][7:]))
                rec["status"] = "ok"
            else:
                rec["status"] = "error"
                rec["error"] = (r.stderr or r.stdout)[-300:].replace(os.path.expanduser("~"), "~")
        except subprocess.TimeoutExpired:
            if time.time() > deadline - 35:   # killed by the global stop, not a real point timeout
                return
            rec["status"] = "timeout"
            rec["timeout_s"] = int(tmo)
        rec["wall_s"] = round(time.time() - t0, 1)
        with lock:
            with open(a.out, "a") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            n_done[0] += 1
            print(f"[arch_sweep] {len(done) + n_done[0]} {key} {rec['status']} {rec['wall_s']}s "
                  f"cycles={rec.get('total_cycles')}", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(work, todo))
    print(f"[arch_sweep] finished loop: {n_done[0]} new points; stopped_by_deadline={stop.is_set()}", flush=True)


if __name__ == "__main__":
    main()
