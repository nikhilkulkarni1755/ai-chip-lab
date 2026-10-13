#!/usr/bin/env python3
"""P2.3 stage 62_pdk_compare: systolic_os (4x4 INT8, utilization 30 %) on sky130hd, coarse clock search, compared with
nangate45 at its own frontier (results/sweeps/phys.jsonl, 1.25 ns u30). Criteria and comparison definition are registered in
results/p2_62_pdk_compare.json BEFORE the first run.

  python3 scripts/p2_pdk_compare.py run  [--go] [--periods 8.0,5.5,4.0] [--deadline HH:MM]   # one lock hold per point
  python3 scripts/p2_pdk_compare.py summary
Per point: scripts/with_lock.sh pnr scripts/t2_run.sh sky130hd systolic_os pdk_<ps>ps ... with T2_TIMEOUT=2100 (35 min hard,
container start to kill); no retry of a timed-out point. Rows: results/pdk_compare/sky130hd_points.jsonl (resumable).
"""
import argparse, json, os, subprocess, sys, time

LAB = os.path.expanduser("~/ai-chip-lab")
sys.path.insert(0, os.path.join(LAB, "scripts")); sys.path.insert(0, os.path.join(LAB, "sweeps"))
import t2_extract  # noqa: E402
import re  # noqa: E402

CFG_DIR = os.path.join(LAB, "orfs", "pdk_compare", "sky130hd", "systolic_os")   # outside orfs/designs (a repro input)


def make_sdc(period):
    txt = open(os.path.join(CFG_DIR, "constraint.sdc")).read()
    new, n = re.subn(r"(set\s+clk_period\s+)\S+", r"\g<1>%s" % repr(float(period)), txt); assert n == 1
    fn = f"pdk_sky130hd_systolic_os_{int(round(period*1000))}ps.sdc"
    open(os.path.join(LAB, "orfs", "sdc_gen", fn), "w").write(new)
    return "/lab/orfs/sdc_gen/" + fn


def lock_accounting(t0, tag):
    sys.path.insert(0, os.path.join(LAB, "sweeps")); import phys_sweep
    return phys_sweep.lock_accounting(t0, time.time(), tag)

OUT = os.path.join(LAB, "results", "pdk_compare", "sky130hd_points.jsonl")
TIMEOUT_S = 2100
PL, DES, UTIL = "sky130hd", "systolic_os", 30
NG_REF = ("nangate45", "systolic_os", 1.25, 30)   # nangate45 frontier point from sweep B


def rows():
    return [json.loads(l) for l in open(OUT) if l.strip()] if os.path.exists(OUT) else []


def run(a):
    if not a.go:
        sys.exit("refusing to start without --go (start only after infra reported the repro verdict)")
    h, m = map(int, a.deadline.split(":"))
    deadline = time.mktime(time.localtime()[:3] + (h, m, 0, 0, 0, -1))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for p in [float(x) for x in a.periods.split(",")]:
        if any(abs(r["clock_period_ns"] - p) < 1e-6 for r in rows()):
            continue
        if time.time() + TIMEOUT_S > deadline:
            print(f"{p} ns: cannot finish before {a.deadline} in the worst case; not started"); continue
        var = f"pdk_{int(round(p*1000))}ps"
        sdc = make_sdc(p)
        t0 = time.time()
        env = dict(os.environ, T2_TIMEOUT=str(TIMEOUT_S))
        rc = subprocess.call([os.path.join(LAB, "scripts", "with_lock.sh"), "pnr", os.path.join(LAB, "scripts", "t2_run.sh"), PL, DES, var,
                              "--config", "/lab/orfs/pdk_compare/sky130hd/systolic_os/config.mk", f"CORE_UTILIZATION={UTIL}", f"SDC_FILE={sdc}"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        rec = {"platform": PL, "design": DES, "clock_period_ns": p, "core_utilization": UTIL, "variant": var, "rc": rc,
               "wall_s": round(time.time() - t0), "finished_epoch": int(time.time())}
        w, h_ = lock_accounting(t0, var); rec["lock_wait_s"], rec["lock_hold_s"] = w, h_
        try:
            e = t2_extract.extract(PL, DES, var)
            rec.update(e["metrics"]); rec["stage_runtime_s"] = e["stage_runtime_s"]; rec["flow_elapsed_s"] = e["total_elapsed_s_flow"]
            rec["status"] = "ok" if rc == 0 else "flow_error"
            rec["closed"] = e["metrics"].get("wns_setup_ns") is not None and e["metrics"]["wns_setup_ns"] >= 0
        except Exception as ex:
            run_s = h_ if h_ is not None else rec["wall_s"]
            rec["status"] = "timeout" if rc in (137, 124) or run_s >= TIMEOUT_S - 30 else "failed"
            rec["error"] = repr(ex)[:200]
            lg = os.path.join(LAB, "logs/part2/20_pnr_ref", f"{PL}_{DES}_{var}.log")
            if os.path.exists(lg):   # stage reached = last ORFS step banner in the log
                L = open(lg, errors="replace").read().splitlines()
                rec["log_tail"] = [x.strip()[:160] for x in L[-8:]]
                rec["errors"] = [x.strip()[:200] for x in L if "[ERROR" in x or x.startswith("Error:")][:3]
                rec["stage_reached"] = next((x.strip()[:80] for x in reversed(L) if x.startswith("Running ") or "Log:" in x or x.startswith("[INFO FLW")), None)
        with open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(p, rec["status"], rec.get("wns_setup_ns"), rec["wall_s"], flush=True)
        if rec["status"] == "ok" and rec["closed"]:
            pass


def summary(a):
    R = sorted(rows(), key=lambda r: r["clock_period_ns"])
    ng = next(r for r in (json.loads(l) for l in open(os.path.join(LAB, "results/sweeps/phys.jsonl")))
              if (r["platform"], r["design"], r["clock_period_ns"], r["core_utilization"]) == NG_REF)
    ok = [r for r in R if r.get("status") == "ok"]
    closing = [r for r in ok if r["closed"]]; failing = [r for r in ok if not r["closed"]]
    best = min(closing, key=lambda r: r["clock_period_ns"]) if closing else None
    below = [r for r in failing if best and r["clock_period_ns"] < best["clock_period_ns"]]
    if not best:
        label = "no closing point in the tested range: no frontier claim"
    elif below:
        lo = max(r["clock_period_ns"] for r in below)
        label = f"coarse frontier bracket: fails at {lo} ns, closes at {best['clock_period_ns']} ns (true frontier in between; resolution {round(best['clock_period_ns']-lo,3)} ns)"
    else:
        label = f"closing point only (no failing point swept below {best['clock_period_ns']} ns): {best['clock_period_ns']} ns is an UPPER BOUND on the sky130hd closure period, not a frontier"
    cmp_ = None
    if best:
        cmp_ = {}
        for k in ("area_um2", "stdcell_count", "cell_count", "power_total_w", "power_leakage_w", "wns_setup_ns"):
            cmp_[k] = {"nangate45": ng.get(k), "sky130hd": best.get(k), "ratio_sky_over_nangate": (best[k] / ng[k]) if ng.get(k) and best.get(k) is not None else None}
        cmp_["clock_period_ns"] = {"nangate45": ng["clock_period_ns"], "sky130hd": best["clock_period_ns"], "ratio_sky_over_nangate": best["clock_period_ns"] / ng["clock_period_ns"]}
        cmp_["energy_per_cycle_pj"] = {"nangate45": ng["power_total_w"] * ng["clock_period_ns"] * 1e3, "sky130hd": best["power_total_w"] * best["clock_period_ns"] * 1e3}
    S = {"label": label, "points": R, "nangate45_reference_point": {k: ng.get(k) for k in ("clock_period_ns", "core_utilization", "wns_setup_ns", "area_um2", "power_total_w", "stdcell_count", "variant")},
         "comparison_at_each_pdks_fastest_closing_period": cmp_}
    json.dump(S, open(os.path.join(LAB, "results", "pdk_compare", "pdk_compare.json"), "w"), indent=1)
    print(json.dumps(S, indent=1)[:3000])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["run", "summary"]); ap.add_argument("--go", action="store_true")
    ap.add_argument("--periods", default="8.0,5.5,4.0"); ap.add_argument("--deadline", default="20:45")
    a = ap.parse_args()
    run(a) if a.cmd == "run" else summary(a)
