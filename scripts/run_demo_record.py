#!/usr/bin/env python3
"""Run demo/run_demo.sh once for real (as written, every container step through the lock) and record the result:
results/run_demo_last.json (total time, per-step verdict and seconds) + results/evidence/final_run_demo.txt (<= 60 lines).
Parsed from the script's own printed table and .cache/demo_run/timing.json; nothing is typed by hand."""
import json, os, re, subprocess, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(ROOT)
H = os.path.expanduser("~")
os.makedirs("logs/part2/run_demo", exist_ok=True)
log = "logs/part2/run_demo/run_demo_%s.log" % time.strftime("%H%M%S")
t0 = time.time()
with open(log, "w") as f:
    rc = subprocess.run(["bash", "demo/run_demo.sh"] + sys.argv[1:], stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode
wall = time.time() - t0
txt = open(log, errors="replace").read().replace(H, "~")
steps = [{"verdict": m.group(1), "seconds": int(m.group(2)), "step": m.group(3)}
         for m in (re.match(r"^(PASS|FAIL|SKIP)\s+(\d+)s\s+(.*)$", l) for l in txt.splitlines()) if m]
tm = json.load(open(".cache/demo_run/timing.json")) if os.path.exists(".cache/demo_run/timing.json") else {}
m = re.search(r"^RESULT: (\S+)", txt, re.M)
doc = {"command": "bash demo/run_demo.sh", "finished": tm.get("finished"), "result": m.group(1) if m else "NO RESULT LINE", "exit_code": rc,
       "total_s": tm.get("total_s"), "wall_s_measured_by_recorder": round(wall), "lock_wait_s": tm.get("lock_wait_s"), "cases": tm.get("cases"),
       "load_average": tm.get("load_average"), "steps": steps, "longest_step_s": max([s["seconds"] for s in steps] or [0]),
       "all_steps_under_60_s": bool(steps) and all(s["seconds"] < 60 for s in steps),
       "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
       "log": log, "evidence": "results/evidence/final_run_demo.txt",
       "how": "one real run of the script as written (scripts/run_demo_record.py); per-step times exclude lock wait (the script's own accounting)"}
json.dump(doc, open("results/run_demo_last.json", "w"), indent=1)
i = txt.find("================ demo summary")
pre = [l for l in txt[:i].splitlines() if l.strip()][-14:] if i >= 0 else txt.splitlines()[-40:]
ev = ["$ bash demo/run_demo.sh    (finished %s, commit %s, exit %d)" % (tm.get("finished"), doc["git_commit"], rc)] + pre + (txt[i:].rstrip().splitlines() if i >= 0 else [])
open("results/evidence/final_run_demo.txt", "w").write("\n".join(l[:200] for l in ev[:60]) + "\n")
print("run_demo: %s, exit %d, total %s s, steps: %s" % (doc["result"], rc, doc["total_s"], "; ".join("%s %ds" % (s["verdict"], s["seconds"]) for s in steps)))
sys.exit(rc)
