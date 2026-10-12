#!/usr/bin/env python3
"""t2_extract.py -- turn one ORFS run (metadata.json written by the flow's genMetrics.py) into a compact JSON.

  t2_extract.py <platform> <design> [variant=base]       -> results/t2/<platform>_<design>_<variant>.json (+ stdout)
  t2_extract.py --diff <variantA> <variantB> <platform> <design>  -> determinism diff of two runs (JSON on stdout)

Every number is copied from the flow's own metadata.json (never computed by hand), except sha256 of the GDS and
wall-clock time (measured by t2_run.sh). Importable: extract(), compare().
"""
import hashlib, json, os, re, sys

LAB = os.path.expanduser("~/ai-chip-lab")
WORK = os.path.join(LAB, "orfs", "work")

# metadata.json key -> output name.  First existing candidate wins.
KEYS = {
    "area_um2":        ["finish__design__instance__area"],
    "stdcell_area_um2": ["finish__design__instance__area__stdcell"],
    "utilization_frac": ["finish__design__instance__utilization"],
    "wns_setup_ns":    ["finish__timing__setup__ws"],
    "tns_setup_ns":    ["finish__timing__setup__tns"],
    "wns_hold_ns":     ["finish__timing__hold__ws"],
    "tns_hold_ns":     ["finish__timing__hold__tns"],
    "power_total_w":   ["finish__power__total"],
    "power_internal_w": ["finish__power__internal__total"],
    "power_switching_w": ["finish__power__switching__total"],
    "power_leakage_w": ["finish__power__leakage__total"],
    "cell_count":      ["finish__design__instance__count"],
    "stdcell_count":   ["finish__design__instance__count__stdcell"],
    "drc_errors":      ["detailedroute__route__drc_errors"],
    "antenna_violating_nets": ["detailedroute__antenna__violating__nets"],
    "wirelength":      ["detailedroute__route__wirelength"],
    "synth_area_um2":  ["synth__design__instance__area__stdcell"],
    "clock_period_ns": ["constraints__clocks__period", "finish__clock__period"],
}
# fields that legitimately differ between two otherwise identical runs
NONDET = re.compile(r"(elapsed|runtime|peak_mem|memory|timestamp|date|time_s|__mem|cpu|total_time|run__flow__uuid|_s$)", re.I)


def rd(p):
    with open(p) as f:
        return json.load(f)


def paths(plat, des, var):
    sub = os.path.join(plat, des, var)
    return dict(meta=os.path.join(WORK, "reports", sub, "metadata.json"),
                run=os.path.join(WORK, "reports", sub, "t2_run.json"),
                gds=os.path.join(WORK, "results", sub, "6_final.gds"),
                rep=os.path.join(WORK, "reports", sub))


def sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def gds_norm_sha256(p):
    """sha256 of a GDSII stream with the BGNLIB/BGNSTR modification/access timestamps zeroed (only bytes that
    legitimately differ run to run: they hold the wall-clock date of writing)."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        d = f.read()
    out = bytearray(d); i = 0
    while i + 4 <= len(d):
        ln = (d[i] << 8) | d[i + 1]; rt = d[i + 2]
        if ln < 4:
            break
        if rt in (0x01, 0x05):                      # BGNLIB(1), BGNSTR(5): 12 x int16 date fields
            for k in range(i + 4, i + ln):
                out[k] = 0
        i += ln
    h.update(bytes(out))
    return h.hexdigest()


def extract(plat, des, var="base"):
    P = paths(plat, des, var)
    md = rd(P["meta"])
    out = {"platform": plat, "design": des, "variant": var, "metrics": {}, "missing": []}
    for name, cands in KEYS.items():
        for c in cands:
            if c in md and md[c] not in ("N/A", None):
                out["metrics"][name] = md[c]
                break
        else:
            out["missing"].append(name)
    out["stage_runtime_s"] = {k.replace("__elapsed_seconds", ""): v for k, v in md.items() if k.endswith("__elapsed_seconds")}
    out["total_elapsed_s_flow"] = md.get("total_elapsed_seconds")
    if os.path.exists(P["run"]):
        out["run"] = rd(P["run"])
    if os.path.exists(P["gds"]):
        out["gds"] = {"path": os.path.relpath(P["gds"], LAB), "bytes": os.path.getsize(P["gds"]), "sha256": sha256(P["gds"]), "sha256_timestamps_zeroed": gds_norm_sha256(P["gds"])}
    out["flow_version"] = md.get("run__flow__version") or md.get("run__flow__openroad_version")
    out["n_metadata_fields"] = len(md)
    det = {k: v for k, v in md.items() if not NONDET.search(k)}
    out["deterministic_fields_sha256"] = hashlib.sha256(json.dumps(det, sort_keys=True).encode()).hexdigest()
    return out


def compare(plat, des, va, vb):
    """Determinism: compare every metadata field except wall-clock/memory ones, and the GDS bytes."""
    A, B = rd(paths(plat, des, va)["meta"]), rd(paths(plat, des, vb)["meta"])
    diffs, nsame, excluded = {}, 0, []
    for k in sorted(set(A) | set(B)):
        if NONDET.search(k):
            excluded.append(k)
            continue
        if A.get(k) == B.get(k):
            nsame += 1
        else:
            diffs[k] = [A.get(k), B.get(k)]
    ga, gb = paths(plat, des, va)["gds"], paths(plat, des, vb)["gds"]
    sa = sha256(ga) if os.path.exists(ga) else None
    sb = sha256(gb) if os.path.exists(gb) else None
    na = gds_norm_sha256(ga) if os.path.exists(ga) else None
    nb = gds_norm_sha256(gb) if os.path.exists(gb) else None
    return {"gds_sha256_timestamps_zeroed": [na, nb], "gds_identical_ignoring_timestamps": na is not None and na == nb,
            "compared_fields": nsame + len(diffs), "identical_fields": nsame, "differing_fields": diffs,
            "excluded_fields": excluded, "gds_sha256": [sa, sb], "gds_identical": sa is not None and sa == sb,
            "identical": (not diffs) and na is not None and na == nb}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--diff":
        print(json.dumps(compare(a[3], a[4], a[1], a[2]), indent=2))
    else:
        plat, des = a[0], a[1]
        var = a[2] if len(a) > 2 else "base"
        o = extract(plat, des, var)
        os.makedirs(os.path.join(LAB, "results", "t2"), exist_ok=True)
        with open(os.path.join(LAB, "results", "t2", f"{plat}_{des}_{var}.json"), "w") as f:
            json.dump(o, f, indent=2)
        print(json.dumps(o, indent=2))
