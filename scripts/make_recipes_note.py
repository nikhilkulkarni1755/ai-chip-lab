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
        L.append("2. *Most later stages were skipped, not executed.* The run used the marker-only resume (`RESUME=markers`): the %d stages that had already "
                 "succeeded today (%s) were skipped without checking whether their inputs had changed%s. Reason: a full pass costs about 3 hours of the single "
                 "heavy-job queue (Decision P2-1). Consequence: the test shows the control flow continuing past the failure and reaching the end; it does "
                 "**not** show a heavy stage being executed after a failure. Executed for real after the forced failure: %s."
                 % (n_skip, ", ".join(ft["skipped_with_reason"]), (" (the input-aware rule of `RESUME=1` would have rerun: %s)" % ", ".join(would_run)) if would_run else "",
                    ", ".join(ft["executed_for_real"]) or "nothing"))
        if excl:
            L.append("3. *Excluded from the test:* %s. A stage with a `.failed` marker is rerun by the resume rule; this one was left out to keep the lock free." %
                     "; ".join("`%s` — %s" % (k, v.split(": ", 1)[-1]) for k, v in excl.items()))
        L.append("%d. *Sweeps were started but not waited for* (`SWEEPS_DETACH=1`), and Task 3's criterion-A jobs were disabled (`T3_USER_DEADLINE=1`)." % (4 if excl else 3))
        L.append("%d. *One assertion was changed while the test was written:* from \"only the forced stage failed\" to \"the forced stage is first in the failed list\", "
                 "so that a stage failing for its own reasons would be listed instead of failing the test. In this run no other stage failed (%s), so the original, "
                 "stricter assertion would also have held." % (5 if excl else 4, ft.get("other_stages_that_failed_for_their_own_reasons") or "none"))
        L.append("")
        L.append("It is therefore a weaker check than a full `make all` with one stage really failing: it verifies the fail-soft bookkeeping and exit status on the "
                 "real Makefile and markers, with %d of %d stages actually executed. Execution of real recipes after a real failure is covered separately by "
                 "(a) the unit test `scripts/tests/make_all_test.sh` on a scratch repository (cases A and J: every later recipe runs after one or two failing "
                 "recipes; 23 checks) and (b) the recorded `make all` run below, when present, in which a stage fails with its own exit code."
                 % (len(ft["executed_for_real"]), len(ft["stages"])))
    else:
        L.append("**`make all` fail-soft test:** not run yet.")
    al = d.get("make_all_run")
    lastp = os.path.join(ROOT, "results", "make_all_last.json")
    if os.path.exists(lastp):
        la = json.load(open(lastp))
        if "forced failure" not in la.get("mode", "") and "dry" not in la.get("mode", ""):
            al = la; d["make_all_run"] = la
    if al:
        L.append("")
        L.append("**`make all` (%s):** exit %d; failed stages: %s; per stage: %s." % (al.get("mode"), al["exit_code"], ", ".join(al["failed_stages"]) or "none",
                 "; ".join("%s %s%s%s" % (s["stage"], s["action"], (" exit %s" % s["exit_code"]) if s.get("exit_code") not in (None, 0) else "", (" — " + s["reason"]) if s["action"] == "skipped" else "") for s in al["stages"])))
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
    print(text)


if __name__ == "__main__":
    main()
