"""One real SCALE-Sim invocation (bundled TPU-like google.cfg, 16x16 array, output-stationary, 6 GEMM layers)
checked against the closed-form model in model/analytic.py (parameters read off the SCALE-Sim source, not fitted here).
Runs inside the lab-sim container: python3 demo/demo_scalesim.py <out.json>"""
import json, os, sys
sys.path.insert(0, "/lab/model")
import sim, analytic

pts = [(16, 16, 16), (32, 16, 64), (48, 32, 24), (16, 64, 128), (100, 20, 33), (64, 64, 64)]
R = C = 16
res = sim.run_gemm_points(pts, R, C, "os", os.path.join(sim.SCALESIM_SRC, "configs/google.cfg"))
rows = []
for (M, N, K), r in zip(pts, res):
    meas = int(float(r["total_cycles"]))
    pred = analytic.predict("os", M, N, K, R, C)
    rows.append({"M": M, "N": N, "K": K, "scalesim_cycles": meas, "analytic_cycles": pred, "residual": meas - pred})
    print("M=%-4d N=%-4d K=%-4d scalesim=%-7d analytic=%-9s residual=%s" % (M, N, K, meas, pred, meas - pred if isinstance(pred, (int, float)) else "?"))
mx = max(abs(x["residual"]) for x in rows)
json.dump({"rows": rows, "max_abs_residual": mx}, open(sys.argv[1], "w"), indent=1)
print("max |residual| = %s cycles" % mx)
