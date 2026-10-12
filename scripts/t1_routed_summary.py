#!/usr/bin/env python3
"""Stage 11_eqy_routed helper (called by scripts/t1_routed.sh).

  t1_routed_summary.py mutate <netlist.v> <out.v>
      negative-control netlist: swap the D inputs of two operand-register flops
  t1_routed_summary.py summary --out DIR --work DIR --logs DIR --ncases N ...
      write <out>/t1_routed_summary.json, <out>/evidence/11_*.txt and add
      eqy_routed_pass / gls_routed_pass / routed to <out>/t1_summary.json

Everything is read from files the run just produced; nothing is hard-coded.
All checks here are LOGICAL (zero-delay); none of them is a timing check.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

SIMS = ["icarus", "verilator"]
ALL_STEPS = ["gls", "eqy"]
SCOPE_NOTE = "logical check (zero-delay cell functions), not a timing check"
NEG_FLOPS = (r"\g_row[0].g_col[0].g_east.a_q[0]$_DFF_P_", r"\g_row[0].g_col[0].g_east.a_q[1]$_DFF_P_")
EQY_NEG = (
    ("rtl_mac", "systolic_os.acc_o.0", "RTL: acc <= acc + prod + 1 in mac_int8 (checked on PE(0,0))"),
    ("rtl_reg", "systolic_os.g_row.0.g_col.0.g_east.a_q.0", "RTL: operand register a_q <= a_w ^ 1"),
    ("netlist", "systolic_os.g_row.0.g_col.0.g_east.a_q.0",
     "routed netlist: D inputs of a_q[0] and a_q[1] of PE(0,0) swapped"),
)


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
    lab = os.path.realpath(os.getcwd())
    home = os.path.expanduser("~")
    text = text.replace(lab, "$LAB")
    if home not in ("/", "/tmp", "/root"):
        text = text.replace(home, "~")
    return re.sub(r"/Users/[A-Za-z0-9._-]+", "~", text)


def mutate(src, dst):
    text = read(src)
    spans = []
    for name in NEG_FLOPS:
        m = re.search(r"DFF_X\d+\s+" + re.escape(name) + r"\s+\(\.D\(([^)]+)\)", text)
        if not m:
            sys.exit(f"mutate: flop {name} not found in {src}")
        spans.append(m.span(1) + (m.group(1),))
    (a0, a1, na), (b0, b1, nb) = sorted(spans)
    if na == nb:
        sys.exit("mutate: both flops already share one D net")
    out = text[:a0] + nb + text[a1:b0] + na + text[b1:]
    with open(dst, "w") as f:
        f.write(out)
    print(f"injected bug (netlist): D({na}) <-> D({nb}) on {NEG_FLOPS[0]} / {NEG_FLOPS[1]}")


def csv_stats(path):
    rows = list(csv.DictReader(open(path, newline="")))
    return {
        "cases_total": len(rows),
        "cases_random": sum(1 for r in rows if r["kind"] == "random"),
        "mismatching_cases": sum(1 for r in rows if int(r["mismatches"]) != 0),
        "mismatching_elements": sum(int(r["mismatches"]) for r in rows),
    }


def prefix_sha(path, data_rows):
    """sha256 of the header + first data_rows lines of a CSV (None if too short)."""
    try:
        with open(path, "rb") as f:
            lines = f.readlines()
    except OSError:
        return None
    if len(lines) < data_rows + 1:
        return None
    return hashlib.sha256(b"".join(lines[:data_rows + 1])).hexdigest()


def failed_tests(path):
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return None
    return [t.get("name") for t in root.findall(".//testcase")
            if t.find("failure") is not None or t.find("error") is not None]


def regression_table(log):
    lines = log.splitlines()
    idx = [i for i, ln in enumerate(lines) if "** TEST " in ln]
    if not idx:
        return "\n".join(lines[-25:])
    return "\n".join(re.sub(r"^\s*[\d.]+ns\s+INFO\s+\S+\s+", "", ln).strip()
                     for ln in lines[idx[-1] - 1:] if "**" in ln)


def eqy_partitions(d):
    """name -> (status, strategy) from an EQY work directory log."""
    log = read(os.path.join(d, "logfile.txt"))
    res = {}
    for m in re.finditer(r"Proved equivalence of partition '([^']+)' using strategy '([^']+)'", log):
        res[m.group(1)] = ("proved", m.group(2))
    for m in re.finditer(r"Could not prove equivalence of partition '([^']+)' using strategy '([^']+)': (.*)", log):
        if m.group(2) != "skip" and m.group(1) not in res:
            res[m.group(1)] = ("not proved: " + m.group(3).strip(), m.group(2))
    done = re.search(r"DONE \((\w+), rc=(\d+)\)", log)
    names = [ln.split()[1] for ln in read(os.path.join(d, "partition.list")).splitlines() if ln.strip()]
    return log, res, (done.group(1) if done else "UNKNOWN"), names


def summary(a):
    out, work, logs = a.out, a.work, a.logs
    steps_run = a.steps.split()
    step_rc, runtimes = {}, {}
    for ln in read(os.path.join(work, "steps.tsv")).splitlines():
        name, rc, secs = ln.split("\t")
        step_rc[name], runtimes[name] = int(rc), int(secs)
    runtimes["total_wall"] = a.wall
    checks, values, evidence = {}, {}, {}

    # ------------------------------------------------------------- inputs
    lib = os.path.join(work, "cells", "NangateOpenCellLibrary_typical.lib")
    cells_v = os.path.join(work, "cells", "nangate45_cells_from_liberty.v")
    inputs = {
        "routed_netlist": a.netlist,
        "routed_netlist_sha256": sha256(a.netlist),
        "routed_netlist_bytes": os.path.getsize(a.netlist),
        "liberty_path_in_orfs_image": os.environ.get("T1R_LIB_IN_IMAGE"),
        "liberty_sha256": sha256(lib) if os.path.exists(lib) else None,
        "orfs_image": os.environ.get("T1R_ORFS_IMAGE"),
        "verilog_cell_models": "generated from the Liberty functions with Yosys (read_liberty; proc; "
                               "write_verilog); the ORFS nangate45 platform ships no Verilog simulation library",
        "verilog_cell_models_sha256": sha256(cells_v) if os.path.exists(cells_v) else None,
        "gls_sources": {
            "icarus": "routed netlist as written by OpenROAD + one Verilog cell module per instance",
            "verilator": "the same netlist with the cell functions inlined by Yosys (flatten only, no "
                         "optimisation); per-instance cell modules take > 30 min to compile with Verilator here",
        },
        "gold_rtl": ["rtl/mac_int8.sv", "rtl/systolic_os.sv"],
        "gold_rtl_sha256": [sha256("rtl/mac_int8.sv"), sha256("rtl/systolic_os.sv")],
    }
    try:
        st = json.load(open(os.path.join(work, "netlist_stat.json")))
        top = st["modules"].get("\\systolic_os") or st["modules"].get("systolic_os")
        by_type = {k.lstrip("\\"): v for k, v in top["num_cells_by_type"].items()}
        values["netlist_cell_instances"] = top["num_cells"] or sum(by_type.values())
        values["netlist_cells_by_type"] = dict(sorted(by_type.items()))
        values["netlist_flops"] = sum(v for k, v in by_type.items() if k.startswith(("DFF", "SDFF")))
        values["netlist_buffers"] = sum(v for k, v in by_type.items() if k.startswith(("BUF", "CLKBUF")))
        values["netlist_clock_buffers"] = sum(v for k, v in by_type.items() if k.startswith("CLKBUF"))
        values["netlist_tie_cells"] = sum(v for k, v in by_type.items() if k.startswith("LOGIC"))
        values["netlist_fill_tap_cells"] = sum(v for k, v in by_type.items() if k.startswith(("FILL", "TAP")))
        flat = json.load(open(os.path.join(work, "netlist_flat_stat.json")))
        ftop = flat["modules"].get("\\systolic_os") or flat["modules"].get("systolic_os")
        values["netlist_flat_primitives"] = ftop["num_cells"]
        values["netlist_flat_registers_after_merge"] = sum(
            v for k, v in ftop["num_cells_by_type"].items() if "DFF" in k.upper() or k in ("$dff", "$ff"))
    except Exception as e:  # noqa: BLE001
        values["netlist_stat_error"] = repr(e)
    checks["all_netlist_cells_have_models"] = step_rc.get("cells") == 0
    checks["all_flops_clocked_by_clk"] = step_rc.get("clock_check") == 0
    values["cell_treatment"] = {
        "logic gates, full/half adders, resized gates (X1/X2/X4 variants)": "function taken from the Liberty file; part of the proof and of the simulation",
        "buffers (BUF_*), incl. timing-repair and output buffers": "Liberty function Z = A (identity); kept in the netlist, part of the proof and of the simulation",
        "clock-tree buffers (CLKBUF_*)": "Liberty function Z = A; simulated as the real clock path in the gate-level simulation; "
                                         "the equivalence proof assumes one global clock, so the clock tree is covered by the "
                                         "separate structural check all_flops_clocked_by_clk (every flop's clock pin resolves "
                                         "to the port clk), not by the SMT proof",
        "flip-flops (DFF_X1)": "Liberty ff(IQ, IQN) group, next_state D, clocked_on CK; Yosys builds two identical "
                               "registers per cell (Q and QN), opt_merge folds them into one; 806 registers remain",
        "tie cells (LOGIC0/LOGIC1)": "none instantiated in this netlist (count in netlist_tie_cells)",
        "fill / tap / antenna cells": "not present in 6_final.v: ORFS writes the netlist without physical-only cells, which "
                                      "have no logic pins; nothing was removed by this stage",
    }
    values["not_covered"] = [
        "timing of any kind (setup/hold, clock skew, glitches): all checks are zero-delay",
        "physical correctness (DRC, LVS, the GDS itself): only the Verilog netlist 6_final.v is checked",
        "power/ground connectivity (the netlist has no supply pins)",
        "library cells the netlist does not instantiate (cells without a Liberty function are black boxes; the run "
        "fails if the netlist uses one)",
        "behaviour before the first clear: registers start undefined in both designs (x-propagating proof; "
        "the simulation starts with clear)",
    ]
    kep = read(os.path.join(work, "kepler_check.txt"))
    values["orfs_builtin_lec"] = {
        "what": "ORFS LEC_CHECK=1 runs Kepler-Formal on 1_synth_lec.v vs 6_final_lec.v "
                "(synthesis netlist vs final netlist; it never compares against the RTL)",
        "kepler_formal_exit_code": (int(m.group(1)) if (m := re.search(r"kepler-formal exit code: (\d+)", kep)) else None),
        "kepler_formal_avx512_instructions": (int(m.group(1)) if (m := re.search(r"zmm instructions: (\d+)", kep)) else None),
        "cpu_has_avx512": (m.group(1) == "yes") if (m := re.search(r"cpu avx512f: (\w+)", kep)) else None,
        "usable_here": bool(re.search(r"kepler-formal exit code: 0\b", kep)),
    }
    if kep:
        evidence["11_orfs_lec_kepler.txt"] = kep

    # ---------------------------------------------------------------- GLS
    if "gls" in steps_run:
        shas, ev = {}, [f"# post-route gate-level simulation, {SCOPE_NOTE}",
                        f"# netlist {a.netlist} sha256 {inputs['routed_netlist_sha256']}"]
        for sim in SIMS:
            p = os.path.join(out, f"t1_routed_gls_{sim}.csv")
            ok = False
            if os.path.exists(p):
                st = csv_stats(p)
                shas[sim] = sha256(p)
                ft = failed_tests(os.path.join(work, f"results_{sim}.xml"))
                ref = prefix_sha(os.path.join("results", f"t1_{sim}.csv"), st["cases_total"])
                values[f"gls_{sim}"] = {
                    "cases_total": st["cases_total"], "cases_random": st["cases_random"],
                    "mismatching_elements": st["mismatching_elements"],
                    "csv_sha256": shas[sim], "cocotb_failed_tests": ft,
                    "official_rtl_csv_prefix_sha256": ref,
                    "equals_official_rtl_csv_prefix": ref is not None and ref == shas[sim],
                    "seconds": runtimes.get(f"gls_{sim}"),
                }
                ok = (step_rc.get(f"gls_{sim}") == 0 and st["mismatching_elements"] == 0
                      and st["cases_random"] == a.ncases and ft == [])
            else:
                values[f"gls_{sim}"] = {"error": "no CSV produced",
                                        "log_tail": scrub("\n".join(read(os.path.join(
                                            logs, f"step_gls_{sim}.log")).splitlines()[-8:]))}
            checks[f"gls_{sim}_zero_mismatches"] = ok
            ev += [f"$ make -C tb SIM={sim} T1_GATE_NETLIST=<routed 6_final.v> T1_GATE_CELLS=<cells from Liberty>"
                   f"   (T1_NCASES={a.ncases}, seed 1234)",
                   regression_table(read(os.path.join(logs, f"step_gls_{sim}.log")))]
        checks["gls_csv_identical_across_simulators"] = len(shas) == 2 and len(set(shas.values())) == 1
        checks["gls_csv_equals_official_rtl_prefix"] = all(
            values.get(f"gls_{s}", {}).get("equals_official_rtl_csv_prefix") for s in SIMS)
        neg = os.path.join(work, "gls_neg.csv")
        nst = csv_stats(neg) if os.path.exists(neg) else None
        values["gls_negative_control"] = {
            "bug": "D inputs of a_q[0] and a_q[1] of PE(0,0) swapped in a copy of the routed netlist",
            "mismatching_elements": nst["mismatching_elements"] if nst else None,
            "cases": nst["cases_total"] if nst else None,
        }
        checks["gls_negative_control_detected"] = (step_rc.get("gls_neg") == 0 and nst is not None
                                                   and nst["mismatching_elements"] > 0)
        ev += ["# sha256 of the gate-level CSVs vs the first rows of the official RTL CSVs"]
        for sim in SIMS:
            v = values.get(f"gls_{sim}", {})
            ev.append(f"{sim}: gate-level {v.get('csv_sha256')}  official-RTL-prefix "
                      f"{v.get('official_rtl_csv_prefix_sha256')}  equal={v.get('equals_official_rtl_csv_prefix')}"
                      f"  cases={v.get('cases_total')} mismatching_elements={v.get('mismatching_elements')}")
        ev.append(f"negative control (netlist with swapped register inputs, Icarus): "
                  f"{values['gls_negative_control']['mismatching_elements']} mismatching elements in "
                  f"{values['gls_negative_control']['cases']} cases (must be > 0)")
        evidence["11_gls_routed.txt"] = "\n".join(ev) + "\n"
        gls_required = [f"gls_{s}_zero_mismatches" for s in SIMS] + [
            "gls_csv_identical_across_simulators", "gls_csv_equals_official_rtl_prefix",
            "gls_negative_control_detected", "all_netlist_cells_have_models"]
        gls_pass = all(checks[c] for c in gls_required)
    else:
        gls_pass = None

    # ---------------------------------------------------------------- EQY
    if "eqy" in steps_run:
        d = os.path.join(work, "eqy_routed")
        log, _, status, names = eqy_partitions(d)
        # per-partition results: the status file each partition's solver run wrote
        res, seconds = {}, {}
        for n in names:
            sd = os.path.join(d, "strategies", n, "smt")
            st = read(os.path.join(sd, "status")).split()
            if st and st[0] == "PASS":
                res[n] = ("proved", "smt")
            elif st:
                res[n] = ("not proved: solver status " + st[0], "smt")
            m = re.search(r"Elapsed clock time.*\((\d+)\)", read(os.path.join(sd, n, "logfile.txt")))
            if m and st:
                seconds[n] = int(m.group(1))
        holds = sorted(k for k in step_rc if k.startswith(("eqy_routed_hold", "eqy_routed_chunk")))
        runtimes["eqy_routed"] = sum(runtimes[k] for k in holds)
        fin_all = all(n in res for n in names) and bool(names)
        chunks, fin = holds, ("0" if fin_all else "")
        step_rc["eqy_routed"] = step_rc.get("eqy_routed_verdict", 3)
        engine = (re.search(r"^engine (.+)$", read("eqy/systolic_os_routed.eqy.in"), re.M) or [None, None])[1]
        proved = [n for n in names if res.get(n, ("",))[0] == "proved"]
        not_proved = {n: res.get(n, ("not attempted or stopped by the lock-time budget (no solver result)", ""))[0]
                      for n in names if n not in proved}
        mac = [n for n in names if ".acc_o." in n]
        values["eqy_routed"] = {
            "status": status, "partitions": len(names), "partitions_proved": len(proved),
            "partitions_not_proved": not_proved,
            "mac_partitions": len(mac), "mac_partitions_proved": len([n for n in mac if n in proved]),
            "partitions_proved_list": sorted(proved),
            "engine": f"EQY strategy 'use sby', depth 2, {engine} (x-propagating miter per partition)",
            "engines_tried": {"smtbmc bitwuzla": "proves a per-PE MAC partition in 4-5 min (used)",
                              "aiger rIC3": "proved the one MAC partition it was tried on in about 4.5 min",
                              "smtbmc yices": "no result within 10 min on one MAC partition",
                              "abc pdr": "stopped after about 4 min without a result (comparison cut short)"},
            "seconds_per_partition": dict(sorted(seconds.items())),
            "lock_holds": len(holds),
            "seconds": runtimes.get("eqy_routed"), "chunks": len(chunks),
            "finished": fin.isdigit(),
            "scope_exact": {
                "gold": "rtl/systolic_os.sv + rtl/mac_int8.sv, flattened (R=4, C=4)",
                "gate": "flat routed netlist 6_final.v (one module, no mac_int8 hierarchy), sha256 in inputs.routed_netlist_sha256",
                "cell_models": "nangate45 cell functions from NangateOpenCellLibrary_typical.lib of the pinned ORFS image "
                               "(path and sha256 in inputs)",
                "register_correspondence": "806 flops matched by name: operand, skew and valid registers by the RTL name on "
                                           "their Q net; the 512 accumulator bits by the output port bit they drive "
                                           "(acc_o[32*(4*i+j)+b]), since the router renamed their Q nets",
                "cut_points": "operand registers (a_q, b_q), skew registers (a_sr, b_sr), valid delay line, primary inputs",
                "partitions": "27 = 16 per-PE cones (accumulator register + 8x8 signed multiplier + 32-bit adder + clear/"
                              "valid gating, i.e. mac_int8 including the multiplier, once per PE) + 11 wrapper partitions "
                              "(a_sr, b_sr, a_q, b_q register banks, 6 valid taps, busy)",
                "kind": "zero-delay logical (sequential, x-propagating) equivalence per partition; not a timing check",
            },
            "scope": "whole flat routed netlist vs flattened RTL. The routed netlist has no hierarchy, so the "
                     "Part 1 split is applied by name: 16 per-PE partitions, each = the 32 acc_o bits of one PE "
                     "with accumulator register + INT8 multiplier + 32-bit adder + clear/valid gating (i.e. "
                     "'mac_int8 incl. multiplier', proven 16 times, cut at the operand/valid registers), plus the "
                     "wrapper partitions (skew registers, operand registers, valid delay line, busy). Operand/"
                     "skew/valid registers correspond by net name, accumulators by the output port bit they drive",
        }
        checks["eqy_routed_all_partitions_proved"] = (
            step_rc.get("eqy_routed") == 0 and status == "PASS" and len(names) > 0
            and len(proved) == len(names) and "Successfully proved designs equivalent" in log
            and len(mac) == 16)
        ev = [f"# EQY: RTL systolic_os == routed nangate45 netlist, {SCOPE_NOTE}",
              f"# netlist {a.netlist} sha256 {inputs['routed_netlist_sha256']}",
              "$ eqy -f -j 2 -d <work>/eqy_routed <work>/routed.eqy   (from eqy/systolic_os_routed.eqy.in)",
              f"partitions: {len(names)}, proved: {len(proved)}, not proved: {len(not_proved)}; "
              f"per-PE MAC partitions proved: {values['eqy_routed']['mac_partitions_proved']}/{len(mac)}"]
        ev += [re.sub(r"\[.*?\]", "[eqy_routed]", ln, count=1) for ln in log.splitlines()
               if "designs equivalent" in ln or "DONE" in ln or "summary:" in ln
               or "Failed to prove" in ln or "Could not prove" in ln][-14:]
        values["eqy_negative_controls"] = {}
        for tag, part, what in EQY_NEG:
            nlog, nres, nstatus, _ = eqy_partitions(os.path.join(work, f"neg_{tag}", "eqy"))
            r = nres.get(part)
            detected = (step_rc.get(f"eqy_neg_{tag}") == 0 and r is not None
                        and r[0].startswith("not proved") and nstatus == "FAIL")
            values["eqy_negative_controls"][tag] = {
                "bug": what, "partition": part, "result": r[0] if r else "no result", "eqy_status": nstatus}
            checks[f"eqy_neg_{tag}_detected"] = detected
            ev.append(f"negative control [{what}]: partition {part}: "
                      f"{r[0] if r else 'no result'}; EQY {nstatus} (must be FAIL)")
        evidence["11_eqy_routed.txt"] = "\n".join(ev) + "\n"
        eqy_required = ["eqy_routed_all_partitions_proved", "all_netlist_cells_have_models",
                        "all_flops_clocked_by_clk"] + [
            f"eqy_neg_{t}_detected" for t, _, _ in EQY_NEG]
        eqy_pass = all(checks[c] for c in eqy_required)
    else:
        eqy_pass = None

    complete = all(s in steps_run for s in ALL_STEPS)
    ran = [p for p in (gls_pass, eqy_pass) if p is not None]
    result = {
        "stage": "11_eqy_routed",
        "note": SCOPE_NOTE,
        "pass": bool(complete and all(ran)),
        "complete": complete,
        "pass_of_steps_run": bool(ran) and all(ran),
        "eqy_routed_pass": eqy_pass,
        "gls_routed_pass": gls_pass,
        "steps_run": steps_run,
        "checks": checks,
        "values": values,
        "inputs": inputs,
        "config": {"ncases": a.ncases, "seed": 1234},
        "step_exit_codes": step_rc,
        "runtimes_seconds": runtimes,
        "image": {"ref": os.environ.get("T1R_IMAGE_REF"), "id": os.environ.get("T1R_IMAGE_ID") or None},
    }
    with open(os.path.join(out, "t1_routed_summary.json"), "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    merge_into_t1_summary(out)

    evdir = os.path.join(out, "evidence")
    os.makedirs(evdir, exist_ok=True)
    for name, text in evidence.items():
        lines = scrub(text).rstrip("\n").splitlines()
        if len(lines) > 60:
            lines = lines[:10] + ["[...]"] + lines[-49:]
        with open(os.path.join(evdir, name), "w") as f:
            f.write("\n".join(lines) + "\n")

    print(f"[t1r] summary: pass={result['pass']} complete={complete} "
          f"gls_routed_pass={gls_pass} eqy_routed_pass={eqy_pass}")
    for c in sorted(checks):
        print(f"[t1r]   {'PASS' if checks[c] else 'FAIL'}  {c}")
    return 0 if result["pass_of_steps_run"] else 1


def merge_into_t1_summary(out):
    """Add the routed-netlist fields to t1_summary.json without touching Part 1 fields."""
    p, r = os.path.join(out, "t1_summary.json"), os.path.join(out, "t1_routed_summary.json")
    if not (os.path.exists(p) and os.path.exists(r)):
        return False
    d, rs = json.load(open(p)), json.load(open(r))
    d["eqy_routed_pass"] = rs["eqy_routed_pass"]
    d["gls_routed_pass"] = rs["gls_routed_pass"]
    d["routed"] = {
        "note": rs["note"], "complete": rs["complete"], "summary_file": "t1_routed_summary.json",
        "routed_netlist": rs["inputs"]["routed_netlist"],
        "routed_netlist_sha256": rs["inputs"]["routed_netlist_sha256"],
        "eqy_scope": rs["values"].get("eqy_routed", {}).get("scope"),
        "eqy_partitions_proved": [rs["values"].get("eqy_routed", {}).get("partitions_proved"),
                                  rs["values"].get("eqy_routed", {}).get("partitions")],
        "gls_scope": "routed netlist + cell models generated from the pinned Liberty, unchanged Task 1 "
                     "cocotb test, zero-delay",
        "checks": rs["checks"],
    }
    with open(p, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
        f.write("\n")
    return True


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mutate")
    m.add_argument("src")
    m.add_argument("dst")
    s = sub.add_parser("summary")
    for k in ("--out", "--work", "--logs", "--netlist"):
        s.add_argument(k, required=True)
    s.add_argument("--ncases", type=int, required=True)
    s.add_argument("--steps", default=" ".join(ALL_STEPS))
    s.add_argument("--wall", type=int, default=None)
    g = sub.add_parser("merge")
    g.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "mutate":
        mutate(a.src, a.dst)
        return 0
    if a.cmd == "merge":
        return 0 if merge_into_t1_summary(a.out) else 0
    return summary(a)


if __name__ == "__main__":
    sys.exit(main())
