#!/bin/bash
# Fail-soft self-test of `make all` (TASK2 P1.2 item 3), designed not to cost another full 3-hour pass:
#   1. `MAKE_ALL_FAIL=<stage> RESUME=1 make all` — the chosen stage (default: preflight, the cheapest) is forced
#      to fail: its recipe is not run and its marker is switched from .done to .failed. Every other stage goes
#      through the normal RESUME logic (runs for real if its inputs changed since it last succeeded, otherwise
#      it is skipped and the reason is logged). `demo` always runs.
#   2. Assertions: exit status non-zero; the failed stage is listed; every stage has a recorded outcome; the
#      demo recipe ran and succeeded after the failure; no stage after the failed one was dropped.
#   3. Restore: marker back to the original .done (same mtime), then `make demo` again so the page no longer
#      shows the forced failure. Verified.
# Result (what ran, what was skipped and why, the assertions) -> results/make_all_failsoft.json, and folded into
# results/make_recipes.json under "failsoft_test" when that file exists. Exit 0 iff all assertions hold.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 2
STAGE="${1:-preflight}"; ST=results/.stages
LOGD=logs/part2/32_make_recipes; mkdir -p "$LOGD"; LOG="$LOGD/failsoft_test_$(date +%H%M%S).log"
T0=$(date +%s)
MAKE_ALL_FAIL="$STAGE" RESUME=1 make all > "$LOG" 2>&1; RC=$?
cp results/make_all_last.json "$LOGD/failsoft_make_all_last.json" 2>/dev/null
# restore the marker(s) no matter what
restored=1
for saved in "$ST"/*.done.failsoft_saved; do
  [ -e "$saved" ] || continue
  m="${saved%.done.failsoft_saved}"; rm -f "$m.failed"; mv "$saved" "$m.done" || restored=0
done
ls "$ST"/*.failsoft_saved >/dev/null 2>&1 && restored=0
make demo > "$LOGD/failsoft_restore_demo.log" 2>&1; RC_DEMO2=$?
T1=$(date +%s)
python3 - "$STAGE" "$RC" "$RC_DEMO2" "$restored" "$LOG" "$T0" "$T1" <<'PY'
import json, os, sys, time
stage, rc, rc_demo2, restored, log, t0, t1 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1", sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
last = json.load(open(os.path.join("logs/part2/32_make_recipes", "failsoft_make_all_last.json")))
cfg = json.load(open("scripts/stage_inputs.json"))
text = open(log, errors="replace").read()
st = {x["stage"]: x for x in last["stages"]}
order = cfg["order"]
after = order[order.index(stage) + 1:]
markers = cfg["stages"][stage].get("markers", [])
checks = {
    "exit_status_nonzero": rc != 0,
    "failed_stage_listed": ("stages that failed: " in text) and stage in last["failed_stages"],
    "every_stage_has_an_outcome": all(s in st for s in order),
    "later_stages_not_dropped": all(st[s]["action"] in ("ran", "skipped") for s in after if s in st),
    "demo_ran_after_the_failure_and_succeeded": st.get("demo", {}).get("action") == "ran" and st["demo"]["exit_code"] == 0,
    "only_the_forced_stage_failed": last["failed_stages"] == [stage],
    "marker_restored": restored and all(os.path.exists("results/.stages/%s.done" % m) and not os.path.exists("results/.stages/%s.failed" % m) for m in markers),
    "demo_rebuilt_after_restore": rc_demo2 == 0,
}
doc = {
    "generated": time.strftime("%F %T %Z"), "pass": all(checks.values()), "checks": checks,
    "command": "MAKE_ALL_FAIL=%s RESUME=1 make all   (then marker restored and `make demo` rerun)" % stage,
    "forced_stage": stage, "make_all_exit_code": rc, "runtime_s": t1 - t0, "log": log,
    "executed_for_real": [s for s in order if st.get(s, {}).get("action") == "ran"],
    "skipped_with_reason": {s: st[s]["reason"] for s in order if st.get(s, {}).get("action") == "skipped"},
    "not_run_forced_failure": [s for s in order if st.get(s, {}).get("action") == "forced_fail"],
    "stages": last["stages"],
    "scope_note": "This test proves the control flow of `make all` (continue after a failure, always build the demo, "
                  "non-zero exit listing the failed stage). The forced stage's recipe was NOT executed; stages listed under "
                  "skipped_with_reason were NOT executed in this test (their real runs are the per-recipe entries).",
}
json.dump(doc, open("results/make_all_failsoft.json", "w"), indent=1)
if os.path.exists("results/make_recipes.json"):
    d = json.load(open("results/make_recipes.json")); d["failsoft_test"] = doc
    json.dump(d, open("results/make_recipes.json.tmp", "w"), indent=1); os.replace("results/make_recipes.json.tmp", "results/make_recipes.json")
for k, v in checks.items(): print("%-5s %s" % ("OK" if v else "FAIL", k))
print("fail-soft test: %s (make all exit %d; ran: %s; skipped: %s)" % ("PASS" if doc["pass"] else "FAIL", rc, " ".join(doc["executed_for_real"]) or "-", " ".join(doc["skipped_with_reason"]) or "-"))
sys.exit(0 if doc["pass"] else 1)
PY
