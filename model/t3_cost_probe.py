"""Cost-only probe for amendment P2-A2 (decision rule written in COORDINATION.md BEFORE this ran).
Times single ResNet-18 layers (small / median / large by estimated cost) at candidate (array, B) settings,
serially, inside one lock hold of <= 9 minutes. Prints ONLY wall time, peak RSS and the cost estimate; the
simulation results (cycles, stalls) are discarded on purpose so no result is examined before the design is fixed."""
import json, os, subprocess, sys, tempfile, time, resource
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytic as an, sim

TOPO = os.path.join(sim.SCALESIM_SRC, "topologies/conv_nets/Resnet18.csv")
BASE = os.path.join(sim.SCALESIM_SRC, "configs/scale.cfg")
BUDGET_S = 540
PER_S = 170


def est(L, R, df="ws"):
    f, T = an.shape_map(df, L["M"], L["N"], L["K"], R, R)
    return f * (T + 3 * R)


def one(R, B, i, out):
    import configparser
    L = an.load_topology(TOPO)
    lines = open(TOPO).read().splitlines()
    with tempfile.TemporaryDirectory() as td:
        cfg = sim.make_config(os.path.join(td, "c.cfg"), BASE, R, R, "ws", run_name="probe")
        cp = configparser.ConfigParser(); cp.optionxform = str; cp.read(cfg)
        cp["run_presets"]["InterfaceBandwidth"] = "USER"
        cp["architecture_presets"]["Bandwidth"] = str(B)
        l = cp["layout"]; l["IfmapSRAMBankBandwidth"] = l["FilterSRAMBankBandwidth"] = str(B)
        l["IfmapSRAMBankNum"] = l["FilterSRAMBankNum"] = "1"
        cp.write(open(cfg, "w"))
        t1 = os.path.join(td, "t.csv"); open(t1, "w").write(lines[0] + "\n" + lines[1 + i] + "\n")
        sim.run(cfg, t1, os.path.join(td, "o"), gemm=False)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        one(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), None)
        sys.exit(0)
    L = an.load_topology(TOPO)
    out = []
    t_start = time.time()
    for R, B in ((128, 16), (256, 64)):
        order = sorted(range(len(L)), key=lambda i: est(L[i], R))
        pick = [("small", order[2]), ("median", order[len(order) // 2]), ("large", order[-1])]
        for tag, i in pick:
            left = BUDGET_S - (time.time() - t_start)
            if left < 20:
                out.append(dict(array=R, B=B, size=tag, layer=L[i]["name"], est_lines=est(L[i], R), skipped="probe budget"))
                continue
            tmo = int(min(PER_S, left))
            t0 = time.time()
            r = subprocess.run(["timeout", str(tmo), sys.executable, __file__, "--one", str(R), str(B), str(i)],
                               capture_output=True)
            wall = time.time() - t0
            rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0
            out.append(dict(array=R, B=B, size=tag, layer=L[i]["name"], est_lines=est(L[i], R),
                            wall_s=round(wall, 1), timed_out=(r.returncode == 124), rc=r.returncode,
                            max_child_rss_mb_so_far=round(rss)))
            print(json.dumps(out[-1]), flush=True)
    print("TOTAL_probe_s", round(time.time() - t_start))
    print("est_lines_all_layers_ws:", {R: sum(est(l, R, "ws") for l in L) for R in (128, 256)},
          "os:", {R: sum(est(l, R, "os") for l in L) for R in (128, 256)},
          "is:", {R: sum(est(l, R, "is") for l in L) for R in (128, 256)})
