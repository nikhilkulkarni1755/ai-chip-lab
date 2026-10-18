# AI chip lab, Part 2: final status, 12 October

Part 2 finished at 20:14 PDT: 11 h 11 min of the 14 h budget (started 09:03).

Not everything is green. Task 3 fails, the routed gate-level simulation is partial, and the bf16 PE fails on one lint line.

Work was done on branch `part2-green` (185 commits). On 17 October, at your request, it was merged into `main` as a fast-forward and pushed, together with the `p2/*` agent branches. Start with `demo/index.html`; the README carries the same status table.

## Final state

| Item | Result | How it was tested |
|---|---|---|
| Task 1 (simulation, formal, EQY) | PASS | 10,000 cases vs NumPy on Verilator and Icarus, SBY proof, EQY |
| P1.3 Routed-netlist equivalence | PASS | EQY, 27 of 27 partitions proven, four negative controls rejected |
| P1.3 Routed-netlist gate-level simulation | PARTIAL | Icarus: 229 cases, 0 mismatches. Verilator never ran |
| Task 2 thresholds | PASS | ORFS shipped thresholds for gcd on nangate45 and sky130hd |
| P1.5 ORFS published cross-check | PASS | Exact match with ORFS's CI dashboard for the pinned commit |
| P1.1 Task 3 roofline | **FAIL** | Pre-registered criteria on all 21 ResNet-18 layers, 128×128 array |
| P1.4 Determinism (repro) | PASS | Full second run compared file by file with the first |
| P1.6 Sweeps | Cut at the gate | Every planned point listed as done, errored or cut |
| P1.2 / P1.7 Make recipes and `make all` | Run for real; exit non-zero | Each recipe recorded with exit code, run time and queue wait |
| P2.1 Activity-based power | PASS, 8 of 8 | OpenROAD `read_vcd` on the routed netlist, three workloads |
| P2.2 bf16 PE | **FAIL** on lint only | 10,042 cases on both simulators; ORFS flow for each MAC |
| P2.3 sky130hd comparison | PASS, 5 of 5 | Four ORFS runs of `systolic_os` on sky130hd |
| P2.4 SRAM with CACTI | PASS, 7 of 7 | CACTI 7 at 45 nm for the lab's buffer sizes |
| P2.5 Roadmap | Written | `docs/next.md` |
| `demo/run_demo.sh` | PASS | Real timed run: 115 s, 6 of 6 steps |

## What is not green, and why

### Task 3 roofline: FAIL

- **Criterion B** asks that arithmetic intensity rank inversely with SCALE-Sim's required DRAM bandwidth (Spearman rho ≤ −0.6). It fails on all three dataflows: ws +0.366, os −0.556, is −0.509. Three parties computed the same numbers independently.
- **Criterion A** (stall fraction under a fixed user bandwidth) is "not evaluated (cost)". One probe hold showed the largest layer alone needs more than 481 s; a full evaluation would take several hours of the single job queue.
- The Part 2 hypothesis was wrong in its mechanism: the bundled config already uses user bandwidth, and its stall counts are all zero.
- No criterion was changed after a result existed. The reviewer checked the git history.

### Routed gate-level simulation: PARTIAL

The Verilator model build of the 27k-cell flat routed netlist was stopped at 544 s and does not fit a lock hold on this machine. The task asks for Verilator if the cell models parse, and they do, so that half stays open.

### bf16 PE: FAIL on lint only

- One comment line in `rtl/mac_bf16.sv` is 104 characters against a limit of 100. Every other criterion passes, including bit-exact results on both simulators.
- The fix is on branch `p2/rtl` (commit `e21fd3b`) and was deliberately not merged. The RTL directory is an input of Task 1, the routed stage and repro, so merging would have forced over an hour of reruns for a cosmetic change.

### `make all` exit code

`make all RESUME=1` ran for real from 19:11 to 19:58 and exits non-zero listing Task 3 as the only failed stage. That follows from the Task 3 verdict.

### Sweeps: accounted for, not complete

- **Sweep A (architecture):** 173 of 264 planned points done, 91 cut at the gate. The two points that failed in Part 1 now pass, which supports the out-of-memory explanation.
- **Sweep B (physical):** 16 of 26 refinement points done, 6 cut deliberately, 4 not reached. `systolic_os` closes at 1.25 ns at 30, 40 and 50 % utilization; the 30 % frontier is bracketed by a failing run at 1.20 ns.

## Results worth knowing

### Determinism

- The first repro at 15:40 failed on Task 3. The cause was bookkeeping and provenance (a scheduler script changed between passes, one summary regenerated outside the container, a commit during the rerun). No SCALE-Sim report differed.
- A clean Task 3 pass on frozen inputs and a full rerun passed at 19:07. One file class is excluded and reported: three `timing.timing` run-time measurement files.
- After the final `make all` re-executed Task 1, Task 2 and Task 3, the files on the branch were checked again: Task 1's five files and Task 3's 42 files match the repro hashes, and the fresh Task 2 runs are identical to every earlier run.

### Activity-based power (routed netlist, 4.0 ns clock)

| Workload | Total power |
|---|---|
| ORFS default (vectorless) | 28.51 mW |
| random INT8 | 7.84 mW |
| 50 % zeros | 5.16 mW |
| all-max | 4.31 mW |

The simulation is zero-delay, so there is no glitch power and the workload figures are a lower bound.

### INT8 MAC vs bf16 MAC (nangate45, 1.25 ns clock)

| | INT8 | bf16 | Ratio |
|---|---|---|---|
| Setup slack | +0.006 ns | −2.841 ns | |
| Area | 1,676 µm² | 5,064 µm² | 3.02× |
| Power (vectorless) | 10.7 mW | 64.2 mW | 6.0× |

The bf16 power figure is at a clock it does not meet.

### nangate45 vs sky130hd (`systolic_os`, 30 % utilization)

| Metric | nangate45 | sky130hd | Ratio |
|---|---|---|---|
| Fastest tested closing clock | 1.25 ns | 6.75 ns | 5.4× |
| Area | 23,970 µm² | 121,473 µm² | 5.1× |
| Energy per cycle | 128 pJ | 514 pJ | 4.0× |

The sky130hd frontier is a coarse bracket (fails at 5.5 ns, closes at 6.75 ns), so the clock ratio is an upper bound on the true slowdown.

### SRAM (CACTI 7, 45 nm, per buffer)

| Size | Area | Access time |
|---|---|---|
| 64 kB | 0.27 mm² | 0.50 ns |
| 1024 kB | 4.19 mm² | 1.96 ns |
| 6144 kB | 26.1 mm² | 4.16 ns |

No ORFS run includes an SRAM macro, so these absolute numbers have nothing in the lab to check against.

## What needs you

1. **Done on 17 October:** `part2-green` was merged into `main` and pushed. The Part 1 agent branches (`arch/t3`, `demo/main-work`, `infra/runtime`, `pnr/t2`, `rtl/t1`) stay local: their pre-rewrite history carries a machine identity and personal paths, and their content is already on `main`.
2. **Optional bf16 fix:** `git cherry-pick e21fd3b`, then `scripts/t61_run.sh 10000 results && python3 scripts/p2_61_finish.py` (about 4 minutes of lock). `make all` will then rerun Task 1 and the routed stage. Keep the `p2/rtl` branch until you decide.
3. **To run anything again:** the VM is stopped. `source ~/ai-chip-lab/env.sh && colima start` brings it back with all images intact.

## State of the machine

- Colima is stopped; the heartbeat and keep-awake processes are ended.
- The working tree is clean. The privacy scan reports 0 findings in 535 tracked files.
- This file was committed to `part2-green` after the final state was recorded, and is on `main` since the 17 October push.

## Comments on the process

- **The single job queue was the bottleneck all day.** Only one heavy container job can run at a time on this machine. Recipes often waited far longer than they ran: `make t2` ran 9 minutes and waited 60; the repro rerun ran about 30 minutes inside 125 minutes of wall time.
- **Every decision that traded scope for time is recorded** in the coordination doc as P2-0 to P2-12, each with its reason. The ones that shaped the result: one probe hold for criterion A, 45 minutes of proof time for the routed netlist, a clean repro on frozen inputs, a coarse sky130hd search, and a stage-input freeze before the final `make all`.
- **An independent reviewer audited twice.** At the gate it found the results sound but the presentation overstated in places (sweeps shown as done, a PASS badge on the Icarus-only result, "every recipe ran for real"). All were corrected. The final audit found no PASS that the files contradict.
- **Mistakes made and corrected the same hour:** a Task 3 job held the lock for 13 minutes and finished nothing; one agent truncated the coordination file and restored it; one agent amended another's commit; the repro marker said "done" while the verdict was false; the first fail-soft test skipped a failed stage because of that marker.
- **One hold was wasted.** A sky130hd point at 4.0 ns took the lock before I could cut it, and the permission layer refused my attempt to stop the running flow. It ran 28 minutes and failed timing, as expected.
- **Mid-run restart.** Four agents were stopped at 13:05 and replaced with fresh ones briefed from the files on disk. No results were lost; about 20 minutes were.
- **Approval prompts.** Agents cleaning scratch directories triggered `rm -rf` prompts. They were told to leave scratch under `.cache/` and stop running recursive deletes as shell commands.

## Not verified by anyone

- Whether the 27 partitions cover every matched point of the design (taken from EQY's own partitioning and final verdict).
- The Task 2 rerun hashes beyond the stage's own comparison.
- That the cherry-picked bf16 fix actually clears lint (it was not run).
- How the page renders in a browser.

The reviewer's two audits are in `.cache/review/REPORT_gate.md` and `.cache/review/REPORT_final.md`.
