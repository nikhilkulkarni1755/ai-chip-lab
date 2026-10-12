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
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evidence_privacy import scan_text, scrub_text  # noqa: E402

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


def task_state(L, stage, summary_rel):
    """PASS only with a .done marker AND summary pass==true. Returns (state, detail, summary_dict)."""
    st, body, _ = stage_marker(L, stage)
    s = L.jload(summary_rel)
    first = (body.splitlines() or [""])[0][:200]
    if st == "failed":
        return "FAIL", "marker .failed: " + first, s
    if st == "blocked":
        return "BLOCKED", "marker .blocked: " + first, s
    if isinstance(s, dict) and isinstance(s.get("pass"), bool):
        if s["pass"] and st in ("done", "none"):
            return "PASS", "%s: pass=true" % summary_rel.split("/")[-1], s
        if s["pass"] and st == "running":
            return "RUNNING", "summary says pass=true but a re-run is in progress", s
        return "FAIL", "%s: pass=false" % summary_rel.split("/")[-1], s
    if st == "running":
        return "RUNNING", "stage in progress" + (": " + first if first else ""), s
    if st == "done":
        return "UNKNOWN", "stage .done but %s missing or has no boolean 'pass'" % summary_rel, s
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
        if hits:
            okk = all(v for _, v in hits)
            rows.append(Row(label, "PASS" if okk else "FAIL",
                            "checks: " + ", ".join("%s=%s" % (k, fmt_val(v)) for k, v in hits), "results/t1_summary.json"))
        else:
            rows.append(Row(label, "PENDING" if s1 in ("PENDING", "RUNNING") else ("BLOCKED" if s1 == "BLOCKED" else "UNKNOWN"),
                            "not reported in t1_summary.json yet" if t1 else "waits for Task 1 summary", None))
    s2, d2, _ = task_state(L, "20_pnr_ref", "results/t2_summary.json")
    rows.append(Row("Task 2: OpenROAD reference flow vs shipped thresholds", s2, d2, "results/t2_summary.json"))
    s3, d3, _ = task_state(L, "30_arch_model", "results/t3_summary.json")
    rows.append(Row("Task 3: SCALE-Sim vs analytical model", s3, d3, "results/t3_summary.json"))

    group = stage_group(L, "40_sweeps")
    for name, label in (("arch", "Sweep A: architecture (SCALE-Sim)"), ("phys", "Sweep B: physical (ORFS)")):
        pts = sweep_points(L, name)
        gstates = [g for g in group if g[0].lower().endswith(("_" + name[0], name[0], name)) or name in g[0].lower()
                   or g[0].lower().endswith(("_a", "a") if name == "arch" else ("_b", "b"))]
        gs = gstates or group
        states = [g[1] for g in gs]
        if "failed" in states:
            state, why = "FAIL", "marker .failed: " + next((g[2].splitlines() or [""])[0][:160] for g in gs if g[1] == "failed")
        elif "blocked" in states:
            state, why = "BLOCKED", "marker .blocked: " + next((g[2].splitlines() or [""])[0][:160] for g in gs if g[1] == "blocked")
        elif "running" in states:
            state, why = "RUNNING", "sweep in progress"
        elif "done" in states and pts and pts[0] > 0:
            state, why = "PASS", "sweep stage done"
        elif pts and pts[0] > 0:
            state, why = "RUNNING", "points on disk, no .done marker yet (partial results are shown)"
        else:
            state, why = "PENDING", "no points yet"
        if pts:
            why += "; %d point(s) in results/sweeps/%s.jsonl%s" % (pts[0], name, ("; %d unparsable line(s)" % pts[1]) if pts[1] else "")
        rows.append(Row(label, state, why, "results/sweeps/%s.jsonl" % name if pts else None))

    sr, dr, _ = task_state(L, "50_repro", "results/repro_report.json")
    rows.append(Row("Repeatability rerun (repro)", sr, dr, "results/repro_report.json"))
    return rows


# ----------------------------------------------------------------------------- html helpers
BADGE = {"PASS": "ok", "FAIL": "bad", "BLOCKED": "warn", "RUNNING": "run", "PENDING": "dim", "UNKNOWN": "dim"}


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
    ("docker/requirements.lock", "Hash-locked Python dependencies installed in the lab-sim image."),
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
    ("demo/run_demo.sh", "The 5-minute re-run: Task 1 (200 cases, both simulators), formal proof, one SCALE-Sim run, ORFS check."),
    ("demo/assets/", "Waveform, layout, plots and evidence PNGs referenced by this page."),
    ("Makefile", "make preflight runtime images t1 t2 t3 sweeps repro demo all."),
]

CONCEPTS = [
    ("MAC: multiply-accumulate",
     "The atom of neural-network arithmetic: <code>acc = acc + a*b</code>. A matrix product is nothing but many of "
     "these. Here a and b are signed 8-bit integers and the accumulator is 32-bit, so a long sum cannot overflow "
     "(127*127*K stays far below 2<sup>31</sup> for any realistic K).",
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
     "make t1 (runs scripts/t1_run.sh inside the lab-sim image).",
     "Random INT8 matrices from seed 1234, tiled onto the 4x4 array, plus directed cases (all -128, all 127, zeros, identity, "
     "clear mid-stream, K=1, shapes not a multiple of the array size). Run on Verilator and Icarus.",
     "0 mismatches on both simulators; sha256 of the two result CSVs equal; formal proof passes; EQY passes."),
    ("Task 2 - OpenROAD reference flow", "20_pnr_ref", "results/t2_summary.json",
     "Published thresholds shipped with ORFS (<code>rules-base.json</code>), checked by ORFS's own <code>checkMetadata.py</code>.",
     "make t2 (runs scripts/t2_run.sh and scripts/t2_check.sh with the pinned ORFS image).",
     "nangate45 gcd (and sky130hd gcd if time allowed), each twice from a clean directory with the same image digest and core count.",
     "All metrics within thresholds; final DRC count 0; GDS exists; the two runs give identical metrics."),
    ("Task 3 - SCALE-Sim vs analytical model", "30_arch_model", "results/t3_summary.json",
     "A closed-form model (folds x (K + fill/drain)) and the roofline model, both in <code>model/analytic.py</code>.",
     "make t3 (runs scripts/t3_run.sh in the lab-sim image).",
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
    b = L.jload("budget.json") or {}
    se = b.get("start_epoch")
    if not se:
        return "unknown (budget.json missing)", None
    el = time.time() - se
    return "%dh %02dm since start (%s), budget %sh" % (int(el // 3600), int(el % 3600 // 60), b.get("start", "?"),
                                                       b.get("total_budget_h", "?")), el


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



PPA_COLS = [("area_um2", "area (um2)"), ("utilization_frac", "utilization (fraction)"), ("wns_setup_ns", "WNS setup (ns)"),
            ("tns_setup_ns", "TNS setup (ns)"), ("power_total_w", "power total (W)"), ("power_leakage_w", "leakage (W)"),
            ("cell_count", "cells"), ("drc_errors", "DRC errors"), ("wall_s", "wall (s)")]


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
    h.append("</tbody></table></div>")
    tv = s2.get("tool_versions") or []
    h.append("<p class='sub'>Tool versions as reported by the image: %s. A version of &quot;unknown&quot; is what this OpenROAD build prints; "
             "the build is identified by the image digest %s. "
             "The utilization column is the fraction stored in <code>t2_summary.json</code> (0.876 = 87.6 %%). Negative setup WNS can still be "
             "within the shipped thresholds because those rules allow a margin.</p>" % (
                 e("; ".join(t.strip() for t in tv)), e(str(s2.get("image", "?")))))
    return "".join(h)


def build_html(L, rows, vm):
    el_s, _ = elapsed_str(L)
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
         "<title>AI chip design lab: demo</title><style>%s</style></head><body><main>" % CSS]
    now = time.strftime("%Y-%m-%d %H:%M %Z")
    h.append("<h1>AI chip design lab</h1><p class='sub'>An open-source flow from a multiply-accumulate unit to a laid-out chip, "
             "built and checked unattended on an old Intel MacBook. Generated %s from the files on disk; nothing on this page "
             "is typed in by hand except the explanations.</p>" % e(now))
    h.append("<nav>%s</nav>" % " ".join('<a href="#%s">%d. %s</a>' % (i, k + 1, t) for k, (i, t) in enumerate(NAV)))

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
    h.append("<p class='sub'>PASS needs the stage's .done marker and <code>\"pass\": true</code> in its summary JSON; "
             "a missing piece is shown as PENDING, RUNNING, BLOCKED or UNKNOWN, never assumed.</p>")
    route = ""
    m = re.search(r'route:\s*"([^"]+)"', L.read("versions.lock"))
    if m:
        route = m.group(1)
    h.append('<div class="cards"><div class="card"><span class="sub">Elapsed</span><b>%s</b></div>'
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
                 "<tr><th>result file</th><td>%s</td></tr></tbody></table>" % (
                     oracle, e(cmd), e(inputs), e(crit), link(L, summ)))
        if isinstance(s, dict):
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
        h.append(kv_table(rr, 80))
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
                if v is False:
                    items.append("<li>%s: <code>%s</code> is false</li>" % (e(tname), e(k)))
    t1v = ((L.jload("results/t1_summary.json") or {}).get("values") or {})
    if t1v.get("eqy_scope"):
        items.append("<li>Equivalence scope as recorded by Task 1: <code>%s</code>. If this says per-PE or partial, the full 4x4 multiplier "
                     "cones did not close in the time available and the claim is limited to what is stated.</li>" % e(str(t1v["eqy_scope"])))
    items.append("<li><code>demo/run_demo.sh</code> runs only the sby tasks <code>prove</code> (unbounded induction) and <code>cover</code>; "
                 "the full BMC depth-20 run is part of <code>make t1</code> and takes about 9 minutes on this machine. "
                 "Measured run time of the short demo: %s</li>" % e(demo_timing(L)))
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
    h.append("<hr><p class='sub'>Re-generate this page at any time: <code>python3 scripts/demo_build.py</code>. "
             "5-minute re-run: <code>bash demo/run_demo.sh</code>.</p></main></body></html>")
    return "".join(h)


def md_table(rows):
    out = ["| Check | Status | Detail |", "|---|---|---|"]
    for r in rows:
        out.append("| %s | **%s** | %s |" % (r.label, r.state, r.detail.replace("|", "/")))
    return "\n".join(out)


def demo_timing(L):
    t = L.jload(".cache/demo_run/timing.json")
    if not t:
        return "Measured run time: not measured yet (run it once; the result is recorded in .cache/demo_run/timing.json)."
    return ("Last measured run time: %s s with %s cases (finished %s, load average at the end: %s). The load average reflects "
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

Elapsed: %s
Machine: %s

START / STOP THE VM
  source ~/ai-chip-lab/env.sh && colima start      # starts the Linux VM that runs the containers
  source ~/ai-chip-lab/env.sh && colima stop       # stops it (frees RAM and CPU)
  %s

RE-RUN THE SHORT DEMO
  source ~/ai-chip-lab/env.sh && bash demo/run_demo.sh
  Runs: Task 1 on 200 cases (Verilator + Icarus), the formal MAC proof restricted to the sby tasks "prove" (unbounded
  induction) and "cover", one SCALE-Sim run vs the analytic model, and ORFS's threshold check on the existing outputs.
  The full BMC-20 formal run is part of `make t1`, not of this cut (it takes ~9 minutes on this machine).
  %s

FREE DISK AFTERWARDS (all inside ~/ai-chip-lab; nothing outside the lab was changed)
  Safe to delete (re-creatable, results already saved under results/ and demo/):
    orfs/work/        ORFS working directories (large)
    logs/             raw run logs (not committed)
    downloads/        installer archives
    .venv*/           local Python environments
    docker images:    source env.sh && docker image rm <lab-sim image> <ORFS image>   (needs a re-pull/rebuild to re-run)
    the whole VM:     source env.sh && colima delete    (removes the VM disk, up to 60 GiB sparse)
  Keep: results/, demo/, versions.lock, the source directories (rtl/ tb/ formal/ eqy/ model/ arch/ orfs/ sweeps/ scripts/).
  Safe to remove everything: delete the ~/ai-chip-lab directory after `colima delete`.
""" % ("\n".join("  %-8s %s - %s" % (r.state, r.label, r.detail) for r in rows), el_s, machine_str(L), vmtxt, demo_timing(L))


def build_root_readme(L, rows, vm):
    el_s, _ = elapsed_str(L)
    h = []
    h.append("# AI chip design lab\n\nAn open-source, reproducible lab that takes a small AI accelerator from a multiply-accumulate unit to a "
             "laid-out chip using only open tools, run unattended on an old 2-core Intel MacBook with 8 GB of RAM (no Homebrew, "
             "no sudo; a Colima VM runs the containers). Three baseline checks establish objective truth (answers checked against "
             "math, a second independent tool, or published reference values); sweeps then explore the design space.\n")
    h.append("Open [`demo/index.html`](demo/index.html) for the full walk-through: concepts, tool map, how each result was tested, "
             "plots, and honest caveats.\n")
    h.append("## Status\n\nGenerated from the files in this repository by `python3 scripts/demo_build.py` (elapsed at generation: %s).\n" % el_s)
    h.append(md_table(rows))
    h.append("\nPASS means the stage's `.done` marker exists and its summary JSON says `\"pass\": true`. Anything unfinished is shown as "
             "PENDING/RUNNING/BLOCKED/UNKNOWN and not assumed.\n")
    h.append("## What is in it\n\n| Path | What |\n|---|---|")
    for rel, what in TREE:
        h.append("| `%s` | %s |" % (rel, what))
    h.append("\n## Reproduce\n\n```sh\nsource env.sh                 # lab-local PATH; all VM/Docker state stays inside this directory\n"
             "make preflight runtime images # Colima VM + pinned images (digests in coord/images.env, versions.lock)\n"
             "make t1 t2 t3                 # Task 1 (RTL vs NumPy, formal, equivalence), Task 2 (OpenROAD), Task 3 (SCALE-Sim)\n"
             "make sweeps                   # architecture and physical sweeps\n"
             "make repro                    # clean-directory rerun, writes results/repro_report.json\n"
             "make demo                     # regenerate demo/index.html and this README\n"
             "bash demo/run_demo.sh         # the 5-minute cut (cached images, scratch output dir)\n```\n")
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
    ap.add_argument("--vm", choices=["running", "stopped"], default="running")
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
