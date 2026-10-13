"""demo_part2.py - Part 2 sections of the demo page, built only from files on disk (stdlib only).
Used by demo_build.py. Everything shown is read from: coord/part2_before.json, results/.stages markers, results/p2_<stage>.json,
results/make_recipes.json, results/t*_summary.json, docs/part2_changes.json, docs/next.md, COORDINATION.md, budget_part2.json, git.
Missing input = PENDING; nothing is invented."""
import glob
import html
import json
import os
import re
import subprocess
import time

e = html.escape
P2_STAGES = [("31_roofline_fix", "P1.1 Task 3 roofline check"), ("32_make_recipes", "P1.2 every make recipe run for real"),
             ("11_eqy_routed", "P1.3 equivalence and gate-level simulation of the routed netlist"), ("51_repro_full", "P1.4 complete determinism story"),
             ("21_orfs_crosscheck", "P1.5 Task 2 against ORFS's published results"), ("41_sweeps_finish", "P1.6 finish and refine the sweeps"),
             ("60_power_activity", "P2.1 activity-based power"), ("61_pe_bf16", "P2.2 bf16 processing element"), ("62_pdk_compare", "P2.3 systolic_os on sky130hd"),
             ("63_sram_cacti", "P2.4 SRAM modelling (CACTI)"), ("64_roadmap", "P2.5 roadmap")]
BADGE = {"PARTIAL": "warn", "INCOMPLETE": "warn", "PASS": "ok", "DONE": "ok", "FAIL": "bad", "BLOCKED": "warn", "RUNNING": "run", "PENDING": "dim", "UNKNOWN": "dim"}


def badge(s):
    return '<span class="b %s">%s</span>' % (BADGE.get(s, "dim"), e(s))


def active(L):
    return os.path.exists(L.p("budget_part2.json"))


def marker(L, stage):
    """Marker of a stage; sub-stages named <stage>_<x> (e.g. 41_sweeps_finish_A / _B) are merged: failed > blocked > running > done."""
    names = {stage}
    for f in glob.glob(L.p("results/.stages/%s_*" % stage)):
        names.add(os.path.basename(f).rsplit(".", 1)[0])
    seen = {}
    for n in sorted(names):
        for st in ("failed", "blocked", "done", "running"):
            rel = "results/.stages/%s.%s" % (n, st)
            if os.path.exists(L.p(rel)):
                seen.setdefault(st, []).append((n, L.read(rel).strip()))
                break
    for st in ("failed", "blocked", "running", "done"):
        if st in seen:
            body = "\n".join(("%s: %s" % (n, b)) if len(names) > 1 else b for n, b in seen[st])
            return st, body
    return "none", ""


def p2json(L, stage):
    return L.jload("results/p2_%s.json" % stage)


def stage_state(L, stage):
    """-> (state, detail). PASS only with marker .done AND (if present) p2 json pass==true; FAIL when failed marker or pass false."""
    st, body = marker(L, stage)
    j = p2json(L, stage)
    first = (body.splitlines() or [""])[0][:200]
    if st == "failed":
        return "FAIL", ".failed: " + first
    if st == "blocked":
        return "BLOCKED", ".blocked: " + first
    if isinstance(j, dict) and isinstance(j.get("pass"), bool):
        if j["pass"] and st == "done":
            return "PASS", "results/p2_%s.json pass=true" % stage
        if st == "running":
            return "RUNNING", "stage in progress"
        if j["pass"]:
            return "UNKNOWN", "summary says pass but no .done marker"
        return "FAIL", "results/p2_%s.json pass=false" % stage
    if st == "running":
        return "RUNNING", "stage in progress"
    if st == "done":
        return "DONE", ".done marker (no p2 summary JSON found; nothing further to verify)"
    inf = inferred_progress(L, stage)
    if inf:
        return inf
    return "PENDING", "no marker and no summary yet"


def inferred_progress(L, stage):
    """Stages that have no marker of their own but whose work is visibly on disk (run inside another recipe or by a driver)."""
    if stage == "31_roofline_fix":
        done = sorted(os.path.basename(x)[:-5] for x in glob.glob(L.p("results/t3.partial/roofline2/*.json")))
        if done or os.path.isdir(L.p("results/t3.partial/roofline2")):
            return "INCOMPLETE", ("no stage marker: the roofline runs are executed inside the real `make t3` (stage 32_make_recipes). Runs finished: %s; the fixed-bandwidth runs "
                                 "(criterion A) are in progress or not started; see the Task 3 row for the pre-registered criteria" % (", ".join(done) or "none"))
    if stage == "62_pdk_compare":
        n = len(pdk_points(L))
        if n:
            return "RUNNING", "no stage marker yet; %d sky130hd point(s) recorded in results/pdk_compare/sky130hd_points.jsonl; label by rule: %s" % (n, pdk_label(pdk_points(L)))
    if stage == "41_sweeps_finish":
        t0 = (L.jload("budget_part2.json") or {}).get("start_epoch") or 0
        new = 0
        try:
            for ln in open(L.p("results/sweeps/phys.jsonl"), encoding="utf-8"):
                ln = ln.strip()
                if ln and (json.loads(ln).get("finished_epoch") or 0) >= t0:
                    new += 1
        except (OSError, ValueError):
            pass
        if new or os.path.exists(L.p("results/sweeps/phys_plan_status.json")):
            return "INCOMPLETE", ("no stage marker: the sweep drivers work through the Part 2 plan under the low-priority lock queue; %d sweep B point(s) finished since Part 2 started; "
                                  "every planned point is listed with its state in section 12 (sweep A: see results/sweeps/arch_summary.json)" % new)
    return None


def ev_links(L, files, ctx_prefix="../"):
    out = []
    for f in files or []:
        if os.path.exists(L.p(f)):
            out.append('<a href="%s%s"><code>%s</code></a>' % (ctx_prefix, e(f), e(f)))
        else:
            out.append('<code class="missing" title="not on disk">%s</code>' % e(f))
    return ", ".join(out) if out else "<span class='sub'>none cited</span>"


def find_bool(d, key, depth=0):
    if not isinstance(d, dict) or depth > 4:
        return None
    if isinstance(d.get(key), bool):
        return d[key]
    for v in d.values():
        r = find_bool(v, key, depth + 1)
        if r is not None:
            return r
    return None


def extra_rows(L, Row, t1, t2, t3):
    """Part 2 rows appended to the one-screen table (Row is demo_build.Row)."""
    rows = []
    for key, label, stage in (("eqy_routed_pass", "Task 1: RTL = ROUTED netlist equivalence (EQY)", "11_eqy_routed"),
                              ("gls_routed_pass", "Task 1: routed gate-level simulation vs NumPy", "11_eqy_routed")):
        v = find_bool(t1, key)
        mst, mbody = marker(L, stage)
        if v is None:
            rows.append(Row(label, {"failed": "FAIL", "blocked": "BLOCKED", "running": "RUNNING"}.get(mst, "PENDING"),
                            "not reported in t1_summary.json yet (stage 11_eqy_routed: %s)" % (mst if mst != "none" else "no marker"), None))
        else:
            rt = (t1 or {}).get("routed") if isinstance(t1, dict) else None
            more = ""
            if isinstance(rt, dict):
                ck = rt.get("checks") or {}
                if key == "eqy_routed_pass" and isinstance(rt.get("eqy_partitions_proved"), list) and len(rt["eqy_partitions_proved"]) == 2:
                    pr = rt["eqy_partitions_proved"]
                    more = "; EQY partitions proved: %s of %s%s" % (pr[0], pr[1], "" if pr[0] == pr[1] else " (the rest were not proved; see the diagnosis in the not-green list)")
                if key == "gls_routed_pass":
                    gb = rt.get("gls_by_simulator") or {}
                    more = "; %s; Icarus 0 mismatches against NumPy: %s; negative control detected: %s; Verilator: %s" % (
                        rt.get("gls_routed_status") or "see the per-simulator status", ck.get("gls_icarus_zero_mismatches"), ck.get("gls_negative_control_detected"),
                        str(gb.get("verilator", "no result"))[:160])
            lead = (str(rt.get("gls_routed_status")).upper()[:1] + str(rt.get("gls_routed_status"))[1:] + "; ") if (key == "gls_routed_pass" and isinstance(rt, dict) and rt.get("gls_routed_status")) else ""
            if lead:
                more = more.replace("; %s; " % rt.get("gls_routed_status"), "; ", 1)
            stt = "PASS" if v else "FAIL"
            if v and key == "gls_routed_pass" and " only" in lead:
                stt = "PARTIAL"
                lead = "Icarus PASS; Verilator not run (partial against the task, not counted as a PASS). " + lead
            rows.append(Row(label, stt, "%s%s = %s in t1_summary.json%s" % (lead, key, str(v).lower(), more), "results/t1_summary.json"))
    v = find_bool(t2, "matches_published")
    mst, _ = marker(L, "21_orfs_crosscheck")
    rows.append(Row("Task 2: matches ORFS's published reference results", ("PASS" if v else "FAIL") if v is not None else {"failed": "FAIL", "blocked": "BLOCKED", "running": "RUNNING"}.get(mst, "PENDING"),
                    ("matches_published = %s in t2_summary.json" % str(v).lower()) if v is not None else "not reported yet (stage 21_orfs_crosscheck: %s)" % (mst if mst != "none" else "no marker"),
                    "results/t2_summary.json" if v is not None else None))
    for stage, label in (("60_power_activity", "P2.1 Activity-based power"), ("61_pe_bf16", "P2.2 bf16 processing element"), ("62_pdk_compare", "P2.3 systolic_os on sky130hd"),
                         ("63_sram_cacti", "P2.4 SRAM modelling (CACTI)")):
        stt, det, evf = phase2_state(L, stage)
        rows.append(Row(label, stt, det, evf))
    mr = L.jload("results/make_recipes.json")
    st, det = stage_state(L, "32_make_recipes")
    if isinstance(mr, dict):
        recs = mr.get("recipes") or []
        bad = [r.get("name") for r in recs if r.get("exit_code") not in (0, None)]
        if st in ("PASS", "DONE") or recs:
            state = "FAIL" if (bad and st != "RUNNING") else ("PASS" if (recs and st in ("PASS", "DONE")) else (st if st != "DONE" else "UNKNOWN"))
            det = "%d recipe(s) recorded in results/make_recipes.json; non-zero exit: %s" % (len(recs), ", ".join(map(str, bad)) or "none")
            if state == "FAIL" and not bad:
                state = st
            st = state
    if isinstance(mr, dict) and mr.get("running"):
        st = "RUNNING"
        det += "; still running: %s (the row keeps reading RUNNING until that run has finished and results/make_all_last.json and the note say otherwise)" % ", ".join(
            "%s (started %s)" % (v.get("command"), v.get("start")) for v in mr["running"].values() if isinstance(v, dict))
    rows.append(Row("Make recipes executed for real", st, det, "results/make_recipes.json" if isinstance(mr, dict) else None))
    return rows


def render_before_after(L, rows, before):
    """Table: every TASK2 start-of-Part-2 row next to its state now; every PASS cites evidence (checked on disk)."""
    by = {}
    for r in rows:
        by.setdefault(r.label.split(":")[0] if r.label.startswith("Task") else r.label, []).append(r)

    def pick(prefixes):
        return [r for r in rows if any(r.label.startswith(p) for p in prefixes)]
    spec = {"runtime": (["Container runtime"], ["results/evidence/01_runtime_docker.txt"]),
            "images": (["Lab images"], ["results/evidence/02_images_smoke.txt"]),
            "task1": (["Task 1:"], ["results/t1_summary.json", "results/evidence/10_eqy.txt", "results/evidence/10_sby.txt", "results/evidence/10_sha256.txt"]),
            "task2": (["Task 2:"], ["results/t2_summary.json", "results/evidence/20_threshold_check_nangate45_gcd.txt", "docs/t2_timing_explained.md"]),
            "task3": (["Task 3:"], ["results/t3_summary.json", "results/evidence/30_roofline.txt", "docs/t3_roofline_explained.md"]),
            "sweepA": (["Sweep A"], ["results/sweeps/arch_summary.json", "results/evidence/40_sweepA_summary.txt"]),
            "sweepB": (["Sweep B"], ["results/sweeps/phys_frontier.json", "results/evidence/40_sweepB_frontier.txt"]),
            "repro": (["Repeatability"], ["results/repro_report.json"]),
            "recipes": (["Make recipes"], ["results/make_recipes.json"])}
    h = ["<div class='tw'><table class='big'><thead><tr><th>Check</th><th>At the start of Part 2</th><th>Now</th><th>Detail (computed)</th><th>Evidence</th></tr></thead><tbody>"]
    missing_ev = 0
    for b in before.get("rows", []):
        pfx, evf = spec.get(b["id"], ([b["check"]], []))
        rs = pick(pfx)
        if not rs:
            now, det = "PENDING", "no matching row"
        else:
            order = ["FAIL", "BLOCKED", "INCOMPLETE", "PARTIAL", "RUNNING", "PENDING", "UNKNOWN", "DONE", "PASS"]
            now = sorted((r.state for r in rs), key=lambda x: order.index(x) if x in order else 3)[0]
            det = "; ".join("%s: %s" % (r.label.replace("Task 1: ", "").replace("Task 2: ", ""), r.state) for r in rs) if len(rs) > 1 else rs[0].detail
        has_ev = [f for f in evf if os.path.exists(L.p(f))]
        flag = ""
        if now == "PASS" and not has_ev:
            flag = " <b class='badt'>(PASS without an evidence file on disk)</b>"
            missing_ev += 1
        h.append("<tr><td>%s<div class='sub'>%s</div></td><td>%s</td><td>%s</td><td>%s</td><td>%s%s</td></tr>" % (
            e(b["check"]), e(b.get("note", "")), e(b["before"]), badge(now), e(det[:600]), ev_links(L, has_ev or evf), flag))
    h.append("</tbody></table></div>")
    return "".join(h), missing_ev


def part2_stage_table(L):
    h = ["<div class='tw'><table><thead><tr><th>Stage</th><th>What</th><th>State</th><th>Detail</th><th>Evidence</th></tr></thead><tbody>"]
    for stage, what in P2_STAGES:
        st, det = stage_state(L, stage)
        j = p2json(L, stage) or {}
        h.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(stage), e(what), badge(st), e(det), ev_links(L, j.get("evidence"))))
    h.append("</tbody></table></div>")
    return "".join(h)


def runtime_line(L):
    b = L.jload("budget_part2.json") or {}
    se = b.get("start_epoch")
    if not se:
        return "Part 2 runtime: budget_part2.json missing"
    fin = None
    try:
        fin = int(L.read("results/.stages/99_part2.done").split()[0])
    except Exception:
        pass
    el = (fin or time.time()) - se
    return "%s: %dh %02dm, from %s to %s, budget %sh (Part 1's total runtime stays as recorded in its own section)" % (
        "Part 2 runtime" if fin else "Part 2 elapsed so far (not finished)", int(el // 3600), int(el % 3600 // 60), b.get("start", "?"),
        time.strftime("%H:%M", time.localtime(fin)) if fin else "now", b.get("total_budget_h", "?"))


def _git(L, *a):
    try:
        r = subprocess.run(["git", "-C", L.lab] + list(a), capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def what_changed(L):
    base, head = "main", "part2-green"
    if _git(L, "rev-parse", "--verify", head) is None:
        head = "HEAD"
    ns = _git(L, "diff", "--numstat", "%s..%s" % (base, head))
    if ns is None:
        return "<p class='sub'>git diff %s..%s is not available in this checkout (no <code>main</code> branch); see docs/part2_changes.json.</p>" % (e(base), e(head))
    ch = L.jload("docs/part2_changes.json")
    notes = {}
    if isinstance(ch, list):
        for ent in ch:
            for f in ent.get("files") or []:
                notes.setdefault(f, []).append("%s/%s: %s" % (ent.get("agent", "?"), ent.get("stage", "?"), ent.get("what", "")))
    rows = []
    for ln in ns.splitlines():
        a = ln.split("\t")
        if len(a) == 3:
            rows.append(a)
    skip = re.compile(r"^(results/part1_snapshot/|demo/assets/|results/evidence/|results/t[0-9]|results/sweeps/.*\.jsonl|demo/index\.html|README\.md|demo/README\.md)")
    h = ["<p>Files changed between <code>%s</code> and <code>%s</code>: <b>%d</b> (git numstat). Descriptions come from <code>docs/part2_changes.json</code>; "
         "a file without an entry shows no description rather than a guess.</p>" % (e(base), e(head), len(rows))]
    h.append("<div class='tw'><table><thead><tr><th>file</th><th>+</th><th>-</th><th>what (one line, as recorded by the agent)</th></tr></thead><tbody>")
    shown = 0
    for add, dele, f in rows:
        if skip.match(f) and f not in notes:
            continue
        shown += 1
        if shown > 400:
            break
        h.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(f), e(add), e(dele), e(" | ".join(notes.get(f, [])) or "-")))
    h.append("</tbody></table></div>")
    gen = len(rows) - shown
    h.append("<p class='sub'>%d generated or bulk files (plots, evidence texts, result CSV/JSON, the page itself) are counted above but not listed; "
             "list them with <code>git diff --stat main..part2-green</code>.</p>" % max(gen, 0))
    if isinstance(ch, list) and ch:
        h.append("<details><summary>docs/part2_changes.json: one line per change (%d entries)</summary><ul>" % len(ch))
        for ent in ch:
            h.append("<li><b>%s</b> %s: %s</li>" % (e(str(ent.get("agent", "?"))), e(str(ent.get("stage", ""))), e(str(ent.get("what", "")))))
        h.append("</ul></details>")
    elif not isinstance(ch, list):
        h.append("<p class='sub'><span class='b dim'>PENDING</span> docs/part2_changes.json not written yet.</p>")
    return "".join(h)


def commit_exists(L, c):
    return bool(c) and _git(L, "cat-file", "-e", "%s^{commit}" % c) is not None


def kvflat(d, prefix="", depth=0, out=None):
    out = [] if out is None else out
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)) and depth < 3:
                kvflat(v, "%s%s." % (prefix, k), depth + 1, out)
            else:
                out.append(("%s%s" % (prefix, k), v))
    elif isinstance(d, list):
        for i, v in enumerate(d[:60]):
            if isinstance(v, (dict, list)):
                kvflat(v, "%s%d." % (prefix, i), depth + 1, out)
            else:
                out.append(("%s%d" % (prefix, i), v))
    return out


def recipes_block(L):
    h = ["<h3>P1.2 make recipes (generated by the recipe recorder; verbatim from results/make_recipes.md)</h3>"]
    md = L.read("results/make_recipes.md")
    h.append(md_to_html(md) if md.strip() else "<p class='sub'><span class='b dim'>PENDING</span> results/make_recipes.md not written yet.</p>")
    ma = L.jload("results/make_all_last.json")
    if isinstance(ma, dict):
        h.append("<p><b>Last <code>make all</code></b> (mode %s, exit code %s, failed stages: %s, demo built: %s). In resume mode a stage is skipped only when its inputs are unchanged; the reason is printed verbatim:</p>" % (
            e(str(ma.get("mode"))), e(str(ma.get("exit_code"))), e(", ".join(ma.get("failed_stages") or []) or "none"), e(str(ma.get("demo_built")))))
        h.append("<div class='tw'><table><thead><tr><th>stage</th><th>action</th><th>reason</th><th>exit</th><th>run time (s)</th><th>lock wait (s)</th></tr></thead><tbody>")
        for st in ma.get("stages") or []:
            h.append("<tr><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(str(st.get("stage"))), e(str(st.get("action"))), e(str(st.get("reason", ""))),
                     e(str(st.get("exit_code"))), e(str(st.get("runtime_s"))), e(str(st.get("lock_wait_s")))))
        h.append("</tbody></table></div>")
    else:
        h.append("<p class='sub'>results/make_all_last.json not written yet (the final <code>make all</code> has not run).</p>")
    return "".join(h)


def fmt_num(v):
    return "%.4g" % v if isinstance(v, (int, float)) and not isinstance(v, bool) else ("-" if v is None else str(v))


def sweep_b_accounting(L):
    """Every planned sweep B point: done / failed / cut with reason. From results/sweeps/phys_plan_status.json; if that is not written yet,
    the points on disk (phys.jsonl) are listed with a PENDING note for the plan."""
    d = L.jload("results/sweeps/phys_plan_status.json")
    h = ["<h3>Sweep B: every planned point accounted for</h3>"]
    pts = (d or {}).get("points") if isinstance(d, dict) else None
    if pts:
        cnt = {}
        for r in pts:
            cnt[r.get("state")] = cnt.get(r.get("state"), 0) + 1
        h.append("<p>Part 2 refinement plan (results/sweeps/phys_plan_status.json): %s.</p>" % e(", ".join("%s %s" % (v, k) for k, v in sorted(cnt.items()))))
        h.append("<div class='tw'><table><thead><tr><th>design</th><th>clock (ns)</th><th>utilization (%)</th><th>state</th><th>setup WNS (ns)</th><th>reason</th></tr></thead><tbody>")
        for r in pts:
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(str(r.get("design"))), e(str(r.get("clock_period_ns"))),
                     e(str(r.get("core_utilization"))), e(str(r.get("state"))), e(fmt_num(r.get("wns_setup_ns"))), e(str(r.get("reason") or ""))))
        h.append("</tbody></table></div>")
        return "".join(h)
    h.append("<p class='sub'><span class='b dim'>PENDING</span> results/sweeps/phys_plan_status.json (the per-point plan accounting) is not written yet; the points that exist on disk are listed from results/sweeps/phys.jsonl.</p>")
    rows = []
    try:
        for ln in open(L.p("results/sweeps/phys.jsonl"), encoding="utf-8"):
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    except (OSError, ValueError):
        rows = []
    so = sorted((r for r in rows if r.get("design") == "systolic_os"), key=lambda r: (r.get("core_utilization", 0), -float(r.get("clock_period_ns", 0))))
    if so:
        h.append("<p>systolic_os points on disk (nangate45): the 30 %% utilization frontier is bracketed by the closest failing and closing periods below; setup WNS &gt;= 0 means the clock closes.</p>"
                 "<table><thead><tr><th>clock (ns)</th><th>utilization (%)</th><th>status</th><th>setup WNS (ns)</th><th>closes</th></tr></thead><tbody>")
        for r in so:
            w = r.get("wns_setup_ns")
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(str(r.get("clock_period_ns"))), e(str(r.get("core_utilization"))), e(str(r.get("status"))),
                     e(fmt_num(w)), "yes" if isinstance(w, (int, float)) and w >= 0 else "no"))
        h.append("</tbody></table>")
    fails = [r for r in rows if r.get("status") not in ("ok", None)]
    for r in fails:
        h.append("<p>Point not completed: %s %s ns u%s status %s (rc %s).</p>" % (e(str(r.get("design"))), e(str(r.get("clock_period_ns"))), e(str(r.get("core_utilization"))), e(str(r.get("status"))), e(str(r.get("rc")))))
    return "".join(h)


def _ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def _spearman(x, y):
    if len(x) < 3:
        return None
    a, b = _ranks(x), _ranks(y)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    den = (sum((p - ma) ** 2 for p in a) * sum((q - mb) ** 2 for q in b)) ** 0.5
    return None if den == 0 else num / den


def calc_rhos(L):
    """Criterion B per dataflow from the saved CALC-mode per-layer data: -> {df: rho or None}."""
    out = {}
    for df in ("ws", "os", "is"):
        for base in ("results/t3", "results/t3.partial"):
            r = L.jload("%s/roofline2/rl2_calc_%s.json" % (base, df))
            ls = (r or {}).get("layers") or []
            if ls:
                out[df] = _spearman([x["ai"] for x in ls], [x["required_bw_words_per_cycle"] for x in ls])
                break
    return out


def t3_roofline2_block(L, t3s):
    """Task 3 re-specified roofline check (stage 31_roofline_fix): pre-registration, amendment, what has run and what has not.
    Cell status comes from the summary when it has one, else from the job files on disk (results/t3.partial or results/t3)."""
    crit = L.jload("model/t3_roofline2_criteria.json")
    if not isinstance(crit, dict):
        return ""
    h = ["<h4>Roofline check re-specified in Part 2 (stage 31_roofline_fix)</h4>"]
    h.append("<p>The Part 2 hypothesis was that SCALE-Sim's default bandwidth mode only calculates the bandwidth a layer needs and therefore reports no stalls. "
             "<b>That was wrong in its mechanism:</b> the bundled google.cfg already uses USER bandwidth, and its stalls are all zero because the bandwidth is generous for that workload "
             "(results/evidence/31_original_stalls.txt). A check that correlates stalls with intensity therefore needs a configuration in which stalls actually occur. "
             "Thresholds were fixed before any new run in <code>model/t3_roofline2_criteria.json</code> (the commit order is the evidence). Criterion B (CALC mode: arithmetic intensity versus the DRAM bandwidth SCALE-Sim says each layer requires, Spearman rho &lt;= -0.6) "
             "does not depend on stalls. Criterion A (stalls at a fixed user bandwidth: rho(intensity, stall fraction) &lt;= -0.6 at both levels, plus stall cycles non-increasing as bandwidth rises) "
             "uses B = 64 and 256 words per cycle on a 128x128 array over all 21 ResNet-18 layers.</p>")
    h.append("<p>Amendment P2-A2 (cost only, written before any criterion-A result existed): the registered low level (B = 16) is dropped and both remaining levels are required (stricter than 2 of 3), because the registered design needs at least 4.5 h of the single-job lock per pass "
             "(model/t3_roofline2_amendment_A2_rule.md, Decisions P2-A1, P2-A2-rule and P2-7 in COORDINATION.md). A row is PASS only when every pre-registered criterion has been evaluated and passes.</p>")
    roof = ((t3s or {}).get("roofline") if isinstance(t3s, dict) and isinstance((t3s or {}).get("roofline"), dict) and "cell_status" in t3s["roofline"] else t3s) if isinstance(t3s, dict) else None
    cs = (roof or {}).get("cell_status") if isinstance(roof, dict) else None
    per = (roof or {}).get("per_dataflow") if isinstance(roof, dict) else None
    base = None
    for cand in ("results/t3", "results/t3.partial"):
        if os.path.isdir(L.p(cand + "/roofline2")):
            if base is None or (cs is None and cand.endswith("partial")):
                base = cand
    h.append("<div class='tw'><table><thead><tr><th>dataflow</th><th>criterion B: CALC run</th><th>rho(intensity, required bandwidth)</th><th>criterion A at B=64</th><th>criterion A at B=256</th></tr></thead><tbody>")
    for df in ("ws", "os", "is"):
        cells = []
        for job in ("rl2_calc_%s" % df, "rl2_user_%s_mid" % df, "rl2_user_%s_high" % df):
            stt = (cs or {}).get(job)
            if stt is not None and stt != "evaluated" and "_user_" in job:
                stt = "NOT EVALUATED (cost): %s" % ("blocked, the largest layer alone needs more than 481 s, over the lock-hold rule (results/evidence/31_a_probe.txt)" if stt == "blocked" else "not run, cost")
            if stt is None:
                if base and os.path.exists(L.p("%s/.jobs/%s.done" % (base, job))):
                    stt = "evaluated"
                elif base and os.path.isdir(L.p("%s/roofline2/%s/layers" % (base, job))):
                    n = len(glob.glob(L.p("%s/roofline2/%s/layers/*" % (base, job))))
                    stt = "in progress (%d of 21 layers done)" % n
                else:
                    stt = "not run yet"
            cells.append(stt)
        rho = None
        d = (per or {}).get(df) or {}
        rho = d.get("calc_rho_ai_vs_required_bw")
        if rho is None and base and os.path.exists(L.p("%s/roofline2/rl2_calc_%s.json" % (base, df))):
            r = L.jload("%s/roofline2/rl2_calc_%s.json" % (base, df))
            ls = (r or {}).get("layers") or []
            rho = _spearman([x["ai"] for x in ls], [x["required_bw_words_per_cycle"] for x in ls]) if ls else None
        ua = []
        for lv in ("mid", "high"):
            u = ((d.get("user") or {}).get(lv)) or {}
            if u.get("rho") is not None:
                ua.append("rho %.2f, %s layers with stalls: %s" % (u["rho"], u.get("n_layers_with_stalls"), "satisfies" if u.get("satisfies") else "does not satisfy"))
            else:
                ua.append(None)
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (df, e(cells[0]),
                 ("%.3f (threshold &lt;= -0.6: %s)" % (rho, "pass" if rho <= -0.6 else "FAIL")) if rho is not None else "-", e(ua[0] or cells[1]), e(ua[1] or cells[2])))
    h.append("</tbody></table></div>")
    if cs is None:
        h.append("<p class='sub'>results/t3_summary.json has not been rewritten by the Part 2 Task 3 stage yet; the table above is read from the job files on disk, and the per-cell correlation for criterion B is recomputed here from the saved per-layer data with the same rank-correlation definition.</p>")
    return "".join(h)


def how_tested(L):
    files = sorted(glob.glob(L.p("results/p2_*.json")))
    h = [recipes_block(L), sweep_b_accounting(L)]
    if not files:
        h.append("<p class='sub'><span class='b dim'>PENDING</span> no <code>results/p2_&lt;stage&gt;.json</code> files yet; each Part 2 stage writes one (schema in COORDINATION.md, Interfaces (Part 2)).</p>")
    for f in files:
        j = L.jload(os.path.relpath(f, L.lab)) or {}
        stage = j.get("stage") or os.path.basename(f)[3:-5]
        st, det = stage_state(L, stage)
        h.append("<h3><code>%s</code> %s</h3><table class='kv'><tbody>" % (e(stage), badge(st)))
        h.append("<tr><th>oracle (what is right)</th><td>%s</td></tr>" % e(str(j.get("oracle", "not stated"))))
        h.append("<tr><th>commands</th><td>%s</td></tr>" % ("<br>".join("<code>%s</code>" % e(str(c)) for c in j.get("commands") or []) or "not stated"))
        h.append("<tr><th>seeds</th><td>%s</td></tr><tr><th>evidence</th><td>%s</td></tr></tbody></table>" % (e(str(j.get("seeds", "not stated"))), ev_links(L, j.get("evidence"))))
        crit = j.get("criteria") or []
        if crit:
            h.append("<div class='tw'><table><thead><tr><th>criterion</th><th>threshold</th><th>written before the run (commit)</th><th>measured</th><th>result</th></tr></thead><tbody>")
            for c in crit:
                cid = str(c.get("written_before_run", ""))
                known = commit_exists(L, cid)
                h.append("<tr><td>%s</td><td>%s</td><td><code>%s</code>%s</td><td>%s</td><td class='%s'>%s</td></tr>" % (
                    e(str(c.get("name", ""))), e(str(c.get("threshold", ""))), e(cid[:12]), "" if known else " <b class='badt'>(commit not found)</b>",
                    e(str(c.get("measured", ""))), "okt" if c.get("pass") else "badt", "pass" if c.get("pass") else "FAIL"))
            h.append("</tbody></table></div>")
        sup = sup_items(j)
        if sup:
            h.append("<p><b>Superseded criteria (kept, not hidden)</b></p><div class='tw'><table><thead><tr><th>criterion</th><th>threshold</th><th>measured</th><th>result</th><th>why superseded</th></tr></thead><tbody>")
            for c in sup:
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(str(c.get("name", ""))), e(str(c.get("threshold", ""))), e(str(c.get("measured", ""))),
                                                                                          "pass" if c.get("pass") else "FAIL", e(str(c.get("reason", "")))))
            h.append("</tbody></table></div>")
    return "".join(h)


def sup_items(j):
    """Normalise a 'superseded' field (list of dicts, dict name -> dict, or anything else) to a list of dicts with a name."""
    v = (j or {}).get("superseded") if isinstance(j, dict) else None
    out = []
    if isinstance(v, dict):
        for k, c in v.items():
            out.append(dict(c, name=k) if isinstance(c, dict) else {"name": k, "reason": str(c)})
    elif isinstance(v, list):
        for c in v:
            out.append(c if isinstance(c, dict) else {"name": str(c)})
    return out


def decisions(L):
    t = L.read("COORDINATION.md")
    m = re.search(r"^## Decisions \(Part 2\)\s*\n(.*?)(?=^## )", t, re.M | re.S)
    rows = []
    if m:
        for ln in m.group(1).splitlines():
            if ln.startswith("| P2-"):
                c = [x.strip() for x in ln.strip().strip("|").split(" | ")]
                if len(c) == 4:   # rows without a time cell
                    c = [c[0], "-"] + c[1:]
                if len(c) >= 5:
                    c = c[:4] + [" | ".join(c[4:])]
                    rows.append(c)
    h = ["<p>Full text and evidence: <a href=\"../COORDINATION.md\"><code>COORDINATION.md</code></a>, section &quot;Decisions (Part 2)&quot;.</p>"]
    if rows:
        h.append("<div class='tw'><table><thead><tr><th>#</th><th>time</th><th>agent</th><th>decision</th><th>evidence / reasoning</th></tr></thead><tbody>")
        for c in rows:
            h.append("<tr>%s</tr>" % "".join("<td>%s</td>" % e(x[:1500]) for x in c[:5]))
        h.append("</tbody></table></div>")
    sup = []
    for f in sorted(glob.glob(L.p("results/p2_*.json"))):
        j = L.jload(os.path.relpath(f, L.lab)) or {}
        for c in sup_items(j):
            sup.append((j.get("stage"), c))
    for nm in ("t1", "t2", "t3"):
        j = L.jload("results/%s_summary.json" % nm) or {}
        for c in sup_items(j):
            sup.append((nm, c))
    h.append("<p><b>Superseded criteria across all summaries:</b> %s</p>" % (", ".join("<code>%s</code> (%s)" % (e(str(c.get("name"))), e(str(s))) for s, c in sup) if sup else "none recorded"))
    return "".join(h)


def caveats(L, rows):
    h = ["<ul>"]
    t = L.read("COORDINATION.md")
    m = re.search(r"^## Needs owner \(Part 2\)\s*\n(.*?)(?=^## )", t, re.M | re.S)
    if m and m.group(1).strip() and "(none" not in m.group(1)[:30]:
        h.append("<li><b>Needs the owner (COORDINATION.md):</b><pre>%s</pre></li>" % e(m.group(1).strip()[:3000]))
    for stage, what in P2_STAGES:
        st, body = marker(L, stage)
        if st in ("blocked", "failed"):
            h.append("<li>%s <code>%s</code> (%s): <pre>%s</pre></li>" % (badge(st.upper()), e(stage), e(what), e(body[:2500])))
    for r in rows:
        if r.state in ("FAIL", "BLOCKED"):
            h.append("<li>%s <b>%s</b>: %s</li>" % (badge(r.state), e(r.label), e(r.detail[:500])))
        elif r.state in ("PENDING", "RUNNING", "UNKNOWN"):
            h.append("<li>%s <b>%s</b> is not finished: %s</li>" % (badge(r.state), e(r.label), e(r.detail[:300])))
    h.append("</ul><p class='sub'>Each BLOCKED or failed marker carries the exact command for the owner in its text above.</p>")
    return "".join(h)


NOT_GREEN = [
    ("Task 1: INT8", "Part 2 changed inputs of the Task 1 recipe (the routed-netlist runner and shared scripts) after the recorded result, so the page refuses to show the old PASS as current.",
     "The real `make t1` recipe (infra) re-runs the stage and rewrites results/t1_summary.json; the row turns PASS or FAIL from that file. Nothing to do by hand."),
    ("Task 1: formal", "Same as the Task 1 row.", "Same as the Task 1 row (`make t1`)."),
    ("Task 1: RTL = netlist", "Same as the Task 1 row.", "Same as the Task 1 row (`make t1`)."),
    ("Task 1: RTL = ROUTED", "Complete when the file says so: every partition proved, EQY PASS, all negative controls rejected.", "Nothing further; re-checked by `make t1-routed`."),
    ("Task 1: routed gate-level", "PASS on Icarus only: the task also asks for Verilator if the cell models parse (they do). The Verilator model build of the routed netlist did not finish within the 10-minute lock hold, so no Verilator gate-level result exists; every check that needs one is listed as NOT EVALUATED, neither pass nor fail. This is partial against the task, not a pass of the full item.",
     "Build the Verilator gate-level model in a bounded way (a smaller or pre-built model, or a longer hold approved by the owner), then `T1R_STEPS=gls scripts/t1_routed.sh`. Until then the page keeps saying Icarus only."),
    ("Task 3", "FAIL on the pre-registered criterion B: in CALC mode the intensity versus required-bandwidth rank correlation does not reach -0.6 for ws, os or is (values in the row and section 6). Criterion A (stalls at a fixed user bandwidth) is NOT EVALUATED, neither pass nor fail: a probe showed the largest ResNet-18 layer alone needs more than 481 s, over the 10-minute lock-hold rule, and SCALE-Sim cannot checkpoint inside a layer. The original hypothesis (default bandwidth mode hides stalls) was wrong: the bundled config uses user bandwidth and its stalls are all zero.",
     "Thresholds are final and were not retuned. To finish criterion A the owner can approve long holds (several hours of exclusive machine time) or a smaller layer set registered as a new amendment before running; criterion B's failure needs a diagnosis of the analytic intensity (see docs/t3_roofline_explained.md)."),
    ("Sweep A", "Accounted for, not complete: every planned point is done, errored, or cut with a stated reason, but the cut points were not run; points never reached before the sweep deadline (cut because sweeps run at low priority behind stage jobs in the one-job-at-a-time queue; cheapest points ran first).",
     "Nothing is hidden: the cut points are listed in the sweep section with the reason. A later `make sweeps` with a later deadline would run them."),
    ("Sweep B", "Accounted for, not complete: every planned point is done, failed, or cut at the gate with its state listed in section 12; the cut points were not run. The systolic_os frontier at 30 % utilization is bracketed by a failing and a closing period (see the row).",
     "Running the cut points (`python3 sweeps/phys_sweep.py --plan part2`, low priority) would extend the plan; nothing is claimed for them now."),
    ("Repeatability", "The comparison says FAIL: Task 1 and Task 2 are identical, but three Task 3 checks differ (bookkeeping, provenance, and one 1-ulp float difference from a different Python version). Diagnosis (results/evidence/51_repro_t3_diagnosis.txt, arch): no SCALE-Sim report differs; the differences are scheduling bookkeeping files, a summary file regenerated on another Python version (1-ulp float differences) plus the probe state, and provenance (Task 3 inputs were committed while the rerun was running). The user-bandwidth Task 3 runs are not rerun (cost) and are reported as such, never as identical. The only excluded file class is the per-layer run-time measurements (timing.timing).",
     "Right after the gate a clean Task 3 first pass and rerun on frozen inputs is run (Decision P2-10): `REPRO_PART=t3 scripts/repro.sh` keeps the Task 1 rerun if its inputs are verified unchanged, else the full `scripts/repro.sh` runs. Until the new verdict exists this row stays FAIL."),
    ("P2.1", "Open caveats only: zero-delay simulation has no glitch power (simulated switching power is a lower bound) and the workloads are small synthetic ones.", "Optional: glitch-aware power needs a timing-annotated (SDF) simulation; not planned."),
    ("P2.2", "Verification is bit-exact on both simulators; the stage fails on the single check `lint_clean` (one comment line over the 100-character limit). The PPA table is from one flow run per design at a clock the bf16 MAC does not meet.", "`git cherry-pick e21fd3b` (from branch p2/rtl; shortens one comment line, no logic change), then `scripts/t61_run.sh 10000 results && python3 scripts/p2_61_finish.py` (about 4 minutes of lock). Decision P2-12 deferred it because rtl/ is an input of the t1 stages. Search the bf16 frontier clock before quoting its power."),
    ("P2.3", "The sky130hd search is coarse and runs in the low-priority queue with a hard per-point timeout; until a failing point exists below a closing point the result is an upper bound, not a frontier.", "Let the remaining planned points finish (`python3 scripts/p2_pdk_compare.py run --go`, then `summary`)."),
    ("P2.4", "Passes its registered criteria; CACTI is analytical, 45 nm only matches nangate45 in feature size, no SRAM macro exists to check absolute numbers.", "Compare against a real SRAM macro (e.g. OpenRAM or a vendor compiler) in a later round."),
    ("Make recipes", "Each recipe is executed for real by the recorder in queue order. `make t3` exits non-zero because the Task 3 stage verdict is FAIL (criterion B; criterion A not evaluated), so `make all` exits non-zero and lists t3 as the failed stage; the fail-soft test of that behaviour ran in the reduced form its note describes. The row reads RUNNING while the real `make all` is still running.",
     "No fix for the exit code is intended: it is the honest result of the Task 3 verdict. It changes only if Task 3's criteria are re-registered or criterion A is evaluated and criterion B passes."),
]


def not_green_items(L, rows):
    out = []
    for r in rows:
        if r.state in ("PASS", "DONE") and not r.label.startswith("Sweep") and True:
            continue
        for pfx, diag, act in NOT_GREEN:
            if r.label.startswith(pfx):
                out.append((r, diag, act))
                break
    return out


def not_green_html(L, rows):
    items = not_green_items(L, rows)
    h = ["<h3>What is not green yet, why, and the next action</h3><p class='sub'>The state is computed from the files; the diagnosis and next action are written by the demo agent from the decisions in COORDINATION.md.</p>"]
    if not items:
        return "".join(h) + "<p>Every row is PASS or DONE.</p>"
    h.append("<div class='tw'><table><thead><tr><th>Row</th><th>State now</th><th>Diagnosis</th><th>Next action</th></tr></thead><tbody>")
    for r, diag, act in items:
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(r.label), badge(r.state), e(diag), e(act)))
    h.append("</tbody></table></div>")
    return "".join(h)


def not_green_md(L, rows):
    items = not_green_items(L, rows)
    out = ["### What is not green yet, why, and the next action\n", "State is computed from the files; diagnosis and next action are explanations written from the decisions in COORDINATION.md.\n"]
    if not items:
        return "\n".join(out + ["Every row is PASS or DONE.\n"])
    out += ["| Row | State now | Diagnosis | Next action |", "|---|---|---|---|"]
    for r, diag, act in items:
        out.append("| %s | **%s** | %s | %s |" % (r.label, r.state, diag, act))
    return "\n".join(out) + "\n"


def md_to_html(md):
    out, para, intable = [], [], False

    def inline(s):
        s = e(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para)))
            para.clear()
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            out.append("<div class='tw'><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>" % (
                "".join("<th>%s</th>" % inline(c) for c in rows[0]), "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows[1:])))
            continue
        if ln.startswith("#"):
            flush()
            out.append("<h3>%s</h3>" % inline(ln.lstrip("# ")))
        elif ln.startswith("- "):
            flush()
            out.append("<ul><li>%s</li></ul>" % inline(ln[2:]))
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()
    return "".join(out)


def where_next(L):
    md = L.read("docs/next.md")
    if not md:
        return "<p class='sub'><span class='b dim'>PENDING</span> docs/next.md not written yet.</p>"
    md = re.sub(r"^# .*\n", "", md, count=1)
    return md_to_html(md)


def md_section(md, heading):
    """Body of the '## heading' section of a markdown text (up to the next '## '), or ''."""
    m = re.search(r"^## %s[^\n]*\n(.*?)(?=^## |\Z)" % re.escape(heading), md or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def _mw(x):
    return "%.2f" % (x * 1000.0) if isinstance(x, (int, float)) else "-"


def phase2_state(L, stage):
    """(state, detail, evidence_file) for P2.1-P2.4 rows, from the p2 JSON and markers only."""
    j = p2json(L, stage) or {}
    st, body = marker(L, stage)
    crit = [c for c in (j.get("criteria") or []) if isinstance(c, dict)]
    ev = [f for f in (j.get("evidence") or []) if os.path.exists(L.p(f))]
    evf = ev[0] if ev else None
    npass = sum(1 for c in crit if c.get("pass") is True)
    nfail = [c.get("name") for c in crit if c.get("pass") is False]
    nnull = sum(1 for c in crit if c.get("pass") is None)
    nev = sum(1 for c in crit if c.get("pass") is not None)
    cnt = ("%d of %d evaluated criteria pass" % (npass, nev) + ("; %d reported only or not evaluated yet (neither pass nor fail)" % nnull if nnull else "")) if crit else "no criteria file"
    if stage == "60_power_activity":
        base = ("%s. %s Zero-delay gate-level simulation has no glitch power, so the simulated switching power is a lower bound. The vectorless figure is OpenROAD's default-activity assumption "
                "(0.1 transitions per cycle on every input), not a measurement (docs/power_explained.md)." % (cnt, j.get("finding", "")))
    elif stage == "63_sram_cacti":
        base = ("%s. CACTI is an analytical model: 45 nm matches nangate45 in feature size only and no SRAM macro exists in any ORFS run, so absolute numbers are unchecked; the energy model is order-of-magnitude "
                "(SRAM read energy only, DRAM and MAC energy not modelled); the non-monotone cycle time is an unregistered observation (docs/sram_explained.md)" % cnt)
    elif stage == "61_pe_bf16":
        sm = L.jload("results/p2_61_pe_bf16_summary.json") or {}
        v = (sm.get("values") or {}).get("verilator") or {}
        base = ("%s; failing checks: %s; bit-exact checks over %s cases: Verilator %s, Icarus %s. INT8 vs bf16 MAC PPA table in section 16: "
                "bf16 power is at a clock it does not meet and fmax comes from one run per design, not a frontier" % (
                    cnt, ", ".join(str(x) for x in [k for k, vv in (sm.get("checks") or {}).items() if vv is False]) or "none", v.get("cases_total", "?"),
                    (sm.get("checks") or {}).get("bit_exact_verilator"), (sm.get("checks") or {}).get("bit_exact_icarus")))
        if isinstance(sm.get("checks"), dict):
            nfail = [k for k, vv in sm["checks"].items() if vv is False]
    else:
        base = cnt
    if stage == "62_pdk_compare":
        pts = pdk_points(L)
        lab = pdk_label(pts)
        base = "%d sky130hd points recorded (planned 8.0 / 5.5 / 4.0 ns plus one refinement, Decision P2-11a); result label by the file's rule: %s; %s. Clock ratio is an upper bound on the slowdown; power is at clocks 5.4x apart, so energy per cycle is shown too" % (len(pts), lab, cnt)
        if j.get("pass") is True and st == "done":
            return "PASS", base, evf
        if st == "failed" or j.get("pass") is False:
            return "FAIL", base, evf
        return ("RUNNING" if (pts or st == "running") else "PENDING"), base, evf
    if j.get("pass") is True and st == "done":
        return "PASS", base, evf
    if j.get("pass") is False or st == "failed":
        return "FAIL", base + ("; failing: %s" % ", ".join(map(str, nfail)) if nfail else ""), evf
    if st == "running":
        return "RUNNING", base, evf
    if j.get("pass") is True:
        return "UNKNOWN", base + "; summary says pass but no .done marker", evf
    return "PENDING", base, evf


def pdk_points(L):
    out = []
    try:
        for ln in open(L.p("results/pdk_compare/sky130hd_points.jsonl"), encoding="utf-8"):
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def pdk_label(pts):
    ok = [p for p in pts if p.get("status", "ok") == "ok" and isinstance(p.get("wns_setup_ns"), (int, float))]
    closing = [p for p in ok if p["wns_setup_ns"] >= 0]
    failing = [p for p in ok if p["wns_setup_ns"] < 0]
    if not closing:
        return "no closing point yet (no frontier claimed)"
    fc = min(p["clock_period_ns"] for p in closing)
    below = [p for p in failing if p["clock_period_ns"] < fc]
    if below:
        return "coarse frontier bracket: fails at %s ns, closes at %s ns" % (max(p["clock_period_ns"] for p in below), fc)
    return "UPPER BOUND on the closure period: closes at %s ns, no failing point below it (not a frontier)" % fc


def phase2_html(L):
    h = ['<h2 id="p2res">16. Phase 2 results</h2><p class="sub">Each block is generated from the stage result file named in it; a stage that has not produced its file is shown as PENDING. Criteria and their thresholds are listed with the stage in section 12.</p>']
    # ---- P2.1
    pa = L.jload("results/power_activity.json")
    st, det, evf = phase2_state(L, "60_power_activity")
    h.append("<h3>P2.1 Activity-based power (stage 60_power_activity) %s</h3>" % badge(st))
    if isinstance(pa, dict):
        h.append("<p>%s</p>" % e(det))
        h.append("<div class='tw'><table><thead><tr><th>workload</th><th>total (mW)</th><th>dynamic (mW)</th><th>leakage (mW)</th><th>fraction of ORFS default vectorless</th></tr></thead><tbody>")
        h.append("<tr><td>ORFS default vectorless estimate</td><td>%s</td><td>-</td><td>-</td><td>1</td></tr>" % _mw(pa.get("orfs_vectorless_total_w")))
        for wl, w in ((pa.get("raw") or {}).get("workloads") or {}).items():
            r = (w or {}).get("result") or {}
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(wl), _mw(r.get("total_w")), _mw(r.get("dynamic_w")), _mw(r.get("leakage_w")),
                     e("%.3f" % (pa.get("ratios_to_orfs_vectorless") or {}).get(wl)) if isinstance((pa.get("ratios_to_orfs_vectorless") or {}).get(wl), (int, float)) else "-"))
        h.append("</tbody></table></div>")
        if os.path.exists(L.p("demo/assets/power_activity.png")):
            h.append('<p><img src="assets/power_activity.png" alt="power per workload versus the default estimate" style="max-width:100%"></p>')
        md = L.read("docs/power_explained.md")
        for hd in ("Caveats", "Why the default estimate is so much higher"):
            sec = md_section(md, hd)
            if sec:
                h.append("<h4>%s</h4>%s" % (e(hd), md_to_html(sec)))
        h.append("<p>Full explanation: <a href='../docs/power_explained.md'><code>docs/power_explained.md</code></a>. Evidence: %s</p>" % ev_links(L, (p2json(L, "60_power_activity") or {}).get("evidence")))
    else:
        h.append("<p class='sub'><span class='b dim'>PENDING</span> results/power_activity.json not written yet.</p>")
    # ---- P2.2
    sm = L.jload("results/p2_61_pe_bf16_summary.json")
    st, det, evf = phase2_state(L, "61_pe_bf16")
    h.append("<h3>P2.2 bf16 processing element (stage 61_pe_bf16) %s</h3>" % badge(st))
    j = p2json(L, "61_pe_bf16") or {}
    if isinstance(sm, dict):
        h.append("<p>%s</p>" % e(det))
        ck = sm.get("checks") or {}
        h.append("<div class='tw'><table><thead><tr><th>check</th><th>result</th></tr></thead><tbody>%s</tbody></table></div>" % "".join(
            "<tr><td><code>%s</code></td><td class='%s'>%s</td></tr>" % (e(k), "okt" if v else "badt", "pass" if v else "FAIL") for k, v in ck.items()))
        pp = (j.get("reported_not_gating") or {}).get("ppa") or {}
        if pp.get("mac_int8") and pp.get("mac_bf16"):
            a, b = pp["mac_int8"], pp["mac_bf16"]
            rows = [("clock period (ns)", "clock_period_ns"), ("setup WNS (ns)", "wns_setup_ns"), ("timing met at that clock", "timing_met_at_clock"), ("area (um2)", "area_um2"), ("std cells", "stdcell_count"),
                    ("total power (W, default vectorless estimate)", "power_total_w"), ("fmax reported by the flow (MHz)", "fmax_reported_by_flow_mhz"), ("max clock estimate 1/(period - WNS) (MHz)", "max_clock_estimate_mhz"), ("DRC errors", "drc_errors")]
            h.append("<div class='tw'><table><thead><tr><th>metric (nangate45, one flow run each)</th><th>INT8 MAC</th><th>bf16 MAC</th></tr></thead><tbody>%s</tbody></table></div>" % "".join(
                "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(n), e(str(a.get(k))), e(str(b.get(k)))) for n, k in rows))
            rat = (j.get("reported_not_gating") or {}).get("ratio_bf16_over_int8") or {}
            h.append("<p>bf16 / INT8: %s. <b>Caveats:</b> the bf16 power is measured at 1.25 ns, a clock the bf16 MAC does not meet (WNS %s ns), so it is not a power at its own operating point; fmax comes from a single run per design, not from a timing-closure frontier search. "
                     "</p>" % (e(", ".join("%s %s" % (k, v) for k, v in rat.items())), e(str(b.get("wns_setup_ns")))))
        d = sm.get("design") or {}
        if d:
            h.append("<p><b>Design choices (documented):</b> rounding: %s; subnormals: %s.</p>" % (e(str(d.get("rounding"))), e(str(d.get("subnormals")))))
        na = j.get("next_action")
        if isinstance(na, dict):
            h.append("<p><b>Why it stays FAIL and what to do (%s; the result file's next_action):</b> %s. Apply: <code>%s</code>; re-verify: <code>%s</code>; cost: %s</p>" % (
                e(str(na.get("decision"))), e(str(na.get("why_failed"))), e(str(na.get("apply"))), e(str(na.get("then_reverify"))), e(str(na.get("cost")))))
            h.append("<p>The fix is a comment-only change on branch %s (commit %s): %s.</p>" % (e(str(na.get("branch"))), e(str(na.get("commit"))), e(str(na.get("what")))))
        h.append("<p>Full explanation: <a href='../docs/pe_bf16_explained.md'><code>docs/pe_bf16_explained.md</code></a>.</p>")
        h.append("<p>Why floating point costs area: a bf16 MAC adds an exponent adder, a mantissa multiplier plus a 24-bit alignment shifter, a wide adder, leading-zero detection, a normalisation shifter and rounding on top of the integer datapath that an INT8 MAC needs; the table above shows the measured cost. Evidence: %s</p>" % ev_links(L, j.get("evidence")))
    else:
        h.append("<p class='sub'><span class='b dim'>PENDING</span> results/p2_61_pe_bf16_summary.json not written yet.</p>")
    # ---- P2.3
    st, det, evf = phase2_state(L, "62_pdk_compare")
    pj = p2json(L, "62_pdk_compare") or {}
    h.append("<h3>P2.3 systolic_os on sky130hd (stage 62_pdk_compare) %s</h3><p>%s</p>" % (badge(st), e(det)))
    pts = pdk_points(L)
    if pts:
        h.append("<div class='tw'><table><thead><tr><th>sky130hd clock (ns)</th><th>utilization (%)</th><th>status</th><th>setup WNS (ns)</th><th>area (um2)</th><th>total power (W)</th><th>DRC</th></tr></thead><tbody>")
        for p in sorted(pts, key=lambda q: -float(q.get("clock_period_ns", 0))):
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % tuple(e(str(p.get(k, "-"))) for k in ("clock_period_ns", "core_utilization", "status", "wns_setup_ns", "area_um2", "power_total_w", "drc_errors")))
        h.append("</tbody></table></div>")
    if isinstance(pj.get("plan_change"), dict):
        pc = pj["plan_change"]
        h.append("<p><b>Plan change (%s, %s):</b> %s</p>" % (e(str(pc.get("decision"))), e(str(pc.get("when"))), e(str(pc.get("what")))))
    pc2 = L.jload("results/pdk_compare/pdk_compare.json") or {}
    cmpd = pc2.get("comparison_at_each_pdks_fastest_closing_period")
    if isinstance(cmpd, dict):
        h.append("<div class='tw'><table><thead><tr><th>metric</th><th>nangate45 (45 nm, 1.25 ns, sweep B)</th><th>sky130hd (130 nm, fastest closing tested point)</th><th>sky130hd / nangate45</th></tr></thead><tbody>")
        for k, v in cmpd.items():
            if isinstance(v, dict):
                r_ = v.get("ratio_sky_over_nangate")
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(k), e("%.6g" % v["nangate45"]), e("%.6g" % v["sky130hd"]), e("%.4g" % r_) if isinstance(r_, (int, float)) else "-"))
        h.append("</tbody></table></div>")
        h.append("<p><b>Caveats.</b> The clock ratio (5.4x) is an upper bound on the true slowdown at the frontier: the sky130hd closing point is 6.75 ns and the failing point is 5.5 ns, so the true frontier lies in between. Total power is compared at clocks that differ by 5.4x, so energy per cycle is shown as well (power x period). "
                 "The sky130hd leakage is tiny because the Liberty file's leakage values are tiny, not because the cells are efficient. Area and cell counts are at the tested periods. 130 nm is a coarser process, so cells are larger and gates slower; the table shows the measured ratios.</p>")
    md = L.read("docs/pdk_compare_explained.md")
    sec = md_section(md, "Why sky130 is slower and larger")
    if sec:
        h.append("<h4>Why sky130 is slower and larger</h4>" + md_to_html(sec))
    if os.path.exists(L.p("demo/assets/pdk_compare.png")):
        h.append('<p><img src="assets/pdk_compare.png" alt="sky130hd versus nangate45 comparison" style="max-width:100%"></p>')
    h.append("<p>Full explanation: <a href='../docs/pdk_compare_explained.md'><code>docs/pdk_compare_explained.md</code></a>. Evidence: %s</p>" % ev_links(L, pj.get("evidence")))
    # ---- P2.4
    sc = L.jload("results/sram_cacti.json")
    em = L.jload("results/sram_energy_model.json")
    st, det, evf = phase2_state(L, "63_sram_cacti")
    h.append("<h3>P2.4 SRAM modelling with CACTI (stage 63_sram_cacti) %s</h3><p>%s</p>" % (badge(st), e(det)))
    if isinstance(sc, dict) and isinstance(sc.get("points"), dict):
        h.append("<p class='sub'>%s; settings: %s</p>" % (e(str(sc.get("model"))), e(json.dumps(sc.get("settings"), sort_keys=True))))
        h.append("<div class='tw'><table><thead><tr><th>point</th><th>size (kB)</th><th>technology (um)</th><th>area (mm2)</th><th>access (ns)</th><th>cycle (ns)</th><th>read energy (nJ)</th><th>leakage (mW)</th></tr></thead><tbody>")
        for k, v in sorted(sc["points"].items(), key=lambda kv: (kv[1].get("tech_um", 0), kv[1].get("size_kB", 0))):
            h.append("<tr><td>%s</td>%s</tr>" % (e(k), "".join("<td>%s</td>" % e(("%.4g" % v[x]) if isinstance(v.get(x), (int, float)) else str(v.get(x, "-"))) for x in ("size_kB", "tech_um", "area_mm2", "access_ns", "cycle_ns", "read_nJ", "leak_mW"))))
        h.append("</tbody></table></div>")
    if isinstance(em, dict):
        h.append("<p><b>%s</b></p><p>Workload: %s</p>" % (e(str(em.get("label"))), e(str(em.get("workload")))))
        h.append("<div class='tw'><table><thead><tr><th>configuration</th><th>cycles</th><th>SRAM read energy (uJ)</th><th>leakage energy at 1 GHz (uJ)</th><th>DRAM words moved</th></tr></thead><tbody>%s</tbody></table></div>" % "".join(
            "<tr><td>%s</td><td>%s</td><td>%.2f</td><td>%.2f</td><td>%s</td></tr>" % (e(c["config"]), c["cycles"], c["sram_energy_uJ"], c["leakage_energy_uJ_at_1GHz"], c["dram_words"]) for c in em.get("configs") or []))
        h.append("<p>Break-even DRAM energy per word that would pay for the larger SRAM: %s.</p>" % e(json.dumps(em.get("break_even"))))
    if os.path.exists(L.p("demo/assets/sram_cacti.png")):
        h.append('<p><img src="assets/sram_cacti.png" alt="CACTI SRAM area, access time and energy versus capacity" style="max-width:100%"></p>')
    sec = md_section(L.read("docs/sram_explained.md"), "Caveats")
    if sec:
        h.append("<h4>Caveats</h4>" + md_to_html(sec))
    h.append("<p>Full explanation: <a href='../docs/sram_explained.md'><code>docs/sram_explained.md</code></a>. Evidence: %s</p>" % ev_links(L, (p2json(L, "63_sram_cacti") or {}).get("evidence")))
    return "".join(h)


def part2_html(L, rows, before):
    ba, missing = render_before_after(L, rows, before)
    h = ['<h2 id="p2sum">10. Part 2 summary: before and after</h2>',
         "<p>Part 2 set out to get every check green and then extend the lab. The left column is the status table at the start of Part 2 (data in <code>coord/part2_before.json</code>); "
         "the right column is computed from the stage markers and summary files as they are now. A PASS needs its evidence file on disk.</p>", ba]
    h.append(not_green_html(L, rows))
    if missing:
        h.append("<p class='note'><b>%d PASS row(s) have no evidence file on disk</b>; treat them as unverified.</p>" % missing)
    h.append("<p>%s</p><h3>Part 2 stages</h3>%s" % (e(runtime_line(L)), part2_stage_table(L)))
    h.append('<h2 id="p2changes">11. What changed in Part 2</h2>' + what_changed(L))
    h.append('<h2 id="p2tests">12. How each new result was tested</h2>' + how_tested(L))
    h.append('<h2 id="p2dec">13. Decisions and superseded criteria</h2>' + decisions(L))
    h.append('<h2 id="p2cav">14. Remaining caveats and BLOCKED items</h2>' + caveats(L, rows))
    h.append('<h2 id="p2next">15. Where to go next</h2><p>From <a href="../docs/next.md"><code>docs/next.md</code></a> (costs are grounded in this lab\'s measurements; unverified items say so).</p>' + where_next(L))
    h.append(phase2_html(L))
    return "".join(h)


def part2_md(L, rows, before):
    out = [not_green_md(L, rows), "## Part 2: before and after\n", "| Check | At the start of Part 2 | Now |", "|---|---|---|"]
    ba = {}
    for b in before.get("rows", []):
        pfx = {"runtime": ["Container runtime"], "images": ["Lab images"], "task1": ["Task 1:"], "task2": ["Task 2:"], "task3": ["Task 3:"], "sweepA": ["Sweep A"],
               "sweepB": ["Sweep B"], "repro": ["Repeatability"], "recipes": ["Make recipes"]}.get(b["id"], [b["check"]])
        rs = [r for r in rows if any(r.label.startswith(p) for p in pfx)]
        order = ["FAIL", "BLOCKED", "INCOMPLETE", "PARTIAL", "RUNNING", "PENDING", "UNKNOWN", "DONE", "PASS"]
        now = sorted((r.state for r in rs), key=lambda x: order.index(x) if x in order else 3)[0] if rs else "PENDING"
        out.append("| %s | %s | **%s** |" % (b["check"], b["before"], now))
    out.append("\n%s\n" % runtime_line(L))
    out.append("Part 2 stage states:\n\n| Stage | State |\n|---|---|")
    for stage, what in P2_STAGES:
        out.append("| `%s` %s | %s |" % (stage, what, stage_state(L, stage)[0]))
    return "\n".join(out) + "\n"
