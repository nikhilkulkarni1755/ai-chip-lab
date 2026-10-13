# bf16 processing element (stage `61_pe_bf16`)

**Status: FAIL on one criterion (`lint_clean`); every other criterion passes.** Result files:
`results/p2_61_pe_bf16.json` (common schema), `results/p2_61_pe_bf16_summary.json` (criteria written
before any run, commit c0e5b87), evidence `results/evidence/61_*.txt`.

## What it is
`rtl/mac_bf16.sv`: `acc(FP32) <= clear ? +0 : valid ? acc + a(bf16) * b(bf16) : acc`.
- The product of two bf16 values has at most 16 significant bits, so it is exact in FP32; only the
  addition rounds (round-to-nearest-even).
- Subnormals are flushed to zero (inputs, product and sum): no denormalising shifter and no
  subnormal rounding, which is the cheaper choice and the one the golden model applies too.
- Any NaN operand, inf x 0 and inf - inf give the quiet NaN 0x7FC00000; overflow gives infinity.

## How it was tested
- Oracle: `tb/bf16_golden.py` (ml_dtypes / NumPy float32 with the same flush, NaN and overflow rules),
  itself cross-checked against an exact-rational reference on 20,002 MAC steps (0 disagreements).
- cocotb on Verilator and Icarus, seed 1234: 10,000 random cases + 42 directed cases = 84,651 MAC
  steps per simulator, accumulator compared bit for bit after every step: 0 mismatches, the two CSVs
  are byte-identical, 101 of 101 functional-coverage bins hit.
- Negative control: an RTL copy that rounds half up instead of half to even is detected (55
  mismatching steps).
- Commands: `scripts/t61_run.sh 10000 results`, `scripts/p2_61_orfs.sh mac_int8`,
  `scripts/p2_61_orfs_staged.sh mac_bf16`, `python3 scripts/p2_61_finish.py`.

## INT8 MAC vs bf16 MAC (nangate45, each MAC alone, same flow settings, clock 1.25 ns)
1.25 ns is the closure clock of the INT8 MAC array (sweep B frontier of `systolic_os`), fixed before
the first run. Numbers are from each flow's own `metadata.json` (`results/evidence/61_ppa.txt`).

| | INT8 MAC | bf16 MAC | bf16 / INT8 |
|---|---|---|---|
| Setup WNS at 1.25 ns | +0.006 ns (met) | -2.841 ns (not met) | |
| fmax reported by the flow | 927.7 MHz | 330.7 MHz | 0.36x |
| Area | 1676 um^2 | 5064 um^2 | 3.02x |
| Standard cells | 948 | 4083 | 4.31x |
| Power (flow's vectorless estimate) | 10.7 mW | 64.2 mW | 6.0x |
| DRC errors | 0 | 0 | |

Caveats: one run per design, so "max clock" is not a searched timing-closure frontier; the WNS covers
the input-to-register paths as well (inputs arrive 20 % into the cycle); the bf16 power figure is at
a clock the bf16 MAC does not meet. The bf16 flow needs more than one 10-minute lock hold on this
machine and was run with one hold per ORFS stage group.

## Why floating point costs more area
The INT8 MAC is an 8x8 multiplier and a 32-bit adder. The bf16 MAC's multiplier is the same size
(8x8 significands), so the extra area is not in the multiply; it is in what an FP addition needs
around its adder: unpacking and special-case detection, a magnitude compare and swap, an alignment
shifter (up to 31 positions, with sticky collection), a 28-bit add/subtract, a leading-zero count and
a normalisation shifter, rounding with its own carry chain, exponent arithmetic and the result
multiplexer for NaN / infinity / zero / flush. All of it sits in one clock cycle between the operand
inputs and the accumulator, which is also why the single-cycle bf16 MAC is about three times slower.

## Open item: the one failing criterion
`lint_clean` fails because verible-verilog-lint reports one comment line of 104 characters (limit
100) in `rtl/mac_bf16.sv` (line 91); Verilator's lint is clean. The fix is a comment-only change and
is deliberately **not merged** (COORDINATION.md, Decision P2-12): `rtl/` is a stage input of `t1`,
`t1-routed` and the repro check, so merging it after those passed would make `make all` re-execute
them and leave the repro verdict not matching the checked-in files.

To apply it later:
```
git cherry-pick e21fd3b          # branch p2/rtl: comment shortened, no logic change
scripts/t61_run.sh 10000 results && python3 scripts/p2_61_finish.py     # about 4 minutes of lock
```
Afterwards `RESUME=1 make all` will re-run `t1` and `t1-routed` (pass
`T1R_RESUME=1 T1R_SKIP=gls_verilator` to `make t1-routed` to keep the proven partitions).
