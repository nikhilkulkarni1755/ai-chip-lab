#!/usr/bin/env python3
"""Run ONE make recipe for real and record what happened in results/make_recipes.json (stage 32_make_recipes).

  python3 scripts/make_record.py <recipe> [VAR=value ...] [--note "text"]

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


def main():
    args = sys.argv[1:]
    note = None
    if "--note" in args:
        i = args.index("--note"); note = args[i + 1]; del args[i:i + 2]
    recipe, mvars = args[0], args[1:]
    os.makedirs(LOGD, exist_ok=True)
    tag = "make-%s-%d" % (recipe, int(time.time()))
    log = os.path.join(LOGD, "%s_%s.log" % (recipe, time.strftime("%H%M%S")))
    cmd = ["make", recipe] + mvars
    expanded = subprocess.run(["make", "-n", recipe] + mvars, cwd=LAB, capture_output=True, text=True).stdout
    expanded = [l.replace(HOME, "~") for l in expanded.splitlines() if l.strip()]
    env = dict(os.environ, LAB_LOCK_TAG=tag)
    t0 = time.time()
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
    doc = json.load(open(OUT)) if os.path.exists(OUT) else {"stage": "32_make_recipes", "recipes": [], "attempts": []}
    doc["attempts"].append(rec)
    doc["recipes"] = [r for r in doc["recipes"] if r["recipe"] != recipe] + [rec]
    doc["generated"] = time.strftime("%F %T %Z")
    doc["how"] = "each entry: `python3 scripts/make_record.py <recipe>` = a real `make <recipe>`; runtime_s is wall time incl. queueing for the heavy-job lock (lock_wait_s)"
    tmp = OUT + ".tmp"; json.dump(doc, open(tmp, "w"), indent=1); os.replace(tmp, OUT)
    print("make %s: exit %d in %.0fs (lock wait %ds) log %s" % (recipe, rc, t1 - t0, sum(waits), rec["log"]))
    sys.exit(rc)


if __name__ == "__main__":
    main()
