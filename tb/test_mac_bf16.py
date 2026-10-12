"""cocotb testbench for rtl/mac_bf16.sv: bit-exact against the golden model.

Every MAC step is compared (accumulator as a uint32 bit pattern) with
bf16_golden.mac_step (NumPy float32 + ml_dtypes) and, as a cross-check of the oracle
itself, with bf16_golden.mac_step_exact (exact rational arithmetic), which also
provides the classification for functional coverage.

Environment: T61_NCASES (default 10000), T61_CSV, T61_COV.
CSV: one row per case -- case, kind, name, seed, steps, in_sha256 (operand bit
patterns), out_sha256 (accumulator after every step), final_acc, mismatches.
"""
import csv
import hashlib
import json
import os
import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb_coverage.coverage import CoverCross, CoverPoint, coverage_db

from bf16_cases import DIRECTED, SEED, random_case
from bf16_golden import mac_step, mac_step_exact

NCASES = int(os.environ.get("T61_NCASES", "10000"))
CSV_PATH = os.environ.get("T61_CSV", "t61_sim.csv")
COV_PATH = os.environ.get("T61_COV", "t61_coverage.json")
CSV_FIELDS = ["case", "kind", "name", "seed", "steps", "in_sha256", "out_sha256", "final_acc",
              "mismatches", "oracle_disagreements"]
ROWS = []

# ---------------------------------------------------------------- coverage
# (bins fixed before the first run; see results/p2_61_pe_bf16_summary.json)
OPC = ["zero", "sub", "normal", "inf", "nan"]


@CoverPoint("bf16.operand.a", xf=lambda i: i["a"], bins=OPC)
@CoverPoint("bf16.operand.b", xf=lambda i: i["b"], bins=OPC)
@CoverCross("bf16.operand.cross", items=["bf16.operand.a", "bf16.operand.b"])
@CoverPoint("bf16.product.kind", xf=lambda i: i["product"],
            bins=["nan", "inf_operand", "overflow_inf", "zero_operand", "flushed", "normal"])
@CoverPoint("bf16.acc.in", xf=lambda i: i["acc_in"], bins=["zero", "normal", "inf", "nan"])
@CoverPoint("bf16.add.kind", xf=lambda i: i["add"],
            bins=["special", "both_zero", "one_zero", "eff_add", "eff_sub"])
@CoverPoint("bf16.result.kind", xf=lambda i: i["result"],
            bins=["+0", "-0", "normal", "+inf", "-inf", "nan", "flushed_sum", "overflow_sum"])
def sample_step(i):
    """Classification of one MAC step."""


# alignment x normalisation combinations that cannot occur (d = exponent difference):
#  * d >= 2: a subtraction loses at most one leading bit, so no left shift by 2 or more
#    and no cancellation to zero                                    (in the first version)
#  * d = 0, "none": equal exponents either carry out (add) or lose >= 1 bit (subtract)
#  * d = 0, "left>=24": two 24-bit significands with equal exponents differ by >= 1 ulp,
#    so at most 23 leading bits cancel
#  * d = 1, "cancel_to_zero": different exponents cannot cancel exactly
#  * d >= 24, "carry_out": the larger operand is <= 2 - 2^-23 and the smaller < 2^-23
#    (relative), so the exact sum stays below 2
# The last four lines (5 bins) were added after the first 300-case run showed them
# unhit; see "coverage_bins_amended" in results/p2_61_pe_bf16_summary.json.
UNREACHABLE_ALIGN_NORM = (
    [(a, n) for a in ["2..3", "4..8", "9..23", "24..26", ">=27"]
     for n in ["left2..8", "left9..23", "left>=24", "cancel_to_zero"]]
    + [("0", "none"), ("0", "left>=24"), ("1", "cancel_to_zero"),
       ("24..26", "carry_out"), (">=27", "carry_out")])


@CoverPoint("bf16.add.align", xf=lambda i: i["align"],
            bins=["0", "1", "2..3", "4..8", "9..23", "24..26", ">=27"])
@CoverPoint("bf16.add.norm", xf=lambda i: i["norm"],
            bins=["carry_out", "none", "left1", "left2..8", "left9..23", "left>=24", "cancel_to_zero"])
@CoverCross("bf16.add.align_x_norm", items=["bf16.add.align", "bf16.add.norm"],
            ign_bins=UNREACHABLE_ALIGN_NORM)
def sample_add(i):
    """Alignment and normalisation of a finite, non-zero addition."""


@CoverPoint("bf16.round.kind", xf=lambda i: i["round"], bins=["exact", "down", "up", "tie_up", "tie_down"])
def sample_round(i):
    """Rounding decision of a normal result."""


def sample(info):
    sample_step(info)
    if info["align"] is not None and info["norm"] is not None:
        sample_add(info)
    if info["round"] is not None:
        sample_round(info)


# ------------------------------------------------------------------ driver
async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.clear.value = 1
    dut.valid.value = 0
    dut.a.value = 0
    dut.b.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.clear.value = 0


async def run_case(dut, kind, name, seed, steps):
    """clear, then one MAC step per clock; compares after every step."""
    dut.clear.value = 1
    dut.valid.value = 0
    await FallingEdge(dut.clk)
    dut.clear.value = 0
    assert int(dut.acc.value) == 0, "acc not +0 after clear"
    acc, outs, mism, disagree = 0, [], 0, 0
    for a, b in steps:
        dut.valid.value = 1
        dut.a.value = a
        dut.b.value = b
        await FallingEdge(dut.clk)
        got = int(dut.acc.value)
        want = mac_step(acc, a, b)
        exact, info = mac_step_exact(acc, a, b)
        sample(info)
        disagree += int(exact != want)
        if got != want:
            mism += 1
            if mism == 1:
                cocotb.log.error("MISMATCH %s %s: acc=%08x a=%04x b=%04x rtl=%08x golden=%08x",
                                 kind, name, acc, a, b, got, want)
        outs.append(got)
        acc = want                       # keep following the golden trajectory
        if got != want:                  # resynchronise the DUT is impossible; stop the case
            break
    dut.valid.value = 0
    await FallingEdge(dut.clk)           # hold: nothing changes without valid
    if not mism and int(dut.acc.value) != acc:
        mism += 1
    ROWS.append({
        "case": len(ROWS), "kind": kind, "name": name, "seed": seed, "steps": len(steps),
        "in_sha256": hashlib.sha256(b"".join(struct.pack("<HH", a, b) for a, b in steps)).hexdigest(),
        "out_sha256": hashlib.sha256(b"".join(struct.pack("<I", o) for o in outs)).hexdigest(),
        "final_acc": f"{outs[-1]:08x}", "mismatches": mism, "oracle_disagreements": disagree,
    })
    return mism + disagree


@cocotb.test()
async def test_directed(dut):
    """Directed edge cases."""
    await start(dut)
    bad = 0
    for name, steps in DIRECTED:
        bad += await run_case(dut, "directed", name, SEED, steps)
    assert bad == 0, f"{bad} mismatching steps in directed cases"


@cocotb.test()
async def test_random(dut):
    """T61_NCASES random cases from seed 1234."""
    await start(dut)
    bad = 0
    for i in range(NCASES):
        mode, steps = random_case(i)
        bad += await run_case(dut, "random", mode, f"{SEED}:{i}", steps)
        if (i + 1) % 1000 == 0:
            cocotb.log.info("random cases: %d / %d, mismatching steps so far: %d", i + 1, NCASES, bad)
    assert bad == 0, f"{bad} mismatching steps in {NCASES} random cases"


@cocotb.test()
async def test_zz_report(dut):
    """Write the CSV and the coverage report (always last)."""
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(ROWS)
    points = {}
    for name in sorted(coverage_db):
        if not name.startswith("bf16.") or name.count(".") != 2:
            continue
        item = coverage_db[name]
        hits = {str(k): int(v) for k, v in item.detailed_coverage.items()}
        points[name] = {"bins": len(hits), "bins_hit": sum(1 for v in hits.values() if v > 0),
                        "missed": sorted(k for k, v in hits.items() if v == 0)}
    total = sum(p["bins"] for p in points.values())
    hit = sum(p["bins_hit"] for p in points.values())
    with open(COV_PATH, "w") as f:
        json.dump({"bins": total, "bins_hit": hit, "percent": round(100.0 * hit / total, 4) if total else 0.0,
                   "points": points}, f, indent=2, sort_keys=True)
        f.write("\n")
    steps = sum(r["steps"] for r in ROWS)
    cocotb.log.info("cases: %d, MAC steps: %d, mismatching cases: %d, oracle disagreements: %d, "
                    "functional coverage: %d/%d bins", len(ROWS), steps,
                    sum(1 for r in ROWS if r["mismatches"]), sum(r["oracle_disagreements"] for r in ROWS),
                    hit, total)
    assert ROWS and all(r["mismatches"] == 0 and r["oracle_disagreements"] == 0 for r in ROWS)
