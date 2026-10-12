#!/usr/bin/env python3
"""Sweep A: SCALE-Sim architecture sweep.  Resumable JSONL, per-point timeout. Part 2: host-side driver,
one lab-sim container per point under scripts/with_lock.sh at LOW priority; deadline from budget_part2.json.
Later lines of a key supersede earlier attempts.

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
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LAB, "model"))

SRAM_KB = {"small": 16, "default": 64, "large": 1024}
TOPOS = {  # name -> (path under arch/bundled/topologies, gemm?)
    "gemm_test": ("GEMM_mnk/test_mnk_input.csv", True),   # one small 256x128x256 GEMM: separate workload for small arrays
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
    sq5 = [(n, n) for n in (8, 16, 32, 64, 128)]
    sq4 = [(n, n) for n in (16, 32, 64, 128)]
    rect = [(16, 64), (64, 16), (32, 128), (128, 32)]
    big = ["alexnet_part", "vit_s", "ncf"]
    # phase tags only label the intent; actual order = cheapest estimated cost first (stable), so points that
    # finish in tens/hundreds of seconds are done before anything slow.  8x8/16x16 on the big workloads are the
    # most expensive (many folds); small arrays are covered by the separate small workload "gemm_test".
    add(1, big, sq4, ["default"])
    add(2, ["gemm_test"], sq5, ["default", "small", "large"])
    add(3, big, rect, ["default"])
    add(4, big, sq4, ["small", "large"])
    add(5, ["gemm_test"], rect, ["default"])
    add(6, ["alexnet_part", "vit_s"], [(8, 8)], ["default"])
    add(7, ["alexnet"], sq4, ["default"])
    add(8, big, [(24, 24), (48, 48), (96, 96)], ["default"])
    add(9, ["resnet18"], [(64, 64), (128, 128)], ["default"])
    add(10, ["alexnet"], rect, ["default"])
    out = sorted(pts, key=lambda p: (est_cost(p[1], p[2], p[3], p[4]) // 60, p[0]))
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


def latest(path):
    """key -> last JSONL record (later lines supersede earlier attempts of the same key)."""
    out = {}
    if os.path.exists(path):
        for line in open(path):
            try:
                d = json.loads(line)
                out[d["key"]] = d
            except Exception:
                pass
    return out


def exec_point(key_args, tmo, name):
    """Run one point in a lab-sim container, under the lab lock at LOW priority (waits while any
    high-priority job is queued).  The per-point timeout starts only once the lock is held (it is
    enforced by `timeout` inside the container).  Returns (returncode, stdout, stderr, oom_killed|None,
    lock_wait_s)."""
    snippet = (
        'source "$LAB/env.sh"; source "$LAB/coord/images.env"; '
        'docker rm -f "$NAME" >/dev/null 2>&1; T0=$(date +%s); '
        'docker run --name "$NAME" --platform linux/amd64 -e PYTHONHASHSEED=0 -v "$LAB":/lab -w /lab "$LAB_SIM_IMAGE" '
        'timeout "$TMO" python3 sweeps/arch_sweep.py --one "$ARGS"; rc=$?; '
        'echo "OOMKilled=$(docker inspect -f {{.State.OOMKilled}} "$NAME" 2>/dev/null) ExitCode=$(docker inspect -f {{.State.ExitCode}} "$NAME" 2>/dev/null) ran_s=$(( $(date +%s) - T0 ))" >&2; '
        'docker rm -f "$NAME" >/dev/null 2>&1; exit $rc')
    env = dict(os.environ, LAB=LAB, NAME=name, TMO=str(int(tmo)), ARGS=key_args, LOCK_PRIO="low")
    t0 = time.time()
    r = subprocess.run([os.path.join(LAB, "scripts/with_lock.sh"), "arch", "bash", "-c", snippet],
                       capture_output=True, text=True, env=env, cwd=LAB)
    meta = [l for l in r.stderr.splitlines() if l.startswith("OOMKilled=")]
    oom = None
    ran = None
    if meta:
        oom = "OOMKilled=true" in meta[-1]
        try:
            ran = int(meta[-1].split("ran_s=")[1])
        except Exception:
            pass
    return r.returncode, r.stdout, r.stderr, oom, ran, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(LAB, "results/sweeps/arch.jsonl"))
    ap.add_argument("--timeout", type=int, default=1200, help="per-point run timeout (s), measured after the lock is held")
    ap.add_argument("--retry-timeout-factor", type=int, default=2, help="timeout multiplier for the retry pass")
    ap.add_argument("--budget", default=os.path.join(LAB, "budget_part2.json"))
    ap.add_argument("--max-points", type=int, default=0)
    ap.add_argument("--one", help="internal (runs inside the container): topo,df,R,C,sram")
    a = ap.parse_args()
    if a.one:
        t, df, R, C, s = a.one.split(",")
        run_one(t, df, int(R), int(C), s)
        return
    deadline = json.load(open(a.budget))["deadline_sweeps_stop_epoch"]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    cur = latest(a.out)
    planned = grid()
    todo = [p for p in planned if key_of(*p[1:]) not in cur]
    if a.max_points:
        todo = todo[:a.max_points]
    print(f"[arch_sweep] {len(cur)} keys recorded, {len(todo)} never attempted, "
          f"{max(0, int(deadline - time.time()))}s until stop deadline (budget_part2.json)", flush=True)
    n = [0]

    def record(rec):
        with open(a.out, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        n[0] += 1
        cur[rec["key"]] = rec
        print(f"[arch_sweep] +{n[0]} {rec['key']} {rec['status']} {rec.get('wall_s')}s cycles={rec.get('total_cycles')}", flush=True)

    def attempt(p, tmo, attempt_no):
        ph, t, df, R, C, s = p
        key = key_of(t, df, R, C, s)
        tmo = min(tmo, deadline - time.time() - 60)
        if tmo < 120:
            return None
        rec = dict(key=key, phase=ph, topo=t, dataflow=df, rows=R, cols=C, sram=s, sram_kb=SRAM_KB[s],
                   scalesim="3.0.0", attempt=attempt_no, timeout_s=int(tmo))
        rc, out, err, oom, ran, waited = exec_point(f"{t},{df},{R},{C},{s}", tmo, f"arch-pt-{os.getpid()}")
        line = [l for l in out.splitlines() if l.startswith("RESULT ")]
        rec["wall_s"] = round(ran if ran is not None else waited, 1)
        rec["docker_exit_code_incl_timeout"] = rc
        if rc == 0 and line:
            rec.update(json.loads(line[-1][7:]))
            rec["status"] = "ok"
        else:
            if time.time() > deadline - 90 and rc not in (124,):
                return None          # cut by the global stop, not a point failure
            rec["status"] = "timeout" if rc == 124 else "error"
            rec["oom_killed"] = oom
            rec["returncode"] = rc
            tail = [l for l in err.splitlines() if not l.startswith("OOMKilled=")][-12:]
            rec["error"] = "\n".join(tail)[-800:].replace(os.path.expanduser("~"), "~")
            rec["diagnosis"] = ("timeout: `timeout` killed the run after %ds (exit 124)" % tmo if rc == 124 else
                                "container OOM-killed (docker State.OOMKilled=true)" if oom else
                                "exit code %s, OOMKilled=%s; see error tail" % (rc, oom))
        return rec

    failed = {}
    for p in todo:
        key = key_of(*p[1:])
        if time.time() > deadline - 180:
            print("[arch_sweep] deadline reached", flush=True)
            break
        size = (p[1], p[3], p[4])
        if size in failed:
            record(dict(key=key, phase=p[0], topo=p[1], dataflow=p[2], rows=p[3], cols=p[4], sram=p[5], sram_kb=SRAM_KB[p[5]],
                        scalesim="3.0.0", status="skipped_after_timeout",
                        reason=f"{p[1]} at {p[3]}x{p[4]} already failed ({failed[size]}); retried in the retry pass"))
            continue
        rec = attempt(p, a.timeout, 1)
        if rec is None:
            break
        record(rec)
        if rec["status"] != "ok":
            failed[size] = f"{rec['status']} on {rec['key']}"
    # ---- retry pass: failed / skipped points, doubled timeout, failing points first ----
    bad = [p for p in planned if cur.get(key_of(*p[1:]), {}).get("status") in ("error", "timeout", "skipped_after_timeout")]
    bad.sort(key=lambda p: (cur[key_of(*p[1:])]["status"] == "skipped_after_timeout", est_cost(p[1], p[2], p[3], p[4])))
    resolved_sizes, dead_sizes = set(), set()
    for p in bad:
        if time.time() > deadline - 180:
            print("[arch_sweep] deadline reached in retry pass", flush=True)
            break
        size = (p[1], p[3], p[4])
        key = key_of(*p[1:])
        if cur[key]["status"] == "skipped_after_timeout" and size in dead_sizes:
            continue
        rec = attempt(p, a.timeout * a.retry_timeout_factor, cur[key].get("attempt", 1) + 1)
        if rec is None:
            break
        record(rec)
        (dead_sizes if rec["status"] != "ok" else resolved_sizes).add(size)
    print(f"[arch_sweep] finished: {n[0]} new records", flush=True)


if __name__ == "__main__":
    main()
