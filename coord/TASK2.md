# Part 2 task spec (owner's text): Get everything green, then extend

Machine: old 2-core Intel MacBook, 8 GB RAM. **No Homebrew (never install or use `brew`). No sudo.** Containers run in the Colima VM; always `source ~/ai-chip-lab/env.sh` first. Nobody watches; the owner looks only at the regenerated demo and README.

## Status at the start of Part 2
| Check | Status | Notes |
|---|---|---|
| Runtime, Images | PASS | |
| Task 1: sim vs NumPy, SBY, EQY | PASS | EQY compared RTL against the *generic Yosys netlist*, not the routed nangate45 netlist |
| Task 2: ORFS gcd within thresholds | PASS | Neither reference design is timing-closed at its reference clock: nangate45 0.25 ns → WNS −0.16 ns; sky130hd 1.1 ns → WNS −1.46 ns |
| Task 3: SCALE-Sim vs analytic | **FAIL** | Only the roofline-vs-stalls agreement criteria fail; analytic cycle fit and byte identity pass |
| Sweep A | Incomplete | 165 of 264 points done, 97 not reached, 1 error, 1 timeout |
| Sweep B | Coarse | gcd frontier ≈ 0.42 ns; systolic_os closes at 1.6 ns, fails at 1.2 ns, 30 % utilization only |
| Repro | PASS | 10/10, but Task 2 reused its original two runs; systolic_os has a single run |
| Make recipes | Untested | Only `make preflight` was executed as a recipe |

## Hard constraints
- **Never block on an interactive prompt.** Timeouts on every long command; non-interactive flags everywhere.
- Needs sudo or Homebrew → mark **BLOCKED** with the exact command for the owner; continue with the rest.
- **Stay inside `~/ai-chip-lab/`.** No system/shell-profile changes; no `rm -rf` outside it.
- Keep the Mac awake (`caffeinate -dimsu` is running).
- **Only one heavy job at a time. Route EVERY container job through `scripts/with_lock.sh`.** Never two ORFS flows, never ORFS plus SCALE-Sim, concurrently.
- **Fail soft.** Two retries per stage, then log the error, last 50 log lines and diagnosis; move on.
- **Be resumable.** Stage markers in `results/.stages/`, JSONL keyed by parameters; skip completed work on restart.
- **Never weaken a check just to make it pass.** A criterion may change only if you can show it measured the wrong thing. Then: keep the old criterion and its result in the summary JSON as `superseded`; add the new one; write the reasoning with evidence in `COORDINATION.md` under "Decisions (Part 2)". An honest FAIL beats a fake PASS.
- **Pin everything.** Don't change pinned image digests/tool versions unless required for a fix; any change goes in `versions.lock` with the reason.
- **Privacy.** Pre-commit hook and `scripts/evidence_privacy.py` keep passing: no personal paths, hostnames, credentials in committed files.
- **Git.** Commit to branch **`part2-green`**, logical commits (one per stage). **Do NOT push. Do not touch `main`.** The owner reviews and merges.
- **Time budget 14 h** (see `budget_part2.json`): Phase 1 up to 8 h; Phase 2 whatever remains minus 1 h reserved for the final `make all` verification and demo rebuild. The demo must always get rebuilt.
- Heartbeat: `STATUS.md` after every stage and every 10 sweep points (generated from markers). Logs go to `logs/part2/<stage>/`.

# PHASE 1: Get everything green

## P1.1 Fix or correctly re-specify the Task 3 roofline check (stage `31_roofline_fix`)
**Hypothesis to test first.** SCALE-Sim's default bandwidth mode *computes the DRAM bandwidth each layer requires* instead of enforcing a limit; if so it reports no meaningful memory stalls and a "roofline vs stalls" correlation has nothing to correlate against.
1. Read the `arch/` configs and the pinned SCALE-Sim version. Find which bandwidth mode was used (a `Bandwidth`/`UseUserBandwidth`-style option; check that version's source/README for the exact key).
2. Look at the stall columns in the existing Task 3 reports: all zero or nearly constant? Save that as evidence.
3. Fix according to what you find:
   - **(a) Stalls were zero or meaningless.** Add a run with a fixed **user-specified DRAM bandwidth**: a few realistic values (low/mid/high words per cycle), recorded. Re-evaluate: low-arithmetic-intensity layers should show more stall cycles and the rank correlation should have the expected sign. Also add a second, mode-independent criterion: in calculated-bandwidth mode, arithmetic intensity should **inversely** rank-correlate with SCALE-Sim's reported required DRAM bandwidth.
   - **(b) Stalls were real but still disagreed.** Debug `model/analytic.py`'s intensity calculation: bytes per element (INT8 vs the config's word size); whether reuse and SRAM capacity are counted; per-dataflow traffic. Fix the actual bug, with a unit test showing the hand-calculation for one layer.
4. **Pick thresholds before looking at the new results, and write them down.** Criterion = Spearman ρ sign plus a magnitude (e.g. |ρ| ≥ 0.6) per dataflow, or a documented alternative. Don't tune thresholds after seeing results.
5. Run it twice; confirm byte-identical outputs.
6. Update `results/t3_summary.json` (superseded criteria kept) and `demo/assets/t3_roofline.png`. Add `docs/t3_roofline_explained.md`: what the roofline is; what SCALE-Sim's bandwidth modes do; why the original check failed; what the new check proves.

## P1.2 Run every `make` recipe for real (stage `32_make_recipes`)
1. Run each recipe for real, in order: `make runtime images t1 t2 t2-stretch t3 repro demo`. Reuse cached images; don't re-download. If a recipe drifted from the script that originally ran, fix the recipe to call the same script with the same arguments. Record each recipe's exit code and runtime in `results/make_recipes.json`.
2. `make t3` must now exit 0 if P1.1 succeeded.
3. `make all` must: run fail-soft; always build the demo; exit non-zero listing failed stages if any fail. Test that last behaviour once by temporarily forcing a stage marker to fail, then restore it.
4. Replace the README's "honesty note on the recipes" with the actual verification result.

## P1.3 Equivalence against the real routed netlist (stage `11_eqy_routed`)
1. Find the ORFS logic-equivalence step that was disabled (README caveat, `COORDINATION.md`) and why.
2. Re-enable it for `systolic_os` on nangate45 if feasible. Otherwise run **EQY / Yosys equivalence** directly: **Gold** `rtl/systolic_os.sv`; **Gate** the final routed netlist (`6_final.v` or equivalent) with the nangate45 Liberty/Verilog cell models. Keep the split strategy that worked: (1) `mac_int8` including the multiplier, (2) the 4×4 array with `mac_int8` black-boxed. Watch for netlist changes from the physical flow (buffers inserted, gates resized, clock-tree cells, tie cells, hold buffers). Map them properly; don't drop logic.
3. If the full proof is too slow for 8 GB RAM, prove each PE plus the array wrapper; document the scope exactly.
4. Also run the **post-route gate-level simulation**: routed netlist + cell models through the Task 1 cocotb test, 200 cases, fixed seed, Icarus (and Verilator if the cell models parse). 0 mismatches against NumPy. Zero-delay simulation; state that this is a logical check, not a timing check.
5. Update `t1_summary.json` with `eqy_routed_pass` and `gls_routed_pass` plus scope notes.

## P1.4 Complete the determinism story (stage `51_repro_full`)
1. Run **nangate45/gcd and sky130hd/gcd a third time from clean** (sky130 only if disk allows: `df` first, ≥ 15 GB free). Compare against both previous runs.
2. Run **systolic_os on nangate45 a second time from clean**, same clock and utilization as its first run; compare.
3. Fold everything into `results/repro_report.json`: each check gets a run count and an identical/different verdict.
4. If anything differs, find what (metric, flow stage, thread count) and record it as a determinism finding. It stays FAIL; don't hide it.

## P1.5 Check Task 2 timing against ORFS's own published results (stage `21_orfs_crosscheck`)
1. Find the reference metrics ORFS publishes for `nangate45/gcd` and `sky130hd/gcd` at the pinned ORFS commit: `metadata-base-ok.json` / rules files and CI metrics in the repo. Compare WNS/TNS, area, power against ours.
2. Add a criterion `matches_published` within a stated tolerance.
3. Explain in `docs/t2_timing_explained.md` why the reference designs pass ORFS's thresholds despite negative slack at the reference clock (ORFS sets these clocks aggressively on purpose; its rules allow some negative slack — confirm from the rules files, not from memory).
4. Use sweep B's measured frontier (≈ 0.42 ns) as the real closure clock, and state it plainly.

## P1.6 Finish and refine the sweeps (stage `41_sweeps_finish`)
1. **Sweep A.** Resume to finish the remaining 97 points. Rerun the 1 error and the 1 timeout point with a doubled timeout; diagnose if they fail again. SCALE-Sim is single-threaded: expect slow progress; run it in the lock queue between ORFS jobs.
2. **Sweep B, `systolic_os`.** Refine the frontier between 1.2 and 1.6 ns in 0.05 ns steps at 30 % utilization. Then add utilization 40 % and 50 % at the 3–4 periods nearest the frontier. ~30 min per point: budget accordingly; stop at the Phase 1 deadline.
3. **Sweep B, `gcd`.** Add points at 0.40–0.43 ns in 0.005 ns steps for utilizations 40 and 60, to pin down the zero-margin edge.
4. Regenerate the sweep heatmaps and frontier plots.

## P1.7 Phase 1 gate
Run `make all` for real once. Regenerate `demo/index.html` and `README.md` via `scripts/demo_build.py`.
**"Green"** = every baseline check row PASS, and: sweeps DONE with all planned points accounted for (completed, errored, or deliberately cut and explained); every PASS cites its evidence file. If something remains FAIL, the README must say so plainly with diagnosis and next action. Then continue to Phase 2 anyway if time allows.

# PHASE 2: Next steps (only after the Phase 1 gate, in this order)
Each item: own stage, own summary JSON with pass criteria **written before running**, evidence PNGs, a demo section. Stop starting new items when the reserve deadline hits.

## P2.1 Activity-based power (stage `60_power_activity`)
1. cocotb + Verilator on `systolic_os`: dump **VCD** (or **SAIF**) for three fixed-seed workloads: random INT8; sparse (50 % zeros); all-max operands.
2. Feed into **OpenROAD power analysis** (`read_vcd` / `read_saif` + `report_power`, whichever the pinned version supports) on the routed nangate45 `systolic_os`.
3. Compare against ORFS's default vectorless estimate.
4. Plot: power per workload vs the default estimate.
Expected sanity: sparse uses less dynamic power than random; leakage roughly constant across workloads. Explain in `docs/power_explained.md`: dynamic power (αCV²f), leakage, why switching activity matters.

## P2.2 bf16 processing element (stage `61_pe_bf16`)
1. `rtl/mac_bf16.sv`: bf16 × bf16 multiply into an FP32 accumulate. Simple: round-to-nearest-even, flush subnormals to zero (document the choice).
2. Golden model with `ml_dtypes` / NumPy applying the **same** rounding and subnormal handling. Bit-exact match required.
3. cocotb on both simulators: 10k random + directed edge cases (±0, ±inf, NaN propagation, max/min normal, rounding ties, values that would be subnormal).
4. Synthesize through ORFS on nangate45 at the INT8 MAC's closure clock.
5. Table: INT8 vs bf16 MAC area, power, max clock. Explain why floating point costs more area.
If time is short, do FP8 E4M3 instead (smaller, faster to close).

## P2.3 `systolic_os` on sky130hd (stage `62_pdk_compare`)
Only if disk allows: find its timing-closure frontier (coarse search); compare PPA against nangate45 at their respective frontiers. Explain plainly why sky130 is slower and larger (130 nm process vs Nangate's 45 nm library).

## P2.4 SRAM modeling (stage `63_sram_cacti`)
1. Build **CACTI** (official source repository, pinned SHA) inside the lab-sim image or a new pinned image.
2. Model the double-buffered scratchpad sizes used in sweep A's SRAM configs: area, read/write energy, access time.
3. Combine with sweep A: rough energy per inference for 2–3 configurations. Label clearly as an order-of-magnitude model.

## P2.5 Roadmap (stage `64_roadmap`, no long compute)
`docs/next.md`: concrete plan for the next round, each item with a one-line why and a rough cost on this machine: Gemmini/Chipyard (likely too heavy for 8 GB — say so, propose a bigger machine); TVM/VTA or MLIR/CIRCT flow; DREAMPlace (needs a GPU); LLM-generated-RTL evaluation against VerilogEval using this lab's harness; double-buffered SRAM in the RTL.

# Final steps (always run, even after failures)
1. Run `make all` for real (fail-soft), then `make demo`.
2. In `demo/index.html` and `README.md`: **Part 2 summary** (before/after status table, every row at the start of this run next to its state now); **What changed** (files added/modified, one line each); **How each new result was tested** (oracle, commands, seeds, criteria, actual result); **Decisions and superseded criteria** linking to `COORDINATION.md`; **Remaining caveats and BLOCKED items**, each with the exact command for the owner; **Where to go next** from `docs/next.md`.
3. Run `bash demo/run_demo.sh`; confirm it still passes in about 5 minutes. Add the routed-netlist simulation and the fixed roofline check to it if each stays under 1 minute.
4. Run the privacy hook. Commit everything to `part2-green` in logical commits. Don't push.
5. Stop the Colima VM (`colima stop`) unless the demo needs it. Final `STATUS.md` says **DONE**, with the branch name and a pointer to `demo/index.html`.
