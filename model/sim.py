"""Thin, deterministic wrapper around SCALE-Sim (scalesim 3.0.0, in-process API).

Used by the analytic-model fit, the roofline study and the architecture sweep.
Nothing here is analytic: every number comes from running the simulator.
"""
import configparser
import csv
import io
import os
import contextlib
import tempfile

LAB = os.environ.get("LAB") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Bundled SCALE-Sim assets, vendored in arch/bundled (tag v3.0.0, SHA 7fd972e7c650); the PyPI wheel ships none.
SCALESIM_SRC = os.environ.get("SCALESIM_SRC", os.path.join(LAB, "arch/bundled"))
BUNDLED_LAYOUT = os.path.join(SCALESIM_SRC, "layouts/conv_nets/test.csv")  # parsed but unused (custom layout off)

COMPUTE_COLS = ["LayerID", "total_cycles_incl_prefetch", "total_cycles", "stall_cycles",
                "overall_util", "mapping_eff", "compute_util"]
BW_COLS = ["LayerID", "ifmap_sram_bw", "filter_sram_bw", "ofmap_sram_bw",
           "ifmap_dram_bw", "filter_dram_bw", "ofmap_dram_bw"]
DET_COLS = ["LayerID", "ifmap_sram_start", "ifmap_sram_stop", "ifmap_sram_reads",
            "filter_sram_start", "filter_sram_stop", "filter_sram_reads",
            "ofmap_sram_start", "ofmap_sram_stop", "ofmap_sram_writes",
            "ifmap_dram_start", "ifmap_dram_stop", "ifmap_dram_reads",
            "filter_dram_start", "filter_dram_stop", "filter_dram_reads",
            "ofmap_dram_start", "ofmap_dram_stop", "ofmap_dram_writes"]


def make_config(path, base_cfg, rows, cols, dataflow, ifmap_kb=None, filter_kb=None,
                ofmap_kb=None, bandwidth=None, run_name="run"):
    """Copy a bundled .cfg, overriding only the named knobs. Returns path."""
    cp = configparser.ConfigParser()
    cp.optionxform = str
    cp.read(base_cfg)
    a = cp["architecture_presets"]
    a["ArrayHeight"] = str(rows)
    a["ArrayWidth"] = str(cols)
    a["Dataflow"] = dataflow
    if ifmap_kb is not None:
        a["IfmapSramSzkB"] = str(ifmap_kb)
    if filter_kb is not None:
        a["FilterSramSzkB"] = str(filter_kb)
    if ofmap_kb is not None:
        a["OfmapSramSzkB"] = str(ofmap_kb)
    if bandwidth is not None:
        a["Bandwidth"] = str(bandwidth)
        cp["run_presets"]["InterfaceBandwidth"] = "USER"
    cp["general"]["run_name"] = run_name
    with open(path, "w") as f:
        cp.write(f)
    return path


def write_gemm_topology(path, layers):
    """layers: list of (name, M, N, K). SCALE-Sim GEMM format: 'Layer Name, M, N, K,'"""
    with open(path, "w") as f:
        f.write("Layer Name, M, N, K,\n")
        for name, m, n, k in layers:
            f.write(f"{name}, {m}, {n}, {k},\n")


def _read_report(path, cols):
    rows = []
    with open(path) as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            row = [x.strip() for x in row if x.strip() != ""]
            if not row:
                continue
            d = {}
            for c, v in zip(cols, row):
                d[c] = int(v) if c == "LayerID" else float(v)
            rows.append(d)
    return rows


def run(cfg, topo, outdir, gemm=False, keep_traces=False):
    """Run SCALE-Sim; returns list of per-layer dicts (compute+bandwidth+detail columns merged).
    Reports (COMPUTE_REPORT.csv, BANDWIDTH_REPORT.csv, DETAILED_ACCESS_REPORT.csv) land in
    <outdir>/<run_name>/ ."""
    from scalesim.scale_sim import scalesim
    os.makedirs(outdir, exist_ok=True)
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        s = scalesim(save_disk_space=not keep_traces, verbose=False, config=cfg, topology=topo,
                     layout=BUNDLED_LAYOUT, input_type_gemm=gemm)
        s.run_scale(top_path=outdir)
    rn = configparser.ConfigParser()
    rn.read(cfg)
    rd = os.path.join(outdir, rn["general"]["run_name"])
    comp = _read_report(os.path.join(rd, "COMPUTE_REPORT.csv"), COMPUTE_COLS)
    bw = _read_report(os.path.join(rd, "BANDWIDTH_REPORT.csv"), BW_COLS)
    det = _read_report(os.path.join(rd, "DETAILED_ACCESS_REPORT.csv"), DET_COLS)
    out = []
    for c, b, d in zip(comp, bw, det):
        m = dict(c)
        m.update({k: v for k, v in b.items() if k != "LayerID"})
        m.update({k: v for k, v in d.items() if k != "LayerID"})
        out.append(m)
    return out, rd


def run_gemm_points(points, rows, cols, dataflow, base_cfg, ifmap_kb=None, filter_kb=None,
                    ofmap_kb=None, bandwidth=None, workdir=None):
    """points: list of (M,N,K). One SCALE-Sim invocation, one layer per point."""
    with tempfile.TemporaryDirectory(dir=workdir) as td:
        cfg = make_config(os.path.join(td, "c.cfg"), base_cfg, rows, cols, dataflow, ifmap_kb,
                          filter_kb, ofmap_kb, bandwidth)
        topo = os.path.join(td, "t.csv")
        write_gemm_topology(topo, [(f"g{i}", m, n, k) for i, (m, n, k) in enumerate(points)])
        res, _ = run(cfg, topo, os.path.join(td, "out"), gemm=True)
    return res


def run_per_layer(cfg, topo, td, gemm=False):
    """One SCALE-Sim invocation per topology row; returns (per-layer dicts, merged report texts).
    SCALE-Sim keeps every layer's demand/trace matrices alive until the whole run ends
    (simulator.single_layer_sim_object_list), so many-layer / many-fold runs can exhaust memory; layers are
    independent in SCALE-Sim, and model/test_perlayer.py checks per-layer == whole-topology results."""
    import shutil
    names = ["COMPUTE_REPORT.csv", "BANDWIDTH_REPORT.csv", "DETAILED_ACCESS_REPORT.csv"]
    lines = open(topo).read().splitlines()
    header, rows = lines[0], [l for l in lines[1:] if l.strip()]
    res, merged = [], {n: None for n in names}
    for i, row in enumerate(rows):
        t1 = os.path.join(td, f"layer{i}.csv")
        open(t1, "w").write(header + "\n" + row + "\n")
        out_i = os.path.join(td, f"out{i}")
        r, rd = run(cfg, t1, out_i, gemm=gemm)
        r[0]["LayerID"] = i
        res.append(r[0])
        for n in names:
            ls = open(os.path.join(rd, n)).read().splitlines()
            body = ls[1].split(",", 1)[1]
            merged[n] = (ls[0] + "\n" if merged[n] is None else merged[n]) + f"{i},{body}\n"
        shutil.rmtree(out_i)
    return res, merged
