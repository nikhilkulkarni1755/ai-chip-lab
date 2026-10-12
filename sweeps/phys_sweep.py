#!/usr/bin/env python3
"""Sweep B: ORFS physical sweep, clock period x CORE_UTILIZATION.

One ORFS run at a time (scripts/t2_run.sh holds the heavy lock). One JSON line per point in
results/sweeps/phys.jsonl keyed by (platform, design, clock_period_ns, core_utilization); resumable (existing keys
are skipped, failed/timeout points are recorded and not retried unless --retry).

Phases: coarse grid (every utilization x every period), then refinement: for each utilization, bisect between the
tightest passing period (WNS >= 0) and the next failing one until the step is <= --min-step ns.
Stops by itself at budget.json:deadline_sweeps_stop_epoch (a point is only started if its expected runtime fits),
or when results/sweeps/phys.stop exists.

Clock period override: the stock constraint.sdc is read from the pinned image, `set clk_period <x>` is rewritten
into orfs/sdc_gen/<design>_<period>.sdc and passed as SDC_FILE=... on the make command line (image untouched).
Utilization override: CORE_UTILIZATION=<n> on the make command line (the stock gcd configs use CORE_UTILIZATION,
not absolute die/core area; checked in flow/designs/*/gcd/config.mk).
"""
import argparse, json, os, re, subprocess, sys, time

LAB = os.path.expanduser("~/ai-chip-lab")
sys.path.insert(0, os.path.join(LAB, "scripts"))
import t2_extract  # noqa: E402

OUT = os.path.join(LAB, "results", "sweeps", "phys.jsonl")
STOP = os.path.join(LAB, "results", "sweeps", "phys.stop")
SDCDIR = os.path.join(LAB, "orfs", "sdc_gen")


def now():
    return time.time()


def log(msg):
    line = time.strftime("%F %T ") + msg
    print(line, flush=True)
    with open(os.path.join(LAB, "logs", "run.log"), "a") as f:
        f.write(time.strftime("%H:%M:%S ") + "phys_sweep: " + msg + "\n")


def key(plat, des, p, u):
    return (plat, des, round(float(p), 4), int(u))


def load_done():
    done = {}
    if os.path.exists(OUT):
        for l in open(OUT):
            l = l.strip()
            if l:
                r = json.loads(l)
                done[key(r["platform"], r["design"], r["clock_period_ns"], r["core_utilization"])] = r
    return done


def stock_sdc(plat, des):
    """Stock constraint.sdc: from the custom design dir if it exists, else from inside the pinned image."""
    cached = os.path.join(SDCDIR, f"stock_{plat}_{des}.sdc")
    if os.path.exists(cached):
        return open(cached).read()
    own = os.path.join(LAB, "orfs", "designs", plat, des, "constraint.sdc")
    if os.path.exists(own):
        txt = open(own).read()
    else:
        env = dict(l.strip().split("=", 1) for l in open(os.path.join(LAB, "coord", "images.env")) if "=" in l)
        txt = subprocess.check_output(
            ["docker", "run", "--rm", "--platform", "linux/amd64", env["ORFS_IMAGE"], "cat",
             f"/OpenROAD-flow-scripts/flow/designs/{plat}/{des}/constraint.sdc"], text=True)
    os.makedirs(SDCDIR, exist_ok=True)
    open(cached, "w").write(txt)
    return txt


def make_sdc(plat, des, period):
    txt = stock_sdc(plat, des)
    new, n = re.subn(r"(set\s+clk_period\s+)\S+", r"\g<1>%s" % repr(float(period)), txt)
    assert n == 1, "expected exactly one 'set clk_period' in the stock SDC"
    fn = f"{des}_{int(round(period*1000))}ps.sdc"
    open(os.path.join(SDCDIR, fn), "w").write(new)
    return "/lab/orfs/sdc_gen/" + fn


def run_point(plat, des, period, util, timeout):
    var = f"sw_{int(round(period*1000))}ps_u{util}"
    sdc = make_sdc(plat, des, period)
    env = dict(os.environ, T2_TIMEOUT=str(timeout))
    t0 = now()
    rc = subprocess.call([os.path.join(LAB, "scripts", "t2_run.sh"), plat, des, var,
                          f"CORE_UTILIZATION={util}", f"SDC_FILE={sdc}"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rec = {"platform": plat, "design": des, "clock_period_ns": round(period, 4), "core_utilization": util,
           "variant": var, "rc": rc, "wall_s": round(now() - t0), "finished_epoch": int(now())}
    try:
        e = t2_extract.extract(plat, des, var)
        rec.update(e["metrics"])
        rec["stage_runtime_s"] = e["stage_runtime_s"]
        rec["status"] = "ok" if rc == 0 else "flow_error"
        rec["gds_exists"] = "gds" in e
        # crude closure flag from the flow's own number
        rec["closed"] = (e["metrics"].get("wns_setup_ns") is not None and e["metrics"]["wns_setup_ns"] >= 0)
    except Exception as ex:  # no metadata => failed/timeout
        rec["status"] = "timeout" if rc in (137, 124) or rec["wall_s"] >= timeout - 5 else "failed"
        rec["error"] = repr(ex)[:200]
    # keep disk small: drop the heavy intermediate dirs, keep reports + logs
    for d in ("objects", "results"):
        subprocess.call(["rm", "-rf", os.path.join(LAB, "orfs", "work", d, plat, des, var)])
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def next_points(plat, des, periods, utils, done, min_step):
    """Coarse first (period-major so every utilization gets the slow periods early), then bisection refinement."""
    for p in periods:
        for u in utils:
            if key(plat, des, p, u) not in done:
                yield p, u
    # refinement: per utilization, between tightest closed period and the next-tighter non-closed one
    for u in utils:
        pts = sorted((k[2], r) for k, r in done.items() if k[0] == plat and k[1] == des and k[3] == u and r.get("status") == "ok")
        closed = [p for p, r in pts if r.get("closed")]
        failed = [p for p, r in pts if not r.get("closed")]
        if not closed or not failed:
            continue
        hi = min(closed)
        lo_cands = [p for p in failed if p < hi]
        if not lo_cands:
            continue
        lo = max(lo_cands)
        if hi - lo > min_step + 1e-9:
            mid = round(round((hi + lo) / 2 / 0.005) * 0.005, 4)
            if lo < mid < hi and key(plat, des, mid, u) not in done:
                yield mid, u


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default="nangate45")
    ap.add_argument("--design", default="gcd")
    ap.add_argument("--periods", default="0.60,0.50,0.45,0.40,0.35,0.30", help="coarse clock periods (ns), comma list")
    ap.add_argument("--utils", default="30,40,50,60")
    ap.add_argument("--timeout", type=int, default=1800, help="per-point timeout (s)")
    ap.add_argument("--min-step", type=float, default=0.01)
    ap.add_argument("--max-points", type=int, default=10**6)
    ap.add_argument("--retry", action="store_true", help="re-run failed/timeout points")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    budget = json.load(open(os.path.join(LAB, "budget.json")))
    deadline = budget["deadline_sweeps_stop_epoch"]
    periods = [float(x) for x in a.periods.split(",")]
    utils = [int(x) for x in a.utils.split(",")]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    os.makedirs(os.path.join(LAB, "logs", "40_sweeps"), exist_ok=True)
    open(os.path.join(LAB, "results", "sweeps", "phys.pid"), "w").write(str(os.getpid()))
    npts = 0
    while npts < a.max_points:
        done = load_done()
        if a.retry:
            done = {k: r for k, r in done.items() if r.get("status") == "ok"}
        pt = next(next_points(a.platform, a.design, periods, utils, done, a.min_step), None)
        if pt is None:
            log("no more points (grid + refinement exhausted)"); break
        walls = [r["wall_s"] for k, r in done.items() if r.get("status") == "ok" and k[1] == a.design]
        est = max(walls) if walls else (2400 if a.design == "systolic_os" else 600)
        if os.path.exists(STOP):
            log("stop file present, exiting"); break
        if now() + est * 1.2 > deadline:
            log(f"deadline: now+{est*1.2:.0f}s > sweeps stop; exiting"); break
        p, u = pt
        log(f"point {a.platform}/{a.design} period={p} util={u} (est {est}s)")
        if a.dry_run:
            print("would run", pt); npts += 1; done[key(a.platform, a.design, p, u)] = {"status": "dry"}; break
        r = run_point(a.platform, a.design, p, u, a.timeout)
        log(f"  -> {r['status']} wns={r.get('wns_setup_ns')} area={r.get('area_um2')} wall={r['wall_s']}s")
        npts += 1
    log("phys_sweep exit")


if __name__ == "__main__":
    main()
