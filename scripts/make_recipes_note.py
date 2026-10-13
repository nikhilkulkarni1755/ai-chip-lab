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
    resume_r = [r for r in rec if rec[r].get("watch")]
    L.append("Each row is one recorded invocation of `make` from the repo root with exactly the command shown (recorded by "
             "`scripts/make_record.py`, raw data in `results/make_recipes.json`). Not every recipe re-executed all of its work: "
             + ("; ".join("`%s` ran in resume mode (%d step/job results kept from earlier runs of the same day by the identical commands, %d executed under the recipe)"
                          % (rec[r]["command"], len(rec[r].get("kept_from_before_this_recipe", [])), len(rec[r].get("executed_under_this_recipe", []))) for r in resume_r)
                or "no recipe used resume mode")
             + ". Variables on a command line restrict what ran (`T3_USER_DEADLINE=1`: Task 3 criterion-A jobs not started; `T1R_SKIP=gls_verilator`: "
             "Verilator gate-level simulation not run; `REPRO_PART=t3`: Task 3 rerun only). Wall time includes waiting in the one-job-at-a-time queue of this "
             "machine; the time without that wait is shown separately. The recipes were not run in the order of the task text; all recorded invocations by start time: "
             + ", ".join("%s %s (exit %d)" % (a["start"][11:16], a["recipe"], a["exit_code"]) for a in sorted(d.get("attempts", []), key=lambda a: a["start_epoch"])) + ".")
    L += ["", "| Recipe | Exit code | Wall time | of which queue wait | Run time | Started | Log |", "|---|---|---|---|---|---|---|"]
    for r in REQUIRED:
        run = d.get("running", {}).get(r)
        if run and (r not in rec or run["start_epoch"] > rec[r]["end_epoch"]):
            L.append("| `make %s` | still running%s | – | – | – | %s | `%s` |" % (r, (" (previous attempt: exit %d)" % rec[r]["exit_code"]) if r in rec else "", run["start"][11:19], run["log"])); continue
        if r not in rec:
            L.append("| `make %s` | not run yet | – | – | – | – | – |" % r); continue
        x = rec[r]
        L.append("| `%s` | %d | %s | %s | %s | %s | `%s` |" % (x["command"], x["exit_code"], hm(x["runtime_s"]), hm(x["lock_wait_s"]),
                 hm(x["runtime_excl_lock_wait_s"]), x["start"][11:19], x["log"]))
    extra = [r for r in rec if r not in REQUIRED]
    for r in extra:
        x = rec[r]
        L.append("| `%s` | %d | %s | %s | %s | %s | `%s` |" % (x["command"], x["exit_code"], hm(x["runtime_s"]), hm(x["lock_wait_s"]),
                 hm(x["runtime_excl_lock_wait_s"]), x["start"][11:19], x["log"]))
    L.append("")
    if missing: L.append("**Not run as a recipe yet:** " + ", ".join("`make %s`" % m for m in missing) + ".")
    if failed: L.append("**Recipes that exited non-zero:** " + ", ".join("`make %s` (exit %d)" % (m, rec[m]["exit_code"]) for m in failed) + " — see the log of each.")
    notes = ["`make %s`: %s" % (r, " ".join(rec[r][k] for k in ("note", "executed_note", "annotation_by_infra") if rec[r].get(k))) for r in rec
             if any(rec[r].get(k) for k in ("note", "executed_note", "annotation_by_infra"))]
    prev = {}
    for a_ in d.get("attempts", []):
        if a_["recipe"] in rec and a_["start_epoch"] != rec[a_["recipe"]]["start_epoch"]:
            prev.setdefault(a_["recipe"], []).append("attempt started %s: exit %d after %s%s" % (a_["start"][11:19], a_["exit_code"], hm(a_["runtime_s"]),
                                                    (" — " + a_["annotation_by_infra"]) if a_.get("annotation_by_infra") else ""))
    if prev: notes += ["earlier attempts of `make %s`: %s" % (r, " | ".join(v)) for r, v in prev.items()]
    if notes: L += ["", "Notes:", ""] + ["- " + n for n in notes]
    ft = d.get("failsoft_test")
    L.append("")
    if ft:
        L.append("**`make all` fail-soft test: %s.** Command: `%s`. `make all` exited %d and listed the failed stage; "
                 "the demo was built after the failure. In this test the forced stage's recipe was not run (%s); "
                 "executed for real: %s; skipped because they had already succeeded (marker-only resume of the test, see each reason): %s; excluded from the test: %s. "
                 "The marker was restored and the demo rebuilt afterwards. Details: `results/make_all_failsoft.json`."
                 % ("PASS" if ft["pass"] else "FAIL", ft["command"], ft["make_all_exit_code"], ", ".join(ft["not_run_forced_failure"]) or "-",
                    ", ".join(ft["executed_for_real"]) or "none", ", ".join(ft["skipped_with_reason"]) or "none",
                    "; ".join("%s (%s)" % kv for kv in ft.get("excluded_from_this_test", {}).items()) or "none"))
        # how the executed test differs from the test as first specified (generated from the recorded test, not typed per run)
        n_skip = len(ft["skipped_with_reason"]); excl = ft.get("excluded_from_this_test", {})
        would_run = [s for s, why in ft["skipped_with_reason"].items() if "would say: RUN" in why]
        L += ["", "**How this test differs from the test as first specified, and why.** The specification (TASK2 P1.2 item 3) was: run `make all`, "
              "temporarily force one stage marker to fail, confirm that all stages still run, the demo is built and the exit status is non-zero "
              "listing the failed stage, then restore. What was executed differs in these points:", ""]
        L.append("1. *The failure is injected by a hook, not by a failing recipe.* `MAKE_ALL_FAIL=%s` makes `scripts/make_all.py` skip that stage's recipe, "
                 "switch its marker from `.done` to `.failed` and count the stage as failed. This matches the specification (\"forcing a stage marker to fail\"); "
                 "it does not show a recipe that fails by itself." % ft["forced_stage"])
        L.append("2. *Most later stages were skipped, not executed.* The run used the marker-only resume (`RESUME=markers`): the %d stages that already had a `.done` marker or a recorded "
                 "successful run (%s) were skipped without checking whether their inputs had changed%s. Reason: a full pass costs about 3 hours of the single "
                 "heavy-job queue (Decision P2-1). Consequence: the test shows the control flow continuing past the failure and reaching the end; it does "
                 "**not** show a heavy stage being executed after a failure. Executed for real after the forced failure: %s."
                 % (n_skip, ", ".join(ft["skipped_with_reason"]), (" (the input-aware rule of `RESUME=1` would have rerun: %s)" % ", ".join(would_run)) if would_run else "",
                    ", ".join(ft["executed_for_real"]) or "nothing"))
        if excl:
            L.append("3. *Excluded from the test:* %s. A stage with a `.failed` marker is rerun by the resume rule; this one was left out to keep the lock free." %
                     "; ".join("`%s` — %s" % (k, v.split(": ", 1)[-1]) for k, v in excl.items()))
        L.append("%d. *Sweeps were started but not waited for* (`SWEEPS_DETACH=1`), and Task 3's criterion-A jobs were disabled (`T3_USER_DEADLINE=1`)." % (4 if excl else 3))
        L.append("%d. *One assertion was changed while the test was written:* from \"only the forced stage failed\" to \"the forced stage is first in the failed list\", "
                 "so that a stage failing for its own reasons is listed instead of failing the test. Failed list of this run besides the forced stage: %s.%s"
                 % (5 if excl else 4, ", ".join(ft.get("other_stages_that_failed_for_their_own_reasons") or []) or "empty",
                    (" " + ft["known_weakness"]) if ft.get("known_weakness") else ""))
        L.append("")
        L.append("It is therefore a weaker check than a full `make all` with one stage really failing: it verifies the fail-soft bookkeeping and exit status on the "
                 "real Makefile and markers, with %d of %d stages actually executed. Execution of real recipes after a real failure is covered separately by "
                 "(a) the unit test `scripts/tests/make_all_test.sh` on a scratch repository (cases A and J: every later recipe runs after one or two failing "
                 "recipes) and (b) the recorded `make all` run below, when present, in which a stage fails with its own exit code."
                 % (len(ft["executed_for_real"]), len(ft["stages"])))
    else:
        L.append("**`make all` fail-soft test:** not run yet.")
    hist = d.get("failsoft_history", [])
    if hist:
        L += ["", "Earlier fail-soft test runs (kept for the record):", ""]
        for h in hist:
            L.append("- %s: %s; executed for real: %s; excluded: %s.%s" % (h["generated"][11:16], "PASS" if h["pass"] else "FAIL", ", ".join(h["executed_for_real"]) or "none",
                     ", ".join(h.get("excluded_from_this_test", {})) or "none", (" " + h["known_weakness"]) if h.get("known_weakness") else ""))
    al = d.get("make_all_run")
    lastp = os.path.join(ROOT, "results", "make_all_last.json")
    if os.path.exists(lastp):
        la = json.load(open(lastp))
        if "forced failure" not in la.get("mode", "") and "dry" not in la.get("mode", ""):
            al = la; d["make_all_run"] = la
    if al:
        L.append("")
        L.append("**`make all` (%s):** exit %d; failed stages: %s; per stage: %s." % (al.get("mode"), al["exit_code"], ", ".join(al["failed_stages"]) or "none",
                 "; ".join("%s %s%s%s" % (s["stage"], s["action"] + ((" %.0f s, of which lock wait %s s" % (s["runtime_s"], s.get("lock_wait_s", 0))) if s["action"] == "ran" else ""), (" exit %s" % s["exit_code"]) if s.get("exit_code") not in (None, 0) else "", (" — " + s["reason"]) if s["action"] == "skipped" else "") for s in al["stages"])))
    if not al:
        L += ["", "**`make all` run for real once (TASK2 P1.7 / Final steps): not run yet.**"]
    pr = (al or {}).get("post_repro_identity_check")
    if pr:
        t1c = pr["task1"]
        L += ["", "**Why the repro verdict still covers the files on HEAD.** `make all` re-executed stages whose first-run files `make repro` had already compared. "
              "Checked afterwards by `scripts/post_repro_identity_check.py`: Task 1 files on HEAD vs the rerun copies repro compared — %s; "
              "summary check booleans equal to the rerun's (%d compared): %s; Task 2 (the stage's own comparison against every earlier run): %s. Overall: **%s**."
              % ("; ".join("`%s` %s" % (f["file"], "identical" if f["identical"] else "DIFFERENT") for f in t1c["files"]), t1c["summary_check_booleans_compared"],
                 "yes" if t1c["summary_check_booleans_equal_to_rerun"] else "NO (%s)" % ", ".join(t1c["differing_summary_checks"]),
                 "; ".join("%s run %s %s" % (x["design"], x["runs"], "identical" if x["identical_to_all_earlier_runs"] else "DIFFERENT") for x in pr["task2_stage_own_comparison"]) or "no record",
                 "identical" if pr["identical"] else "DIFFERENCE FOUND — a determinism finding, see results/make_all_last.json")]
    ce = os.path.join(ROOT, "coord", "images_cacti.env")
    if os.path.exists(ce):
        ref = [l.split("=", 1)[1].strip() for l in open(ce) if l.startswith("CACTI_IMAGE=")]
        L += ["", "**Image pins.** `coord/images.env` holds the two images every baseline stage uses (lab-sim, ORFS) and is an input of those stages. The CACTI image of "
              "stage 63 (`%s`) is pinned separately in `coord/images_cacti.env` and in the `cacti:` section of `versions.lock`, on purpose: adding it to `coord/images.env` "
              "would change an input of Task 1 and of the repro stage and force their rerun (Decision P2-12)." % (ref[0] if ref else "?")]
    d["pass"] = (not missing) and (not failed) and bool(ft and ft["pass"])
    d["missing_recipes"] = missing; d["failed_recipes"] = failed
    text = "\n".join(L) + "\n"
    d["readme_note"] = text; d["note_generated"] = time.strftime("%F %T %Z")
    # write back only the generated keys, under the recorder's mutex, on a fresh read (recorders may be running)
    mx = P + ".lock.d"
    for _ in range(600):
        try: os.mkdir(mx); break
        except FileExistsError: time.sleep(0.2)
    try:
        cur = json.load(open(P))
        for k in ("pass", "missing_recipes", "failed_recipes", "readme_note", "note_generated", "make_all_run"):
            if k in d: cur[k] = d[k]
        json.dump(cur, open(P + ".tmp", "w"), indent=1); os.replace(P + ".tmp", P)
    finally:
        try: os.rmdir(mx)
        except OSError: pass
    open(os.path.join(ROOT, "results", "make_recipes.md"), "w").write(text)
    # stage marker follows the verdict (never left at .running)
    st = os.path.join(ROOT, "results", ".stages", "32_make_recipes")
    for ext in ("running", "done", "failed"):
        if os.path.exists(st + "." + ext): os.remove(st + "." + ext)
    line = "pass=%s; exit codes: %s; not run: %s; fail-soft test: %s; make all for real: %s; %s\n" % (
        d["pass"], ", ".join("%s=%d" % (r, rec[r]["exit_code"]) for r in rec), ", ".join(missing) or "none",
        ("PASS" if ft["pass"] else "FAIL") if ft else "not run", "recorded" if al else "not run yet", time.strftime("%F %T"))
    open(st + (".done" if d["pass"] else ".failed"), "w").write(line)
    print(text)


if __name__ == "__main__":
    main()
