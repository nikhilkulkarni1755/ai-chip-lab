#!/usr/bin/env python3
"""repro_compare.py - compare the first (official) run with the clean rerun -> results/repro_report.json.
  repro_compare.py --lab DIR --run RELDIR [--out results/repro_report.json]
Verdict per check: identical | different | not_run. pass = every check identical (not_run counts as not passing).
Only fields that should be deterministic are compared; wall-clock/timestamp fields are excluded by name."""
import argparse, hashlib, json, os, re, sys, time

VOLATILE = re.compile(r"(wall|runtime|elapsed|seconds|epoch|generated|timestamp|date|_s$|^_s$)", re.I)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def strip(o, out_rel):
    if isinstance(o, dict):
        return {k: strip(v, out_rel) for k, v in o.items() if not VOLATILE.search(k)}
    if isinstance(o, list): return [strip(v, out_rel) for v in o]
    if isinstance(o, str): return o.replace(out_rel, "<out>")
    return o

def jl(p):
    try: return json.load(open(p))
    except Exception: return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", required=True); ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="results/repro_report.json")
    ap.add_argument("--t2-note", default="")
    a = ap.parse_args()
    P = lambda *x: os.path.join(a.lab, *x)
    checks = []
    def add(name, first, second, note=""):
        if first is None or second is None: v = "not_run"
        else: v = "identical" if first == second else "different"
        checks.append({"check": name, "verdict": v, "first_run": first, "rerun": second, "note": note})

    # Task 1
    for sim in ("icarus", "verilator"):
        f, r = P("results/t1_%s.csv" % sim), P(a.run, "t1/t1_%s.csv" % sim)
        add("t1 csv sha256 (%s)" % sim, sha(f) if os.path.exists(f) else None, sha(r) if os.path.exists(r) else None)
    s1, r1 = jl(P("results/t1_summary.json")), jl(P(a.run, "t1/t1_summary.json"))
    if s1 and r1:
        add("t1 pass/check booleans", strip(s1.get("checks"), a.run), strip(r1.get("checks"), a.run))
        add("t1 measured values (mismatches, cases, coverage, csv hashes, proof status)",
            strip(s1.get("values"), a.run), strip(r1.get("values"), a.run))
    else:
        add("t1 summary", None, None, "missing summary")
    # Task 3: every file under results/t3
    d1, d2 = P("results/t3"), P(a.run, "t3")
    files = sorted(os.path.relpath(os.path.join(b, f), d1) for b, _, fs in os.walk(d1) for f in fs) if os.path.isdir(d1) else []
    if files and os.path.isdir(d2):
        h1 = {f: sha(os.path.join(d1, f)) for f in files}
        h2 = {f: (sha(os.path.join(d2, f)) if os.path.exists(os.path.join(d2, f)) else None) for f in files}
        add("t3 result files byte-identical (%d files)" % len(files), h1, h2)
        extra = [os.path.relpath(os.path.join(b, f), d2) for b, _, fs in os.walk(d2) for f in fs]
        add("t3 same set of files", files, sorted(extra))
    else:
        add("t3 result files", None, None, "missing results/t3 or rerun output")
    s3, r3 = jl(P("results/t3_summary.json")), jl(P(a.run, "t3_summary.json"))
    if s3 and r3:
        add("t3 summary (checks and fitted values)", strip(s3, "results/t3"), strip(r3, a.run + "/t3"))
    else:
        add("t3 summary", None, None, "missing summary")
    # Task 2: reuse pnr's own two-run-from-clean verdict
    s2 = jl(P("results/t2_summary.json"))
    det = ((s2 or {}).get("designs", {}).get("nangate45/gcd") or {}).get("determinism")
    if det:
        checks.append({"check": "t2 nangate45/gcd two clean runs (metrics + GDS with timestamps zeroed)",
                       "verdict": "identical" if det.get("verdict") == "PASS" else "different",
                       "first_run": det.get("gds_sha256_timestamps_zeroed", [None])[0],
                       "rerun": (det.get("gds_sha256_timestamps_zeroed") or [None, None])[-1],
                       "note": a.t2_note or "reused from pnr's two-run determinism check (no third P&R run)"})
    else:
        checks.append({"check": "t2 determinism", "verdict": "not_run", "first_run": None, "rerun": None, "note": "no determinism block in t2_summary.json"})
    rep = {"generated_epoch": int(time.time()), "rerun_dir": a.run,
           "pass": all(c["verdict"] == "identical" for c in checks), "checks": checks,
           "counts": {v: sum(1 for c in checks if c["verdict"] == v) for v in ("identical", "different", "not_run")}}
    json.dump(rep, open(P(a.out), "w"), indent=2, sort_keys=True); open(P(a.out), "a").write("\n")
    for c in checks: print("%-10s %s" % (c["verdict"], c["check"]))
    print("repro pass:", rep["pass"])
    return 0 if rep["pass"] else 1

if __name__ == "__main__": sys.exit(main())
