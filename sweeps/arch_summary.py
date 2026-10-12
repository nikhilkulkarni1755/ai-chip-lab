#!/usr/bin/env python3
"""Summarise sweep A -> results/sweeps/arch_summary.json (+ text on stdout)."""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(LAB, "model"))
import arch_sweep as S  # noqa: E402

rows = [json.loads(l) for l in open(os.path.join(LAB, "results/sweeps/arch.jsonl"))]
planned = {S.key_of(*p[1:]): p for p in S.grid()}
by_key = {r["key"]: r for r in rows}
st = Counter(r["status"] for r in rows)
ok = [r for r in rows if r["status"] == "ok"]
cov = defaultdict(lambda: dict(planned=0, ok=0, error=0, skipped_after_timeout=0, timeout=0, not_run=0))
for k, p in planned.items():
    c = cov[p[1]]
    c["planned"] += 1
    r = by_key.get(k)
    c[r["status"] if r else "not_run"] += 1
best = {}
tab = defaultdict(dict)
for r in ok:
    if r["sram"] == "default":
        tab[(r["topo"], f"{r['rows']}x{r['cols']}")][r["dataflow"]] = r["total_cycles"]
for (t, a), v in sorted(tab.items()):
    best[f"{t}|{a}"] = dict(best=min(v, key=v.get), cycles=v, complete=len(v) == 3)
err = [{k: r.get(k) for k in ("key", "status", "wall_s", "error", "returncode")} for r in rows if r["status"] in ("error", "timeout")]
nr = [k for k in planned if k not in by_key]
out = dict(
    sweep="A (SCALE-Sim 3.0.0 architecture sweep)", rows_total=len(rows), status_counts=dict(st),
    planned_points=len(planned), not_run_points=len(nr), coverage_per_topology=cov,
    not_run_sample=nr[:12], best_dataflow_default_sram=best, errored_points=err,
    notes=["SCALE-Sim ran in CALC interface-bandwidth mode (bundled scale.cfg): stall_cycles = 0 is structural there "
           "(stalls are not modelled in that mode) and dram_bw_* is SCALE-Sim's estimated DRAM demand, not a measured stall effect.",
           "SRAM levels are per buffer: small 16 kB, default 64 kB, large 1024 kB.",
           "Workloads are NOT interchangeable: alexnet_part = AlexNet Conv1 only (1 layer); gemm_test = one 256x128x256 GEMM, "
           "used as the separate small-array (8x8/16x16) workload; vit_s, ncf, alexnet as named.",
           "Points were ordered cheapest-estimated-first; points never reached before the deadline are in not_run_points.",
           "alexnet_part|ws|8x8|default: process ended without a result after the logged wall time, empty error text; "
           "the cause is unverified (not shown to be a timeout; likely out-of-memory kill but not confirmed)."])
json.dump(out, open(os.path.join(LAB, "results/sweeps/arch_summary.json"), "w"), indent=1, sort_keys=True)
print(f"rows {len(rows)} status {dict(st)} planned {len(planned)} not_run {len(nr)}")
for t, c in sorted(cov.items()):
    print(f"{t:13s} planned {c['planned']:3d} ok {c['ok']:3d} err {c['error']} skipped {c['skipped_after_timeout']} timeout {c['timeout']} not_run {c['not_run']}")
print("best dataflow (default SRAM):")
for k, v in best.items():
    print(f"  {k:22s} {v['best']} {'' if v['complete'] else '(partial: <3 dataflows)'}")
for e in err:
    print("errored:", json.dumps(e))
print(out["notes"][0])
