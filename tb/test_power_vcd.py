"""Activity workloads for power analysis (Part 2, P2.1): one fixed-seed workload per run.

T1P_WORKLOAD = random   : uniform INT8 operands
               sparse50 : uniform INT8 operands, each element zeroed with p = 0.5
               allmax   : every operand 127
All three use the same schedule (T1P_TILES tiles of K = T1P_K steps on the R x C
array, seed 1234), so they differ only in the data.  Results are still checked
against NumPy.  The simulator dumps the VCD (Verilator --trace or Icarus
t1_dump.sv); T1P_JSON records what was run.
"""
import json
import os

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb.utils import get_sim_time

from test_systolic import Array, oracle

WORKLOAD = os.environ.get("T1P_WORKLOAD", "random")
TILES = int(os.environ.get("T1P_TILES", "16"))
K = int(os.environ.get("T1P_K", "32"))
CLK_PS = int(os.environ.get("T1P_CLK_PS", "4000"))
SEED = 1234


def operands(rng, shape):
    if WORKLOAD == "allmax":
        return np.full(shape, 127, dtype=np.int8)
    x = rng.integers(-128, 128, shape, dtype=np.int8)
    if WORKLOAD == "sparse50":
        x = x * (rng.random(shape) < 0.5)
    elif WORKLOAD != "random":
        raise ValueError(f"unknown T1P_WORKLOAD {WORKLOAD!r}")
    return x.astype(np.int8)


@cocotb.test()
async def test_power_workload(dut):
    arr = Array(dut)
    dut.clear.value = 1
    dut.in_valid.value = 0
    dut.a_i.value = 0
    dut.b_i.value = 0
    cocotb.start_soon(Clock(dut.clk, CLK_PS, unit="ps").start())
    for _ in range(arr.R + arr.C):
        await FallingEdge(dut.clk)
    dut.clear.value = 0
    rng = np.random.default_rng([SEED, 2_000_000_000])   # same stream for every workload
    t_start = get_sim_time("ps")
    bad, zeros, total = 0, 0, 0
    for _ in range(TILES):
        A = operands(rng, (arr.R, K))
        B = operands(rng, (K, arr.C))
        zeros += int((A == 0).sum() + (B == 0).sum())
        total += A.size + B.size
        await arr.clear()
        await arr.feed(A, B)
        res, _ = await arr.drain()
        bad += int(np.count_nonzero(res != oracle(A, B)))
    t_end = get_sim_time("ps")
    with open(os.environ["T1P_JSON"], "w") as f:
        json.dump({"workload": WORKLOAD, "seed": SEED, "tiles": TILES, "K": K,
                   "clock_period_ps": CLK_PS, "active_window_ps": [t_start, t_end],
                   "clock_cycles": arr.cycles, "operand_zero_fraction": round(zeros / total, 6),
                   "mismatching_elements_vs_numpy": bad}, f, indent=1, sort_keys=True)
        f.write("\n")
    assert bad == 0
