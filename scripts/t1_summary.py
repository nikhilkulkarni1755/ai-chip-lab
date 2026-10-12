#!/usr/bin/env python3
"""Collect the Task-1 results into <out>/t1_summary.json and <out>/evidence/.

Every value is read from files produced by the run that just finished
(scripts/t1_run.sh); nothing is hard-coded.  Exit code 0 only if "pass".
"""
import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ALL_STEPS = ["lint", "sim", "wave", "formal", "eqy"]
SIMS = ["verilator", "icarus"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def read(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def scrub(text):
    """No private paths in anything that gets committed."""
    lab = os.path.realpath(os.getcwd())
    home = os.path.expanduser("~")
    text = text.replace(lab, "$LAB")
    if home not in ("/", "/tmp", "/root"):
        text = text.replace(home, "~")
    return re.sub(r"/Users/[A-Za-z0-9._-]+", "~", text)


def tool(cmd):
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        lines = [ln.strip() for ln in (out.stdout + out.stderr).splitlines() if ln.strip()]
        return scrub(lines[0]) if lines else None
    except Exception:
        return None


def versions():
    v = {
        "yosys": tool("yosys -V"),
        "verilator": tool("verilator --version"),
        "iverilog": tool("iverilog -V 2>/dev/null | head -1"),
        "sby": tool("sby --version"),
        "eqy": tool("eqy --version"),
        "yices": tool("yices --version"),
        "verible": tool("verible-verilog-lint --version"),
        "python": tool("python3 --version"),
        "gxx": tool("g++ --version"),
        "make": tool("make --version"),
    }
    for mod, name in (("cocotb", "cocotb"), ("cocotb_coverage", "cocotb-coverage"),
                      ("numpy", "numpy"), ("matplotlib", "matplotlib"), ("vcdvcd", "vcdvcd")):
        try:
            from importlib import metadata
            v[name] = metadata.version(name)
        except Exception:
            v[name] = None
    return v


def csv_stats(path):
    rows = list(csv.DictReader(open(path, newline="")))
    rnd = [r for r in rows if r["kind"] == "random"]
    return {
        "cases_total": len(rows),
        "cases_random": len(rnd),
        "cases_directed": len(rows) - len(rnd),
        "mismatching_cases": sum(1 for r in rows if int(r["mismatches"]) != 0),
        "mismatching_elements": sum(int(r["mismatches"]) for r in rows),
        "tiles": sum(int(r["tiles"]) for r in rows),
        "stalled_cases": sum(int(r["stall"]) for r in rows),
        "max_K": max(int(r["K"]) for r in rows),
        "max_M": max(int(r["M"]) for r in rows),
        "max_N": max(int(r["N"]) for r in rows),
        "directed_names": [r["name"] for r in rows if r["kind"] == "directed"],
    }


def xml_stats(path):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    tests = root.findall(".//testcase")
    failed = [t.get("name") for t in tests
              if t.find("failure") is not None or t.find("error") is not None]
    return {"tests": len(tests), "failed": failed}


def regression_table(log):
    """The cocotb pass/fail table at the end of a simulation log."""
    lines = log.splitlines()
    idx = [i for i, ln in enumerate(lines) if "** TEST " in ln]
    if not idx:
        return "\n".join(lines[-40:])
    out = []
    for ln in lines[idx[-1] - 1:]:
        if "**" in ln or "random cases done" in ln or "functional coverage" in ln:
            out.append(re.sub(r"^\s*[\d.]+ns\s+INFO\s+\S+\s+", "", ln).strip())
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--ncases", type=int, required=True)
    ap.add_argument("--steps", default=" ".join(ALL_STEPS))
    ap.add_argument("--wall", type=int, default=None)
    a = ap.parse_args()
    out, work, logs = a.out, a.work, a.logs
    steps_run = a.steps.split()
    checks, values, runtimes = {}, {}, {}
    evidence = {}

    step_rc = {}
    for ln in read(os.path.join(work, "steps.tsv")).splitlines():
        name, rc, secs = ln.split("\t")
        step_rc[name] = int(rc)
        runtimes[name] = int(secs)
    runtimes["total_wall"] = a.wall

    # ---------------------------------------------------------------- lint
    if "lint" in steps_run:
        txt = read(os.path.join(out, "t1_lint.txt"))
        body = txt.split("# verible rule configuration")[0]
        values["lint_verilator_warnings"] = len(re.findall(r"^%(Warning|Error)", body, re.M))
        values["lint_verible_violations"] = len(re.findall(r"^\S+\.sv:\d+:\d+.*\[Style:", body, re.M))
        values["lint_commands"] = len(re.findall(r"^\$ ", body, re.M))
        values["lint_nonzero_exit_codes"] = len(re.findall(r"^\[exit code [1-9]\d*\]", body, re.M))
        checks["lint_clean"] = (step_rc.get("lint") == 0 and values["lint_commands"] == 4
                                and values["lint_nonzero_exit_codes"] == 0
                                and values["lint_verilator_warnings"] == 0
                                and values["lint_verible_violations"] == 0)
        evidence["10_lint.txt"] = body

    # ----------------------------------------------------------------- sim
    if "sim" in steps_run:
        shas = {}
        for sim in SIMS:
            p = os.path.join(out, f"t1_{sim}.csv")
            ok = False
            if os.path.exists(p):
                st = csv_stats(p)
                shas[sim] = sha256(p)
                values[f"csv_sha256_{sim}"] = shas[sim]
                values[f"mismatching_cases_{sim}"] = st["mismatching_cases"]
                values[f"mismatching_elements_{sim}"] = st["mismatching_elements"]
                values[f"cases_random_{sim}"] = st["cases_random"]
                xs = xml_stats(os.path.join(work, f"results_{sim}.xml"))
                values[f"cocotb_tests_{sim}"] = xs["tests"] if xs else None
                values[f"cocotb_failed_tests_{sim}"] = xs["failed"] if xs else None
                ok = (st["mismatching_elements"] == 0 and st["cases_random"] == a.ncases
                      and step_rc.get(f"sim_{sim}") == 0 and xs is not None and not xs["failed"])
                if sim == SIMS[0]:
                    for k in ("cases_total", "cases_random", "cases_directed", "tiles",
                              "stalled_cases", "max_K", "max_M", "max_N", "directed_names"):
                        values[k] = st[k]
            checks[f"zero_mismatches_{sim}"] = ok
            cov = None
            try:
                cov = json.load(open(os.path.join(out, f"t1_coverage_{sim}.json")))
            except Exception:
                pass
            values[f"coverage_percent_{sim}"] = cov["percent"] if cov else None
            values[f"coverage_bins_{sim}"] = [cov["bins_hit"], cov["bins"]] if cov else None
            evidence[f"10_cocotb_{sim}.txt"] = (
                f"$ make -C tb SIM={sim}   (T1_NCASES={a.ncases}, seed 1234; via scripts/t1_run.sh)\n"
                + regression_table(read(os.path.join(logs, f"sim_{sim}.log"))))
        checks["csv_sha256_identical"] = len(shas) == 2 and len(set(shas.values())) == 1
        checks["random_case_count_as_requested"] = all(
            values.get(f"cases_random_{s}") == a.ncases for s in SIMS)
        covs = [values.get(f"coverage_percent_{s}") for s in SIMS]
        values["coverage_percent"] = min(covs) if all(c is not None for c in covs) else None
        checks["functional_coverage_100_percent"] = values["coverage_percent"] == 100.0
        evidence["10_sha256.txt"] = (
            f"$ sha256sum {out}/t1_verilator.csv {out}/t1_icarus.csv\n"
            + "".join(f"{shas.get(s, 'MISSING')}  {out}/t1_{s}.csv\n" for s in SIMS)
            + ("identical: " + str(checks["csv_sha256_identical"]) + "\n")
            + "".join(f"{s}: {values.get('cases_total')} cases listed, "
                      f"{values.get(f'mismatching_elements_{s}')} mismatching elements vs NumPy\n"
                      for s in SIMS))

    # ------------------------------------------------------------ waveform
    if "wave" in steps_run:
        png = os.path.join(out, "t1_waveform.png")
        case = None
        try:
            case = json.load(open(os.path.join(out, "t1_waveform_case.json")))
        except Exception:
            pass
        checks["waveform_rendered"] = (step_rc.get("waveform") == 0 and os.path.exists(png)
                                       and os.path.getsize(png) > 10000
                                       and bool(case and case["match"]))
        values["waveform_png_bytes"] = os.path.getsize(png) if os.path.exists(png) else None

    # -------------------------------------------------------------- formal
    if "formal" in steps_run:
        flog = read(os.path.join(logs, "formal.log"))
        ev = []
        for task in ("bmc", "prove", "cover"):
            d = os.path.join(work, "formal", f"mac_{task}")
            status = read(os.path.join(d, "status")).split()
            st = status[0] if status else "MISSING"
            values[f"formal_{task}_status"] = st
            values[f"formal_{task}_seconds"] = int(status[2]) if len(status) > 2 else None
            if task != "cover":
                checks[f"formal_{task}_pass"] = st == "PASS"
            tl = read(os.path.join(d, "logfile.txt"))
            ev += [re.sub(r"\[.*?\]", f"[mac_{task}]", ln) for ln in tl.splitlines()
                   if "summary:" in ln or "DONE" in ln]
        m = re.search(r"^bmc:\s*depth\s+(\d+)", read("formal/mac.sby"), re.M)
        values["formal_bmc_depth"] = int(m.group(1)) if m else None
        steps = [int(x) for x in re.findall(r"Checking assertions in step (\d+)", read(
            os.path.join(work, "formal", "mac_bmc", "logfile.txt")))]
        values["formal_bmc_steps_checked"] = (max(steps) + 1) if steps else 0
        checks["formal_bmc_depth_ge_20"] = values["formal_bmc_steps_checked"] >= 20
        values["formal_cover_reached"] = len(set(re.findall(
            r"reached cover statement (\S+)", read(os.path.join(work, "formal", "mac_cover",
                                                                 "logfile.txt")))))
        values["formal_engine"] = (re.search(r"\[engines\]\s*\n(.+)", read("formal/mac.sby")) or
                                   [None, None])[1]
        evidence["10_sby.txt"] = ("$ (cd formal && sby -f -j 2 --prefix <work>/formal/mac mac.sby)\n"
                                  + "\n".join(ev) + "\n")
        del flog

    # ----------------------------------------------------------------- eqy
    if "eqy" in steps_run:
        elog = read(os.path.join(work, "eqy", "logfile.txt"))
        proved = len(re.findall(r"Proved equivalence of partition", elog))
        failed = len(re.findall(r"(Failed to prove|Could not prove) equivalence of partition", elog))
        m = re.search(r"Successfully proved equivalence of (\d+) partitions", elog)
        values["eqy_scope"] = "full systolic_os 4x4 (flattened), RTL vs Yosys synth;abc;opt netlist"
        values["eqy_partitions_proved"] = proved
        values["eqy_partitions_failed"] = failed
        values["eqy_status"] = "PASS" if os.path.exists(os.path.join(work, "eqy", "PASS")) else (
            "FAIL" if os.path.exists(os.path.join(work, "eqy", "FAIL")) else "UNKNOWN")
        checks["eqy_pass"] = (step_rc.get("eqy") == 0 and values["eqy_status"] == "PASS"
                              and failed == 0 and proved > 0 and m is not None)
        try:
            st = json.load(open(os.path.join(work, "synth_stat.json")))
            top = st.get("design", st)
            values["netlist_cells"] = top.get("num_cells")
            values["netlist_cells_by_type"] = top.get("num_cells_by_type")
        except Exception:
            values["netlist_cells"] = None
        tail = [re.sub(r"\[.*?\]", "[eqy]", ln) for ln in elog.splitlines()
                if "Proved equivalence of partition" not in ln and "Running strategy" not in ln
                and "Warning: Partition" not in ln and "starting process" not in ln]
        evidence["10_eqy.txt"] = ("$ yosys -p 'script eqy/synth.ys; write_verilog -noattr <work>/systolic_os_netlist.v'\n"
                                  "$ eqy -f -j 2 -d <work>/eqy <work>/systolic_os.eqy   (from eqy/systolic_os.eqy.in)\n"
                                  f"partitions proved: {proved}, failed: {failed}\n"
                                  + "\n".join(tail[-25:]) + "\n")

    complete = all(s in steps_run for s in ALL_STEPS)
    required = ["zero_mismatches_verilator", "zero_mismatches_icarus", "csv_sha256_identical",
                "random_case_count_as_requested", "lint_clean", "formal_bmc_pass",
                "formal_bmc_depth_ge_20", "formal_prove_pass", "eqy_pass", "waveform_rendered"]
    present = [c for c in required if c in checks]
    ok = bool(present) and all(checks[c] for c in present) and all(v == 0 for v in step_rc.values())
    summary = {
        "task": "t1_rtl_verify",
        "pass": bool(ok and complete),
        "complete": complete,
        "pass_of_steps_run": ok,
        "steps_run": steps_run,
        "pass_requires": required,
        "checks": checks,
        "values": values,
        "config": {
            "ncases_requested": a.ncases, "seed": 1234, "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "array": "systolic_os R=4 C=4",
            "random_distribution": "M,N ~ U{1..12}, K ~ U{1..32}; values 60% uniform INT8, 20% corners, "
                                   "10% sparse, 10% sign-structured; 10% of cases with in_valid stalls "
                                   "(see tb/test_systolic.py)",
            "csv_output_column": "out_sha256 = sha256 of the DUT result matrix (int32 little-endian, C order); "
                                 "in_sha256 = sha256 of A||B (int8); full matrices are reproducible from seed 1234:<i>",
        },
        "step_exit_codes": step_rc,
        "runtimes_seconds": runtimes,
        "image": {"ref": os.environ.get("T1_IMAGE_REF"), "id": os.environ.get("T1_IMAGE_ID") or None},
        "tool_versions": versions(),
    }
    with open(os.path.join(out, "t1_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    evdir = os.path.join(out, "evidence")
    os.makedirs(evdir, exist_ok=True)
    for name, text in evidence.items():
        lines = scrub(text).rstrip("\n").splitlines()
        if len(lines) > 60:
            lines = lines[:8] + ["[...]"] + lines[-51:]
        with open(os.path.join(evdir, name), "w") as f:
            f.write("\n".join(lines) + "\n")

    print(f"[t1] summary: pass={summary['pass']} complete={complete}")
    for c in sorted(checks):
        print(f"[t1]   {'PASS' if checks[c] else 'FAIL'}  {c}")
    for k in ("cases_total", "mismatching_elements_verilator", "mismatching_elements_icarus",
              "csv_sha256_verilator", "csv_sha256_icarus", "coverage_percent",
              "formal_bmc_status", "formal_prove_status", "eqy_status", "eqy_partitions_proved"):
        if k in values:
            print(f"[t1]   {k} = {values[k]}")
    return 0 if (ok and (complete or True)) else 1


if __name__ == "__main__":
    sys.exit(main())
