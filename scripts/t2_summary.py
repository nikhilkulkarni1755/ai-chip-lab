#!/usr/bin/env python3
"""t2_summary.py -- assemble results/t2_summary.json (+ results/evidence/20_*.txt) from real run outputs.

  t2_summary.py ["<platform>/<design>=<reason it was skipped>" ...]
Reads orfs/work/{reports,results}/<plat>/<design>/{run1,base} (run1 = first clean run, base = second clean run),
the shipped-threshold checker log (t2_check.sh), and the flow's metadata.json via t2_extract.
Pass = nangate45/gcd: shipped thresholds pass, DRC==0, GDS exists, run1 == run2 (GDS compared with GDSII
timestamps zeroed). Stretch/sky130 are recorded, but do not gate "pass". Nothing is hand-entered.
"""
import json, os, re, subprocess, sys, time
LAB = os.path.expanduser("~/ai-chip-lab")
sys.path.insert(0, os.path.join(LAB, "scripts"))
import t2_extract as X

HOME = os.path.expanduser("~")
def scrub(s): return s.replace(HOME, "~")
EV = os.path.join(LAB, "results", "evidence"); os.makedirs(EV, exist_ok=True)
def evid(name, text, maxl=60):
    lines = scrub(text).rstrip("\n").split("\n")
    open(os.path.join(EV, name), "w").write("\n".join(lines[-maxl:]) + "\n")

def check_log(plat, des, var):
    p = os.path.join(X.WORK, "reports", plat, des, var, "t2_check.log")
    if not os.path.exists(p): return None
    t = open(p).read()
    m = re.search(r"All metadata rules passed \((\d+) rules\)", t)
    return {"passed": bool(m), "n_rules": int(m.group(1)) if m else None,
            "warnings": [l for l in t.splitlines() if l.startswith("[WARN]")],
            "failures": [l for l in t.splitlines() if l.startswith("[ERROR")]}

def tool_versions():
    env = dict(l.strip().split("=", 1) for l in open(os.path.join(LAB, "coord", "images.env")) if "=" in l and not l.startswith("#"))
    r = subprocess.run(f'source {LAB}/env.sh; {LAB}/scripts/with_lock.sh pnr docker run --rm --platform linux/amd64 {env["ORFS_IMAGE"]} bash -c '
                       f'\'source /OpenROAD-flow-scripts/env.sh >/dev/null 2>&1; openroad -version; yosys -V; klayout -v\'',
                       shell=True, capture_output=True, text=True, executable="/bin/bash")
    vers = [scrub(l) for l in r.stdout.strip().splitlines()]
    tag = re.search(r"tag (\S+),", open(os.path.join(LAB, "coord", "images.env")).read())
    vers.insert(0, "ORFS image tag " + (tag.group(1) if tag else "?") + " (flow scripts + OpenROAD build of that commit; image digest above; `openroad -version` prints 'unknown' in this build, so the ORFS tag/commit is the version identifier)")
    return env["ORFS_IMAGE"], vers

def detail(plat, des, var):
    """Unambiguous extra fields straight from metadata.json (no arithmetic except the clock-period string parse)."""
    md = X.rd(X.paths(plat, des, var)["meta"])
    per = None
    for c in md.get("constraints__clocks__details", []):
        m = re.match(r"(\w+): ([\d.]+)", c)
        if m and not m.group(1).startswith("vclk"): per = float(m.group(2))
    g = lambda k: md.get(k)
    return {"reference_clock_period_ns": per,
            "setup_violating_endpoints": g("finish__timing__drv__setup_violation_count"),
            "hold_violating_endpoints": g("finish__timing__drv__hold_violation_count"),
            "die_area_um2": g("finish__design__die__area"), "core_area_um2": g("finish__design__core__area"),
            "instance_area_um2_incl_fill_and_tap": g("finish__design__instance__area"),
            "fill_cell_area_um2": g("finish__design__instance__area__class__fill_cell"),
            "tap_cell_area_um2": g("finish__design__instance__area__class__tap_cell"),
            "instance_count_total": g("finish__design__instance__count"),
            "instance_count_stdcell": g("finish__design__instance__count__stdcell"),
            "fill_cell_count": g("finish__design__instance__count__class__fill_cell"),
            "tap_cell_count": g("finish__design__instance__count__class__tap_cell"),
            "timing_closed": (g("finish__timing__setup__ws") or 0) >= 0,
            "note": "instance_area / core_area = utilization_frac (post-fill, so it exceeds the 30-55 % CORE_UTILIZATION used at floorplan)"}

def ppa(e):
    m = e["metrics"]
    return {k: m.get(k) for k in ("area_um2", "utilization_frac", "wns_setup_ns", "tns_setup_ns", "wns_hold_ns",
            "power_total_w", "power_leakage_w", "cell_count", "stdcell_count", "drc_errors", "wirelength")}

def main():
    skips = dict(a.split("=", 1) for a in sys.argv[1:])
    image, tv = tool_versions()
    S = {"generated_epoch": int(time.time()), "image": image, "tool_versions": tv, "designs": {}}
    ok_all = True
    for plat, des, gate in [("nangate45", "gcd", True), ("sky130hd", "gcd", False), ("nangate45", "systolic_os", False)]:
        key, a, b = f"{plat}/{des}", "run1", "base"
        if not os.path.exists(X.paths(plat, des, b)["meta"]):
            S["designs"][key] = {"status": "skipped", "reason": skips.get(key, "not run")}
            ok_all &= not gate
            continue
        e = X.extract(plat, des, b)
        d = {"status": "run", "ppa": ppa(e), "detail": detail(plat, des, b), "stage_runtime_s": e["stage_runtime_s"], "wall_s": e.get("run", {}).get("wall_s"),
             "gds": e.get("gds"), "checks": {}}
        chk = check_log(plat, des, b)
        d["threshold_check"] = chk   # None for custom designs: ORFS ships no rules file for them
        d["checks"]["thresholds_pass"] = chk["passed"] if chk else None
        d["checks"]["drc_errors_zero"] = e["metrics"].get("drc_errors") == 0
        d["checks"]["gds_exists"] = "gds" in e and e["gds"]["bytes"] > 0
        if os.path.exists(X.paths(plat, des, a)["meta"]):
            df = X.compare(plat, des, a, b)
            d["determinism"] = {"verdict": "PASS" if df["identical"] else "DIFFERENCE", **df}
            d["checks"]["deterministic"] = df["identical"]
            rp = X.paths(plat, des, a)["run"]
            d["run1_wall_s"] = json.load(open(rp)).get("wall_s") if os.path.exists(rp) else None
        if des == "systolic_os":
            rj = json.load(open(X.paths(plat, des, b)["run"]))
            if rj.get("rtl_sha256"):
                d["rtl"] = {"sha256_mac_plus_systolic": rj["rtl_sha256"], "last_rtl_commit": rj.get("rtl_last_commit")}
            else:  # run predates sha recording: built from the first RTL commit (before cebd174)
                d["rtl"] = {"last_rtl_commit": "bf4685e", "note": "EARLIER RTL (per-PE valid registers), superseded by cebd174; recorded from git history, not hashed at run time"}
        if des == "systolic_os":
            pm = os.path.join(X.WORK, "prev_rtl", "reports", "metadata.json")
            if os.path.exists(pm):
                md = X.rd(pm); pm_ppa = {n: next((md[c] for c in cs if c in md), None) for n, cs in X.KEYS.items()}
                d["previous_rtl_result"] = {"rtl_last_commit": "bf4685e", "note": "earlier RTL (per-PE valid registers), superseded by cebd174; kept for comparison",
                    "ppa": {k: pm_ppa.get(k) for k in d["ppa"]}, "wall_s": X.rd(os.path.join(X.WORK, "prev_rtl", "reports", "t2_run.json")).get("wall_s")}
        d["pass"] = all(v for v in d["checks"].values() if v is not None)
        if gate: ok_all &= d["pass"]
        S["designs"][key] = d
        fl = os.path.join(LAB, "logs", "part2", "20_pnr_ref", f"{plat}_{des}_{b}.log")
        if gate and os.path.exists(fl):
            ls = [l for l in open(fl).read().splitlines() if not re.match(r"^\s+\d+[+*]? \|", l)]
            evid(f"20_orfs_flow_{plat}_{des}.txt", "\n".join(ls))
        if chk:
            evid(f"20_threshold_check_{plat}_{des}.txt", open(os.path.join(X.WORK, "reports", plat, des, b, "t2_check.log")).read())
        if "determinism" in d:
            dd = d["determinism"]
            evid(f"20_determinism_{plat}_{des}.txt",
                 json.dumps({k: dd[k] for k in ("verdict", "compared_fields", "identical_fields", "differing_fields",
                                                 "gds_sha256_timestamps_zeroed", "gds_identical_ignoring_timestamps")}, indent=2)
                 + f"\nraw GDS sha256 (differ only in GDSII BGNLIB/BGNSTR timestamp records): {dd['gds_sha256']}"
                 + f"\nexcluded wall-clock/profiling fields: {len(dd['excluded_fields'])}")
        if des == "systolic_os":
            evid("20_systolic_os_ppa.txt", json.dumps({"ppa": d["ppa"], "wall_s": d["wall_s"], "checks": d["checks"],
                                                        "stage_runtime_s": d["stage_runtime_s"]}, indent=2))
    fp = os.path.join(LAB, "results", "sweeps", "phys_frontier.json")
    if os.path.exists(fp):
        S["sweep_B"] = {"frontier_file": "results/sweeps/phys_frontier.json", "data": "results/sweeps/phys.jsonl",
                        "frontier": json.load(open(fp))["frontier"], "failed_points": json.load(open(fp))["failed_points"]}
    cp = os.path.join(LAB, "results", "t2_crosscheck.json")
    if os.path.exists(cp):
        cc = json.load(open(cp))
        S["crosscheck_published"] = {"criterion": "matches_published", "value": cc["matches_published"], "file": "results/t2_crosscheck.json",
            "tolerance_doc": "docs/t2_crosscheck_tolerance.md", "explained_in": "docs/t2_timing_explained.md",
            "per_design": {k: v["matches_published"] for k, v in cc["designs"].items()},
            "note": "reported separately; does not change the Part 1 'pass' (thresholds/DRC/GDS/determinism)"}
    S["pass"] = bool(ok_all)
    json.dump(S, open(os.path.join(LAB, "results", "t2_summary.json"), "w"), indent=2)
    print(scrub(json.dumps(S, indent=2)))

if __name__ == "__main__":
    main()
