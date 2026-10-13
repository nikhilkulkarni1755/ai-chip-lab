#!/usr/bin/env python3
"""Stage 61_pe_bf16: fold the ORFS runs of the two MACs into the stage summary and write the
common-schema result, evidence and stage marker.

  p2_61_finish.py            (after scripts/t61_run.sh 10000 results and scripts/p2_61_orfs.sh)

Every number comes from the flow's own metadata.json (via scripts/t2_extract.py) or from the
verification summary; the only derived values are period - WNS and its reciprocal, labelled
as estimates.  The pass criteria in the summary are not changed here.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t2_extract  # noqa: E402

CRITERIA_COMMIT = "c0e5b87"    # results/p2_61_pe_bf16_summary.json pass criteria, before any run
# mac_int8: one clean run in one lock hold (scripts/p2_61_orfs.sh).  mac_bf16: its flow does not fit a
# 10-minute hold (first attempt stopped at 564 s in detailed routing, variant p2_61), so it was run
# with one hold per ORFS stage group (scripts/p2_61_orfs_staged.sh, fresh variant p2_61s).
VARIANT = {"mac_int8": "p2_61", "mac_bf16": "p2_61s"}
CLOCK_NS = 1.25
SUMMARY = "results/p2_61_pe_bf16_summary.json"


def main():
    d = json.load(open(SUMMARY))
    ppa, complete = {}, True
    for des in ("mac_int8", "mac_bf16"):
        meta = os.path.join(t2_extract.WORK, "reports", "nangate45", des, VARIANT[des], "metadata.json")
        if not os.path.exists(meta):
            ppa[des] = {"error": "no metadata.json: the flow did not finish"}
            complete = False
            continue
        x = t2_extract.extract("nangate45", des, VARIANT[des])
        m = x["metrics"]
        run = x.get("run", {})
        e = {k: m.get(k) for k in ("clock_period_ns", "wns_setup_ns", "tns_setup_ns", "wns_hold_ns", "area_um2",
                                   "stdcell_area_um2", "synth_area_um2", "stdcell_count", "utilization_frac",
                                   "power_total_w", "power_internal_w", "power_switching_w", "power_leakage_w",
                                   "drc_errors", "wirelength")}
        e["flow_exit_code"] = run.get("rc")
        e["flow_variant"] = VARIANT[des]
        e["lock_holds"] = run.get("staged_holds_s") or "one hold for the whole flow"
        e["flow_wall_s_incl_lock_wait"] = run.get("wall_s")
        e["flow_elapsed_s"] = x.get("total_elapsed_s_flow")
        e["gds_sha256_timestamps_zeroed"] = (x.get("gds") or {}).get("sha256_timestamps_zeroed")
        e["metrics_missing"] = x.get("missing")
        if e["wns_setup_ns"] is not None and e["clock_period_ns"] is not None:
            p = float(e["clock_period_ns"]) - float(e["wns_setup_ns"])
            e["min_period_estimate_ns"] = round(p, 4)
            e["max_clock_estimate_mhz"] = round(1000.0 / p, 1)
            e["timing_met_at_clock"] = float(e["wns_setup_ns"]) >= 0
        ok = (run.get("rc") == 0 and x.get("gds") is not None and e["area_um2"] is not None
              and e["power_total_w"] is not None and e["wns_setup_ns"] is not None)
        e["flow_completes_with_metrics"] = bool(ok)
        complete = complete and ok
        ppa[des] = e
    same_clock = all(abs(float(ppa[k].get("clock_period_ns") or 0) - CLOCK_NS) < 1e-9 for k in ppa)
    d.setdefault("checks", {})["orfs_flow_completes"] = bool(complete and same_clock)
    v = d.setdefault("values", {})
    v["ppa"] = ppa
    v["ppa_clock"] = {"period_ns": CLOCK_NS,
                      "why": "closure clock of the INT8 MAC array: sweep B frontier of systolic_os on nangate45 "
                             "(results/sweeps/phys.jsonl: 1.25 ns closes at 30/40/50 % utilization, 1.20 ns does not)",
                      "fixed_before_first_run_in": "orfs/p2_designs/nangate45/*/constraint.sdc"}
    v["ppa_max_clock_note"] = ("max clock = 1 / (period - setup WNS) of the single run at 1.25 ns: an estimate from one "
                               "run, not a searched timing-closure frontier")
    a, b = ppa.get("mac_int8", {}), ppa.get("mac_bf16", {})
    if a.get("area_um2") and b.get("area_um2"):
        v["ppa_ratio_bf16_over_int8"] = {
            "area": round(float(b["area_um2"]) / float(a["area_um2"]), 3),
            "stdcell_count": round(float(b["stdcell_count"]) / float(a["stdcell_count"]), 3) if a.get("stdcell_count") else None,
            "power_total": round(float(b["power_total_w"]) / float(a["power_total_w"]), 3) if a.get("power_total_w") else None,
            "min_period_estimate": round(b["min_period_estimate_ns"] / a["min_period_estimate_ns"], 3)
            if a.get("min_period_estimate_ns") and b.get("min_period_estimate_ns") else None}
    v["timing_at_int8_clock"] = {"mac_bf16_wns_setup_ns": b.get("wns_setup_ns"), "met": b.get("timing_met_at_clock"),
                                 "mac_int8_wns_setup_ns": a.get("wns_setup_ns"), "mac_int8_met": a.get("timing_met_at_clock")}
    ver = bool(d.get("verification_pass"))
    d["pass"] = bool(ver and d["checks"]["orfs_flow_completes"])
    d["status"] = "verification and ORFS comparison run"
    with open(SUMMARY, "w") as f:
        json.dump(d, f, indent=2)
        f.write("\n")

    # evidence
    rows = ["# INT8 MAC vs bf16 MAC alone, nangate45, ORFS synthesis-to-final, clock %.2f ns (zero I/O logic, same settings)" % CLOCK_NS,
            "# numbers from each run's metadata.json; min period / max clock are estimates (period - setup WNS) from this one run",
            "%-28s %14s %14s" % ("metric", "mac_int8", "mac_bf16")]
    for k in ("flow_exit_code", "clock_period_ns", "wns_setup_ns", "timing_met_at_clock", "min_period_estimate_ns",
              "max_clock_estimate_mhz", "area_um2", "stdcell_count", "utilization_frac", "power_total_w",
              "power_internal_w", "power_switching_w", "power_leakage_w", "drc_errors", "flow_elapsed_s"):
        rows.append("%-28s %14s %14s" % (k, a.get(k), b.get(k)))
    rows.append("ratio bf16 / int8: " + json.dumps(v.get("ppa_ratio_bf16_over_int8")))
    os.makedirs("results/evidence", exist_ok=True)
    with open("results/evidence/61_ppa.txt", "w") as f:
        f.write("\n".join(rows) + "\n")

    # common schema
    c, crit = d["checks"], d["pass_criteria"]
    val = d.get("values", {})

    def measured(name):
        if name.startswith("bit_exact_"):
            s = val.get(name.split("_")[-1], {})
            return "%s cases (%s random), %s MAC steps, %s mismatching" % (
                s.get("cases_total"), s.get("cases_random"), s.get("mac_steps"), s.get("mismatching_steps"))
        if name == "csv_sha256_identical":
            return "verilator %s / icarus %s" % (val.get("verilator", {}).get("csv_sha256"), val.get("icarus", {}).get("csv_sha256"))
        if name == "random_case_count":
            return "%s / %s random cases" % (val.get("verilator", {}).get("cases_random"), val.get("icarus", {}).get("cases_random"))
        if name == "directed_cases_present":
            return "missing: %s" % (json.dumps(val.get("directed_missing")) if val.get("directed_missing") else "none")
        if name == "functional_coverage":
            return "; ".join("%s %s/%s bins" % (s, (val.get("coverage_" + s) or {}).get("bins_hit"),
                                                (val.get("coverage_" + s) or {}).get("bins")) for s in ("verilator", "icarus"))
        if name == "oracle_cross_check":
            return json.dumps(val.get("oracle_cross_check"))
        if name == "negative_control":
            return "%s mismatching steps" % val.get("negative_control", {}).get("mismatching_steps")
        if name == "lint_clean":
            return "%s warnings; step exit code %s" % (val.get("lint_warnings"), d.get("step_exit_codes", {}).get("lint"))
        if name == "orfs_flow_completes":
            return "mac_int8 exit %s, mac_bf16 exit %s, both at %.2f ns" % (a.get("flow_exit_code"), b.get("flow_exit_code"), CLOCK_NS)
        return None

    criteria = [{"name": k, "threshold": crit[k], "written_before_run": CRITERIA_COMMIT, "measured": measured(k),
                 "pass": bool(c.get(k))} for k in crit]
    ev = ["results/evidence/61_bit_exact.txt", "results/evidence/61_cocotb_verilator.txt",
          "results/evidence/61_cocotb_icarus.txt", "results/evidence/61_lint.txt", "results/evidence/61_ppa.txt",
          SUMMARY]
    p2 = {"stage": "61_pe_bf16", "pass": d["pass"],
          "oracle": d.get("oracle"),
          "criteria": criteria,
          "superseded": [dict(name="functional coverage bin set (106 bins as first written)",
                              threshold="100 % of 106 bins", measured=d["coverage_bins_amended"]["superseded"]["result"],
                              **{"pass": False},
                              reason="5 bins are mathematically unreachable, removed before any official run; see "
                                     "coverage_bins_amended in " + SUMMARY)] if "coverage_bins_amended" in d else [],
          "reported_not_gating": {"timing_at_int8_clock": val.get("timing_at_int8_clock"), "ppa": ppa,
                                  "ratio_bf16_over_int8": val.get("ppa_ratio_bf16_over_int8"),
                                  "clock": val.get("ppa_clock"), "max_clock_note": val.get("ppa_max_clock_note")},
          "design": d.get("design"),
          "commands": ["scripts/t61_run.sh 10000 results", "scripts/p2_61_orfs.sh mac_int8", "scripts/p2_61_orfs_staged.sh mac_bf16", "python3 scripts/p2_61_finish.py"],
          "seeds": "1234", "evidence": [e for e in ev if os.path.exists(e)]}
    with open("results/p2_61_pe_bf16.json", "w") as f:
        json.dump(p2, f, indent=2)
        f.write("\n")
    st = "results/.stages/61_pe_bf16"
    for s in (".done", ".failed", ".running"):
        if os.path.exists(st + s):
            os.remove(st + s)
    failed = [k for k in crit if not c.get(k)]
    with open(st + (".done" if d["pass"] else ".failed"), "w") as f:
        f.write("pass %s verification_pass %s orfs_flow_completes %s\n" % (d["pass"], ver, c["orfs_flow_completes"]))
        if failed:
            f.write("failed criteria: %s\n" % ", ".join(failed))
    print(open("results/evidence/61_ppa.txt").read())
    print("pass", d["pass"], "failed criteria:", failed)
    return 0 if d["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
