#!/usr/bin/env python3
"""Fill the results of stage 61_pe_bf16 into <out>/p2_61_pe_bf16_summary.json.

The pass criteria in that file were committed before the first run and are kept
verbatim; this script only adds "checks", "values", "verification_pass" and "pass".
Everything is read from the files of the run that just finished.
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

SIMS = ["verilator", "icarus"]
DIRECTED_REQUIRED = {
    "+0/-0 operands and results": ["zero_plus_zero", "neg_zero_product", "flush_sum_neg_then_neg_zero"],
    "+inf/-inf": ["pos_inf", "neg_inf"],
    "NaN operand propagation": ["nan_operand_a", "nan_operand_b", "nan_negative"],
    "inf x 0 = NaN": ["inf_times_zero", "zero_times_inf"],
    "inf - inf = NaN": ["inf_minus_inf"],
    "max normal": ["max_normal"],
    "min normal": ["min_normal"],
    "overflow to infinity (product and sum)": ["product_overflow", "sum_overflow"],
    "rounding ties to even (both directions)": ["tie_to_even_down", "tie_to_even_up"],
    "subnormal bf16 inputs": ["subnormal_inputs"],
    "product flushed to zero": ["flush_product"],
    "sum flushed to zero": ["flush_sum_pos", "flush_sum_neg_then_neg_zero"],
    "exact cancellation to +0": ["exact_cancel_pos_zero"],
}


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


def tool(cmd):
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        lines = [ln.strip() for ln in (out.stdout + out.stderr).splitlines() if ln.strip()]
        return lines[0] if lines else None
    except Exception:
        return None


def table(log):
    lines = log.splitlines()
    idx = [i for i, ln in enumerate(lines) if "** TEST " in ln]
    keep = lines[idx[-1] - 1:] if idx else lines[-20:]
    return "\n".join(re.sub(r"^\s*[\d.]+ns\s+INFO\s+\S+\s+", "", ln).strip() for ln in keep
                     if "**" in ln or "cases:" in ln)


def main():
    ap = argparse.ArgumentParser()
    for k in ("--out", "--work", "--logs"):
        ap.add_argument(k, required=True)
    ap.add_argument("--ncases", type=int, required=True)
    ap.add_argument("--wall", type=int, default=None)
    a = ap.parse_args()
    out, work, logs = a.out, a.work, a.logs
    crit_path = os.path.join(out, "p2_61_pe_bf16_summary.json")
    d = json.load(open(crit_path if os.path.exists(crit_path) else "results/p2_61_pe_bf16_summary.json"))
    step_rc, runtimes = {}, {}
    for ln in read(os.path.join(work, "steps.tsv")).splitlines():
        n, rc, s = ln.split("\t")
        step_rc[n], runtimes[n] = int(rc), int(s)
    runtimes["total_wall"] = a.wall
    checks, values, shas, ev = {}, {}, {}, {}

    for sim in SIMS:
        p = os.path.join(out, f"t61_{sim}.csv")
        ok = False
        if os.path.exists(p):
            rows = list(csv.DictReader(open(p, newline="")))
            rnd = [r for r in rows if r["kind"] == "random"]
            shas[sim] = sha256(p)
            try:
                root = ET.parse(os.path.join(work, f"results_{sim}.xml")).getroot()
                failed = [t.get("name") for t in root.findall(".//testcase")
                          if t.find("failure") is not None or t.find("error") is not None]
            except Exception:
                failed = None
            values[sim] = {
                "cases_total": len(rows), "cases_random": len(rnd), "cases_directed": len(rows) - len(rnd),
                "mac_steps": sum(int(r["steps"]) for r in rows),
                "mismatching_steps": sum(int(r["mismatches"]) for r in rows),
                "oracle_disagreements": sum(int(r["oracle_disagreements"]) for r in rows),
                "csv_sha256": shas[sim], "cocotb_failed_tests": failed, "seconds": runtimes.get(f"sim_{sim}"),
            }
            ok = (step_rc.get(f"sim_{sim}") == 0 and values[sim]["mismatching_steps"] == 0
                  and values[sim]["oracle_disagreements"] == 0 and failed == [])
            if sim == SIMS[0]:
                names = {r["name"] for r in rows if r["kind"] == "directed"}
                missing = {k: [n for n in v if n not in names] for k, v in DIRECTED_REQUIRED.items()}
                values["directed_names"] = sorted(names)
                values["directed_missing"] = {k: v for k, v in missing.items() if v}
                checks["directed_cases_present"] = not values["directed_missing"]
                checks["random_case_count"] = len(rnd) == a.ncases
        checks[f"bit_exact_{sim}"] = ok
        try:
            cov = json.load(open(os.path.join(out, f"t61_coverage_{sim}.json")))
            values[f"coverage_{sim}"] = {"bins": cov["bins"], "bins_hit": cov["bins_hit"],
                                         "missed": {k: v["missed"] for k, v in cov["points"].items() if v["missed"]}}
        except Exception:
            values[f"coverage_{sim}"] = None
        ev[f"61_cocotb_{sim}.txt"] = (f"$ make -C tb SIM={sim} T1_SOURCES=mac_bf16.sv COCOTB_TOPLEVEL=mac_bf16 "
                                      f"COCOTB_TEST_MODULES=test_mac_bf16   (T61_NCASES={a.ncases}, seed 1234)\n"
                                      + table(read(os.path.join(logs, f"step_sim_{sim}.log"))) + "\n")
    checks["random_case_count"] = checks.get("random_case_count", False) and all(
        values.get(s, {}).get("cases_random") == a.ncases for s in SIMS)
    checks["csv_sha256_identical"] = len(shas) == 2 and len(set(shas.values())) == 1
    covs = [values.get(f"coverage_{s}") for s in SIMS]
    checks["functional_coverage"] = all(c and c["bins"] > 0 and c["bins_hit"] == c["bins"] for c in covs)

    try:
        oc = json.load(open(os.path.join(work, "oracle_check.json")))
        values["oracle_cross_check"] = {k: oc[k] for k in ("steps_compared", "mismatches", "random_cases",
                                                           "directed_cases", "first_mismatch")}
        checks["oracle_cross_check"] = (step_rc.get("oracle") == 0 and oc["mismatches"] == 0
                                        and oc["steps_compared"] >= 20000)
    except Exception:
        checks["oracle_cross_check"] = False

    neg = os.path.join(work, "t61_neg.csv")
    nm = None
    if os.path.exists(neg):
        nm = sum(int(r["mismatches"]) for r in csv.DictReader(open(neg, newline="")))
    values["negative_control"] = {"bug": "round half up instead of round half to even (RTL copy)",
                                  "mismatching_steps": nm}
    checks["negative_control"] = step_rc.get("neg_control") == 0 and nm is not None and nm > 0

    lint = read(os.path.join(out, "t61_lint.txt"))
    values["lint_warnings"] = len(re.findall(r"^%(Warning|Error)", lint, re.M)) + len(
        re.findall(r"^\S+\.sv:\d+:\d+.*\[Style:", lint, re.M))
    checks["lint_clean"] = (step_rc.get("lint") == 0 and values["lint_warnings"] == 0
                            and len(re.findall(r"^\[exit code 0\]", lint, re.M)) == 2)
    ev["61_lint.txt"] = lint
    ev["61_bit_exact.txt"] = (
        "# bf16 MAC vs golden model: accumulator compared as a uint32 bit pattern after every MAC step\n"
        + "".join(f"{s}: {values.get(s, {}).get('cases_total')} cases, {values.get(s, {}).get('mac_steps')} MAC steps, "
                  f"{values.get(s, {}).get('mismatching_steps')} mismatching, csv sha256 {shas.get(s)}\n" for s in SIMS)
        + f"csv identical across simulators: {checks['csv_sha256_identical']}\n"
        + f"oracle cross-check (golden vs exact-rational): {json.dumps(values.get('oracle_cross_check'))}\n"
        + f"negative control (round half up): {nm} mismatching steps (must be > 0)\n"
        + "".join(f"coverage {s}: {json.dumps(values.get(f'coverage_{s}'))}\n" for s in SIMS))

    verification = ["bit_exact_verilator", "bit_exact_icarus", "csv_sha256_identical", "random_case_count",
                    "directed_cases_present", "functional_coverage", "oracle_cross_check", "negative_control",
                    "lint_clean"]
    d["checks"] = {**d.get("checks", {}), **checks}
    d["values"] = {**d.get("values", {}), **values}
    d["verification_pass"] = all(checks.get(c) for c in verification) and all(v == 0 for v in step_rc.values())
    orfs = d["checks"].get("orfs_flow_completes")
    d["pass"] = None if orfs is None else bool(d["verification_pass"] and orfs)
    d["status"] = ("verification run complete" + ("" if orfs is not None else "; ORFS comparison not run yet"))
    d["config"] = {"ncases": a.ncases, "seed": 1234}
    d["step_exit_codes"] = step_rc
    d["runtimes_seconds"] = runtimes
    d["image"] = {"ref": os.environ.get("T61_IMAGE_REF"), "id": os.environ.get("T61_IMAGE_ID") or None}
    d["tool_versions"] = {"verilator": tool("verilator --version"), "iverilog": tool("iverilog -V 2>/dev/null | head -1"),
                          "python": tool("python3 --version"),
                          "numpy": tool("python3 -c 'import numpy;print(numpy.__version__)'"),
                          "ml_dtypes": tool("python3 -c 'import ml_dtypes;print(ml_dtypes.__version__)'"),
                          "cocotb": tool("python3 -c 'import cocotb;print(cocotb.__version__)'")}
    with open(os.path.join(out, "p2_61_pe_bf16_summary.json"), "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")
    evdir = os.path.join(out, "evidence")
    os.makedirs(evdir, exist_ok=True)
    lab = os.path.realpath(os.getcwd())
    for name, text in ev.items():
        lines = text.replace(lab, "$LAB").rstrip("\n").splitlines()[:60]
        with open(os.path.join(evdir, name), "w") as f:
            f.write("\n".join(lines) + "\n")
    print(f"[t61] verification_pass={d['verification_pass']} pass={d['pass']}")
    for c in sorted(checks):
        print(f"[t61]   {'PASS' if checks[c] else 'FAIL'}  {c}")
    return 0 if d["verification_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
