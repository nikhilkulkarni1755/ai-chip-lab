#!/bin/bash
# Stage 00_preflight, re-runnable and NON-DESTRUCTIVE:
#  * measures the machine now and checks the lab's hard requirements;
#  * creates env.json / budget.json only if they do not exist yet. An existing budget.json is never
#    rewritten (its start time is the run's clock); an existing env.json is kept as the record of the
#    machine at the start of the run, and the fresh measurement goes to logs/00_preflight/env_now.json.
# Env: BUDGET_H (default 6) is used only when budget.json has to be created.
# Exit 0 = all hard checks pass (warnings allowed).
set -u
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 2
source "$LAB/env.sh"
mkdir -p logs/00_preflight results/.stages
python3 - "${BUDGET_H:-6}" <<'PY'
import json, os, shutil, subprocess, sys, time
H = os.path.expanduser("~")
def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception: return ""
def scrub(s): return s.replace(H, "~") if isinstance(s, str) else s
ver = sh("sw_vers -productVersion")
free = int(sh("df -g ~ | tail -1").split()[3])
env = {
    "sw_vers": sh("sw_vers"), "product_version": ver, "arch": sh("uname -m"),
    "cpu": sh("sysctl -n machdep.cpu.brand_string"), "ncpu": int(sh("sysctl -n hw.ncpu")),
    "physical_cpu": int(sh("sysctl -n hw.physicalcpu")), "memsize_bytes": int(sh("sysctl -n hw.memsize")),
    "df_g_home": sh("df -g ~ | tail -1"), "free_disk_gb": free,
    "sudo_passwordless": subprocess.run("sudo -n true", shell=True, capture_output=True).returncode == 0,
    "tools": {t: scrub(shutil.which(t)) for t in ("docker", "colima", "limactl", "python3", "git", "curl", "gh", "uv")},
}
json.dump(env, open("logs/00_preflight/env_now.json", "w"), indent=2)
if not os.path.exists("env.json"):
    json.dump(env, open("env.json", "w"), indent=2); print("env.json: created")
else:
    print("env.json: kept (start-of-run record); current measurement -> logs/00_preflight/env_now.json")
now = int(time.time())
if not os.path.exists("budget.json"):
    h = float(sys.argv[1]); s = now
    b = {"start_epoch": s, "start": time.strftime("%F %T %Z", time.localtime(s)), "total_budget_h": h,
         "note": "created by scripts/preflight.sh; milestones scaled from the task's 14 h plan (baselines 2.5/6, sweeps stop 5/6)",
         "deadline_baselines_epoch": int(s + h * 3600 * 2.5 / 6), "deadline_sweeps_stop_epoch": int(s + h * 3600 * 5 / 6),
         "deadline_final_epoch": int(s + h * 3600)}
    json.dump(b, open("budget.json", "w"), indent=2); print("budget.json: created (%.1f h)" % h)
else:
    b = json.load(open("budget.json")); print("budget.json: kept (start %s, never rewritten)" % b.get("start"))
def left(k):
    d = b[k] - now; return ("%dh%02dm left" % (d // 3600, d % 3600 // 60)) if d > 0 else ("passed %dh%02dm ago" % (-d // 3600, -d % 3600 // 60))
fail = 0
def chk(name, ok, detail, hard=True):
    global fail
    print("%-5s %-28s %s" % ("OK" if ok else ("FAIL" if hard else "WARN"), name, detail))
    if hard and not ok: fail = 1
chk("macOS >= 13 (vz)", int(ver.split(".")[0]) >= 13, ver)
chk("x86_64 host", env["arch"] == "x86_64", env["arch"])
chk("free disk >= 20 GB", free >= 20, "%d GB free" % free)
chk("memory >= 8 GB", env["memsize_bytes"] >= 8 * 2**30, "%.0f GB" % (env["memsize_bytes"] / 2**30))
for t in ("python3", "git", "curl"): chk("tool " + t, bool(env["tools"][t]), str(env["tools"][t]))
chk("caffeinate running", bool(sh("pgrep -x caffeinate")), "keeps the Mac awake (start: caffeinate -dimsu &)", hard=False)
chk("passwordless sudo", env["sudo_passwordless"], "not required (Route A needs no sudo)", hard=False)
chk("lab runtime installed", all(env["tools"][t] for t in ("docker", "colima", "limactl")), "else: make runtime", hard=False)
chk("budget: sweeps window", b["deadline_sweeps_stop_epoch"] > now, left("deadline_sweeps_stop_epoch") + " (sweeps start no new point after it)", hard=False)
chk("budget: final deadline", b["deadline_final_epoch"] > now, left("deadline_final_epoch"), hard=False)
sys.exit(fail)
PY
rc=$?
if [ $rc -eq 0 ]; then [ -f results/.stages/00_preflight.done ] || : > results/.stages/00_preflight.done; echo "preflight: PASS"; else echo "preflight: FAIL"; fi
exit $rc
