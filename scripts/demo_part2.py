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
BADGE = {"INCOMPLETE": "warn", "PASS": "ok", "DONE": "ok", "FAIL": "bad", "BLOCKED": "warn", "RUNNING": "run", "PENDING": "dim", "UNKNOWN": "dim"}


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
                    more = "; EQY partitions proved: %s of %s (the rest were not proved; see the diagnosis in the not-green list)" % tuple(rt["eqy_partitions_proved"])
                if key == "gls_routed_pass":
                    more = "; per simulator (0 mismatches against NumPy): Icarus %s, Verilator %s; negative control detected: %s" % (
                        ck.get("gls_icarus_zero_mismatches"), ck.get("gls_verilator_zero_mismatches"), ck.get("gls_negative_control_detected"))
            rows.append(Row(label, "PASS" if v else "FAIL", "%s = %s in t1_summary.json%s" % (key, str(v).lower(), more), "results/t1_summary.json"))
    v = find_bool(t2, "matches_published")
    mst, _ = marker(L, "21_orfs_crosscheck")
    rows.append(Row("Task 2: matches ORFS's published reference results", ("PASS" if v else "FAIL") if v is not None else {"failed": "FAIL", "blocked": "BLOCKED", "running": "RUNNING"}.get(mst, "PENDING"),
                    ("matches_published = %s in t2_summary.json" % str(v).lower()) if v is not None else "not reported yet (stage 21_orfs_crosscheck: %s)" % (mst if mst != "none" else "no marker"),
                    "results/t2_summary.json" if v is not None else None))
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
            order = ["FAIL", "BLOCKED", "INCOMPLETE", "RUNNING", "PENDING", "UNKNOWN", "DONE", "PASS"]
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
    cs = (t3s or {}).get("cell_status") if isinstance(t3s, dict) else None
    per = (t3s or {}).get("per_dataflow") if isinstance(t3s, dict) else None
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
        sup = j.get("superseded") or []
        if sup:
            h.append("<p><b>Superseded criteria (kept, not hidden)</b></p><div class='tw'><table><thead><tr><th>criterion</th><th>threshold</th><th>measured</th><th>result</th><th>why superseded</th></tr></thead><tbody>")
            for c in sup:
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(str(c.get("name", ""))), e(str(c.get("threshold", ""))), e(str(c.get("measured", ""))),
                                                                                          "pass" if c.get("pass") else "FAIL", e(str(c.get("reason", "")))))
            h.append("</tbody></table></div>")
    return "".join(h)


def decisions(L):
    t = L.read("COORDINATION.md")
    m = re.search(r"^## Decisions \(Part 2\)\s*\n(.*?)(?=^## )", t, re.M | re.S)
    rows = []
    if m:
        for ln in m.group(1).splitlines():
            if ln.startswith("| P2-"):
                c = [x.strip() for x in ln.strip().strip("|").split(" | ")]
                if len(c) >= 5:
                    rows.append(c)
    h = ["<p>Full text and evidence: <a href=\"../COORDINATION.md\"><code>COORDINATION.md</code></a>, section &quot;Decisions (Part 2)&quot;.</p>"]
    if rows:
        h.append("<div class='tw'><table><thead><tr><th>#</th><th>time</th><th>agent</th><th>decision</th><th>evidence / reasoning</th></tr></thead><tbody>")
        for c in rows:
            h.append("<tr>%s</tr>" % "".join("<td>%s</td>" % e(x[:700]) for x in c[:5]))
        h.append("</tbody></table></div>")
    sup = []
    for f in sorted(glob.glob(L.p("results/p2_*.json"))):
        j = L.jload(os.path.relpath(f, L.lab)) or {}
        for c in j.get("superseded") or []:
            sup.append((j.get("stage"), c))
    for nm in ("t1", "t2", "t3"):
        j = L.jload("results/%s_summary.json" % nm) or {}
        for c in j.get("superseded") or []:
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
    ("Task 1: RTL = ROUTED", "The routed netlist is flat, so the Part 1 split is applied by name: 16 per-PE partitions plus wrapper partitions. The partitions proved are counted in the row; the stage marker text on the page says which were not proved and why. The per-PE multiplier/accumulator partitions are the hard ones for the solver on 8 GB.",
     "The rtl agent re-runs the missing wrapper partitions (`T1R_STEPS=eqy scripts/t1_routed.sh`, under the lock). The row stays FAIL until every partition is proved; the scope is stated exactly, never widened."),
    ("Task 1: routed gate-level", "The gate-level result is per simulator: the row detail shows Icarus and Verilator separately. Icarus having 0 mismatches against NumPy and the negative control being caught are shown as true/false in the row; a false Verilator value means that step did not pass or did not complete (see the evidence text on the page).",
     "The rtl agent re-runs the Verilator gate-level step (`T1R_STEPS=gls scripts/t1_routed.sh`). The combined criterion needs both simulators and an identical CSV; a Verilator-only gap is reported as exactly that."),
    ("Task 3", "Criterion B (CALC mode) and criterion A (stalls at a fixed user bandwidth) were pre-registered; the cells that have not been evaluated keep the row open, and criterion B's measured correlations are shown in the row and in section 6. The hypothesis that the default bandwidth mode hid the stalls was wrong: the bundled config uses user bandwidth and its stalls are all zero.",
     "The arch agent makes the fixed-bandwidth jobs resumable and bounded per lock hold, then infra re-runs `make t3`. Whatever the pre-registered thresholds say is final: if criterion B or A fails the row becomes FAIL with the diagnosis, it is not retuned."),
    ("Sweep A", "A completion status: points never reached before the sweep deadline (cut because sweeps run at low priority behind stage jobs in the one-job-at-a-time queue; cheapest points ran first).",
     "`make sweeps` resumes where it stopped; each unreached point is accounted for in the sweep section of the page."),
    ("Sweep B", "A completion status. The systolic_os frontier at 30 % utilization is bracketed by a failing and a closing period (see the row); 40 and 50 % utilization points are listed with their state in section 12.",
     "`make sweeps` (or `python3 sweeps/phys_sweep.py --plan part2`) runs the remaining planned points."),
    ("Repeatability", "The Part 2 repro (Task 1 in full, Task 3 cheap set, Task 2 from the extra clean runs) is still running or has not been summarised; the user-bandwidth Task 3 runs are not rerun because of their cost and are reported as such, never as identical.",
     "`make repro`; results/repro_report.json then shows every check with its run count."),
    ("Make recipes", "Each recipe is executed for real by the recorder in queue order; the ones still running or not run yet are listed in the note on the page.",
     "`make all` (fail-soft, always builds the demo, exits non-zero naming failed stages)."),
]


def not_green_items(L, rows):
    out = []
    for r in rows:
        if r.state in ("PASS", "DONE") and not r.label.startswith("Sweep"):
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
    return "".join(h)


def part2_md(L, rows, before):
    out = [not_green_md(L, rows), "## Part 2: before and after\n", "| Check | At the start of Part 2 | Now |", "|---|---|---|"]
    ba = {}
    for b in before.get("rows", []):
        pfx = {"runtime": ["Container runtime"], "images": ["Lab images"], "task1": ["Task 1:"], "task2": ["Task 2:"], "task3": ["Task 3:"], "sweepA": ["Sweep A"],
               "sweepB": ["Sweep B"], "repro": ["Repeatability"], "recipes": ["Make recipes"]}.get(b["id"], [b["check"]])
        rs = [r for r in rows if any(r.label.startswith(p) for p in pfx)]
        order = ["FAIL", "BLOCKED", "INCOMPLETE", "RUNNING", "PENDING", "UNKNOWN", "DONE", "PASS"]
        now = sorted((r.state for r in rs), key=lambda x: order.index(x) if x in order else 3)[0] if rs else "PENDING"
        out.append("| %s | %s | **%s** |" % (b["check"], b["before"], now))
    out.append("\n%s\n" % runtime_line(L))
    out.append("Part 2 stage states:\n\n| Stage | State |\n|---|---|")
    for stage, what in P2_STAGES:
        out.append("| `%s` %s | %s |" % (stage, what, stage_state(L, stage)[0]))
    return "\n".join(out) + "\n"
