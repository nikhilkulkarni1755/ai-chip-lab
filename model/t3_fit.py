"""Fit + validate the analytic cycle model against SCALE-Sim on synthetic GEMMs.

Protocol (fixed before looking at residuals):
  * stall-free regime: SRAM 4 MiB per operand, DRAM bandwidth 1000 words/cycle, so SCALE-Sim's
    Stall Cycles must be 0 for every point (asserted) and cycles are pure compute+fill/drain.
  * train : arrays R,C in {8,16}^2, 6 non-square, non-multiple GEMM shapes each.
  * test  (never used to fit): double R, double C, double R&C, double K, double M, double N
    relative to the 16x16 / base-shape points, plus new shapes.
  * pass  : fitted (a,b,c,d) within 0.05 of the constants derived from the source, and
    every held-out point predicted within 1 cycle (<= 0.1 %).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytic as an  # noqa: E402
import sim  # noqa: E402

BASE = os.path.join(sim.SCALESIM_SRC, "configs/scale.cfg")
BIG = dict(ifmap_kb=4096, filter_kb=4096, ofmap_kb=4096, bandwidth=1000)

TRAIN_SHAPES = [(40, 24, 30), (64, 48, 20), (33, 70, 45), (90, 17, 60), (20, 50, 77), (56, 56, 56)]  # (M,N,K)
TRAIN_ARRAYS = [(8, 8), (8, 16), (16, 8), (16, 16)]

BASE_SHAPES = [(50, 40, 35), (80, 30, 48), (27, 66, 52)]


def _run(df, arr, shapes):
    R, C = arr
    res = sim.run_gemm_points(shapes, R, C, df, BASE, **BIG)
    out = []
    for (M, N, K), x in zip(shapes, res):
        out.append(dict(M=M, N=N, K=K, R=R, C=C, cycles=int(x["total_cycles"]),
                        stalls=int(x["stall_cycles"]), mapping_eff=x["mapping_eff"]))
    return out


def test_groups():
    g = {}
    g["base(16x16)"] = [((16, 16), s) for s in BASE_SHAPES]
    g["2R(32x16)"] = [((32, 16), s) for s in BASE_SHAPES]
    g["2C(16x32)"] = [((16, 32), s) for s in BASE_SHAPES]
    g["2R+2C(32x32)"] = [((32, 32), s) for s in BASE_SHAPES]
    g["2K"] = [((16, 16), (M, N, 2 * K)) for M, N, K in BASE_SHAPES]
    g["2M"] = [((16, 16), (2 * M, N, K)) for M, N, K in BASE_SHAPES]
    g["2N"] = [((16, 16), (M, 2 * N, K)) for M, N, K in BASE_SHAPES]
    g["2K,2R"] = [((32, 16), (M, N, 2 * K)) for M, N, K in BASE_SHAPES]
    return g


def run_fit():
    out = {"protocol": __doc__.strip().split("\n\n")[1], "dataflows": {}}
    all_ok = True
    for df in an.DATAFLOWS:
        train = []
        for arr in TRAIN_ARRAYS:
            train += _run(df, arr, TRAIN_SHAPES)
        (a, b, c, d), rank = an.fit(df, train)
        da, db, dc, dd = an.derived_params(df)
        k_naive = an.fit_naive_k(df, train)
        groups = {}
        worst_abs = 0
        worst_rel = 0.0
        naive_worst_rel = 0.0
        stalls = sum(r["stalls"] for r in train)
        for name, items in test_groups().items():
            rows = []
            for arr in sorted({i[0] for i in items}):
                rows += _run(df, arr, [i[1] for i in items if i[0] == arr])
            recs = []
            for r in rows:
                pred = an.predict(df, r["M"], r["N"], r["K"], r["R"], r["C"], (a, b, c, d))
                naive = an.naive_predict(df, r["M"], r["N"], r["K"], r["R"], r["C"], k_naive)
                res = r["cycles"] - pred
                rel = abs(res) / r["cycles"]
                nrel = abs(r["cycles"] - naive) / r["cycles"]
                stalls += r["stalls"]
                worst_abs = max(worst_abs, abs(res))
                worst_rel = max(worst_rel, rel)
                naive_worst_rel = max(naive_worst_rel, nrel)
                recs.append(dict(M=r["M"], N=r["N"], K=r["K"], R=r["R"], C=r["C"],
                                 sim_cycles=r["cycles"], model_cycles=round(pred, 3),
                                 residual=round(res, 3), rel_err=rel,
                                 naive_model_cycles=round(naive, 1), naive_rel_err=nrel))
            groups[name] = dict(points=recs,
                                max_abs_residual=max(abs(x["residual"]) for x in recs),
                                mean_residual=sum(x["residual"] for x in recs) / len(recs))
        ok_const = (abs(a - da) < .05 and abs(b - db) < .05 and abs(c - dc) < .05 and abs(d - dd) < .05)
        ok_res = worst_abs <= 1.0 and worst_rel <= 1e-3
        out["dataflows"][df] = dict(
            fitted=dict(a=a, b=b, c=c, d=d), derived=dict(a=da, b=db, c=dc, d=dd),
            design_rank=rank, n_train=len(train), naive_k_fit=k_naive,
            heldout_max_abs_residual=worst_abs, heldout_max_rel_residual=worst_rel,
            naive_heldout_max_rel_residual=naive_worst_rel, total_stalls_in_fit_runs=stalls,
            constants_match_derivation=bool(ok_const), residuals_ok=bool(ok_res and stalls == 0),
            groups=groups)
        all_ok &= bool(ok_const and ok_res and stalls == 0)
    out["pass"] = bool(all_ok)
    return out


def table(fit):
    lines = ["df  fitted(a,b,c,d)            derived        heldout max|res|  max rel   naive-k  naive max rel"]
    for df, v in fit["dataflows"].items():
        f, d = v["fitted"], v["derived"]
        lines.append("%-3s (%.3f,%.3f,%.3f,%.3f)  (%d,%d,%d,%d)   %6.1f cyc       %.2e   %7.2f  %.1f%%" % (
            df, f["a"], f["b"], f["c"], f["d"], d["a"], d["b"], d["c"], d["d"],
            v["heldout_max_abs_residual"], v["heldout_max_rel_residual"], v["naive_k_fit"],
            100 * v["naive_heldout_max_rel_residual"]))
    return "\n".join(lines)


if __name__ == "__main__":
    r = run_fit()
    print(table(r))
    print("pass:", r["pass"])
    if len(sys.argv) > 1:
        json.dump(r, open(sys.argv[1], "w"), indent=1, sort_keys=True)
