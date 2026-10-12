#!/usr/bin/env python3
"""demo_build.py - generate demo/index.html, demo/README.md and the repo README.md from what is on disk.

Pure standard library (runs with the system python3), always succeeds: a missing result is rendered as
PENDING / RUNNING / BLOCKED / FAILED with the reason from the stage marker, never as an invented value.

  python3 scripts/demo_build.py [--lab DIR] [--out DIR] [--vm running|stopped]

--lab  where results live (default $LAB or ~/ai-chip-lab, the main checkout)
--out  where to write demo/index.html, demo/README.md, README.md (default = --lab)
--vm   state in which the Colima VM is left (set by final packaging); default: not stated
"""
import argparse
import glob
import html
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence_privacy import scan_text, scrub_text  # noqa: E402
import demo_part2  # noqa: E402

HOME_LAB = os.path.expanduser("~/ai-chip-lab")
e = html.escape


# ----------------------------------------------------------------------------- reading helpers
class Lab:
    def __init__(self, lab, out):
        self.lab, self.out = lab, out

    def p(self, *a):
        return os.path.join(self.lab, *a)

    def exists(self, rel):
        return os.path.exists(self.p(rel)) or os.path.exists(os.path.join(self.out, rel))

    def read(self, rel, default=""):
        try:
            with open(self.p(rel), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return default

    def jload(self, rel):
        try:
            return json.loads(self.read(rel))
        except Exception:
            return None

    def mtime(self, rel):
        try:
            return os.path.getmtime(self.p(rel))
        except OSError:
            return None


def stage_marker(L, stage):
    """-> (state, body, mtime). state in done/failed/blocked/running/none. Priority: failed>blocked>done>running."""
    found = {}
    for st in ("failed", "blocked", "done", "running"):
        rel = "results/.stages/%s.%s" % (stage, st)
        if os.path.exists(L.p(rel)):
            found[st] = (L.read(rel).strip(), L.mtime(rel))
    for st in ("running", "failed", "blocked", "done"):
        pass
    # a .done together with .running means a re-run is in progress; report running
    if "running" in found and "done" not in found:
        return ("running",) + found["running"]
    for st in ("failed", "blocked", "done", "running"):
        if st in found:
            return (st,) + found[st]
    return ("none", "", None)


def stage_group(L, prefix):
    """Markers for stages whose name starts with prefix (e.g. 40_sweeps*). Returns list of (stage, state, body)."""
    names = set()
    for f in glob.glob(L.p("results/.stages/%s*" % prefix)):
        names.add(os.path.basename(f).rsplit(".", 1)[0])
    return [(n,) + stage_marker(L, n)[:2] for n in sorted(names)]


def find_key(d, rx, depth=0):
    """First key matching rx whose value is a bool, or a dict/obj holding a bool 'pass'/'ok'. -> (key, bool) or None"""
    if not isinstance(d, dict) or depth > 4:
        return None
    rxc = re.compile(rx, re.I)
    for k, v in d.items():
        if rxc.search(str(k)):
            if isinstance(v, bool):
                return (k, v)
            if isinstance(v, dict):
                for kk in ("pass", "passed", "ok", "proved", "equivalent"):
                    if isinstance(v.get(kk), bool):
                        return (k, v[kk])
    for v in d.values():
        r = find_key(v, rx, depth + 1)
        if r:
            return r
    return None


def fmt_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return "%.6g" % v
    if v is None:
        return "null"
    if isinstance(v, (list, tuple)):
        if len(v) <= 6 and all(not isinstance(x, (dict, list)) for x in v):
            return ", ".join(fmt_val(x) for x in v)
        return "[%d items]" % len(v)
    s = str(v)
    return s if len(s) <= 160 else s[:157] + "..."


def flatten(d, prefix="", depth=0):
    rows = []
    if isinstance(d, dict):
        for k, v in d.items():
            key = prefix + str(k)
            if isinstance(v, dict) and depth < 3:
                rows.extend(flatten(v, key + ".", depth + 1))
            else:
                rows.append((key, v))
    return rows


# ----------------------------------------------------------------------------- status model
class Row:
    def __init__(self, label, state, detail, link=None):
        self.label, self.state, self.detail, self.link = label, state, detail, link


STALE_INPUTS = {"10_rtl_verify": ["rtl", "tb", "formal", "eqy"]}


def _git(L, *args):
    try:
        r = subprocess.run(["git", "-C", L.lab] + list(args), capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def stale_inputs(L, stage, summary_rel):
    """Input paths changed after the recorded result. Uses git commit times (a fresh clone has no meaningful mtimes);
    uncommitted edits to the inputs count as newer. Falls back to mtimes only when the summary itself is untracked."""
    ins = STALE_INPUTS.get(stage, [])
    if not ins or L.mtime(summary_rel) is None:
        return []
    dirty = _git(L, "status", "--porcelain", "--", *ins)
    if dirty:
        return [ln[3:] for ln in dirty.splitlines()][:6]
    if _git(L, "ls-files", "--error-unmatch", summary_rel) is not None:
        sct = _git(L, "log", "-1", "--format=%ct", "--", summary_rel)
        ict = _git(L, "log", "-1", "--format=%ct", "--", *ins)
        if sct and ict and int(ict) > int(sct):
            return ["inputs last committed %s, summary last committed %s" % (
                time.strftime("%H:%M:%S", time.localtime(int(ict))), time.strftime("%H:%M:%S", time.localtime(int(sct))))]
        return []
    sm = L.mtime(summary_rel)  # untracked summary: compare file mtimes
    newer = []
    for d in ins:
        for base, _, fs in os.walk(L.p(d)):
            if "work" in base.split(os.sep) or "sim_build" in base:
                continue
            for f in fs:
                fp = os.path.join(base, f)
                try:
                    if os.path.getmtime(fp) > sm + 1 and not f.endswith((".pyc", ".vcd")):
                        newer.append(os.path.relpath(fp, L.lab))
                except OSError:
                    pass
    return newer


def task_state(L, stage, summary_rel):
    """PASS needs the stage marker .done AND summary pass==true AND no input changed since the result. Returns (state, detail, summary_dict)."""
    r = _task_state(L, stage, summary_rel)
    if r[0] in ("PASS", "FAIL") and stage_marker(L, stage)[0] != "failed":
        nw = stale_inputs(L, stage, summary_rel)
        if nw:
            return ("RUNNING", "re-verification in progress: inputs changed after the recorded result (%s%s); the previous result "
                    "(pass=%s) is not shown as current" % (", ".join(nw[:3]), ", ..." if len(nw) > 3 else "", (r[2] or {}).get("pass")), r[2])
    return r


def _task_state(L, stage, summary_rel):
    st, body, _ = stage_marker(L, stage)
    s = L.jload(summary_rel)
    first = (body.splitlines() or [""])[0][:200]
    if st == "failed":
        return "FAIL", "marker .failed: " + first, s
    if st == "blocked":
        return "BLOCKED", "marker .blocked: " + first, s
    if isinstance(s, dict) and isinstance(s.get("pass"), bool):
        if s["pass"] and st == "done":
            return "PASS", "%s: pass=true" % summary_rel.split("/")[-1], s
        if s["pass"] and st == "running":
            return "RUNNING", "summary says pass=true but a re-run is in progress", s
        return "FAIL", "%s: pass=false" % summary_rel.split("/")[-1], s
    if st == "running":
        return "RUNNING", "stage in progress" + (": " + first if first else ""), s
    if st == "done":
        return "UNKNOWN", "stage .done but %s missing or has no boolean 'pass'" % summary_rel, s
    if isinstance(s, dict) and st == "none":
        return "UNKNOWN", "%s exists but the stage has no .done marker" % summary_rel, s
    return "PENDING", "no marker and no %s yet" % summary_rel, s


def sweep_points(L, name):
    p = L.p("results/sweeps/%s.jsonl" % name)
    n, bad = 0, 0
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    n += 1
                except Exception:
                    bad += 1
    except OSError:
        return None
    return n, bad


def build_rows(L):
    rows = []

    st, body, mt = stage_marker(L, "01_runtime")
    route = ""
    m = re.search(r'route:\s*"([^"]+)"', L.read("versions.lock"))
    if m:
        route = m.group(1)
    rows.append(Row("Container runtime install", {"done": "PASS", "failed": "FAIL", "blocked": "BLOCKED",
                                                  "running": "RUNNING", "none": "PENDING"}[st],
                    ("route " + route) if route else (body.splitlines() or ["no marker yet"])[0][:160],
                    "results/evidence/01_runtime_docker.txt"))
    st, body, _ = stage_marker(L, "02_images")
    img = [l.strip() for l in L.read("coord/images.env").splitlines() if "IMAGE=" in l and not l.startswith("#")]
    rows.append(Row("Lab images (lab-sim, ORFS)", {"done": "PASS", "failed": "FAIL", "blocked": "BLOCKED",
                                                   "running": "RUNNING", "none": "PENDING"}[st],
                    "both images referenced in coord/images.env" if len(img) >= 2 and st == "done"
                    else ((body.splitlines() or ["stage in progress" if st == "running" else "no marker yet"])[0][:160]), "coord/images.env"))

    s1, d1, t1 = task_state(L, "10_rtl_verify", "results/t1_summary.json")
    rows.append(Row("Task 1: INT8 systolic array vs NumPy", s1, d1, "results/t1_summary.json"))
    chk = (t1 or {}).get("checks") if isinstance(t1, dict) else None
    for label, rx in (("Task 1: formal MAC proof (SBY)", r"^formal_.*(pass)$"),
                      ("Task 1: RTL = netlist equivalence (EQY)", r"^eqy_.*pass$")):
        hits = [(k, v) for k, v in (chk or {}).items() if isinstance(v, bool) and re.search(rx, k)]
        if hits and s1 == "RUNNING":
            rows.append(Row(label, "RUNNING", "re-verification in progress (see Task 1 row); the earlier values are withheld", "results/t1_summary.json"))
        elif hits:
            okk = all(v for _, v in hits)
            extra = ""
            if "EQY" in label:
                extra = ("; scope: split proof (1) mac_int8 incl. multiplier, (2) full 4x4 array with mac_int8 black-boxed; compared against the generic-gate "
                         "Yosys netlist (synth; abc; opt), NOT the placed-and-routed nangate45 netlist (the ORFS logic-equivalence step is disabled, see caveats)")
            rows.append(Row(label, "PASS" if okk else "FAIL",
                            "checks: " + ", ".join("%s=%s" % (k, fmt_val(v)) for k, v in hits) + extra, "results/t1_summary.json"))
        else:
            rows.append(Row(label, s1 if s1 in ("PENDING", "RUNNING") else ("BLOCKED" if s1 == "BLOCKED" else "UNKNOWN"),
                            "not reported in t1_summary.json yet" if t1 else "waits for Task 1 summary", None))
    s2, d2, t2s = task_state(L, "20_pnr_ref", "results/t2_summary.json")
    nc = []
    for dn, dd in ((t2s or {}).get("designs") or {}).items():
        det = dd.get("detail") or {}
        if dd.get("status") == "run" and det.get("timing_closed") is False:
            pp = dd.get("ppa") or {}
            nc.append("%s misses timing at its %s ns reference clock (WNS %s ns, TNS %s ns, %s violating endpoints)" % (
                dn, det.get("reference_clock_period_ns"), fmt_val(pp.get("wns_setup_ns")), fmt_val(pp.get("tns_setup_ns")), det.get("setup_violating_endpoints")))
    rows.append(Row("Task 2: OpenROAD gcd flows within ORFS's shipped regression thresholds", s2,
                    d2 + ("; NOT timing-closed: " + "; ".join(nc) if nc else ""), "results/t2_summary.json"))
    t3stage = "31_roofline_fix" if stage_marker(L, "31_roofline_fix")[0] != "none" else "30_arch_model"
    s3, d3, t3s = task_state(L, t3stage, "results/t3_summary.json")
    t3f = sorted(k for k, v in ((t3s or {}).get("checks") or {}).items() if v is False)
    if t3f:
        d3 += "; criteria that fail: %s (the roofline-vs-stalls agreement; the analytic cycle model and byte-identity checks pass)" % ", ".join(t3f)
    if isinstance(t3s, dict) and t3s.get("verdict") == "FAIL":
        cs = t3s.get("cell_status") or {}
        d3 = ("FAIL: criteria that fail: %s (criterion B, CALC mode: rho(intensity, required bandwidth) must be <= -0.6 for every dataflow). Criterion A (stalls at a fixed user bandwidth) is "
              "NOT EVALUATED (cost), neither pass nor fail: %s; the probe showed the largest layer alone needs more than 481 s, over the 10-minute lock-hold rule (results/evidence/31_a_probe.txt). "
              "Open items: %s. Pre-registered thresholds were not changed (model/t3_roofline2_criteria.json, P2-A1/P2-A2/P2-7); the Part 2 hypothesis was wrong in its mechanism (the bundled google.cfg already uses USER bandwidth and its stalls are all zero, results/evidence/31_original_stalls.txt). "
              "Explainer: docs/t3_roofline_explained.md") % (
            ", ".join(t3s.get("verdict_failed_criteria") or []) or "see the table in section 6", t3s.get("state"), fmt_val(t3s.get("pending")))
        s3 = "FAIL"
    elif isinstance(t3s, dict) and (t3s.get("complete") is False or str(t3s.get("state", "")).startswith("A_incomplete")) and s3 not in ("RUNNING",):
        cs = t3s.get("cell_status") or (t3s.get("roofline") or {}).get("cell_status")
        calc = {k: v for k, v in ((t3s.get("checks") or {}).items()) if "calc" in k.lower()}
        d3 = ("INCOMPLETE (not PASS, not a bare FAIL): state=%s; criterion B (CALC mode) %s; criterion A (stalls at fixed user bandwidth) per (dataflow x level): %s; pending: %s. "
              "Pre-registered in model/t3_roofline2_criteria.json, cost-only amendment P2-A2 and plan P2-7 (COORDINATION.md); a row is PASS only when every pre-registered criterion has been evaluated and passes. "
              "The Part 2 hypothesis was wrong: the bundled google.cfg already uses USER bandwidth and its stalls are all zero (results/evidence/31_original_stalls.txt)") % (
            t3s.get("state"), (", ".join("%s=%s" % (k, fmt_val(v)) for k, v in calc.items()) or "see the table in section 5"),
            (json.dumps(cs, sort_keys=True)[:700] if cs is not None else "not reported"), fmt_val(t3s.get("pending")))
        s3 = "INCOMPLETE"
    elif isinstance(t3s, dict) and "complete" not in t3s and s3 != "PASS" and glob.glob(L.p("results/t3.partial/roofline2/*")):
        # the re-specified roofline check (Part 2) is under way but its summary has not been written: the file on disk is still the Part 1 result
        done = sorted(os.path.basename(x)[:-5] for x in glob.glob(L.p("results/t3.partial/roofline2/*.json")))
        user_started = sorted(os.path.basename(x) for x in glob.glob(L.p("results/t3.partial/roofline2/rl2_user_*")) if os.path.isdir(x))
        rh = demo_part2.calc_rhos(L)
        bres = ("criterion B (CALC mode, rho(intensity, required bandwidth) <= -0.6 required): " + ", ".join("%s %.2f (%s)" % (k, v, "pass" if v <= -0.6 else "fails") for k, v in rh.items())) if rh else "criterion B not evaluated yet"
        d3 = ("INCOMPLETE (not PASS, not a bare FAIL): the re-specified roofline check is in progress and results/t3_summary.json is still the Part 1 result (%s). "
              "Roofline runs finished so far: %s; " + bres.replace("%", "%%") + "; criterion A (stalls at fixed user bandwidth) started for: %s, no layer-complete run reported yet. "
              "Pre-registered in model/t3_roofline2_criteria.json, cost-only amendment P2-A2, plan P2-7 (COORDINATION.md). "
              "The Part 2 hypothesis was wrong: the bundled google.cfg already uses USER bandwidth and its stalls are all zero (results/evidence/31_original_stalls.txt)") % (
            d3, ", ".join(x for x in done if not x.startswith("rl2_user")) or "none", ", ".join(user_started) or "none")
        s3 = "INCOMPLETE"
    rows.append(Row("Task 3: SCALE-Sim vs analytical model", s3, d3, "results/t3_summary.json"))

    asum = L.jload("results/sweeps/arch_summary.json") or {}
    pfr = L.jload("results/sweeps/phys_frontier.json") or {}
    for name, stage, label in (("arch", "40_sweeps_A", "Sweep A: architecture (SCALE-Sim)"), ("phys", "40_sweeps_B", "Sweep B: physical (ORFS)")):
        pts = sweep_points(L, name)
        st, body, _ = stage_marker(L, stage)
        first = (body.splitlines() or [""])[0][:200]
        if st == "failed":
            state, why = "FAIL", "marker .failed: " + first
        elif st == "blocked":
            state, why = "BLOCKED", "marker .blocked: " + first
        elif st == "running":
            state, why = "RUNNING", "sweep in progress"
        elif st == "done" and pts and pts[0] > 0:
            state, why = "DONE", "sweep stopped (marker .done); this is a completion status, not a pass/fail verdict"
        elif pts and pts[0] > 0:
            state, why = "RUNNING", "points on disk, no .done marker yet (partial results shown)"
        else:
            state, why = "PENDING", "no points yet"
        if name == "arch" and asum:
            sc = asum.get("status_counts") or {}
            why += "; %s ok of %s planned points (%s error, %s skipped after timeout, %s never reached before the deadline)" % (
                sc.get("ok"), asum.get("planned_points"), sc.get("error", 0), sc.get("skipped_after_timeout", 0), asum.get("not_run_points"))
        elif name == "phys" and pfr:
            lf = phys_frontier_live(L)
            fr = lf.get("gcd") or (pfr.get("frontier") or {}).get("gcd") or {}
            so = lf.get("systolic_os") or (pfr.get("frontier") or {}).get("systolic_os") or {}
            lo = min(v["fastest_closing_period_ns"] for v in fr.values()) if fr else None
            hi = max(v["fastest_closing_period_ns"] for v in fr.values()) if fr else None
            mg = [u for u, v in fr.items() if v.get("wns_at_frontier_ns", 1) < 0.001]
            why += "; gcd closes at %s-%s ns depending on utilization%s" % (fmt_val(lo), fmt_val(hi), (" (about zero margin at %s ns, u%s)" % (fmt_val(lo), ",".join(mg))) if mg else "")
            for u, v in so.items():
                why += "; systolic_os at %s %% utilization: closes at %s ns (WNS %s ns), fails at %s ns (WNS %s ns), %s points" % (
                    u, fmt_val(v.get("fastest_closing_period_ns")), fmt_val(v.get("wns_at_frontier_ns")), fmt_val(v.get("next_failing_period_ns")), fmt_val(v.get("wns_at_next_failing_ns")), v.get("points"))
            why += "; %d failed point(s)" % len(pfr.get("failed_points") or [])
        elif pts:
            why += "; %d point(s)" % pts[0]
        rows.append(Row(label, state, why, "results/sweeps/%s.jsonl" % name if pts else None))

    rstage = "51_repro_full" if stage_marker(L, "51_repro_full")[0] != "none" else "50_repro"
    sr, dr, rrep = task_state(L, rstage, "results/repro_report.json")
    if isinstance(rrep, dict):
        chk = rrep.get("checks") or []
        if any("runs" in c for c in chk):
            cnt = {}
            for c in chk:
                cnt[c.get("verdict")] = cnt.get(c.get("verdict"), 0) + 1
            dr += "; %d checks, each with its run count and verdict in section 7: %s%s" % (
                len(chk), ", ".join("%s %s" % (v, k) for k, v in sorted(cnt.items(), key=lambda x: str(x[0]))),
                "" if rrep.get("complete", True) else "; NOT complete: at least one check was not rerun (cost) and is not counted as identical")
        else:
            dr += ("; %s of %s checks identical in the Part 1 report (results/repro_report.json predates the Part 2 repro: its scope was Tasks 1 and 3 re-run once, "
                   "Task 2 from its two original runs, systolic_os a single run). The Part 2 report with every design's run count (gcd 4 runs on both PDKs, systolic_os 3, from "
                   "results/t2_reruns.json) replaces it when `make repro` finishes" % (
                       (rrep.get("counts") or {}).get("identical"), len(chk)))
    rows.append(Row("Repeatability rerun (repro)", sr, dr, "results/repro_report.json"))
    if demo_part2.active(L):
        rows.extend(demo_part2.extra_rows(L, Row, t1, t2s, t3s))
    return rows


def phys_frontier_live(L):
    """Per design and utilization: fastest closing period and the closest failing period below it, computed from results/sweeps/phys.jsonl
    (the ground truth; phys_frontier.json is only regenerated by the plot step and can lag behind)."""
    pts = {}
    try:
        for ln in open(L.p("results/sweeps/phys.jsonl"), encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("status") == "ok" and isinstance(r.get("wns_setup_ns"), (int, float)):
                pts.setdefault((r.get("design"), str(r.get("core_utilization"))), {})[float(r["clock_period_ns"])] = r
    except OSError:
        return {}
    out = {}
    for (d, u), by in pts.items():
        closing = [p for p, r in by.items() if r["wns_setup_ns"] >= 0]
        if not closing:
            continue
        fc = min(closing)
        below = [p for p in by if p < fc and by[p]["wns_setup_ns"] < 0]
        nf = max(below) if below else None
        out.setdefault(d, {})[u] = {"points": len(by), "fastest_closing_period_ns": fc, "wns_at_frontier_ns": by[fc]["wns_setup_ns"],
                                   "next_failing_period_ns": nf, "wns_at_next_failing_ns": by[nf]["wns_setup_ns"] if nf is not None else None}
    return out


# ----------------------------------------------------------------------------- html helpers
BADGE = {"INCOMPLETE": "warn", "DONE": "ok", "PASS": "ok", "FAIL": "bad", "BLOCKED": "warn", "RUNNING": "run", "PENDING": "dim", "UNKNOWN": "dim"}


def badge(state):
    return '<span class="b %s">%s</span>' % (BADGE.get(state, "dim"), e(state))


def link(L, rel, text=None, ctx="demo"):
    """Link relative to demo/index.html (ctx='demo') or repo root (ctx='root'). Plain text if the file is absent."""
    text = text or rel
    if not L.exists(rel):
        return '<code class="missing" title="not present on disk at build time">%s</code>' % e(text)
    href = ("../" + rel) if ctx == "demo" else rel
    return '<a href="%s"><code>%s</code></a>' % (e(href), e(text))


def img(L, rel, cap, ctx="demo"):
    if not L.exists(rel):
        return ""
    src = rel[len("demo/"):] if (ctx == "demo" and rel.startswith("demo/")) else rel
    return '<figure><a href="%s"><img src="%s" alt="%s" loading="lazy"></a><figcaption>%s</figcaption></figure>' % (
        e(src), e(src), e(cap), e(cap))


def kv_table(d, limit=60):
    rows = flatten(d)
    if not rows:
        return ""
    h = ['<table class="kv"><tbody>']
    for k, v in rows[:limit]:
        cls = ""
        if isinstance(v, bool):
            cls = ' class="%s"' % ("okt" if v else "badt")
        h.append("<tr><th>%s</th><td%s>%s</td></tr>" % (e(k), cls, e(fmt_val(v))))
    if len(rows) > limit:
        h.append("<tr><th>...</th><td>%d more fields in the JSON file</td></tr>" % (len(rows) - limit))
    h.append("</tbody></table>")
    return "".join(h)


def images_for(L, prefixes):
    out = []
    for pre in prefixes:
        for f in sorted(glob.glob(L.p("demo/assets/%s*.png" % pre))) + sorted(
                glob.glob(os.path.join(L.out, "demo/assets/%s*.png" % pre))):
            rel = "demo/assets/" + os.path.basename(f)
            if rel not in out:
                out.append(rel)
    return out


def all_result_images(L):
    seen, out = set(), []
    for base in (L.lab, L.out):
        for f in sorted(glob.glob(os.path.join(base, "demo/assets/*.png"))):
            rel = "demo/assets/" + os.path.basename(f)
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out


def caption_of(rel):
    n = os.path.splitext(os.path.basename(rel))[0]
    return n.replace("_", " ")


# ----------------------------------------------------------------------------- static prose
TREE = [
    ("env.sh", "Puts the lab-local tools (colima, docker) on PATH and redirects all VM/Docker state into this directory."),
    ("env.json", "Measured machine facts (CPU, RAM, macOS, free disk) captured at preflight."),
    ("budget.json", "The time budget and its milestones; the build elapsed time is computed from it."),
    ("versions.lock", "Every pinned version, git SHA, image digest, download URL and SHA256 the lab used."),
    ("coord/images.env", "The two container images (lab-sim build, ORFS pinned by digest) that every script sources."),
    ("COORDINATION.md", "How the agents divided the work: rules, decisions with evidence, requests between agents."),
    ("docker/lab-sim/Dockerfile", "Recipe for the simulation image (OSS CAD Suite, Verible, Python venv)."),
    ("docker/requirements.lock", "Hash-locked Python dependencies installed in the lab-sim image (it lives under docker/, not at the repo root)."),
    ("rtl/mac_int8.sv", "The multiply-accumulate unit: signed INT8 x INT8 into an INT32 accumulator."),
    ("rtl/systolic_os.sv", "R x C output-stationary systolic array built from MAC processing elements."),
    ("tb/test_systolic.py", "cocotb testbench: random + directed cases checked against NumPy, with functional coverage."),
    ("formal/", "SymbiYosys property proofs for the MAC (Task 1)."),
    ("eqy/", "Equivalence check: RTL versus the Yosys gate-level netlist (Task 1)."),
    ("orfs/designs/", "Design configs for the OpenROAD flow (gcd reference and the systolic_os stretch design)."),
    ("orfs/render.py", "KLayout batch script that turns a GDS layout into a PNG."),
    ("model/", "analytic.py: the closed-form cycle/roofline model that SCALE-Sim is checked against (Task 3)."),
    ("arch/", "SCALE-Sim configs and topologies used in Task 3 and sweep A."),
    ("sweeps/", "Sweep drivers: architecture (SCALE-Sim) and physical (ORFS clock x utilization)."),
    ("scripts/", "Entry points: with_lock.sh (one heavy job at a time), t1/t2/t3 runners, repro.sh, demo_build.py."),
    ("results/t1_summary.json", "Task 1 verdict and measured values."),
    ("results/t2_summary.json", "Task 2 verdict and PPA metrics."),
    ("results/t3_summary.json", "Task 3 verdict and fit residuals."),
    ("results/repro_report.json", "Per-check identical/different verdicts from the clean rerun."),
    ("results/sweeps/", "One JSON line per sweep point, keyed by its parameters."),
    ("results/evidence/", "Scrubbed real terminal output of each stage's key command; rendered to PNG for the README."),
    ("results/.stages/", "Stage markers (.done/.failed/.blocked/.running) that this page reads for its status."),
    ("demo/index.html", "This page, generated by scripts/demo_build.py from whatever exists on disk."),
    ("demo/run_demo.sh", "The 5-minute re-run: Task 1 (200 cases, both simulators), formal proof, one SCALE-Sim run, ORFS check, and the Task 3 roofline criterion B recomputed from saved reports., plus the routed-netlist gate-level simulation on Icarus with 20 random + 29 directed cases (Verilator not run)."),
    ("demo/assets/", "Waveform, layout, plots and evidence PNGs referenced by this page."),
    ("Makefile", "make preflight runtime images t1 t2 t3 sweeps repro demo all."),
]

CONCEPTS = [
    ("MAC: multiply-accumulate",
     "The atom of neural-network arithmetic: <code>acc = acc + a*b</code>. A matrix product is nothing but many of "
     "these. Here a and b are signed 8-bit integers and the accumulator is 32-bit, so a long sum does not overflow in practice: the worst case is (&minus;128)&sup2; = 16,384 per step, "
     "and a signed 32-bit accumulator only wraps after 131,072 such accumulations (2<sup>31</sup> / 2<sup>14</sup>).",
     ["rtl/mac_int8.sv", "formal/"]),
    ("PE: processing element",
     "A MAC plus the registers that hold its accumulator and pass operands on. In an output-stationary design each PE "
     "owns exactly one element of the output matrix and keeps adding into it until the dot product is complete.",
     ["rtl/mac_int8.sv"]),
    ("Systolic array",
     "A grid of PEs where data flows rhythmically from neighbour to neighbour, like blood through the heart "
     "(systole). Rows of A enter from the left, columns of B from the top, each skewed by one cycle per row/column so "
     "that matching operands meet in the right PE at the right time. No PE needs wide global wiring, which is why "
     "TPU-style chips are built this way.",
     ["rtl/systolic_os.sv", "tb/test_systolic.py"]),
    ("Dataflow: ws / os / is",
     "Which value stays put in the PE: weights (ws), outputs (os) or inputs (is). The choice changes how often each "
     "operand must be re-read from memory, so it changes cycles and bandwidth for the same arithmetic. SCALE-Sim "
     "models all three; the sweep compares them.",
     ["arch/", "model/", "results/sweeps/arch.jsonl"]),
    ("Memory hierarchy and roofline",
     "Arithmetic is cheap, moving data is not. The roofline model plots achievable performance against arithmetic "
     "intensity (operations per byte moved): below the knee a layer is bandwidth-bound, above it compute-bound. Task 3 "
     "checks that SCALE-Sim's stalls agree with this classification layer by layer.",
     ["model/", "results/t3_summary.json"]),
    ("RTL: register-transfer level",
     "Hardware described as registers and the combinational logic between them, in SystemVerilog. It is the level at "
     "which designers write chips and the input to synthesis.",
     ["rtl/systolic_os.sv"]),
    ("Verification",
     "Showing the RTL is right. Three independent oracles are used: simulation against NumPy integer matmul "
     "(random and directed tests, on two different simulators that must produce byte-identical output), a formal proof "
     "that the MAC obeys its equation for all inputs, and an equivalence check that the synthesized netlist behaves "
     "like the RTL.",
     ["tb/test_systolic.py", "formal/", "eqy/", "results/t1_summary.json"]),
    ("Logic synthesis",
     "Turning RTL into a netlist of standard cells (NAND, flip-flop, ...) from a technology library; Yosys with ABC "
     "does this here. The cell count and area it reports are the first real hardware cost numbers.",
     ["orfs/designs/", "results/t2_summary.json"]),
    ("Place and route",
     "Floorplan (chip outline, I/O pins, power grid), placement (where each cell sits), clock-tree synthesis "
     "(distribute the clock with balanced delay), then routing (metal wires on many layers). OpenROAD runs all of "
     "this; utilization is the fraction of the core area occupied by cells.",
     ["orfs/designs/", "results/t2_summary.json"]),
    ("Static timing analysis",
     "Checking every register-to-register path against the clock period without simulating. Slack is the margin; WNS is "
     "the worst negative slack and TNS the total of all negative slacks. WNS &ge; 0 means the design meets timing. "
     "OpenSTA, embedded in OpenROAD, does it. The physical sweep finds the fastest clock that still closes.",
     ["results/t2_summary.json", "results/sweeps/phys.jsonl"]),
    ("PDK",
     "The process design kit: the foundry-supplied cell libraries, timing models, layer stack and design rules for a "
     "manufacturing process. nangate45 is an open teaching PDK; sky130 is a real open 130 nm process.",
     ["orfs/designs/"]),
    ("GDSII",
     "The final geometry file handed to a foundry (the mask layers). The layout images in the results section are "
     "KLayout renders of the GDS that the flow produced; GDS files themselves are large and are not committed.",
     ["orfs/render.py"]),
]

TOOLS = [
    ("Verilator, Icarus Verilog", "RTL simulation", "VCS, Xcelium, Questa"),
    ("cocotb (+ cocotb-coverage)", "Testbench / functional coverage", "UVM"),
    ("SymbiYosys, EQY", "Formal property proof, equivalence checking", "JasperGold, Formality, Conformal"),
    ("Yosys (+ ABC)", "Logic synthesis", "Design Compiler, Genus"),
    ("OpenROAD", "Floorplan, place, CTS, route", "Innovus, ICC2"),
    ("OpenSTA", "Static timing analysis", "PrimeTime, Tempus"),
    ("KLayout, Magic", "Layout viewing, DRC/LVS", "Calibre"),
    ("SCALE-Sim, Timeloop", "Architecture performance model", "In-house architecture models"),
    ("Colima + Docker", "Reproducible tool environment", "Site-wide tool installs and license servers"),
]

TESTS = [
    ("Task 1 - INT8 systolic array", "10_rtl_verify", "results/t1_summary.json",
     "Integer matrix multiplication done by NumPy (<code>A.astype(int32) @ B.astype(int32)</code>), which is exact. "
     "Second oracles: a second simulator, a formal proof and a netlist equivalence proof.",
     "make t1 (scripts/t1_run.sh 10000 results inside the lab-sim image).",
     "Random INT8 matrices from seed 1234, tiled onto the 4x4 array, plus directed cases (all -128, all 127, zeros, identity, "
     "clear mid-stream, K=1, shapes not a multiple of the array size). Run on Verilator and Icarus.",
     "0 mismatches on both simulators; sha256 of the two result CSVs equal; formal proof passes; EQY passes."),
    ("Task 2 - OpenROAD reference flow", "20_pnr_ref", "results/t2_summary.json",
     "Published thresholds shipped with ORFS (<code>rules-base.json</code>), checked by ORFS's own <code>checkMetadata.py</code>.",
     "make t2 (scripts/make_t2.sh ref: both gcd designs twice from clean with the pinned ORFS image, threshold check, summary; about 35 min of ORFS) and make t2-stretch for systolic_os (about 30 min).",
     "nangate45 gcd (and sky130hd gcd if time allowed), each twice from a clean directory with the same image digest and core count.",
     "All metrics within thresholds; final DRC count 0; GDS exists; the two runs give identical metrics."),
    ("Task 3 - SCALE-Sim vs analytical model", "30_arch_model", "results/t3_summary.json",
     "No independent oracle exists for this task: a closed-form cycle model whose constants were derived from SCALE-Sim's own source (so agreement validates the derivation, not the simulator), "
     "plus a roofline model compared with the simulator's stall counts. Both are in <code>model/analytic.py</code> and <code>model/t3_roofline.py</code>.",
     "make t3 (scripts/t3_run.sh in the lab-sim image: two SCALE-Sim passes, fit, roofline; exits non-zero while the roofline criterion fails).",
     "Bundled TPU-like config and bundled topology for ws, os and is; synthetic GEMMs for the fit; array and K doubled to test that residuals stay stable.",
     "Two reruns byte-identical; analytic model within the fitted constant with stable residuals; roofline classification agrees with stalls."),
]

NEXT = [
    ("bfloat16 / FP8 processing elements, checked against <code>ml_dtypes</code>",
     "Modern training and inference chips left INT8-only long ago; a floating-point MAC has a mantissa multiplier and rounding that are easy to get subtly wrong, and ml_dtypes gives a bit-exact oracle."),
    ("Double-buffered SRAM modelled with CACTI",
     "The array is only half the chip; the on-chip buffer decides whether it stays fed, and CACTI turns capacity into area, energy and access time to plug into the roofline."),
    ("systolic_os through sky130 and PPA across PDKs",
     "Comparing the same design on nangate45 and sky130 shows how much of the result is the process rather than the design."),
    ("VCD/SAIF switching activity from cocotb for real power",
     "Power numbers from default activity are guesses; feeding the actual toggle rates of a real matmul to OpenROAD makes them meaningful."),
    ("Gemmini/Chipyard, TVM/VTA or MLIR/CIRCT",
     "Moves from a hand-written array to a full generated accelerator with a compiler stack, which is how real systems are explored."),
    ("DREAMPlace",
     "GPU-style analytical placement; a well-defined component to swap into the flow and compare."),
    ("LLM-written RTL scored against VerilogEval",
     "Uses the same lab as a judge: generated RTL passes only if the simulators and formal tools agree it is right."),
]


# ----------------------------------------------------------------------------- page assembly
CSS = """
:root{--bg:#fff;--fg:#1b2230;--dim:#667085;--card:#f5f7fa;--line:#dde3ec;--ok:#137a3c;--okb:#dcf5e5;--bad:#b42318;--badb:#fde3e0;--warn:#8a5a00;--warnb:#fdf0cf;--run:#1849a9;--runb:#dbe8fd;--dimb:#e8ebf0;--acc:#2b59c3;--code:#eef1f6}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#dde3ee;--dim:#98a2b3;--card:#1a1f28;--line:#2c3441;--ok:#6ee7a1;--okb:#143324;--bad:#ff8a80;--badb:#3d1a18;--warn:#f5c86a;--warnb:#3a2d10;--run:#8ab4ff;--runb:#18284a;--dimb:#262c37;--acc:#8ab4ff;--code:#222936}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1060px;margin:0 auto;padding:1.2rem 1.1rem 4rem}
h1{font-size:1.9rem;margin:.2rem 0}h2{margin:2.6rem 0 .6rem;padding-top:.6rem;border-top:2px solid var(--line);font-size:1.4rem}h3{margin:1.4rem 0 .3rem;font-size:1.05rem}
a{color:var(--acc)}code,pre{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em}code{background:var(--code);padding:.05em .3em;border-radius:4px}
pre{background:var(--code);padding:.8rem;border-radius:8px;overflow-x:auto;line-height:1.4}code.missing{opacity:.55;text-decoration:line-through dotted}
nav{display:flex;flex-wrap:wrap;gap:.35rem .9rem;margin:.6rem 0 1rem;font-size:.9rem}
.sub{color:var(--dim)}table{border-collapse:collapse;width:100%;margin:.5rem 0}th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600}.tw{overflow-x:auto}.b{display:inline-block;min-width:5.6em;text-align:center;padding:.1em .6em;border-radius:99px;font-weight:700;font-size:.8rem;letter-spacing:.03em}
.b.ok{background:var(--okb);color:var(--ok)}.b.bad{background:var(--badb);color:var(--bad)}.b.warn{background:var(--warnb);color:var(--warn)}.b.run{background:var(--runb);color:var(--run)}.b.dim{background:var(--dimb);color:var(--dim)}
.big td,.big th{padding:.65rem .7rem;font-size:1rem}table.kv th{width:34%;font-weight:500;color:var(--dim);font-family:ui-monospace,Menlo,monospace;font-size:.82rem}td.okt{color:var(--ok);font-weight:600}td.badt{color:var(--bad);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.7rem}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.7rem .9rem}.card b{display:block;font-size:1.25rem}
figure{margin:.6rem 0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.6rem}figure img{max-width:100%;height:auto;display:block;margin:0 auto;border-radius:4px}figcaption{color:var(--dim);font-size:.85rem;text-align:center;margin-top:.3rem}
.gal{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:.7rem}.note{border-left:4px solid var(--warn);background:var(--warnb);padding:.5rem .8rem;border-radius:6px;margin:.6rem 0}
details{margin:.4rem 0}summary{cursor:pointer;color:var(--acc)}ol li,ul li{margin:.25rem 0}.concept{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.2rem .9rem .5rem;margin:.6rem 0}.concept h3{margin-top:.5rem}
"""

NAV = [("summary", "Summary"), ("created", "What was created"), ("concepts", "Concepts"), ("tools", "Tool map"),
       ("tests", "How it was tested"), ("results", "Results"), ("repeat", "Repeatability"),
       ("caveats", "Caveats"), ("next", "Where next")]


def elapsed_str(L):
    """Total runtime is frozen once results/.stages/60_demo.done holds the finish epoch; before that it is 'elapsed so far'."""
    b = L.jload("budget.json") or {}
    se = b.get("start_epoch")
    if not se:
        return "unknown (budget.json missing)", None
    fin = None
    try:
        fin = int(L.read("results/.stages/60_demo.done").split()[0])
    except Exception:
        pass
    el = (fin or time.time()) - se
    lab = "Total runtime" if fin else "Elapsed so far (run not finished)"
    return "%s: %dh %02dm, from %s to %s, budget %sh" % (lab, int(el // 3600), int(el % 3600 // 60), b.get("start", "?"),
                                                        time.strftime("%H:%M", time.localtime(fin)) if fin else "now", b.get("total_budget_h", "?")), el


def machine_str(L):
    j = L.jload("env.json") or {}
    if not j:
        return "env.json missing"
    mem = j.get("memsize_bytes")
    return "%s, %s physical / %s logical cores, %s GB RAM, macOS %s (%s)" % (
        j.get("cpu", "?"), j.get("physical_cpu", "?"), j.get("ncpu", "?"),
        ("%.0f" % (mem / 2 ** 30)) if mem else "?", j.get("product_version", "?"), j.get("arch", "?"))


def evidence_blocks(L, h):
    files = sorted(glob.glob(L.p("results/evidence/*.txt")))
    if not files:
        h.append("<p class='sub'>No evidence files yet (results/evidence/*.txt).</p>")
        return
    h.append('<div class="gal">')
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        rel = "demo/assets/evidence/%s.png" % name
        if L.exists(rel):
            h.append(img(L, rel, name))
        else:
            txt = scrub_text(L.read("results/evidence/%s.txt" % name))
            bad = scan_text(txt)
            body = ("<p class='sub'>withheld: failed the privacy check</p>" if bad
                    else "<pre>%s</pre>" % e("\n".join(txt.splitlines()[:60])))
            h.append("<figure>%s<figcaption>%s (text; PNG not rendered yet)</figcaption></figure>" % (body, e(name)))
    h.append("</div>")



PPA_COLS = [("area_um2", "instance area incl. fill and tap (um2)"), ("utilization_frac", "utilization (fraction)"), ("wns_setup_ns", "WNS setup (ns)"),
            ("tns_setup_ns", "TNS setup (ns)"), ("power_total_w", "power total (W)"), ("power_leakage_w", "leakage (W)"),
            ("cell_count", "cells incl. fill/tap"), ("stdcell_count", "std cells"), ("drc_errors", "DRC errors"), ("wall_s", "wall (s)")]


def t2_table(s2):
    h = ["<div class='tw'><table><thead><tr><th>design</th><th>status</th>%s</tr></thead><tbody>" % "".join(
        "<th>%s</th>" % e(c[1]) for c in PPA_COLS)]
    for name, d in (s2.get("designs") or {}).items():
        ppa = dict(d.get("ppa") or {})
        if "utilization_frac" not in ppa and "utilization_pct" in ppa:  # older summaries (pre-rename)
            ppa["utilization_frac"] = ppa["utilization_pct"]
        st = d.get("status", "?")
        extra = ""
        if isinstance(d.get("checks"), dict):
            extra = " (" + ", ".join("%s=%s" % (k, fmt_val(v)) for k, v in d["checks"].items()) + ")"
        if st != "run":
            extra = " - " + str(d.get("reason", ""))
        rt = d.get("rtl")
        if isinstance(rt, dict):
            extra += " [RTL provenance: %s %s]" % (rt.get("last_rtl_commit", "?"), rt.get("note", ""))
        cells = "".join("<td>%s</td>" % e(fmt_val(ppa.get(k, d.get(k)))) if (k in ppa or k in d) else "<td>-</td>" for k, _ in PPA_COLS)
        h.append("<tr><td>%s</td><td>%s%s</td>%s</tr>" % (e(name), e(st), e(extra), cells))
    for name, d in (s2.get("designs") or {}).items():
        pr = d.get("previous_rtl_result")
        if isinstance(pr, dict):
            pp = pr.get("ppa") or {}
            h.append("<tr><td>%s (EARLIER RTL %s, SUPERSEDED)</td><td>%s</td>%s</tr>" % (e(name), e(str(pr.get("rtl_last_commit"))), e(str(pr.get("note", ""))),
                     "".join("<td>%s</td>" % (e(fmt_val(pp[k])) if k in pp else "-") for k, _ in PPA_COLS)))
    h.append("</tbody></table></div>")
    h.append("<p><b>Timing at the reference clock</b> (from the flow's metadata; PASS above means only that the ORFS regression thresholds are met):</p>"
             "<div class='tw'><table><thead><tr><th>design</th><th>reference clock (ns)</th><th>setup WNS (ns)</th><th>setup TNS (ns)</th>"
             "<th>violating setup endpoints</th><th>timing closed</th><th>core area (um2)</th><th>instance area (um2)</th></tr></thead><tbody>")
    for name, d in (s2.get("designs") or {}).items():
        det, ppa = d.get("detail") or {}, d.get("ppa") or {}
        if d.get("status") != "run":
            continue
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(name), e(fmt_val(det.get("reference_clock_period_ns"))), e(fmt_val(ppa.get("wns_setup_ns"))), e(fmt_val(ppa.get("tns_setup_ns"))),
            e(fmt_val(det.get("setup_violating_endpoints"))), "okt" if det.get("timing_closed") else "badt", "yes" if det.get("timing_closed") else "NO",
            e(fmt_val(det.get("core_area_um2"))), e(fmt_val(det.get("instance_area_um2_incl_fill_and_tap")))))
    h.append("</tbody></table></div>")
    tv = s2.get("tool_versions") or []
    h.append("<p class='sub'>Tool versions as reported by the image: %s. A version of &quot;unknown&quot; is what this OpenROAD build prints; "
             "the build is identified by the image digest %s. "
             "The utilization column is the fraction stored in <code>t2_summary.json</code> (0.876 = 87.6 %%). The two gcd reference designs have negative setup slack at their reference clocks, which the shipped regression thresholds allow; "
             "they are therefore reported as within thresholds, not as timing-closed.</p>" % (
                 e("; ".join(t.strip() for t in tv)), e(str(s2.get("image", "?")))))
    return "".join(h)


def t1_block(L, s1):
    v = (s1 or {}).get("values") or {}
    c = (s1 or {}).get("checks") or {}
    if not v:
        return ""
    R = [("random cases per simulator (seed 1234)", "%s (Verilator), %s (Icarus)" % (v.get("cases_random_verilator"), v.get("cases_random_icarus"))),
         ("directed cases", v.get("cases_directed")), ("total cases run", v.get("cases_total")),
         ("mismatching cases / elements, Verilator", "%s / %s" % (v.get("mismatching_cases_verilator"), v.get("mismatching_elements_verilator"))),
         ("mismatching cases / elements, Icarus", "%s / %s" % (v.get("mismatching_cases_icarus"), v.get("mismatching_elements_icarus"))),
         ("result CSV sha256, Verilator", v.get("csv_sha256_verilator")), ("result CSV sha256, Icarus", v.get("csv_sha256_icarus")),
         ("functional coverage bins (hit / total)", "%s (%s %%)" % (" / ".join(str(x) for x in (v.get("coverage_bins_icarus") or [])), v.get("coverage_percent"))),
         ("stalled-stream cases / tiles checked", "%s / %s" % (v.get("stalled_cases"), v.get("tiles"))),
         ("lint: Verilator warnings / Verible violations", "%s / %s" % (v.get("lint_verilator_warnings"), v.get("lint_verible_violations"))),
         ("formal MAC proof (%s)" % v.get("formal_engine"), "BMC depth %s (%s steps checked): %s; induction prove: %s; cover: %s (%s statements reached); negative control (broken MAC) %s" % (
             v.get("formal_bmc_depth"), v.get("formal_bmc_steps_checked"), v.get("formal_bmc_status"), v.get("formal_prove_status"), v.get("formal_cover_status"),
             v.get("formal_cover_reached"), "detected as failing" if c.get("formal_neg_bug_detected") else "NOT detected")),
         ("EQY, MAC incl. multiplier", "%s of %s partitions proved, %s failed (%s); negative control on partition %s: reported not proven equivalent = %s" % (
             v.get("eqy_mac_partitions_proved"), v.get("eqy_mac_partitions"), v.get("eqy_mac_partitions_failed"), v.get("eqy_mac_scope"),
             v.get("eqy_neg_mac_partition"), "bug detected" if c.get("eqy_neg_mac_bug_detected") else "NOT detected")),
         ("EQY, 4x4 array with MAC black-boxed", "%s of %s partitions proved, %s failed (%s); negative control on partition %s: reported not proven equivalent = %s" % (
             v.get("eqy_array_partitions_proved"), v.get("eqy_array_partitions"), v.get("eqy_array_partitions_failed"), v.get("eqy_array_scope"),
             v.get("eqy_neg_array_partition"), "bug detected" if c.get("eqy_neg_array_bug_detected") else "NOT detected")),
         ("netlist compared against", "generic-gate Yosys netlist, %s cells (not the placed-and-routed nangate45 netlist)" % v.get("netlist_cells"))]
    h = ["<table class='kv'><tbody>"]
    for k, x in R:
        h.append("<tr><th>%s</th><td>%s</td></tr>" % (e(k), e(str(x))))
    h.append("</tbody></table>")
    h.append(t1_routed_block(L, s1))
    return "".join(h)


def t1_routed_block(L, s1):
    """Routed-netlist equivalence and gate-level simulation (stage 11_eqy_routed), exactly as the files say."""
    r = (s1 or {}).get("routed")
    top = {k: (s1 or {}).get(k) for k in ("eqy_routed_pass", "gls_routed_pass") if k in (s1 or {})}
    j = L.jload("results/p2_11_eqy_routed.json") or {}
    st, body = demo_part2.marker(L, "11_eqy_routed")
    h = ["<h4>Routed netlist: equivalence and gate-level simulation (stage 11_eqy_routed, marker: %s)</h4>" % e(st)]
    if not r and not top:
        return "".join(h) + "<p class='sub'><span class='b dim'>PENDING</span> no routed results in t1_summary.json yet.</p>"
    h.append("<table class='kv'><tbody>")
    for k, v in top.items():
        h.append("<tr><th>%s</th><td class='%s'>%s%s</td></tr>" % (e(k), "okt" if v else "badt", e(fmt_val(v)),
                 (" &mdash; " + e(str(r.get("gls_routed_status")))) if (k == "gls_routed_pass" and isinstance(r, dict) and r.get("gls_routed_status")) else ""))
    if isinstance(r, dict):
        pp = r.get("eqy_partitions_proved")
        if isinstance(pp, list) and len(pp) == 2:
            h.append("<tr><th>EQY partitions proved</th><td>%s of %s</td></tr>" % (pp[0], pp[1]))
        gs = r.get("gls_by_simulator")
        if isinstance(gs, dict):
            for k, v in gs.items():
                h.append("<tr><th>gate-level simulation, %s</th><td>%s</td></tr>" % (e(k), e(str(v))))
        for k, v in sorted((r.get("checks") or {}).items()):
            h.append("<tr><th>%s <span class='sub'>(evaluated)</span></th><td class='%s'>%s</td></tr>" % (e(k), "okt" if v else "badt", e(fmt_val(v))))
        cne = r.get("checks_not_evaluated")
        if isinstance(cne, dict):
            for k, v in sorted(cne.items()):
                h.append("<tr><th>%s</th><td><span class='b warn'>NOT EVALUATED</span> (neither pass nor fail): %s</td></tr>" % (e(k), e(str(v))))
        sc = r.get("superseded_checks")
        if isinstance(sc, dict):
            for k, v in sc.items():
                h.append("<tr><th>%s <span class='sub'>(superseded, kept)</span></th><td>met: %s; %s</td></tr>" % (e(k), e(fmt_val((v or {}).get("met"))), e(str((v or {}).get("reason", "")))))
        vd = r.get("verdict_definition")
        if vd:
            h.append("<tr><th>verdict_definition</th><td>%s</td></tr>" % e(json.dumps(vd, sort_keys=True) if not isinstance(vd, str) else vd))
        for k in ("eqy_scope", "gls_scope", "note", "routed_netlist", "routed_netlist_sha256"):
            if r.get(k):
                h.append("<tr><th>%s</th><td>%s</td></tr>" % (e(k), e(str(r[k]))))
    h.append("</tbody></table>")
    if st in ("failed", "blocked") and body:
        h.append("<p><b>Stage marker text:</b></p><pre>%s</pre>" % e(scrub_text(body)[:2500]))
    if "P2-R1" in L.read("COORDINATION.md"):
        h.append("<p class='sub'>Why the gate-level criterion is defined as it is: Decision P2-R1 (COORDINATION.md). "
                 "A Verilator gate-level result is only claimed if the file above contains one; a check listed as NOT EVALUATED needs a result that does not exist and is neither passed nor failed.</p>")
    for c in demo_part2.sup_items(j):
        h.append("<p class='sub'>Superseded criterion kept: <code>%s</code> (%s), result: %s</p>" % (e(str(c.get("name"))), e(str(c.get("threshold"))), "pass" if c.get("pass") else "FAIL"))
    return "".join(h)


def repro_table(L, rr):
    if not isinstance(rr, dict):
        return ""
    h = ["<div class='tw'><table><thead><tr><th>check</th><th>verdict</th><th>note</th></tr></thead><tbody>"]
    for c in rr.get("checks", []):
        note = c.get("note") or ""
        if "t2 " in c.get("check", "") and "reused" in note:
            note = "REUSED from the original Task 2 two-clean-run check, not re-run here. " + note
        h.append("<tr><td>%s</td><td class='%s'>%s</td><td>%s</td></tr>" % (e(c.get("check", "")), "okt" if c.get("verdict") == "identical" else "badt",
                                                                       e(c.get("verdict", "")), e(note)))
    t2 = L.jload("results/t2_summary.json") or {}
    for dn, dd in (t2.get("designs") or {}).items():
        det = dd.get("determinism")
        if det and dn != "nangate45/gcd":
            h.append("<tr><td>t2 %s two clean runs (metrics + GDS with timestamps zeroed)</td><td class='%s'>%s</td><td>REUSED from t2_summary.json (original two clean runs); "
                     "not re-run by repro and not part of the repro pass flag</td></tr>" % (e(dn), "okt" if det.get("verdict") == "PASS" else "badt",
                                                                                         "identical" if det.get("verdict") == "PASS" else "different"))
        elif not det and dd.get("status") == "run":
            h.append("<tr><td>t2 %s</td><td>single run</td><td>only one run exists; no determinism verdict</td></tr>" % e(dn))
    h.append("</tbody></table></div>")
    return "".join(h)



def nz(x):
    return "-" if x is None else fmt_val(x)


def frontier_text(L):
    fr = L.jload("results/sweeps/phys_frontier.json")
    if not isinstance(fr, dict):
        return ""
    live = phys_frontier_live(L)
    merged = {}
    for des, by in (fr.get("frontier") or {}).items():
        for u, v in by.items():
            merged.setdefault(des, {})[u] = dict(v)
    for des, by in live.items():
        for u, v in by.items():
            m = merged.setdefault(des, {}).setdefault(u, {})
            if m.get("fastest_closing_period_ns") != v["fastest_closing_period_ns"] or m.get("next_failing_period_ns") != v["next_failing_period_ns"]:
                m.pop("area_um2", None); m.pop("power_total_w", None); m.pop("tightest_swept_period_ns", None)
            m.update(v)
            m["marginal"] = v["wns_at_frontier_ns"] < 0.001
            m["bracketed"] = v["next_failing_period_ns"] is not None
            m["gap"] = (v["fastest_closing_period_ns"] - v["next_failing_period_ns"]) if v["next_failing_period_ns"] is not None else None
    h = ["<h3>Timing-closure frontier per design and utilization (computed from results/sweeps/phys.jsonl; results/sweeps/phys_frontier.json supplies area and power where it is current)</h3><p class='sub'>%s</p>" % e(str(fr.get("note", "")))]
    h.append("<div class='tw'><table><thead><tr><th>design</th><th>core utilization</th><th>points</th><th>tightest period swept (ns)</th><th>fastest closing period (ns)</th>"
             "<th>setup WNS there (ns)</th><th>next tighter period (ns)</th><th>its WNS (ns)</th><th>area (um2)</th><th>power (W)</th><th>remark</th></tr></thead><tbody>")
    for des, by in merged.items():
        for u, v in by.items():
            rem = []
            if v.get("marginal"):
                rem.append("closes with essentially zero margin")
            if not v.get("bracketed"):
                rem.append("not bracketed")
            if des == "systolic_os":
                gap = v.get("gap")
                if gap is not None and gap > 0.06:
                    rem.append("coarse: no bisection between the closing and failing period")
                elif gap is not None:
                    rem.append("bracketed to %s ns" % nz(round(gap, 4)))
                if len(by) < 2:
                    rem.append("one utilization only (40 and 50 % points: see the plan accounting in section 12)")
            h.append("<tr><td>%s</td><td>%s %%</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                e(des), e(u), e(nz(v.get("points"))), e(nz(v.get("tightest_swept_period_ns"))), e(nz(v.get("fastest_closing_period_ns"))),
                e(nz(v.get("wns_at_frontier_ns"))), e(nz(v.get("next_failing_period_ns"))), e(nz(v.get("wns_at_next_failing_ns"))),
                e(nz(v.get("area_um2"))), e(nz(v.get("power_total_w"))), e("; ".join(rem))))
    h.append("</tbody></table></div>")
    for fp in fr.get("failed_points") or []:
        h.append("<p><b>Failed point:</b> %s %s ns u%s: %s. Meaning: %s. Retry: <code>%s</code></p>" % (
            e(str(fp.get("design"))), e(str(fp.get("clock_period_ns"))), e(str(fp.get("core_utilization"))), e(str(fp.get("flow_error_from_log"))),
            e(str(fp.get("meaning"))), e(scrub_text(str(fp.get("retry")))).replace("~/", "~/")))
    return "".join(h)


def arch_coverage(L):
    a = L.jload("results/sweeps/arch_summary.json")
    if not isinstance(a, dict):
        return ""
    h = ["<h3>Sweep A coverage (from results/sweeps/arch_summary.json)</h3><div class='tw'><table><thead><tr><th>workload</th><th>planned</th><th>ok</th><th>error</th>"
         "<th>skipped after timeout</th><th>never reached</th></tr></thead><tbody>"]
    for t, c in (a.get("coverage_per_topology") or {}).items():
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            e(t), c.get("planned"), c.get("ok"), c.get("error"), c.get("skipped_after_timeout"), c.get("not_run")))
    h.append("</tbody></table></div><p>Accounting: every planned point is either done (ok), errored, skipped after a timeout, or <b>not reached</b>: cut because the sweep ran at low "
             "priority behind stage jobs in the one-job-at-a-time lock queue and stopped at its deadline (cost/time only; the points were ordered cheapest-first, so the largest workloads "
             "and arrays are the ones missing). Planned grid %s points; %s ok, %s not reached.</p><ul>" % (a.get("planned_points"), (a.get("status_counts") or {}).get("ok"), a.get("not_run_points")))
    for n in a.get("notes") or []:
        h.append("<li>%s</li>" % e(str(n)))
    h.append("<li>The numbers printed inside narrow heatmap cells can be clipped; read exact values from results/sweeps/arch.jsonl.</li></ul>")
    bd = a.get("best_dataflow_default_sram") or {}
    if bd:
        h.append("<details><summary>Best dataflow per workload and array (default SRAM)</summary><div class='tw'><table><thead><tr><th>workload|array</th><th>best</th>"
                 "<th>total cycles per dataflow</th><th>all three run</th></tr></thead><tbody>")
        for k, v in bd.items():
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(k), e(str(v.get("best"))), e(" \u00b7 ".join("%s %s" % (k, x) for k, x in sorted((v.get("cycles") or {}).items()))), "yes" if v.get("complete") else "NO (best of those run)"))
        h.append("</tbody></table></div></details>")
    return "".join(h)


FORMULA = {"os": ("M, N", "K", "ceil(M/R)*ceil(N/C)", "T + R + C - 2"),
           "ws": ("K, N", "M", "ceil(K/R)*ceil(N/C)", "T + 2R + C - 2"),
           "is": ("K, M", "N", "ceil(K/R)*ceil(M/C)", "T + 2R + C - 2")}


def t3_block(L, s3):
    """Task 3 detail from t3_summary.json and the stage marker text; everything shown is read from those files."""
    h = []
    st, body, _ = stage_marker(L, "30_arch_model")
    if st in ("failed", "blocked") and body:
        h.append("<p><b>Stage marker (%s), written by the arch agent:</b></p><pre>%s</pre>" % (st, e(scrub_text(body)[:3000])))
    h.append(demo_part2.t3_roofline2_block(L, s3) if demo_part2.active(L) else "")
    chk = s3.get("checks") or {}
    if chk:
        h.append("<p><b>Criteria as recorded in results/t3_summary.json%s</b></p><div class='tw'><table><thead><tr><th>check</th><th>result</th></tr></thead><tbody>" % (
            " (this is still the Part 1 file: its roofline_* criteria are the superseded ones)" if "complete" not in s3 and demo_part2.active(L) else ""))
        csr = ((s3.get("roofline") or {}).get("cell_status")) or {}
        for k, v in sorted(chk.items()):
            ne = v is None or (k.startswith(("user_bw_stalls_vs_ai_", "stall_cycles_monotone_in_B_")) and any(
                stt != "evaluated" for jb, stt in csr.items() if jb.startswith("rl2_user_" + k.rsplit("_", 1)[-1] + "_")))
            if ne:
                h.append("<tr><td><code>%s</code></td><td><span class='b warn'>NOT EVALUATED (cost)</span> neither pass nor fail</td></tr>" % e(k))
            else:
                h.append("<tr><td><code>%s</code></td><td class='%s'>%s</td></tr>" % (e(k), "okt" if v else "badt", "pass" if v else "FAIL"))
        h.append("</tbody></table></div>")
    fit = s3.get("fit") or {}
    if fit:
        h.append("<p><b>Analytic model.</b> Each fold takes <code>T + a*R + b*C + c</code> cycles and the total is "
                 "<code>folds*(T + aR + bC + c) + d</code>; (a,b,c,d) were read off the SCALE-Sim source and then re-estimated by least "
                 "squares from simulator runs, as a check. The task's single-constant formula <code>folds*(K + k)</code> is shown for "
                 "comparison: it is wrong because the streamed dimension T is not always K and fill/drain depends on R and C. The constants (a,b,c,d) were derived by reading the "
                 "SCALE-Sim source itself (model/analytic.py), so agreement with the simulator validates that derivation, not an independent oracle.</p>")
        h.append("<div class='tw'><table><thead><tr><th>dataflow</th><th>rows, cols mapped</th><th>streamed T</th><th>folds</th><th>cycles per fold</th>"
                 "<th>derived (a,b,c,d)</th><th>fitted (a,b,c,d)</th><th>held-out max |residual| (cycles)</th>"
                 "<th>single-constant formula, worst relative error</th></tr></thead><tbody>")
        for df in ("ws", "os", "is"):
            f = fit.get(df)
            if not f:
                continue
            fm = FORMULA[df]
            drv = [f["derived"][k] for k in "abcd"]
            if drv[2] != -2 or drv[3] != -1:
                fm = (fm[0], fm[1], fm[2], "see model/analytic.py (table text out of date)")
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%.0f %%</td></tr>" % (
                df, e(fm[0]), e(fm[1]), e(fm[2]), e(fm[3]),
                e(fmt_val([f["derived"][k] for k in "abcd"])), e(", ".join("%.4f" % f["fitted"][k] for k in "abcd")),
                e("%.2g" % f["heldout_max_abs_residual"]), 100 * f["naive_heldout_max_rel_residual"]))
        h.append("</tbody></table></div>")
    rf = s3.get("roofline") or {}
    if rf:
        rule = rf.get("rule") or ""
        m_ag = re.search(r"agreement\s*>=\s*(\d+)\s*%", rule); m_n = re.search(r"(\d+)\s+synthetic GEMMs", rule)
        m_sp = re.search(r"Spearman\(.*?\)\s*<=\s*(-?[\d.]+)", rule)
        gate = "agreement of the predicted label with the stall-based observed label" + (" on at least %s %% of %s layers" % (m_ag.group(1), m_n.group(1)) if m_ag and m_n else "") + \
               ((", Spearman correlation &le; %s" % m_sp.group(1)) if m_sp else "") + " (as written in the rule text below)"
        nfalse = sorted(k for k, v in chk.items() if k.startswith("roofline") and v is False)
        met = chk.get("roofline_agrees")
        h.append("<p><b>Roofline versus SCALE-Sim stalls.</b> Gate: %s. Verdict from the summary: <b>%s</b>. "
                 "The stage marker's &quot;N of M criteria&quot; counts the whole roofline study as one criterion; in the table above that criterion appears as %d "
                 "false per-dataflow booleans (%s).</p>" % (gate, "gate met" if met else ("gate NOT met" if met is False else "not reported"), len(nfalse), e(", ".join(nfalse)) or "none"))
        h.append("<div class='tw'><table><thead><tr><th>dataflow</th><th>agreement (effective traffic)</th>"
                 "<th>agreement (compulsory traffic)</th><th>Spearman (AI, stall fraction)</th><th>layers with stalls</th><th>predicted bound</th><th>observed bound</th></tr></thead><tbody>")
        for df in ("ws", "os", "is"):
            r = rf.get(df)
            if isinstance(r, dict):
                h.append("<tr><td>%s</td><td>%.0f %%</td><td>%.0f %%</td><td>%.2f</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    df, 100 * r["agreement_effective"], 100 * r["agreement_compulsory"], r["spearman_effective"],
                    r["layers_with_stall_cycles"], r["n_pred_bound"], r["n_obs_bound"]))
        h.append("</tbody></table></div>")
        if s3.get("bundled_config_zero_stalls"):
            h.append("<p><b>Finding:</b> with the bundled TPU-like configuration SCALE-Sim reports <b>zero stall cycles</b> for all three dataflows "
                     "(total cycles: %s; stall cycles: %s), so the bundled run alone cannot test the roofline; the roofline study therefore uses a 16x16 array with a lowered DRAM "
                     "interface bandwidth, a setting disclosed in the rule below.</p>" % (
                         e(", ".join("%s %s" % (k, fmt_val(v.get("total_cycles"))) for k, v in (s3.get("bundled_summary") or {}).items())),
                         e(", ".join("%s %s" % (k, fmt_val(v.get("stall_cycles"))) for k, v in (s3.get("bundled_summary") or {}).items()))))
        if rf.get("rule"):
            h.append("<div class='note'><b>Editor's note (added by the demo build, not part of the verbatim text):</b> the opening words of the rule below, "
                     "&quot;fixed here, before any result was looked at&quot;, are inaccurate as written. The rule's own CHRONOLOGY paragraph at the end records that the first "
                     "observed signal could not discriminate and that the stall-based observed signal and the effective-traffic roofline were adopted afterwards (post-hoc). "
                     "The code was left unchanged so that the repeatability run stays valid.</div>")
            h.append("<details open><summary>Roofline rule and chronology, verbatim from t3_summary.json (includes the disclosed post-hoc change of the observed signal)</summary><pre>%s</pre></details>" % e(rf["rule"]))
    return "".join(h)


def sweep_audit(L):
    """Facts computed from the sweep JSONL files, the t2 summary and the drivers' own docstrings."""
    out = []
    rowsd = {}
    for name in ("arch", "phys"):
        rows = []
        for ln in L.read("results/sweeps/%s.jsonl" % name).splitlines():
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        rowsd[name] = rows
        for r in [r for r in rows if r.get("status") not in ("ok", None)]:
            key = str(r.get("key") or r.get("variant"))
            fix = ("delete its line from results/sweeps/arch.jsonl and rerun <code>make sweeps</code> (the driver skips completed keys; it starts no point after the "
                   "sweep deadline in budget.json, so extend <code>deadline_sweeps_stop_epoch</code> first)") if name == "arch" else \
                  "see the failed-point retry command in the sweep B section (the flow is deterministic, a rerun is expected to fail the same way)"
            out.append("sweep %s: point <code>%s</code> has status <b>%s</b> after %s s with error text %s; the cause was not verified. It has no metrics. To retry: %s." % (
                name, e(key), e(str(r.get("status"))), e(str(r.get("wall_s", "?"))), ("&quot;%s&quot;" % e(str(r.get("error")))) if r.get("error") else "empty", fix))
    rows = rowsd["arch"]
    if rows:
        ax = {k: sorted({str(r.get(k)) for r in rows if r.get(k) is not None}) for k in ("dataflow", "sram")}
        by_topo = {}
        for r in rows:
            by_topo.setdefault(str(r.get("topo")), set()).add("%sx%s" % (r.get("rows"), r.get("cols")))
        nl = {t: sorted({r.get("n_layers") for r in rows if str(r.get("topo")) == t and r.get("n_layers") is not None}) for t in by_topo}
        out.append("sweep arch covers %d points: dataflows %s, SRAM levels %s. Arrays per workload: %s. Layers per workload: %s. Workloads are not run on every array size, so comparisons "
                   "across array sizes mix workloads; a point not listed is absent, not zero." % (
                       len(rows), ", ".join(ax["dataflow"]), ", ".join(ax["sram"]),
                       "; ".join("%s: %s" % (t, ", ".join(sorted(v))) for t, v in sorted(by_topo.items())),
                       "; ".join("%s: %s" % (t, ", ".join(str(x) for x in v)) for t, v in sorted(nl.items()))))
        if all(r.get("stall_cycles") == 0 for r in rows if r.get("status") == "ok"):
            doc = re.sub(r"\s+", " ", L.read("sweeps/arch_sweep.py"))
            m = re.search(r"CALC interface-bandwidth mode[^.]*\.[^.]*\.", doc)
            out.append("every sweep A point reports <code>stall_cycles = 0</code>: this is structural, not a finding. From sweeps/arch_sweep.py: &quot;%s&quot;" % (
                e(m.group(0)) if m else "see the driver's docstring"))
    rows = rowsd["phys"]
    if rows:
        t2 = L.jload("results/t2_summary.json") or {}
        ref = (((t2.get("designs") or {}).get("nangate45/gcd") or {}).get("detail") or {})
        per = [r["clock_period_ns"] for r in rows if "clock_period_ns" in r and r.get("design") == "gcd"]
        if per and ref.get("reference_clock_period_ns") is not None:
            out.append("sweep B for gcd runs periods %.3g to %.3g ns, looser than the %s ns reference clock%s." % (
                min(per), max(per), ref["reference_clock_period_ns"], ", which does not close timing" if ref.get("timing_closed") is False else ""))
        out.append("sweep B systolic_os slice: %d point(s) on disk." % len([r for r in rows if r.get("design") == "systolic_os"]))
    return out


def build_html(L, rows, vm):
    el_s, _ = elapsed_str(L)
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<title>AI chip design lab: demo</title><style>%s</style></head><body><main>" % CSS]
    now = time.strftime("%Y-%m-%d %H:%M %Z")
    h.append("<h1>AI chip design lab</h1><p class='sub'>An open-source flow from a multiply-accumulate unit to a laid-out chip, "
             "built and checked unattended on an old Intel MacBook. Generated %s from the files on disk; nothing on this page "
             "is typed in by hand except the explanations.</p>" % e(now))
    nav = list(NAV) + ([("p2sum", "Part 2 summary"), ("p2changes", "What changed"), ("p2tests", "New tests"), ("p2dec", "Decisions"), ("p2cav", "Part 2 caveats"), ("p2next", "Next")] if demo_part2.active(L) else [])
    h.append("<nav>%s</nav>" % " ".join('<a href="#%s">%d. %s</a>' % (i, k + 1, t) for k, (i, t) in enumerate(nav)))

    # 1 summary
    h.append('<h2 id="summary">1. Summary</h2>')
    counts = {}
    for r in rows:
        counts[r.state] = counts.get(r.state, 0) + 1
    h.append('<p>%s</p>' % " ".join("%s &times; %d" % (badge(s), n) for s, n in counts.items()))
    h.append('<div class="tw"><table class="big"><thead><tr><th>Check</th><th>Status</th><th>Detail (from marker / summary file)</th></tr></thead><tbody>')
    for r in rows:
        lk = (" " + link(L, r.link, "file")) if r.link else ""
        h.append("<tr><td>%s</td><td>%s</td><td>%s%s</td></tr>" % (e(r.label), badge(r.state), e(r.detail), lk))
    h.append("</tbody></table></div>")
    h.append("<p class='sub'>PASS needs the stage's .done marker, no input file committed or edited after the result (else it shows RUNNING), and <code>\"pass\": true</code> in its summary JSON; "
             "a missing piece is shown as PENDING, RUNNING, BLOCKED or UNKNOWN, never assumed.</p>")
    route = ""
    m = re.search(r'route:\s*"([^"]+)"', L.read("versions.lock"))
    if m:
        route = m.group(1)
    h.append('<div class="cards"><div class="card"><span class="sub">Runtime</span><b>%s</b></div>'
             '<div class="card"><span class="sub">Runtime route</span><b>%s</b></div>'
             '<div class="card"><span class="sub">Machine</span><b>%s</b></div>'
             '<div class="card"><span class="sub">VM at end of run</span><b>%s</b></div></div>' % (
                 e(el_s), e(route or "not recorded yet"), e(machine_str(L)),
                 e({"running": "left running", "stopped": "stopped"}.get(vm, "not stated yet (set at final packaging)"))))
    h.append("<h3>Proof that it builds and runs</h3><p class='sub'>Real terminal output saved by the stage that produced it, "
             "rendered as an image (not an OS screenshot).</p>")
    evidence_blocks(L, h)

    # 2 created
    h.append('<h2 id="created">2. What was created</h2><p>Important files, one line each. Struck-through names do not exist yet.</p>')
    h.append('<div class="tw"><table><tbody>')
    for rel, what in TREE:
        h.append("<tr><td>%s</td><td>%s</td></tr>" % (link(L, rel.rstrip("/") if rel.endswith("/") else rel, rel), e(what)))
    h.append("</tbody></table></div>")

    # 3 concepts
    h.append('<h2 id="concepts">3. Concepts, from basics</h2><p>In the order a multiply travels from an idea to a chip. '
             "Each box links to the file in this lab that demonstrates it.</p>")
    for i, (t, body, files) in enumerate(CONCEPTS, 1):
        h.append('<div class="concept"><h3>%d. %s</h3><p>%s</p><p class="sub">See: %s</p></div>' % (
            i, e(t), body, ", ".join(link(L, f) for f in files)))

    # 4 tools
    h.append('<h2 id="tools">4. Tool map</h2><div class="tw"><table><thead><tr><th>Open-source tool (used here)</th>'
             "<th>Chip-design stage</th><th>Commercial equivalent</th></tr></thead><tbody>")
    for a, b, c in TOOLS:
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(a), e(b), e(c)))
    h.append("</tbody></table></div>")

    # 5 tests
    h.append('<h2 id="tests">5. How each thing was tested</h2>')
    for title, stage, summ, oracle, cmd, inputs, crit in TESTS:
        state, detail, s = task_state(L, stage, summ)
        h.append("<h3>%s %s</h3><table class='kv'><tbody>" % (e(title), badge(state)))
        h.append("<tr><th>oracle (what is right)</th><td>%s</td></tr><tr><th>command</th><td>%s</td></tr>"
                 "<tr><th>inputs and seeds</th><td>%s</td></tr><tr><th>pass criteria</th><td>%s</td></tr>"
                 "<tr><th>result file</th><td>%s</td></tr><tr><th>logs (local to the lab machine, not in the repository)</th><td><code>logs/%s/</code></td></tr></tbody></table>" % (
                     oracle, e(cmd), e(inputs), e(crit), link(L, summ), e(stage)))
        if isinstance(s, dict) and stage == "10_rtl_verify":
            h.append("<p><b>Actual result</b> (picked from the values in t1_summary.json)</p>" + t1_block(L, s))
        elif isinstance(s, dict) and stage == "30_arch_model":
            h.append("<p><b>Actual result</b> (read from the summary file and stage marker)</p>" + t3_block(L, s))
        elif isinstance(s, dict):
            h.append("<p><b>Actual result</b> (as written to the summary file)</p>" + kv_table(s))
        else:
            h.append("<p class='sub'>Actual result: %s</p>" % e(detail))
    h.append("<h3>Sweeps</h3><p>Sweep A varies array size, dataflow, topology and SRAM size in SCALE-Sim; sweep B varies clock period and "
             "core utilization through OpenROAD. Each point is one JSON line keyed by its parameters (resumable, per-point timeout).</p>")
    for name in ("arch", "phys"):
        pts = sweep_points(L, name)
        if pts:
            h.append("<p>%s: %d point(s) on disk%s.</p>" % (link(L, "results/sweeps/%s.jsonl" % name), pts[0],
                                                              ", %d unparsable" % pts[1] if pts[1] else ""))
        else:
            h.append("<p>results/sweeps/%s.jsonl: <span class='b dim'>PENDING</span> no points yet.</p>" % name)

    # 6 results
    h.append('<h2 id="results">6. Results</h2>')
    groups = [("Task 1: waveform and verification", ("t1_",)), ("Task 2: layouts", ("t2_",)),
              ("Task 3: cycles versus analytic model, roofline", ("t3_",)),
              ("Sweep A: architecture heatmaps", ("sweepA_", "sweepa_")),
              ("Sweep B: heatmaps and timing-closure frontier", ("sweepB_", "sweepb_"))]
    used = set()
    for title, pres in groups:
        ims = images_for(L, pres)
        used.update(ims)
        h.append("<h3>%s</h3>" % e(title))
        if ims:
            h.append('<div class="gal">%s</div>' % "".join(img(L, r, caption_of(r)) for r in ims))
        else:
            h.append("<p class='sub'><span class='b dim'>PENDING</span> no images on disk yet.</p>")
    rest = [r for r in all_result_images(L) if r not in used]
    if rest:
        h.append("<h3>Other plots</h3><div class='gal'>%s</div>" % "".join(img(L, r, caption_of(r)) for r in rest))
    h.append(arch_coverage(L))
    h.append(frontier_text(L))
    h.append("<h3>PPA (power, performance, area) table</h3>")
    s2 = L.jload("results/t2_summary.json")
    if isinstance(s2, dict):
        h.append(t2_table(s2))
    else:
        h.append("<p class='sub'><span class='b dim'>PENDING</span> results/t2_summary.json not written yet.</p>")
    for name in ("phys", "arch"):
        pts = L.read("results/sweeps/%s.jsonl" % name).strip().splitlines()
        if pts:
            try:
                last = json.loads(pts[-1])
                h.append("<details><summary>latest point in results/sweeps/%s.jsonl (of %d)</summary>%s</details>" % (
                    name, len(pts), kv_table(last)))
            except Exception:
                pass

    # 7 repeatability
    h.append('<h2 id="repeat">7. Repeatability</h2>')
    rr = L.jload("results/repro_report.json")
    sr, dr, _ = task_state(L, "50_repro", "results/repro_report.json")
    h.append("<p>%s %s</p>" % (badge(sr), e(dr)))
    if isinstance(rr, dict):
        h.append("<p>What was re-run: Task 1 (all 10,000 random + directed cases, formal and equivalence) and Task 3 (one fresh pass) in clean directories with the pinned images; "
                 "Task 2 is <b>not</b> re-run: its verdicts reuse the two original clean runs of each gcd design. systolic_os has a single run.</p>" + repro_table(L, rr))
    else:
        h.append("<p class='sub'>The clean-directory rerun of Tasks 1-3 with the pinned images runs late in the budget; "
                 "until then there is no repro report and none is invented.</p>")
    h.append("<h3>Images and pinned versions</h3><pre>%s</pre>" % e(scrub_text(L.read("coord/images.env")) or "coord/images.env missing"))
    vl = scrub_text(L.read("versions.lock"))
    h.append("<details><summary>versions.lock (all pins, URLs, SHA256)</summary><pre>%s</pre></details>" % e(vl or "missing"))

    # 8 caveats
    h.append('<h2 id="caveats">8. Problems and honest caveats</h2>')
    items = []
    for r in rows:
        if r.state in ("FAIL", "BLOCKED"):
            items.append("<li>%s <b>%s</b>: %s</li>" % (badge(r.state), e(r.label), e(r.detail)))
    for f in sorted(glob.glob(L.p("results/.stages/*.failed")) + glob.glob(L.p("results/.stages/*.blocked"))):
        body = scrub_text(L.read(os.path.relpath(f, L.lab)).strip())
        items.append("<li><b>%s</b><pre>%s</pre></li>" % (e(os.path.basename(f)), e(body[:2500])))
    for r in rows:
        if r.state in ("PENDING", "RUNNING", "UNKNOWN"):
            items.append("<li>%s <b>%s</b> was not finished when this page was built: %s</li>" % (badge(r.state), e(r.label), e(r.detail)))
    for tname in ("t1", "t2", "t3", "repro_report"):
        s = L.jload("results/%s%s.json" % (tname, "_summary" if tname != "repro_report" else ""))
        if isinstance(s, dict):
            for k, v in flatten(s):
                if v is False and not k.endswith(".gds_identical"):
                    items.append("<li>%s: <code>%s</code> is false</li>" % (e(tname), e(k)))
    items.append("<li>Task 2 determinism: raw GDS files of the two clean runs differ byte-wise only in the GDSII BGNLIB/BGNSTR timestamp records; "
                 "with timestamps zeroed they are identical and all compared metric fields match (see the determinism evidence images).</li>")
    for line in sweep_audit(L):
        items.append("<li>%s</li>" % line)
    t1v = ((L.jload("results/t1_summary.json") or {}).get("values") or {})
    items.append("<li><code>demo/run_demo.sh</code> runs only the sby tasks <code>prove</code> (unbounded induction) and <code>cover</code>; "
                 "the full BMC depth-20 run is part of <code>make t1</code> (%s s in the official run). %s</li>" % (
                     e(str(t1v.get("formal_bmc_seconds", "?"))), e(demo_timing(L))))
    items.append("<li>EQY compares the RTL with Yosys's generic-gate netlist (<code>synth; abc; opt</code>, no liberty cells). The placed-and-routed nangate45 netlist has no "
                 "equivalence proof: ORFS's own logic-equivalence step is disabled.</li>")
    d11 = re.search(r"^\| 11 \|.*$", L.read("COORDINATION.md"), re.M)
    if d11:
        cmd = re.search(r"`(scripts/with_lock.sh[^`]*)`", d11.group(0))
        items.append("<li>Timeloop/Accelergy (optional in the task) was <b>skipped</b> (COORDINATION.md Decision 11). To add it: <code>%s</code></li>" % (
            e(cmd.group(1)) if cmd else "see Decision 11 in COORDINATION.md"))
    items.append("<li>Task 2 'PASS' means the metrics satisfy ORFS's shipped regression thresholds (<code>rules-base.json</code>); both gcd reference designs have negative setup slack at their reference "
                 "clocks and are not timing-closed (table in section 6). 'WNS &ge; 0 means timing is met' in the concepts section is the general definition, not what the reference runs achieve.</li>")
    items.append("<li>Logs under <code>logs/</code> are local to the machine that ran the lab and are not part of the repository; links to them on this page only work there. Some stage logs "
                 "are overwritten by reruns (for example <code>logs/30_arch_model/</code> by the repro run).</li>")
    items.append("<li>ORFS is pinned to image tag 26Q3-600 because newer tags removed the shipped threshold files (<code>rules-base.json</code>, "
                 "<code>checkMetadata.py</code>) that Task 2 compares against (COORDINATION.md Decision 6).</li>")
    items.append("<li>The optional Kepler logic-equivalence step inside the ORFS flow is disabled (<code>LEC_CHECK=0</code>) because it "
                 "crashes with an illegal instruction on this CPU; it does not affect PPA numbers.</li>")
    items.append("<li>Numbers come from a 2-core machine shared by several jobs; wall-clock figures are indicative only.</li>")
    b = L.jload("budget.json") or {}
    items.append("<li>The owner capped the run at %s h (the original task text says 14 h), so all stage budgets were scaled down; "
                 "anything cut for time is listed above.</li>" % e(str(b.get("total_budget_h", "?"))))
    h.append("<ul>%s</ul>" % "".join(items))
    coord = L.read("COORDINATION.md")
    mo = re.search(r"## Needs owner\s*(.*?)(?=\n## |\Z)", coord, re.S)
    if mo and mo.group(1).strip() and "(none" not in mo.group(1).lower()[:20]:
        h.append("<h3>Needs the owner (from COORDINATION.md)</h3><pre>%s</pre>" % e(scrub_text(mo.group(1).strip())[:4000]))
    h.append("<p class='sub'>Fix commands for blocked stages are inside the marker text shown above.</p>")

    # 9 next
    h.append('<h2 id="next">9. Where to go next</h2><ol>')
    for t, why in NEXT:
        h.append("<li><b>%s</b><br><span class='sub'>%s</span></li>" % (t, why))
    h.append("</ol>")
    if demo_part2.active(L):
        h.append(demo_part2.part2_html(L, rows, L.jload("coord/part2_before.json") or {"rows": []}))
    h.append("<hr><p class='sub'>Re-generate this page at any time: <code>python3 scripts/demo_build.py</code>. "
             "5-minute re-run: <code>bash demo/run_demo.sh</code>.</p></main></body></html>")
    return "".join(h)


def md_table(rows):
    out = ["| Check | Status | Detail |", "|---|---|---|"]
    for r in rows:
        out.append("| %s | **%s** | %s |" % (r.label, r.state, r.detail.replace("|", "/")))
    return "\n".join(out)


def bmc_secs(L):
    return str(((L.jload("results/t1_summary.json") or {}).get("values") or {}).get("formal_bmc_seconds", "?"))


def demo_timing(L):
    t = L.jload(".cache/demo_run/timing.json")
    if not t:
        return "Short demo run time: not measured yet (run it once; the result is recorded in .cache/demo_run/timing.json)."
    return ("Last measured run time of the short demo: %s s with %s cases (finished %s, load average at the end: %s). The load average reflects "
            "other jobs on the same 2-core machine, so a quiet machine is faster." % (t.get("total_s"), t.get("cases"), t.get("finished"), t.get("load_average")))


def build_demo_readme(L, rows, vm):
    el_s, _ = elapsed_str(L)
    vmtxt = {"running": "The Colima VM is left RUNNING at the end of the run because demo/run_demo.sh needs it. Stop it with: source ~/ai-chip-lab/env.sh && colima stop",
             "stopped": "The Colima VM was stopped at the end of the run (`colima stop`); start it before re-running."}.get(
        vm, "Final VM state is not recorded yet (it is written at final packaging); check with `colima status`.")
    return """AI chip design lab - demo summary
(generated by scripts/demo_build.py from files on disk)

Open demo/index.html in a browser (double-click; no server needed).

STATUS
%s

%s
Machine: %s

START / STOP THE VM
  source ~/ai-chip-lab/env.sh && colima start      # starts the Linux VM that runs the containers
  source ~/ai-chip-lab/env.sh && colima stop       # stops it (frees RAM and CPU)
  %s

RE-RUN THE SHORT DEMO
  source ~/ai-chip-lab/env.sh && bash demo/run_demo.sh
  Runs: Task 1 on 200 cases (Verilator + Icarus), the formal MAC proof restricted to the sby tasks "prove" (unbounded
  induction) and "cover", one SCALE-Sim run vs the analytic model, and ORFS's threshold check on the existing outputs.
  The full BMC-20 formal run is part of `make t1`, not of this cut (%s s in the official run).
  %s

FREE DISK AFTERWARDS (all inside ~/ai-chip-lab; nothing outside the lab was changed)
  Safe to delete (re-creatable, results already saved under results/ and demo/):
    orfs/work/        ORFS working directories (large); demo/run_demo.sh uses the committed copy results/t2/metadata_*.json, so it is not needed for the demo
    logs/             raw run logs (not committed)
    downloads/        installer archives
    .venv*/           local Python environments
    docker images:    source env.sh && docker image rm <lab-sim image> <ORFS image>   (needs a re-pull/rebuild to re-run)
    the whole VM:     source env.sh && colima delete    (removes the VM disk, up to 60 GiB sparse)
  Keep: results/, demo/, versions.lock, the source directories (rtl/ tb/ formal/ eqy/ model/ arch/ orfs/ sweeps/ scripts/).
  Safe to remove everything: delete the ~/ai-chip-lab directory after `colima delete`.
""" % ("\n".join("  %-8s %s - %s" % (r.state, r.label, r.detail) for r in rows), el_s, machine_str(L), vmtxt, bmc_secs(L), demo_timing(L))


def recipes_note_md(L):
    """The generated note on which make recipes really ran (results/make_recipes.md, verbatim) - replaces the Part 1 'honesty note'."""
    t = L.read("results/make_recipes.md")
    if t.strip():
        return t.strip() + "\n"
    return ("Which `make` recipes were executed for real: not recorded yet (results/make_recipes.md is generated by the recipe recorder; "
            "in Part 1 only `make preflight` was executed as a recipe).\n")


def build_root_readme(L, rows, vm):
    el_s, _ = elapsed_str(L)
    h = []
    h.append("# AI chip design lab\n\nAn open-source, reproducible lab that takes a small AI accelerator from a multiply-accumulate unit to a "
             "laid-out chip using only open tools, run unattended on an old 2-core Intel MacBook with 8 GB of RAM (no Homebrew, "
             "no sudo; a Colima VM runs the containers). Three baseline checks establish objective truth (answers checked against "
             "math, a second independent tool, or published reference values); sweeps then explore the design space.\n")
    h.append("Open [`demo/index.html`](demo/index.html) for the full walk-through: concepts, tool map, how each result was tested, "
             "plots, and honest caveats.\n")
    h.append("## Status\n\nGenerated from the files in this repository by `python3 scripts/demo_build.py` (%s).\n" % el_s)
    h.append(md_table(rows))
    if demo_part2.active(L):
        h.append("\n" + demo_part2.part2_md(L, rows, L.jload("coord/part2_before.json") or {"rows": []}))
    h.append("\nPASS means the stage's `.done` marker exists and its summary JSON says `\"pass\": true`. Anything unfinished is shown as "
             "PENDING/RUNNING/BLOCKED/UNKNOWN and not assumed.\n")
    h.append("## What is in it\n\n| Path | What |\n|---|---|")
    for rel, what in TREE:
        h.append("| `%s` | %s |" % (rel, what))
    h.append("\n## Reproduce\n\n```sh\nsource env.sh                 # lab-local PATH; all VM/Docker state stays inside this directory\n"
             "make preflight                # machine facts\n"
             "make runtime images           # Colima VM + pinned images (digests in coord/images.env, versions.lock)\n"
             "make t1                       # Task 1: RTL vs NumPy on 2 simulators, formal, equivalence (full run incl. BMC-20)\n"
             "make t2                       # Task 2: gcd on nangate45 + sky130hd, twice from clean (about 35 min of ORFS)\n"
             "make t2-stretch               # systolic_os through ORFS (about 30 min)\n"
             "make t3                       # Task 3: SCALE-Sim vs analytic model + roofline (exits non-zero while the roofline criterion fails)\n"
             "make sweeps                   # architecture + physical sweeps; they start no new point after the sweep deadline in budget.json\n"
             "make repro                    # reruns Task 1 in full and the cheap Task 3 set clean and compares; Task 2 runs come from results/t2_reruns.json\n"
             "make demo                     # plots + evidence PNGs + demo/index.html + this README\n"
             "make all                      # fail-soft loop over the above, always builds the demo, exits non-zero listing failed stages\n"
             "bash demo/run_demo.sh         # short cut (cached images, scratch output dir); needs the VM running\n```\n\n"
             + recipes_note_md(L))
    ev = sorted(glob.glob(L.p("results/evidence/*.txt")))
    h.append("## Evidence that it builds and runs\n\nTerminal output saved by each stage, rendered to images from the saved text (not OS screenshots).\n")
    got = False
    for f in ev:
        n = os.path.splitext(os.path.basename(f))[0]
        if L.exists("demo/assets/evidence/%s.png" % n):
            h.append("![%s](demo/assets/evidence/%s.png)\n" % (n, n))
            got = True
    if not got:
        h.append("_No evidence images rendered yet._\n")
    h.append("## Results\n")
    ims = all_result_images(L)
    if ims:
        for r in ims:
            h.append("![%s](%s)\n" % (caption_of(r), r))
    else:
        h.append("_No result plots on disk yet._\n")
    h.append("## Notes\n\n- Versions, image digests, URLs and SHA256s: `versions.lock`, `coord/images.env`.\n"
             "- %s\n- No personal paths, hostnames or credentials are stored in this repository; a pre-commit hook and "
             "`scripts/evidence_privacy.py` enforce that.\n" % {
                 "running": "The Colima VM is left RUNNING at the end of the run because demo/run_demo.sh needs it. Stop it with: source ~/ai-chip-lab/env.sh && colima stop",
                 "stopped": "The Colima VM was stopped at the end of the run; `source env.sh && colima start` brings it back.",
             }.get(vm, "VM end-state is stated at final packaging; start/stop commands are in `demo/README.md`."))
    return "\n".join(h) + "\n"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default=os.environ.get("LAB", HOME_LAB))
    ap.add_argument("--out", default=None)
    ap.add_argument("--vm", choices=["running", "stopped"], default=None)
    a = ap.parse_args()
    L = Lab(os.path.abspath(a.lab), os.path.abspath(a.out or a.lab))
    rows = build_rows(L)
    outs = {"demo/index.html": build_html(L, rows, a.vm), "demo/README.md": build_demo_readme(L, rows, a.vm),
            "README.md": build_root_readme(L, rows, a.vm)}
    bad = False
    for rel, text in outs.items():
        text = scrub_text(text)
        f = scan_text(text)
        if f:
            print("PRIVACY: %s has findings %s - scrubbing" % (rel, f[:5]))
            bad = True
            # last-resort redaction of the offending lines
            lines = text.split("\n")
            for ln, _ in f:
                lines[ln - 1] = "[line withheld by privacy check]"
            text = "\n".join(lines)
        write(os.path.join(L.out, rel), text)
        print("wrote", rel)
    for r in rows:
        print("%-8s %s" % (r.state, r.label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
