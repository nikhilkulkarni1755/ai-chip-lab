"""Unit test: roofline arithmetic intensity, hand calculation for one real layer.
Run: python3 model/test_intensity.py   (exit 0 = ok)

Layer Conv3_s of the bundled Resnet18.csv: IFMAP 56x56, filter 1x1, 64 channels, 128 filters, stride 2.
SCALE-Sim ofmap = ceil((56 - 1 + 2) / 2) = ceil(28.5) = 29 per side  -> M = 29*29 = 841, N = 128, K = 1*1*64 = 64.
FLOPs = 2*841*128*64 = 13,778,944.
Bytes (1 byte/word): ifmap 56*56*64 = 200,704; filter 64*128 = 8,192; ofmap 841*128 = 107,648; total 316,544.
AI = 13,778,944 / 316,544 = 43.5293... FLOP/byte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytic as an  # noqa: E402
import sim  # noqa: E402

L = {l["name"]: l for l in an.load_topology(os.path.join(sim.SCALESIM_SRC, "topologies/conv_nets/Resnet18.csv"))}
c = L["Conv3_s"]
assert (c["M"], c["N"], c["K"]) == (841, 128, 64), c
ai, flops, nbytes = an.layer_intensity(c)
assert flops == 13_778_944, flops
assert nbytes == 200_704 + 8_192 + 107_648 == 316_544, nbytes
assert abs(ai - 13_778_944 / 316_544) < 1e-9 and abs(ai - 43.5293) < 1e-3, ai
# FC layer: 1x1 ifmap, 512 ch, 1000 filters: M=1,N=1000,K=512 -> FLOPs 1,024,000; bytes 512 + 512,000 + 1,000
f = L["FC"]
ai_fc, fl, nb = an.layer_intensity(f)
assert fl == 1_024_000 and nb == 512 + 512_000 + 1_000, (fl, nb)
print("test_intensity: OK  Conv3_s AI = %.4f FLOP/B, FC AI = %.4f FLOP/B" % (ai, ai_fc))
