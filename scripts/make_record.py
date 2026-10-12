#!/usr/bin/env python3
"""Run ONE make recipe for real and record what happened in results/make_recipes.json (stage 32_make_recipes).

  python3 scripts/make_record.py <recipe> [VAR=value ...] [--note "text"] [--watch "<glob of per-job done files>"]

--watch: lists which matching files already existed and were left untouched (work kept from before this recipe,
with its finish time) and which were created/rewritten while the recipe ran (work executed under the recipe).

The recipe is executed exactly as a user would: `make <recipe> VAR=value ...` from the repo root. Recorded per
recipe (latest attempt under "recipes", every attempt under "attempts"): the make command line, the commands
make expanded it to (`make -n`), start/end epoch, exit code, wall time, time spent queueing for the heavy-job
lock (summed from logs/part2/lock.log lines tagged with this run), log path, git commit and whether the
scripts were modified. Nothing here is typed by hand; `readme_note` and results/make_recipes.md are generated
from the same records by scripts/make_recipes_note.py.
"""
import json, os, re, subprocess, sys, time

LAB = os.path.expanduser("~/ai-chip-lab")
OUT = os.path.join(LAB, "results", "make_recipes.json")
LOGD = os.path.join(LAB, "logs", "part2", "32_make_recipes")
HOME = os.path.expanduser("~")


def sh(cmd):
    return subprocess.run(cmd, shell=True, cwd=LAB, capture_output=True, text=True).stdout.strip()


def mvars_change_scope(mvars):
    """make variables that make the run a partial/special one must not produce a 'stage succeeded' record"""
    return any(v.split("=")[0] in ("T1_CASES", "T1_OUT", "T3_OUT", "T3_PASSES", "T3_USER_DEADLINE", "T2_DESIGNS", "DRY_RUN", "T1R_STEPS", "ALL_STAGES") for v in mvars)


def update(fn):
    """read-modify-write of results/make_recipes.json under a small mkdir mutex (several recorders may run at once)"""
    mx = OUT + ".lock.d"
    for _ in range(600):
        try: os.mkdir(mx); break
        except FileExistsError:
            if time.time() - os.path.getmtime(mx) > 120: os.rmdir(mx)
            time.sleep(0.2)
    try:
        doc = json.load(open(OUT)) if os.path.exists(OUT) else {"stage": "32_make_recipes", "recipes": [], "attempts": []}
        fn(doc)
        doc["generated"] = time.strftime("%F %T %Z")
        doc["how"] = "each entry: `python3 scripts/make_record.py <recipe>` = a real `make <recipe>`; runtime_s is wall time incl. queueing for the heavy-job lock (lock_wait_s)"
        tmp = OUT + ".tmp"; json.dump(doc, open(tmp, "w"), indent=1); os.replace(tmp, OUT)
    finally:
        try: os.rmdir(mx)
        except OSError: pass


def main():
    args = sys.argv[1:]
    note = None
    if "--note" in args:
        i = args.index("--note"); note = args[i + 1]; del args[i:i + 2]
    watch = None
    if "--watch" in args:
        i = args.index("--watch"); watch = args[i + 1]; del args[i:i + 2]
    recipe, mvars = args[0], args[1:]
    import glob
    before = {f: os.path.getmtime(f) for f in glob.glob(os.path.join(LAB, watch))} if watch else {}
    os.makedirs(LOGD, exist_ok=True)
    tag = "make-%s-%d" % (recipe, int(time.time()))
    log = os.path.join(LOGD, "%s_%s.log" % (recipe, time.strftime("%H%M%S")))
    cmd = ["make", recipe] + mvars
    expanded = subprocess.run(["make", "-n", recipe] + mvars, cwd=LAB, capture_output=True, text=True).stdout
    expanded = [l.replace(HOME, "~") for l in expanded.splitlines() if l.strip()]
    env = dict(os.environ, LAB_LOCK_TAG=tag)
    # input hash of the stage (scripts/stage_inputs.json) before the run; on success with unchanged inputs a record
    # is written that `RESUME=1 make all` accepts as "this stage succeeded with exactly these inputs"
    sys.path.insert(0, os.path.join(LAB, "scripts"))
    try:
        import make_all as MA
        h0 = MA.input_hash(MA.input_files(recipe)) if recipe in MA.CFG["stages"] and not mvars_change_scope(mvars) else None
    except Exception:
        MA, h0 = None, None
    t0 = time.time()
    update(lambda doc: doc.setdefault("running", {}).__setitem__(recipe, {"command": " ".join(cmd), "start_epoch": int(t0), "start": time.strftime("%F %T %Z", time.localtime(t0)), "log": os.path.relpath(log, LAB), "pid": os.getpid()}))
    with open(log, "w") as f:
        f.write("$ %s   (started %s, lock tag %s)\n" % (" ".join(cmd), time.strftime("%F %T"), tag)); f.flush()
        rc = subprocess.run(cmd, cwd=LAB, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode
    t1 = time.time()
    waits = []
    try:
        for l in open(os.path.join(LAB, "logs", "part2", "lock.log")):
            if "tag=" + tag + " " in l:
                m = re.search(r"waited=(\d+)s", l)
                if m: waits.append(int(m.group(1)))
    except OSError:
        pass
    tail = [l.rstrip("\n").replace(HOME, "~") for l in open(log, errors="replace").readlines()[-6:]]
    rec = {
        "recipe": recipe, "name": recipe, "command": " ".join(cmd),
        "executed": expanded,
        "start_epoch": int(t0), "end_epoch": int(t1), "start": time.strftime("%F %T %Z", time.localtime(t0)),
        "exit_code": rc, "runtime_s": round(t1 - t0, 1),
        "lock_wait_s": sum(waits), "lock_acquisitions": len(waits),
        "runtime_excl_lock_wait_s": round(t1 - t0 - sum(waits), 1),
        "log": os.path.relpath(log, LAB),
        "git_commit": sh("git rev-parse --short HEAD"), "git_branch": sh("git rev-parse --abbrev-ref HEAD"),
        "scripts_modified_vs_commit": bool(sh("git status --porcelain -- Makefile scripts docker sweeps model demo/run_demo.sh")),
        "log_tail": tail,
    }
    if note: rec["note"] = note
    if MA and h0 and rc == 0:
        files = MA.input_files(recipe)
        if MA.input_hash(files) == h0:
            os.makedirs(MA.REC, exist_ok=True)
            json.dump({"stage": recipe, "end_epoch": int(t1), "inputs_sha256": h0, "n_inputs": len(files), "source": "scripts/make_record.py"},
                      open(os.path.join(MA.REC, recipe + ".json"), "w"))
            rec["resume_record"] = "written (inputs unchanged during the run)"
        else:
            rec["resume_record"] = "not written: stage inputs changed while the recipe ran"
    if watch:
        after = {f: os.path.getmtime(f) for f in glob.glob(os.path.join(LAB, watch))}
        rel = lambda f: os.path.relpath(f, LAB)
        stamp = lambda t: time.strftime("%F %T", time.localtime(t))
        rec["watch"] = watch
        # classified by finish time (file mtime) against the recipe start, so a job directory that the recipe
        # renames at its end (results/t3.partial -> results/t3) is not mistaken for newly executed work
        rec["kept_from_before_this_recipe"] = sorted("%s (finished %s)" % (rel(f), stamp(t)) for f, t in after.items() if t < t0)
        rec["executed_under_this_recipe"] = sorted("%s (finished %s)" % (rel(f), stamp(t)) for f, t in after.items() if t >= t0)
        rec["watched_gone_at_end"] = sorted(rel(f) for f in before if f not in after and not any(os.path.basename(g) == os.path.basename(f) for g in after))
    def upd(doc):
        doc["attempts"].append(rec)
        doc["recipes"] = [r for r in doc["recipes"] if r["recipe"] != recipe] + [rec]
        doc.get("running", {}).pop(recipe, None)
    update(upd)
    print("make %s: exit %d in %.0fs (lock wait %ds) log %s" % (recipe, rc, t1 - t0, sum(waits), rec["log"]))
    sys.exit(rc)


if __name__ == "__main__":
    main()
