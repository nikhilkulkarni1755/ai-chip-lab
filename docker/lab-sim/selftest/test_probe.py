"""Image self-test: cocotb 2.x + cocotb-coverage 2.0 + numpy against a tiny MAC, on Icarus and Verilator."""
import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb_coverage.coverage import CoverPoint, coverage_db


@CoverPoint("probe.sign", xf=lambda a, b: (a < 0, b < 0),
            bins=[(False, False), (False, True), (True, False), (True, True)])
def sample(a, b):
    pass


@cocotb.test()
async def mac_matches_numpy(dut):
    rng = random.Random(1234)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.clear.value = 1
    dut.valid.value = 0
    dut.a.value = 0
    dut.b.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.clear.value = 0
    a = np.array([rng.randint(-128, 127) for _ in range(200)] + [-128, 127, -128], dtype=np.int8)
    b = np.array([rng.randint(-128, 127) for _ in range(200)] + [-128, 127, 127], dtype=np.int8)
    for x, y in zip(a, b):
        dut.a.value = int(x)
        dut.b.value = int(y)
        dut.valid.value = 1
        sample(int(x), int(y))
        await RisingEdge(dut.clk)
    dut.valid.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    want = int(a.astype(np.int32) @ b.astype(np.int32))
    got = dut.acc.value.to_signed()
    assert got == want, f"acc={got} want={want}"
    cov = coverage_db["probe.sign"].coverage * 100 / coverage_db["probe.sign"].size
    cocotb.log.info("PROBE sim=%s acc=%d numpy=%d sign_coverage=%.0f%%", os.environ.get("SIM"), got, want, cov)
    assert cov == 100
