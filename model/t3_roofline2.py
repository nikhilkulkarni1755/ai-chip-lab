"""P1.1 roofline re-specification. Criteria were registered BEFORE any run in
model/t3_roofline2_criteria.json (commit order is the evidence). This module only executes them.

Jobs (one SCALE-Sim run each, ResNet-18 bundled topology, 128x128 array, 64 kB SRAM buffers):
  rl2_user_<df>_<low|mid|high>  InterfaceBandwidth=USER, B = 16/64/256 words/cycle
  rl2_calc_<df>                 bundled scale.cfg unchanged (InterfaceBandwidth=CALC)
"""
import configparser
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytic as an  # noqa: E402
import sim  # noqa: E402
from t3_roofline import spearman  # noqa: E402

CRIT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "t3_roofline2_criteria.json")))
DFS = ["ws", "os", "is"]
BW = {"low": 16, "mid": 64, "high": 256}
ARRAY = 128
TOPO = os.path.join(sim.SCALESIM_SRC, "topologies/conv_nets/Resnet18.csv")
BASE = os.path.join(sim.SCALESIM_SRC, "configs/scale.cfg")
RHO_PASS = -0.6
RHO_WRONG = 0.3
MIN_STALLED = 5


def jobs():
    return [f"rl2_user_{df}_{b}" for df in DFS for b in BW] + [f"rl2_calc_{df}" for df in DFS]


def run_job(job, out):
    parts = job.split("_")
    mode, df = parts[1], parts[2]
    layers = an.load_topology(TOPO)
    with tempfile.TemporaryDirectory() as td:
        cfg = sim.make_config(os.path.join(td, "c.cfg"), BASE, ARRAY, ARRAY, df, run_name=job)
        cp = configparser.ConfigParser(); cp.optionxform = str; cp.read(cfg)
        if mode == "user":
            B = BW[parts[3]]
            cp["run_presets"]["InterfaceBandwidth"] = "USER"
            cp["architecture_presets"]["Bandwidth"] = str(B)
            l = cp["layout"]
            l["IfmapSRAMBankBandwidth"] = l["FilterSRAMBankBandwidth"] = str(B)
            l["IfmapSRAMBankNum"] = l["FilterSRAMBankNum"] = "1"
        else:
            B = None
            assert cp["run_presets"]["InterfaceBandwidth"] == "CALC"
        with open(cfg, "w") as f:
            cp.write(f)
        res, rd = sim.run(cfg, TOPO, os.path.join(td, "out"), gemm=False)
        d = os.path.join(out, "roofline2", job)
        os.makedirs(d, exist_ok=True)
        for r in sim_reports():
            shutil.copy(os.path.join(rd, r), os.path.join(d, r))
        shutil.copy(cfg, os.path.join(d, "config.cfg"))
    recs = []
    peak = 2 * ARRAY * ARRAY
    for L, x in zip(layers, res):
        ai, flops, nbytes = an.layer_intensity(L)
        traffic = x["ifmap_dram_reads"] + x["filter_dram_reads"] + x["ofmap_dram_writes"]
        recs.append(dict(
            name=L["name"], M=L["M"], N=L["N"], K=L["K"], ai=ai, flops=flops, bytes=nbytes,
            total_cycles=int(x["total_cycles"]), incl_prefetch=int(x["total_cycles_incl_prefetch"]),
            stall_cycles=int(x["stall_cycles"]), stall_frac=x["stall_cycles"] / x["total_cycles"],
            dram_words_moved=int(traffic), ai_effective=flops / traffic,
            ifmap_reads_over_tensor=x["ifmap_dram_reads"] / L["ifmap_bytes"],
            required_bw_words_per_cycle=x["ifmap_dram_bw"] + x["filter_dram_bw"] + x["ofmap_dram_bw"],
            achieved_flops_per_cycle=flops / x["total_cycles_incl_prefetch"]))
    json.dump(dict(job=job, mode=mode, dataflow=df, B_words_per_cycle=B, array=f"{ARRAY}x{ARRAY}",
                   peak_flops_per_cycle=peak, layers=recs),
              open(os.path.join(out, "roofline2", job + ".json"), "w"), indent=1, sort_keys=True)


def sim_reports():
    return ["COMPUTE_REPORT.csv", "BANDWIDTH_REPORT.csv", "DETAILED_ACCESS_REPORT.csv"]


def assemble(out):
    cells, checks, per_df = {}, {}, {}
    for df in DFS:
        a = {}
        for b, B in BW.items():
            r = json.load(open(os.path.join(out, "roofline2", f"rl2_user_{df}_{b}.json")))
            ai = [l["ai"] for l in r["layers"]]
            sf = [l["stall_frac"] for l in r["layers"]]
            n_st = sum(1 for v in sf if v > 0)
            rho = spearman(ai, sf)
            a[b] = dict(B=B, rho=rho, n_layers_with_stalls=n_st, informative=n_st >= MIN_STALLED,
                        total_stall_cycles=sum(l["stall_cycles"] for l in r["layers"]),
                        rho_effective_ai=spearman([l["ai_effective"] for l in r["layers"]], sf),
                        satisfies=bool(n_st >= MIN_STALLED and rho <= RHO_PASS))
        n_sat = sum(v["satisfies"] for v in a.values())
        wrong = any(v["rho"] >= RHO_WRONG for v in a.values())
        mono = a["low"]["total_stall_cycles"] >= a["mid"]["total_stall_cycles"] >= a["high"]["total_stall_cycles"]
        rc = json.load(open(os.path.join(out, "roofline2", f"rl2_calc_{df}.json")))
        rho_c = spearman([l["ai"] for l in rc["layers"]], [l["required_bw_words_per_cycle"] for l in rc["layers"]])
        per_df[df] = dict(user=a, levels_satisfied=n_sat, wrong_sign_at_any_level=wrong,
                          stall_cycles_monotone_in_B=mono, calc_rho_ai_vs_required_bw=rho_c,
                          calc_rho_effective_ai=spearman([l["ai_effective"] for l in rc["layers"]],
                                                         [l["required_bw_words_per_cycle"] for l in rc["layers"]]),
                          calc_mean_ifmap_reads_over_tensor=sum(l["ifmap_reads_over_tensor"] for l in rc["layers"]) / len(rc["layers"]))
        checks[f"user_bw_stalls_vs_ai_{df}"] = bool(n_sat >= 2 and not wrong)
        checks[f"stall_cycles_monotone_in_B_{df}"] = bool(mono)
        checks[f"calc_required_bw_inverse_to_ai_{df}"] = bool(rho_c <= RHO_PASS)
    res = dict(criteria=CRIT, per_dataflow=per_df, checks=checks, passed=bool(all(checks.values())),
               array=f"{ARRAY}x{ARRAY}", layers=len(rc["layers"]), topology="Resnet18.csv (bundled)")
    json.dump(res, open(os.path.join(out, "roofline2.json"), "w"), indent=1, sort_keys=True)
    return res


def table(res):
    L = ["df  USER-B rho(AI,stall_frac) [layers w/ stalls]        levels  wrong  monotone | CALC rho(AI,req_bw)"]
    for df, v in res["per_dataflow"].items():
        u = v["user"]
        cells = "  ".join(f"{b}:{u[b]['rho']:+.2f}[{u[b]['n_layers_with_stalls']:2d}]" for b in BW)
        L.append(f"{df:3s} {cells}   {v['levels_satisfied']}/3   {str(v['wrong_sign_at_any_level']):5s}  {str(v['stall_cycles_monotone_in_B']):5s}    | {v['calc_rho_ai_vs_required_bw']:+.3f}")
    L.append("roofline2 pass: %s" % res["passed"])
    return "\n".join(L)
