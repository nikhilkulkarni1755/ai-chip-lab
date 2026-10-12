"""Check: per-layer SCALE-Sim invocations give exactly the same numbers as one multi-layer invocation.
Small array/topology so it runs in seconds.  python3 model/test_perlayer.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, t3_roofline2 as R
with tempfile.TemporaryDirectory() as td:
    topo = os.path.join(td, "t.csv")
    sim.write_gemm_topology(topo, [("a", 40, 24, 30), ("b", 64, 48, 20), ("c", 33, 70, 45)])
    for mode in ("CALC", "USER"):
        cfg = sim.make_config(os.path.join(td, "c.cfg"), R.BASE, 8, 8, "ws", run_name="x")
        import configparser
        cp = configparser.ConfigParser(); cp.optionxform = str; cp.read(cfg)
        cp["run_presets"]["InterfaceBandwidth"] = mode
        if mode == "USER":
            cp["architecture_presets"]["Bandwidth"] = "2"
            cp["layout"]["IfmapSRAMBankBandwidth"] = cp["layout"]["FilterSRAMBankBandwidth"] = "2"
            cp["layout"]["IfmapSRAMBankNum"] = cp["layout"]["FilterSRAMBankNum"] = "1"
        cp.write(open(cfg, "w"))
        whole, _ = sim.run(cfg, topo, os.path.join(td, "w_" + mode), gemm=True)
        per, _ = R.run_per_layer(cfg, td + "/p_" + mode if False else td, topo=topo, gemm=True)
        for a, b in zip(whole, per):
            assert a == b, (mode, a, b)
        print(mode, "per-layer == whole-topology for", len(whole), "layers; stall cycles", [int(x["stall_cycles"]) for x in per])
print("test_perlayer: OK")
