"""One small case (A 4x3, B 3x4) for the demo waveform; VCD dumped by tb/t1_dump.sv."""

import json
import os

import cocotb
import numpy as np

from test_systolic import Array, oracle


@cocotb.test()
async def test_small_case(dut):
    arr = Array(dut)
    await arr.start()
    R, C = arr.R, arr.C
    K = 3
    A = (np.arange(R * K, dtype=np.int16).reshape(R, K) - 5).astype(np.int8)   # -5 .. 6
    B = (np.arange(K * C, dtype=np.int16).reshape(K, C) * 3 - 16).astype(np.int8)
    await arr.clear()
    await arr.feed(A, B)
    res, _ = await arr.drain()
    for _ in range(2):
        await arr.tick()
    ref = oracle(A, B)
    with open(os.environ["T1_WAVE_JSON"], "w") as f:
        json.dump({"A": A.tolist(), "B": B.tolist(), "numpy": ref.tolist(),
                   "rtl": res.tolist(), "match": bool((res == ref).all())}, f, sort_keys=True)
        f.write("\n")
    assert (res == ref).all()
