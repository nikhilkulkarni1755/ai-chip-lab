#!/usr/bin/env python3
"""Sweep B gate deliverables (run once the phys_sweep driver has stopped: it refuses while the driver is alive).

 1. back-fill lock_wait_s / lock_hold_s for rows written before the driver recorded them (from logs/part2/lock.log)
 2. regenerate frontier json + per-design plots (sweeps/phys_plots.py)
 3. accounting of EVERY planned Part 2 point: done / timeout / failed (+diagnosis) / cut (+reason) / not_reached (+reason)
    -> results/sweeps/phys_plan_status.json (final=true)
 4. refresh the sweep_B block of results/t2_summary.json (same code as scripts/t2_summary.py)
 5. evidence results/evidence/41_sweepB_{frontier,plan_accounting,lock_accounting}.txt
 6. marker results/.stages/41_sweeps_finish_B.done
Usage: source env.sh; python3 sweeps/phys_gate.py [--dry-run]
"""
import json, os, re, subprocess, sys, time

LAB = os.path.expanduser("~/ai-chip-lab")
sys.path.insert(0, os.path.join(LAB, "sweeps")); sys.path.insert(0, os.path.join(LAB, "scripts"))
import phys_sweep as PS  # noqa: E402

OUTJ = PS.OUT
EV = os.path.join(LAB, "results", "evidence")
T = lambda s: time.mktime(time.strptime(s, "%Y-%m-%d %H:%M:%S"))


def lock_intervals():
    """[(lock_epoch, free_epoch, waited_s, held_s, cmd)] for pnr low jobs running t2_run.sh."""
    L = open(os.path.join(LAB, "logs", "part2", "lock.log")).read().splitlines()
    out = []
    for i, l in enumerate(L):
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) LOCK pnr low waited=(\d+)s (.*)", l)
        if not m or "t2_run.sh" not in m.group(3):
            continue
        for l2 in L[i + 1:]:
            m2 = re.match(r"(\S+ \S+) FREE pnr rc=\S+ ran=(\d+)s", l2)
            if m2:
                out.append((T(m.group(1)), T(m2.group(1)), int(m.group(2)), int(m2.group(2)), m.group(3))); break
    return out


def backfill(rows):
    iv = lock_intervals(); n = 0
    for r in rows:
        if r.get("lock_hold_s") is not None:
            continue
        tag = f"t2_run.sh {r['platform']} {r['design']} {r['variant']}"
        c = [x for x in iv if tag in x[4] and x[1] <= r["finished_epoch"] + 10]
        if c:
            x = max(c, key=lambda y: y[1]); r["lock_wait_s"], r["lock_hold_s"] = x[2], x[3]
            r["lock_accounting"] = "backfilled from lock.log"; n += 1
        else:
            r.setdefault("lock_hold_s", None); r["lock_accounting"] = "unavailable (run before per-point lock logging)"
    return n


def fail_diag(r):
    for d in ("logs/part2/20_pnr_ref", "logs/20_pnr_ref"):
        lg = os.path.join(LAB, d, f"{r['platform']}_{r['design']}_{r['variant']}.log")
        if os.path.exists(lg):
            L = open(lg, errors="replace").read().splitlines()
            errs = [x.strip() for x in L if re.search(r"\[ERROR|^Error:|Killed", x)]
            return {"log": d + "/" + os.path.basename(lg), "errors": errs[:3], "last_lines": [x.strip()[:160] for x in L[-5:]]}
    return None


def accounting(rows):
    done = {PS.key(r["platform"], r["design"], r["clock_period_ns"], r["core_utilization"]): r for r in rows}
    pts = []
    for pl, de, p, u in PS.part2_plan(done):
        r = done.get(PS.key(pl, de, p, u))
        e = {"design": de, "clock_period_ns": p, "core_utilization": u}
        if r:
            st = r.get("status")
            e.update(state="done" if st == "ok" else st, wns_setup_ns=r.get("wns_setup_ns"), closed=r.get("closed"),
                     lock_hold_s=r.get("lock_hold_s"), flow_elapsed_s=r.get("flow_elapsed_s"))
            if st != "ok":
                e["diagnosis"] = fail_diag(r); e["error"] = r.get("error")
                if st == "timeout":
                    e["reason"] = "hit the per-point timeout (systolic_os: hard 15 min, counted from container start)"
        elif de == "systolic_os" and u == 30:
            e.update(state="cut", reason=PS.CUT_30)
        else:
            e.update(state="not_reached", reason="sweep stopped at the Phase 1 gate (deadline_sweeps_stop_epoch in budget_part2.json): "
                     "the heavy-job queue was dominated by stage work (low-priority points wait for every stage job plus a 45 s grace)")
        pts.append(e)
    counts = {}
    for e in pts:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    return {"updated_epoch": int(time.time()), "final": True, "counts": counts, "points": pts}


def write_evidence(F, A, rows):
    os.makedirs(EV, exist_ok=True)
    L = ["Sweep B timing-closure frontier (setup WNS >= 0, the flow's own report), from results/sweeps/phys.jsonl",
         "closed = WNS >= 0 at that (period, utilization); frontier = smallest swept period that closed; 'next failing' = the slower-than-... period just below it that failed",
         ""]
    for des, per in F["frontier"].items():
        L.append(f"{des}: util% | fastest closing ns | WNS there | next failing below ns | its WNS | bracketed | non-monotonic | points")
        for u, e in sorted(per.items(), key=lambda x: int(x[0])):
            L.append(f"  {u:>3} | {e.get('fastest_closing_period_ns')} | {e.get('wns_at_frontier_ns', float('nan')):.5f} | {e.get('next_failing_period_ns')} | "
                     f"{e.get('wns_at_next_failing_ns')} | {e.get('bracketed')} | {e.get('non_monotonic')} | {e['points']}")
        L.append("")
    L.append("failed/timeout points: " + json.dumps(F["failed_points"], indent=1))
    open(os.path.join(EV, "41_sweepB_frontier.txt"), "w").write("\n".join(L) + "\n")
    L = ["Part 2 sweep-B plan accounting (every planned point): " + json.dumps(A["counts"]), ""]
    for e in A["points"]:
        L.append(f"{e['design']:12} T={e['clock_period_ns']:<6} util={e['core_utilization']:<3} {e['state']:12} "
                 + (f"WNS={e['wns_setup_ns']:.5f} hold={e.get('lock_hold_s')}s" if e.get("wns_setup_ns") is not None else (e.get("reason") or json.dumps(e.get("diagnosis")))))
    open(os.path.join(EV, "41_sweepB_plan_accounting.txt"), "w").write("\n".join(L) + "\n")
    L = ["per point: wall_s (queue wait + lock hold, as seen by the driver) vs lock_wait_s vs lock_hold_s (machine time) vs flow_elapsed_s (sum of flow stage times)", ""]
    for r in rows:
        L.append(f"{r['design']:12} T={r['clock_period_ns']:<6} u={r['core_utilization']:<3} {r['status']:8} wall={r['wall_s']:<6} wait={r.get('lock_wait_s')} hold={r.get('lock_hold_s')} flow={r.get('flow_elapsed_s')}")
    open(os.path.join(EV, "41_sweepB_lock_accounting.txt"), "w").write("\n".join(L) + "\n")


def main():
    dry = "--dry-run" in sys.argv
    if subprocess.call(["pgrep", "-f", "sweeps/phys_sweep.py"], stdout=subprocess.DEVNULL) == 0 and not dry:
        sys.exit("phys_sweep driver is still running: touch results/sweeps/phys.stop and wait for it to exit")
    rows = [json.loads(l) for l in open(OUTJ) if l.strip()]
    n = backfill(rows); print("backfilled lock accounting:", n)
    if not dry:
        open(OUTJ + ".tmp", "w").write("".join(json.dumps(r) + "\n" for r in rows)); os.replace(OUTJ + ".tmp", OUTJ)
        py = os.path.join(LAB, ".venv-pnr", "bin", "python")
        subprocess.check_call([py if os.path.exists(py) else sys.executable, os.path.join(LAB, "sweeps", "phys_plots.py")], cwd=LAB)
    A = accounting(rows); print("plan:", A["counts"])
    if dry:
        return
    json.dump(A, open(os.path.join(LAB, "results", "sweeps", "phys_plan_status.json"), "w"), indent=1)
    F = json.load(open(os.path.join(LAB, "results", "sweeps", "phys_frontier.json")))
    write_evidence(F, A, rows)
    import t2_summary
    sp = os.path.join(LAB, "results", "t2_summary.json"); S = json.load(open(sp))
    S["sweep_B"] = t2_summary.sweep_block(); json.dump(S, open(sp, "w"), indent=2)
    open(os.path.join(LAB, "results", ".stages", "41_sweeps_finish_B.done"), "w").write(
        f"Sweep B finished {time.strftime('%F %T')}; {len(rows)} rows; Part 2 plan: {json.dumps(A['counts'])}; see results/evidence/41_sweepB_*.txt\n")


if __name__ == "__main__":
    main()
