#!/usr/bin/env python3
"""`make all`: run every stage in order, fail-soft, and always build the demo.

  make all                 real run of every stage (default: nothing is skipped)
  RESUME=1 make all        skip a stage that already succeeded and whose git-tracked inputs are unchanged
                           since then (table: scripts/stage_inputs.json); every skip is logged with its reason
  RESUME=markers make all  test mode: skip every stage that has succeeded before, WITHOUT the input check (logged)
  FORCE=1 make all         run everything even with RESUME=1
  DRY_RUN=1 make all       stages with a dry mode print their commands; the others are skipped (logged)
  MAKE_ALL_FAIL=<stage>    TEST HOOK (scripts/make_all_failsoft_test.sh): do not run that stage's recipe, set its
                           stage marker to .failed ("forced by the fail-soft test") and count it as failed
  ALL_STAGES="a b c"       run only these stages (same order rules)
  MAKE_ALL_EXCLUDE="a b"   TEST HOOK: do not run these stages; logged as "excluded" with MAKE_ALL_EXCLUDE_REASON

Rules: a failing stage (non-zero recipe, including an honest scientific FAIL) never stops later stages; `demo` is
always run last, even in RESUME mode and even after failures; exit status is 1 if any stage failed and the failed
stages are listed. Outcome of the last invocation: results/make_all_last.json (per stage: action ran|skipped|
forced_fail|dry_skipped, reason, exit code, wall time, lock wait).

"Unchanged since it last succeeded" (RESUME): (1) if this script recorded the stage's last success
(results/.stages/make/<stage>.json), the sha256 over the current contents of all its input files must equal the
recorded one; (2) otherwise the stage must have a .done marker (and no .failed/.running one) that is newer than the
newest modification time of all its input files. Anything else -> the stage runs.
Works from whatever directory holds the Makefile (the repo root), so it can be tested on a scratch copy.
"""
import hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = os.path.join(ROOT, "results", ".stages")
REC = os.path.join(ST, "make")
CFG = json.load(open(os.path.join(ROOT, "scripts", "stage_inputs.json")))
HOME = os.path.expanduser("~")
ts = lambda t: time.strftime("%F %T", time.localtime(t))


def input_files(stage):
    specs = CFG["stages"][stage].get("inputs", [])
    if not specs: return []
    out = subprocess.run(["git", "ls-files", "-z", "--"] + specs, cwd=ROOT, capture_output=True, text=True).stdout
    return sorted(f for f in out.split("\0") if f and os.path.isfile(os.path.join(ROOT, f)))


def input_hash(files):
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode() + b"\0" + hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).digest())
    return h.hexdigest()


def skip_reason(stage, markers_only=False):
    """(skip?, reason) for RESUME mode. markers_only (RESUME=markers, used by the fail-soft self-test): a stage
    that has succeeded before is skipped WITHOUT checking whether its inputs changed since; the reason says so."""
    c = CFG["stages"][stage]
    if c.get("always"): return False, "always runs"
    files = input_files(stage)
    if markers_only:
        for m in c.get("markers", []):
            for ext in ("failed", "running", "blocked"):
                if os.path.exists(os.path.join(ST, m + "." + ext)):
                    return False, "stage marker %s.%s present" % (m, ext)
        rp = os.path.join(REC, stage + ".json"); ms = c.get("markers", [])
        have_rec = os.path.exists(rp); have_done = bool(ms) and all(os.path.exists(os.path.join(ST, m + ".done")) for m in ms)
        if not (have_rec or have_done): return False, "no .done marker and no record of a successful run"
        full_skip, full_why = skip_reason(stage)
        return True, "marker-only test mode: succeeded before (%s); input changes since then are NOT checked in this mode — the input-aware rule would say: %s" % (
            (ms[0] + ".done") if have_done else "recorded successful make run", ("skip, " if full_skip else "RUN, ") + full_why)
    for m in c.get("markers", []):
        for ext in ("failed", "running", "blocked"):
            if os.path.exists(os.path.join(ST, m + "." + ext)):
                return False, "stage marker %s.%s present" % (m, ext)
    rp = os.path.join(REC, stage + ".json")
    if os.path.exists(rp):
        r = json.load(open(rp))
        if r.get("inputs_sha256") == input_hash(files):
            return True, "inputs (%d git-tracked files) byte-identical to the last successful `make %s` at %s" % (len(files), stage, ts(r["end_epoch"]))
        return False, "inputs changed since the last successful `make %s` at %s" % (stage, ts(r["end_epoch"]))
    ms = c.get("markers", [])
    if not ms: return False, "no record of a successful run"
    dones = [os.path.join(ST, m + ".done") for m in ms]
    if not all(os.path.exists(d) for d in dones): return False, "no .done marker (%s)" % ", ".join(ms)
    t_done = min(os.path.getmtime(d) for d in dones)
    newer = [(os.path.getmtime(os.path.join(ROOT, f)), f) for f in files if os.path.getmtime(os.path.join(ROOT, f)) > t_done]
    if newer:
        t, f = max(newer)
        return False, "%d input file(s) modified after %s.done (%s), newest: %s at %s" % (len(newer), ms[0], ts(t_done), f, ts(t))
    return True, "inputs (%d git-tracked files) unchanged since %s.done at %s" % (len(files), ms[0], ts(t_done))


def lock_wait(tag):
    w = 0
    try:
        for l in open(os.path.join(ROOT, "logs", "part2", "lock.log")):
            if "tag=" + tag + " " in l:
                m = re.search(r"waited=(\d+)s", l); w += int(m.group(1)) if m else 0
    except OSError:
        pass
    return w


def main():
    env = os.environ
    resume = env.get("RESUME", "0") in ("1", "markers") and env.get("FORCE", "0") != "1"
    markers_only = env.get("RESUME") == "markers"
    dry = env.get("DRY_RUN", "0") == "1"
    # `make -n all`: make still runs this script (the recipe mentions $(MAKE)) and the sub-makes only print.
    # Nothing was executed then, so nothing may be recorded.
    printonly = bool(re.match(r"^[A-Za-z]*n", env.get("MAKEFLAGS", "").split(" ")[0] if env.get("MAKEFLAGS") else ""))
    forced = env.get("MAKE_ALL_FAIL", "")
    order = env.get("ALL_STAGES", "").split() or CFG["order"]
    make = env.get("MAKE", "make")
    mode = ("resume (marker-only test mode)" if markers_only else "resume") if resume else ("dry-run" if dry else "full")
    if forced: mode += " + forced failure of '%s' (test hook)" % forced
    print("make all: mode = %s; stages: %s" % (mode, " ".join(order)), flush=True)
    os.makedirs(REC, exist_ok=True)
    out, failed = [], []
    for s in order:
        c = CFG["stages"][s]
        e = {"stage": s, "start_epoch": int(time.time())}
        if forced == s and not printonly:
            for m in c.get("markers", []):
                d = os.path.join(ST, m + ".done")
                if os.path.exists(d): os.replace(d, os.path.join(ST, m + ".done.failsoft_saved"))
                open(os.path.join(ST, m + ".failed"), "w").write("forced by the fail-soft test of `make all` (MAKE_ALL_FAIL=%s); the recipe was not run\n" % s)
            e.update(action="forced_fail", reason="MAKE_ALL_FAIL test hook: recipe not run, marker set to .failed", exit_code=1, runtime_s=0)
            failed.append(s)
        elif s in env.get("MAKE_ALL_EXCLUDE", "").split():
            e.update(action="excluded", reason="MAKE_ALL_EXCLUDE (test hook): " + env.get("MAKE_ALL_EXCLUDE_REASON", "excluded by the caller"), exit_code=None, runtime_s=0)
        elif dry and not c.get("dry"):
            e.update(action="dry_skipped", reason="DRY_RUN=1 and the recipe has no dry mode", exit_code=None, runtime_s=0)
        else:
            skip, why = skip_reason(s, markers_only) if resume else (False, "full run" if not dry else "dry run")
            if skip:
                e.update(action="skipped", reason=why, exit_code=None, runtime_s=0)
            else:
                tag = "all-%s-%d" % (s, int(time.time()))
                print("== make %s  (%s)" % (s, why), flush=True)
                t0 = time.time()
                rc = subprocess.run([make, "--no-print-directory", s], cwd=ROOT, env=dict(env, LAB_LOCK_TAG=tag)).returncode
                t1 = time.time()
                e.update(action="ran", reason=why, exit_code=rc, runtime_s=round(t1 - t0, 1), lock_wait_s=lock_wait(tag))
                if rc != 0: failed.append(s)
                elif not dry and not printonly:
                    files = input_files(s)
                    json.dump({"stage": s, "end_epoch": int(t1), "inputs_sha256": input_hash(files), "n_inputs": len(files)},
                              open(os.path.join(REC, s + ".json"), "w"))
        if e["action"] != "ran":
            print("== make %s: %s — %s" % (s, e["action"].upper().replace("_", " "), e["reason"]), flush=True)
        e["inputs"] = c.get("inputs", []); e["markers"] = c.get("markers", [])
        out.append(e)
    if printonly:
        print("make -n all: commands printed only, nothing executed or recorded"); return
    doc = {"generated": time.strftime("%F %T %Z"), "mode": mode, "exit_code": 1 if failed else 0, "failed_stages": failed,
           "demo_built": any(x["stage"] == "demo" and x["action"] == "ran" and x["exit_code"] == 0 for x in out), "stages": out}
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(doc, open(os.path.join(ROOT, "results", "make_all_last.json"), "w"), indent=1)
    print("make all summary: " + "; ".join("%s=%s" % (x["stage"], x["action"] + ("" if x["exit_code"] in (0, None) else "(exit %s)" % x["exit_code"])) for x in out))
    if failed:
        print("make all: stages that failed: " + " ".join(failed)); sys.exit(1)
    print("make all: no stage failed")


if __name__ == "__main__":
    main()
