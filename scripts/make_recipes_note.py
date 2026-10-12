#!/usr/bin/env python3
"""Generate the README note on the make recipes from results/make_recipes.json (nothing hand-written).

  python3 scripts/make_recipes_note.py   -> results/make_recipes.md, and the same text as "readme_note" in the JSON
Also sets the top-level "pass" (every required recipe has a real run with exit code 0 and the fail-soft test passed).
"""
import json, os, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "results", "make_recipes.json")
REQUIRED = ["runtime", "images", "t1", "t2", "t2-stretch", "t3", "repro", "demo"]   # TASK2 P1.2 item 1
EXTRA_ORDER = ["t1-routed"]


def hm(s):
    s = int(round(s)); return "%d min %02d s" % (s // 60, s % 60) if s >= 60 else "%d s" % s


def main():
    d = json.load(open(P))
    rec = {r["recipe"]: r for r in d.get("recipes", [])}
    L = ["### Make recipes: what was actually run", ""]
    done = [r for r in REQUIRED if r in rec]
    missing = [r for r in REQUIRED if r not in rec]
    for r in REQUIRED:   # a recipe that is running again does not count as done
        run = d.get("running", {}).get(r)
        if run and r in rec and run["start_epoch"] > rec[r]["end_epoch"]: missing.append(r)
    failed = [r for r in done if rec[r]["exit_code"] != 0]
    L.append("Each recipe below was executed for real as `make <recipe>` from the repo root (recorded by "
             "`scripts/make_record.py`, raw data in `results/make_recipes.json`). Wall time includes waiting in the "
             "one-job-at-a-time queue of this machine; the time without that wait is shown separately.")
    L += ["", "| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |", "|---|---|---|---|---|---|---|"]
    for r in REQUIRED:
        run = d.get("running", {}).get(r)
        if run and (r not in rec or run["start_epoch"] > rec[r]["end_epoch"]):
            L.append("| `make %s` | still running%s | – | – | – | %s | `%s` |" % (r, (" (previous attempt: exit %d)" % rec[r]["exit_code"]) if r in rec else "", run["start"][11:19], run["log"])); continue
        if r not in rec:
            L.append("| `make %s` | not run yet | – | – | – | – | – |" % r); continue
        x = rec[r]
        L.append("| `make %s` | %d | %s | %s | %s | %s | `%s` |" % (r, x["exit_code"], hm(x["runtime_s"]), hm(x["lock_wait_s"]),
                 hm(x["runtime_excl_lock_wait_s"]), x["start"][11:19], x["log"]))
    extra = [r for r in rec if r not in REQUIRED]
    for r in extra:
        x = rec[r]
        L.append("| `make %s` | %d | %s | %s | %s | %s | `%s` |" % (r, x["exit_code"], hm(x["runtime_s"]), hm(x["lock_wait_s"]),
                 hm(x["runtime_excl_lock_wait_s"]), x["start"][11:19], x["log"]))
    L.append("")
    if missing: L.append("**Not run as a recipe yet:** " + ", ".join("`make %s`" % m for m in missing) + ".")
    if failed: L.append("**Recipes that exited non-zero:** " + ", ".join("`make %s` (exit %d)" % (m, rec[m]["exit_code"]) for m in failed) + " — see the log of each.")
    notes = ["`make %s`: %s" % (r, rec[r]["note"]) for r in rec if rec[r].get("note")]
    if notes: L += ["", "Notes: " + "; ".join(notes) + "."]
    ft = d.get("failsoft_test")
    L.append("")
    if ft:
        L.append("**`make all` fail-soft test: %s.** Command: `%s`. `make all` exited %d and listed the failed stage; "
                 "the demo was built after the failure. In this test the forced stage's recipe was not run (%s); "
                 "executed for real: %s; skipped by the resume rule (inputs unchanged since their last success): %s. "
                 "The marker was restored and the demo rebuilt afterwards. Details: `results/make_all_failsoft.json`."
                 % ("PASS" if ft["pass"] else "FAIL", ft["command"], ft["make_all_exit_code"], ", ".join(ft["not_run_forced_failure"]) or "-",
                    ", ".join(ft["executed_for_real"]) or "none", ", ".join(ft["skipped_with_reason"]) or "none"))
    else:
        L.append("**`make all` fail-soft test:** not run yet.")
    al = d.get("make_all_run")
    if al:
        L.append("")
        L.append("**`make all` (%s):** exit %d; failed stages: %s; per stage: %s." % (al.get("mode"), al["exit_code"], ", ".join(al["failed_stages"]) or "none",
                 "; ".join("%s %s%s" % (s["stage"], s["action"], (" — " + s["reason"]) if s["action"] == "skipped" else "") for s in al["stages"])))
    d["pass"] = (not missing) and (not failed) and bool(ft and ft["pass"])
    d["missing_recipes"] = missing; d["failed_recipes"] = failed
    text = "\n".join(L) + "\n"
    d["readme_note"] = text; d["note_generated"] = time.strftime("%F %T %Z")
    json.dump(d, open(P + ".tmp", "w"), indent=1); os.replace(P + ".tmp", P)
    open(os.path.join(ROOT, "results", "make_recipes.md"), "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
