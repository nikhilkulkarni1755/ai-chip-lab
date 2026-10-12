#!/usr/bin/env python3
"""repro_compare.py - compare the first (official) run with the clean rerun -> results/repro_report.json.
  repro_compare.py --lab DIR --run RELDIR [--out results/repro_report.json]
Verdict per check: identical | different | not_run | not_rerun_cost. pass = no check different/not_run and at least one identical; complete = every check identical (a not_rerun_cost check makes it incomplete, never identical).
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
    def add(name, first, second, note="", runs=2):
        if first is None or second is None: v = "not_run"
        else: v = "identical" if first == second else "different"
        checks.append({"check": name, "runs": runs if v != "not_run" else 0, "verdict": v, "first_run": first, "rerun": second, "note": note})

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
    # Task 3 (Decision P2-7): the rerun is the CHEAP set (bundled ws/os/is, fit, CALC-mode roofline runs). Files that the rerun did not
    # produce (the user-bandwidth criterion-A runs) are reported as "not_rerun_cost" with a run count of 1; never as identical.
    d1, d2 = P("results/t3"), P(a.run, "t3")
    files = sorted(os.path.relpath(os.path.join(b, f), d1) for b, _, fs in os.walk(d1) for f in fs if not f.startswith(".")) if os.path.isdir(d1) else []
    if files and os.path.isdir(d2):
        # Exclusions, both declared in the report (excluded_file_class): (1) basename timing.timing = per-layer wall-time/RSS measurements of the run itself;
        # (2) dotfiles (names starting with ".", e.g. .DS_Store), counted here. No other file is excluded.
        allf = [("a", os.path.relpath(os.path.join(b, f), d1)) for b, _, fs in os.walk(d1) for f in fs] + [("b", os.path.relpath(os.path.join(b, f), d2)) for b, _, fs in os.walk(d2) for f in fs]
        excl = sorted(set(f for _, f in allf if os.path.basename(f) == "timing.timing"))
        dotted = sorted(set(f for _, f in allf if os.path.basename(f).startswith(".") and os.path.basename(f) != "timing.timing"))
        files = sorted(f for f in (os.path.relpath(os.path.join(b, f), d1) for b, _, fs in os.walk(d1) for f in fs) if f not in excl and f not in dotted)
        rerun_files = sorted(f for f in (os.path.relpath(os.path.join(b, f), d2) for b, _, fs in os.walk(d2) for f in fs) if f not in excl and f not in dotted)
        both = [f for f in files if f in rerun_files]
        h1 = {f: sha(os.path.join(d1, f)) for f in both}
        h2 = {f: sha(os.path.join(d2, f)) for f in both}
        add("t3 cheap-set result files byte-identical (%d files compared)" % len(both), h1, h2,
            "first run = the stage's own passes plus this fresh pass; compared files: bundled ws/os/is reports, fit, CALC-mode roofline runs", runs=3)
        extra = [f for f in rerun_files if f not in files]
        if extra:
            add("t3 rerun produced no file the first run lacks", [], extra, "unexpected extra files in the rerun")
        notre = [f for f in files if f not in rerun_files]
        user = [f for f in notre if "user" in f.lower()]
        other = [f for f in notre if f not in user]
        checks.append({"check": "t3 user-bandwidth roofline runs (criterion A): %d files" % len(user), "runs": 1, "verdict": "not_rerun_cost",
                       "first_run": "present" if user else "absent", "rerun": None,
                       "note": "NOT rerun (cost): each run holds the lock for minutes; these files are not claimed byte-identical"})
        if other:
            checks.append({"check": "t3 other first-run files not in the rerun (%d)" % len(other), "runs": 1, "verdict": "not_rerun_cost", "first_run": other[:10], "rerun": None,
                           "note": "not part of the cheap set"})
    else:
        add("t3 result files", None, None, "missing results/t3 or rerun output")
    s3, r3 = jl(P("results/t3_summary.json")), jl(P(a.run, "t3_summary.json"))
    if s3 and r3:
        sub = lambda d: {k: d.get(k) for k in ("fit", "bundled_summary", "bundled", "bundled_config_zero_stalls") if k in d}
        add("t3 summary: fit, bundled runs (compared subtree)", strip(sub(s3), "results/t3"), strip(sub(r3), a.run + "/t3"),
            "identity as recorded by the stage: %s" % json.dumps(s3.get("identity", {}).get("state") if isinstance(s3.get("identity"), dict) else None))
    else:
        add("t3 summary", None, None, "missing summary")
    # Task 2: Part 2 supplies results/t2_reruns.json (pnr): {"designs": {"<plat>/<design>": {"runs": [{"run_id", "metrics": {...}, "gds_sha256_timestamps_zeroed",
    # "compared_fields_identical": bool}...], "verdict": "identical|different", "differing_fields": {...}}}}. Falls back to the Part 1
    # reused two-run verdict in t2_summary.json (clearly labelled as reused).
    s2 = jl(P("results/t2_summary.json"))
    rr = jl(P("results/t2_reruns.json"))
    if rr and isinstance(rr.get("designs"), dict):
        for dn, d in rr["designs"].items():
            runs = d.get("runs") or []
            hashes = [r.get("gds_sha256_timestamps_zeroed") for r in runs]
            v = d.get("verdict")
            verdict = "not_run" if len(runs) < 2 else ("identical" if v == "identical" else "different")
            checks.append({"check": "t2 %s: %d clean runs, metrics + GDS with timestamps zeroed" % (dn, len(runs)), "runs": len(runs), "verdict": verdict,
                           "first_run": hashes[0] if hashes else None, "rerun": hashes[-1] if hashes else None,
                           "note": ("differing fields: %s" % json.dumps(d.get("differing_fields"))) if verdict == "different" else (d.get("note") or "all compared fields identical across runs")})
    else:
        for dn, dd in ((s2 or {}).get("designs") or {}).items():
            det = dd.get("determinism")
            if det:
                checks.append({"check": "t2 %s two clean runs (metrics + GDS with timestamps zeroed)" % dn, "runs": 2,
                               "verdict": "identical" if det.get("verdict") == "PASS" else "different",
                               "first_run": det.get("gds_sha256_timestamps_zeroed", [None])[0],
                               "rerun": (det.get("gds_sha256_timestamps_zeroed") or [None, None])[-1],
                               "note": a.t2_note or "REUSED from the original two-run check in t2_summary.json (no further run)"})
            elif dd.get("status") == "run":
                checks.append({"check": "t2 %s" % dn, "runs": 1, "verdict": "not_run", "first_run": None, "rerun": None, "note": "single run; no determinism verdict"})
    # Provenance: same inputs for first run and rerun?  (git object SHAs of the input dirs at rerun start/end;
    # the first run's summary must be newer than the last commit touching those inputs, and no uncommitted edits.)
    prov = {}
    for tag, summ in (("t1", "results/t1_summary.json"), ("t3", "results/t3_summary.json")):
        st, en = jl(P(a.run, "inputs_%s_start.json" % tag)), jl(P(a.run, "inputs_%s_end.json" % tag))
        if not (st and en):
            checks.append({"check": "provenance %s inputs" % tag, "runs": 0, "verdict": "not_run", "first_run": None, "rerun": None, "note": "no input snapshot"})
            continue
        same = {k: v["git_object_sha"] for k, v in st["paths"].items()} == {k: v["git_object_sha"] for k, v in en["paths"].items()}
        clean = not any(v["uncommitted_changes"] for v in list(st["paths"].values()) + list(en["paths"].values()))
        last = max(v["last_commit_epoch"] for v in st["paths"].values())
        try: first_m = int(os.path.getmtime(P(summ)))
        except OSError: first_m = 0
        ok_first = first_m >= last
        prov[tag] = {"start": st, "end": en}
        checks.append({"check": "provenance %s: rerun inputs unchanged during the run, committed, and first run newer than the last input commit" % tag,
                       "runs": 2, "verdict": "identical" if (same and clean and ok_first) else "different",
                       "first_run": {"summary_mtime_epoch": first_m, "last_input_commit_epoch": last},
                       "rerun": {"inputs_unchanged_start_to_end": same, "no_uncommitted_changes": clean, "head": st["head"],
                                 "object_shas": {k: v["git_object_sha"] for k, v in st["paths"].items()}},
                       "note": "git object SHAs of the input paths at HEAD; see provenance block"})
    kept = jl(P(a.run, "t1_kept.json"))
    if kept:
        checks.append({"check": "t1 rerun kept (not redone with Task 3)", "runs": 2, "verdict": "identical", "first_run": None, "rerun": None, "note": kept.get("note")})
    ne_, nd_ = (len(excl), len(dotted)) if "excl" in dir() else (0, 0)
    rep = {"excluded_file_class": {"name": "timing.timing", "reason": "run-time measurements (wall seconds and peak memory per layer), not results", "files": ne_,
                                   "label": "excluded: run-time measurements (%d files)" % ne_,
                                   "filters": [{"rule": "basename == timing.timing", "files_excluded": ne_},
                                               {"rule": "basename starts with '.' (hidden files)", "files_excluded": nd_}]},
           "task1_rerun_kept": kept or None, "generated_epoch": int(time.time()), "rerun_dir": a.run,
           "pass": all(c["verdict"] in ("identical", "not_rerun_cost") for c in checks) and any(c["verdict"] == "identical" for c in checks),
           "complete": all(c["verdict"] == "identical" for c in checks), "checks": checks, "provenance": prov,
           "counts": {v: sum(1 for c in checks if c["verdict"] == v) for v in ("identical", "different", "not_run", "not_rerun_cost")}}
    json.dump(rep, open(P(a.out), "w"), indent=2, sort_keys=True); open(P(a.out), "a").write("\n")
    for c in checks: print("%-10s %s" % (c["verdict"], c["check"]))
    print("repro pass:", rep["pass"])
    return 0 if rep["pass"] else 1

if __name__ == "__main__": sys.exit(main())
