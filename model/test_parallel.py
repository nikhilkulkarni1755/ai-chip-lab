"""Check: layer-parallel, budgeted, resumable run_job == serial per-layer runs (small array/topology, seconds).
python3 model/test_parallel.py"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t3_roofline2 as R, sim

if __name__ == "__main__":
    td = tempfile.mkdtemp()
    topo = os.path.join(td, "t.csv")
    open(topo, "w").write("Layer name, IFMAP Height, IFMAP Width, Filter Height, Filter Width, Channels, Num Filter, Strides,\n"
                          "a,12,12,3,3,4,8,1,\nb,10,10,3,3,8,16,1,\nc,8,8,1,1,16,8,1,\n")
    R.TOPO, R.ARRAY, R.NWORKERS = topo, 16, 2
    R.HOLD_BUDGET_S = 0                       # first call starts nothing -> partial; proves the resume path
    assert R.run_job("rl2_user_ws_high", td) is False
    R.HOLD_BUDGET_S = 420
    assert R.run_job("rl2_user_ws_high", td) is True
    a = json.load(open(os.path.join(td, "roofline2/rl2_user_ws_high.json")))
    cfg, _, _, _ = R._job_cfg("rl2_user_ws_high", td)
    res, _ = sim.run_per_layer(cfg, topo, td)
    for x, l in zip(res, a["layers"]):
        assert x["total_cycles"] == l["total_cycles"] and x["stall_cycles"] == l["stall_cycles"], (x, l)
    print("test_parallel: OK  parallel/resumed == serial for", len(res), "layers; stalls", [l["stall_cycles"] for l in a["layers"]])
