"""cocotb testbench: INT8 output-stationary systolic array vs NumPy (bit-exact).

Oracle: A.astype(int32) @ B.astype(int32) -- integer math, exact.
The M x N result is computed tile by tile on the R x C array: for every tile
the testbench pulses `clear`, feeds the K steps (column k of the A tile and
row k of the B tile, zero padded at the edges) and reads `acc_o` when `busy`
drops.  All testbench activity happens on the falling clock edge, so there is
no simulator-dependent race with the design's rising-edge registers.

Environment (set by scripts/t1_run.sh):
  T1_NCASES   number of random cases (default 10000)
  T1_SEED     base seed (default 1234); case i uses default_rng([seed, i])
  T1_CSV      output CSV path (one row per case, identical on every simulator)
  T1_COV      output functional-coverage JSON path

Random-case distribution (case i, rng = default_rng([1234, i])):
  M, N  ~ uniform integers 1..12   (1..3 tiles per dimension on the 4x4 array,
                                    9 of 12 values are not multiples of 4)
  K     ~ uniform integer 1..32
  values: 60 % uniform INT8 [-128, 127];
          20 % corner-heavy, drawn from {-128, -127, -1, 0, 1, 126, 127};
          10 % sparse (uniform INT8 with ~70 % of entries zeroed);
          10 % sign-structured (A all <= 0 or all >= 0, same for B)
  stalls: in 10 % of the cases `in_valid` is randomly de-asserted (p = 0.25
          per step) while garbage is driven on the operand buses.
"""

import csv
import hashlib
import json
import os

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb_coverage.coverage import CoverCross, CoverPoint, coverage_db

NCASES = int(os.environ.get("T1_NCASES", "10000"))
SEED = int(os.environ.get("T1_SEED", "1234"))
CSV_PATH = os.environ.get("T1_CSV", "t1_sim.csv")
COV_PATH = os.environ.get("T1_COV", "t1_coverage.json")

M_MAX, N_MAX, K_MAX = 12, 12, 32
CORNERS = np.array([-128, -127, -1, 0, 1, 126, 127], dtype=np.int8)

CSV_FIELDS = ["case", "kind", "name", "seed", "M", "K", "N", "tiles", "stall",
              "in_sha256", "out_sha256", "out_sum", "mismatches"]
ROWS = []          # one dict per case, written by the last test
STATE = {"case": 0}

# --------------------------------------------------------------- coverage
SIGNS = ["neg", "zero", "pos"]
CORNER_BINS = ["min", "neg", "m1", "zero", "p1", "pos", "max"]


def sign_bin(v):
    return "neg" if v < 0 else ("zero" if v == 0 else "pos")


def corner_bin(v):
    return {-128: "min", -1: "m1", 0: "zero", 1: "p1", 127: "max"}.get(
        int(v), "neg" if v < 0 else "pos")


@CoverPoint("t1.operand.a_sign", xf=lambda a, b: sign_bin(a), bins=SIGNS)
@CoverPoint("t1.operand.b_sign", xf=lambda a, b: sign_bin(b), bins=SIGNS)
@CoverCross("t1.operand.sign_cross",
            items=["t1.operand.a_sign", "t1.operand.b_sign"])
@CoverPoint("t1.operand.a_corner", xf=lambda a, b: corner_bin(a), bins=CORNER_BINS)
@CoverPoint("t1.operand.b_corner", xf=lambda a, b: corner_bin(b), bins=CORNER_BINS)
@CoverCross("t1.operand.corner_cross",
            items=["t1.operand.a_corner", "t1.operand.b_corner"])
def sample_operands(a, b):
    """One (a, b) pair that met in a MAC."""


@CoverPoint("t1.shape.k", xf=lambda m, k, n, r, c: k,
            bins=["1", "2..4", "5..16", "17..32", ">32"],
            rel=lambda k, b: {"1": k == 1, "2..4": 2 <= k <= 4, "5..16": 5 <= k <= 16,
                              "17..32": 17 <= k <= 32, ">32": k > 32}[b])
@CoverPoint("t1.shape.rows", xf=lambda m, k, n, r, c: (m, r),
            bins=["lt_array", "eq_array", "multiple", "non_multiple"],
            rel=lambda v, b: b == ("lt_array" if v[0] < v[1] else "eq_array" if v[0] == v[1]
                                   else "multiple" if v[0] % v[1] == 0 else "non_multiple"))
@CoverPoint("t1.shape.cols", xf=lambda m, k, n, r, c: (n, c),
            bins=["lt_array", "eq_array", "multiple", "non_multiple"],
            rel=lambda v, b: b == ("lt_array" if v[0] < v[1] else "eq_array" if v[0] == v[1]
                                   else "multiple" if v[0] % v[1] == 0 else "non_multiple"))
def sample_shape(m, k, n, r, c):
    """Shape of one case relative to the R x C array."""


@CoverPoint("t1.result.acc_sign", bins=SIGNS)
def sample_result_sign(s):
    """Sign of a final accumulator value."""


def sample_case_coverage(A, B, out, R, C):
    """Sample functional coverage for one case.

    Every (A[i][k], B[k][j]) pair meets in a MAC.  To keep the run time
    bounded the cover points are sampled once per *distinct* (corner bin of a,
    corner bin of b) combination present in the case (at most 49 calls), found
    with NumPy; hit/miss information is therefore exact, hit counts are
    per-case rather than per-product.
    """
    seen = set()
    for k in range(A.shape[1]):
        for a in np.unique(A[:, k]):
            for b in np.unique(B[k, :]):
                key = (corner_bin(a), corner_bin(b))
                if key not in seen:
                    seen.add(key)
                    sample_operands(int(a), int(b))
        if len(seen) == 49:
            break
    sample_shape(A.shape[0], A.shape[1], B.shape[1], R, C)
    for s in {sign_bin(v) for v in (int(out.min()), int(out.max()))} | (
            {"zero"} if (out == 0).any() else set()):
        sample_result_sign(s)


# ------------------------------------------------------------------ driver
class Array:
    """Drives one systolic_os instance."""

    def __init__(self, dut):
        self.dut = dut
        # array size from the port widths (a gate-level netlist has no parameters)
        self.R = len(dut.a_i) // 8
        self.C = len(dut.b_i) // 8
        self.cycles = 0

    async def start(self):
        dut = self.dut
        cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
        dut.clear.value = 1
        dut.in_valid.value = 0
        dut.a_i.value = 0
        dut.b_i.value = 0
        for _ in range(self.R + self.C):
            await FallingEdge(dut.clk)
        dut.clear.value = 0

    async def tick(self):
        await FallingEdge(self.dut.clk)
        self.cycles += 1

    async def clear(self):
        self.dut.clear.value = 1
        self.dut.in_valid.value = 0
        await self.tick()
        self.dut.clear.value = 0

    async def feed(self, At, Bt, stall_rng=None):
        """Feed all K steps of one tile. At: R x K int8, Bt: K x C int8."""
        dut = self.dut
        K = At.shape[1]
        a_words = np.ascontiguousarray(At.T).tobytes()   # step k -> R bytes
        b_words = Bt.tobytes()                           # step k -> C bytes
        R, C = self.R, self.C
        for k in range(K):
            if stall_rng is not None:
                while stall_rng.random() < 0.25:
                    dut.in_valid.value = 0
                    dut.a_i.value = int(stall_rng.integers(0, 1 << (8 * R), dtype=np.uint64))
                    dut.b_i.value = int(stall_rng.integers(0, 1 << (8 * C), dtype=np.uint64))
                    await self.tick()
            dut.in_valid.value = 1
            dut.a_i.value = int.from_bytes(a_words[k * R:(k + 1) * R], "little")
            dut.b_i.value = int.from_bytes(b_words[k * C:(k + 1) * C], "little")
            await self.tick()
        dut.in_valid.value = 0

    async def drain(self):
        """Wait for busy to drop, return (R x C int32 result, clocks waited)."""
        waited = 0
        while int(self.dut.busy.value):
            await self.tick()
            waited += 1
            assert waited <= self.R + self.C + 2, "busy stuck high"
        return self.read(), waited

    def read(self):
        raw = int(self.dut.acc_o.value).to_bytes(4 * self.R * self.C, "little")
        return np.frombuffer(raw, dtype="<i4").reshape(self.R, self.C).astype(np.int32)

    async def matmul(self, A, B, stall_rng=None):
        """Full M x N product, tiled onto the array."""
        R, C = self.R, self.C
        M, K = A.shape
        N = B.shape[1]
        out = np.zeros((M, N), dtype=np.int32)
        tiles = 0
        for r0 in range(0, M, R):
            At = np.zeros((R, K), dtype=np.int8)
            rows = min(R, M - r0)
            At[:rows] = A[r0:r0 + rows]
            for c0 in range(0, N, C):
                Bt = np.zeros((K, C), dtype=np.int8)
                cols = min(C, N - c0)
                Bt[:, :cols] = B[:, c0:c0 + cols]
                await self.clear()
                await self.feed(At, Bt, stall_rng)
                res, _ = await self.drain()
                out[r0:r0 + rows, c0:c0 + cols] = res[:rows, :cols]
                # padded rows / columns must stay exactly zero
                pad = res.copy()
                pad[:rows, :cols] = 0
                assert not pad.any(), "padding PEs accumulated a non-zero value"
                tiles += 1
        return out, tiles


def oracle(A, B):
    return A.astype(np.int32) @ B.astype(np.int32)


async def run_case(arr, kind, name, seed, A, B, stall_rng=None):
    """Run one case, compare with NumPy, record a CSV row. Returns #mismatches."""
    A = np.ascontiguousarray(A, dtype=np.int8)
    B = np.ascontiguousarray(B, dtype=np.int8)
    out, tiles = await arr.matmul(A, B, stall_rng)
    ref = oracle(A, B)
    mism = int(np.count_nonzero(out != ref))
    sample_case_coverage(A, B, out, arr.R, arr.C)
    ROWS.append({
        "case": STATE["case"], "kind": kind, "name": name, "seed": seed,
        "M": A.shape[0], "K": A.shape[1], "N": B.shape[1], "tiles": tiles,
        "stall": int(stall_rng is not None),
        "in_sha256": hashlib.sha256(A.tobytes() + B.tobytes()).hexdigest(),
        "out_sha256": hashlib.sha256(out.astype("<i4").tobytes()).hexdigest(),
        "out_sum": int(out.astype(np.int64).sum()),
        "mismatches": mism,
    })
    STATE["case"] += 1
    if mism:
        cocotb.log.error("MISMATCH case %s (%s) %s: %d elements differ",
                         ROWS[-1]["case"], kind, name, mism)
    return mism


def random_case(i):
    """Deterministic random case i (independent of how many cases are run)."""
    rng = np.random.default_rng([SEED, i])
    M = int(rng.integers(1, M_MAX + 1))
    N = int(rng.integers(1, N_MAX + 1))
    K = int(rng.integers(1, K_MAX + 1))
    mode = rng.random()
    if mode < 0.60:
        name = "uniform"
        A = rng.integers(-128, 128, (M, K), dtype=np.int8)
        B = rng.integers(-128, 128, (K, N), dtype=np.int8)
    elif mode < 0.80:
        name = "corners"
        A = rng.choice(CORNERS, (M, K))
        B = rng.choice(CORNERS, (K, N))
    elif mode < 0.90:
        name = "sparse"
        A = rng.integers(-128, 128, (M, K), dtype=np.int8) * (rng.random((M, K)) > 0.7)
        B = rng.integers(-128, 128, (K, N), dtype=np.int8) * (rng.random((K, N)) > 0.7)
    else:
        name = "signed"
        A = -np.abs(rng.integers(-127, 128, (M, K), dtype=np.int8))
        B = np.abs(rng.integers(-127, 128, (K, N), dtype=np.int8))
        if rng.random() < 0.5:
            A = -A
        if rng.random() < 0.5:
            B = -B
    stall_rng = rng if rng.random() < 0.10 else None
    return name, A.astype(np.int8), B.astype(np.int8), stall_rng


# ------------------------------------------------------------------- tests
@cocotb.test()
async def test_directed(dut):
    """Directed corner cases (all compared against NumPy)."""
    arr = Array(dut)
    await arr.start()
    R, C = arr.R, arr.C
    i8 = np.int8
    bad = 0

    def full(shape, v):
        return np.full(shape, v, dtype=i8)

    cases = [
        ("all_min_maxK", full((R, K_MAX), -128), full((K_MAX, C), -128)),
        ("all_min_K4x", full((R, 4 * K_MAX), -128), full((4 * K_MAX, C), -128)),
        ("all_max_maxK", full((R, K_MAX), 127), full((K_MAX, C), 127)),
        ("min_times_max", full((R, K_MAX), -128), full((K_MAX, C), 127)),
        ("max_times_min", full((R, K_MAX), 127), full((K_MAX, C), -128)),
        ("zeros", full((R, 8), 0), full((8, C), 0)),
        ("zero_times_min", full((R, 8), 0), full((8, C), -128)),
        ("identity_left", np.eye(R, dtype=i8),
         np.arange(-128, -128 + R * C, dtype=np.int16).reshape(R, C).astype(i8)),
        ("identity_right", np.arange(127, 127 - R * C, -1, dtype=np.int16).reshape(R, C).astype(i8),
         np.eye(C, dtype=i8)),
        ("neg_identity", (-np.eye(R)).astype(i8), full((R, C), -128)),
        ("K1_scalar", np.array([[-128]], dtype=i8), np.array([[-128]], dtype=i8)),
        ("K1_outer", np.arange(-2, -2 + R, dtype=i8).reshape(R, 1) * 60,
         np.arange(-1, -1 + C, dtype=i8).reshape(1, C) * 127),
        ("K1_wide", full((2 * R + 1, 1), 127), full((1, 2 * C + 3), -128)),
        ("shape_5x7x9", None, None),
        ("shape_1x3x1", None, None),
        ("shape_9x2x6", None, None),
        ("shape_3x33x11", None, None),
        ("shape_12x32x12_min", full((12, K_MAX), -128), full((K_MAX, 12), -128)),
    ]
    rng = np.random.default_rng([SEED, 10**9])
    for name, A, B in cases:
        if A is None:
            m, k, n = (int(x) for x in name.split("_")[1].split("x"))
            A = rng.integers(-128, 128, (m, k), dtype=i8)
            B = rng.integers(-128, 128, (k, n), dtype=i8)
        bad += await run_case(arr, "directed", name, SEED, A, B)

    # stalled stream: gaps in in_valid with garbage on the buses
    A = rng.integers(-128, 128, (R + 1, 9), dtype=i8)
    B = rng.integers(-128, 128, (9, C + 2), dtype=i8)
    bad += await run_case(arr, "directed", "stalled_stream", SEED, A, B,
                          np.random.default_rng([SEED, 10**9 + 1]))
    assert bad == 0, f"{bad} mismatching elements in directed cases"


@cocotb.test()
async def test_clear_midstream(dut):
    """clear in the middle of a stream drops everything in flight; the result
    then holds until the next clear; busy drops R+C-1 clocks after the last step."""
    arr = Array(dut)
    await arr.start()
    R, C = arr.R, arr.C
    rng = np.random.default_rng([SEED, 10**9 + 2])
    bad = 0
    for junk_steps in range(1, R + C + 3):
        K = 6
        J_A = rng.integers(-128, 128, (R, junk_steps), dtype=np.int8)
        J_B = rng.integers(-128, 128, (junk_steps, C), dtype=np.int8)
        A = rng.integers(-128, 128, (R, K), dtype=np.int8)
        B = rng.integers(-128, 128, (K, C), dtype=np.int8)
        ref = oracle(A, B)
        await arr.clear()
        await arr.feed(J_A, J_B)            # junk, partly still in the pipeline ...
        if junk_steps % 2:                  # ... on odd runs: operands present during clear
            dut.in_valid.value = 1
            dut.a_i.value = (1 << (8 * R)) - 1
            dut.b_i.value = (1 << (8 * C)) - 1
            dut.clear.value = 1
            await arr.tick()
            dut.clear.value = 0
            dut.in_valid.value = 0
        else:
            await arr.clear()               # ... wiped by a mid-stream clear
        assert not arr.read().any(), "accumulators not zero right after clear"
        await arr.feed(A, B)
        res, waited = await arr.drain()
        # the last step sat at the ports in clock 0; drain() starts in clock 1
        # and busy must be low from clock R+C-1 on
        assert waited == R + C - 2, f"busy dropped after {waited} clocks, expected {R + C - 2}"
        mism = int(np.count_nonzero(res != ref))
        for _ in range(R + C + 2):          # hold: nothing changes while idle
            dut.a_i.value = int(rng.integers(0, 1 << 30))
            dut.b_i.value = int(rng.integers(0, 1 << 30))
            await arr.tick()
        mism += int(np.count_nonzero(arr.read() != ref))
        sample_case_coverage(A, B, res, R, C)
        ROWS.append({
            "case": STATE["case"], "kind": "directed", "name": f"clear_midstream_{junk_steps}",
            "seed": SEED, "M": R, "K": K, "N": C, "tiles": 1, "stall": 0,
            "in_sha256": hashlib.sha256(A.tobytes() + B.tobytes()).hexdigest(),
            "out_sha256": hashlib.sha256(res.astype("<i4").tobytes()).hexdigest(),
            "out_sum": int(res.astype(np.int64).sum()), "mismatches": mism,
        })
        STATE["case"] += 1
        bad += mism
    assert bad == 0, f"{bad} mismatching elements after mid-stream clear"


@cocotb.test()
async def test_random(dut):
    """NCASES random cases from seed 1234, each compared against NumPy."""
    arr = Array(dut)
    await arr.start()
    bad = 0
    for i in range(NCASES):
        name, A, B, stall_rng = random_case(i)
        bad += await run_case(arr, "random", name, f"{SEED}:{i}", A, B, stall_rng)
        if (i + 1) % 1000 == 0:
            cocotb.log.info("random cases: %d / %d, mismatching elements so far: %d",
                            i + 1, NCASES, bad)
    cocotb.log.info("random cases done: %d, clock cycles: %d", NCASES, arr.cycles)
    assert bad == 0, f"{bad} mismatching elements in {NCASES} random cases"


@cocotb.test()
async def test_zz_report(dut):
    """Write the CSV and the functional-coverage report (always last)."""
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(ROWS)
    points = {}
    for name in sorted(coverage_db):
        item = coverage_db[name]
        if not name.startswith("t1.") or name.count(".") != 2:
            continue
        hits = {str(k): int(v) for k, v in item.detailed_coverage.items()}
        points[name] = {
            "bins": len(hits),
            "bins_hit": sum(1 for v in hits.values() if v > 0),
            "percent": round(float(item.cover_percentage), 4),
            "missed": sorted(k for k, v in hits.items() if v == 0),
        }
    total = sum(p["bins"] for p in points.values())
    hit = sum(p["bins_hit"] for p in points.values())
    cov = {"bins": total, "bins_hit": hit,
           "percent": round(100.0 * hit / total, 4) if total else 0.0,
           "points": points}
    with open(COV_PATH, "w") as f:
        json.dump(cov, f, indent=2, sort_keys=True)
        f.write("\n")
    cocotb.log.info("cases: %d, mismatching cases: %d, functional coverage: %d/%d bins (%.2f %%)",
                    len(ROWS), sum(1 for r in ROWS if r["mismatches"]), hit, total, cov["percent"])
    assert all(r["mismatches"] == 0 for r in ROWS)
    assert len(ROWS) > 0
