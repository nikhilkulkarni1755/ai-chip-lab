# Activity-based power (stage 60_power_activity)

## What is measured
Power of the routed nangate45 `systolic_os` (4x4 INT8 output-stationary array, 4.0 ns clock, 11 152 standard cells) from the pinned OpenROAD:
`report_power` combines Liberty power tables with the switching activity of every pin.

* Dynamic power is roughly alpha * C * V^2 * f: alpha = transitions per cycle of a net, C = wire plus pin capacitance it drives, V = supply, f = clock.
  OpenROAD splits it into *internal* power (short-circuit and cell-internal node charging, from the Liberty tables) and *switching* power (charging the net load).
* Leakage is the static current of the transistors; it does not depend on activity except through state-dependent Liberty leakage tables
  (which input values a gate sees), so it varies a few percent between workloads.
* Why activity matters: C, V and f are fixed by the design, so alpha alone decides how much of the dynamic power is spent. A flop whose input never changes still toggles its clock pin, but nothing downstream moves.

## Methods compared
1. **ORFS default (vectorless):** every input gets activity 0.1 and duty 0.5, propagated through the logic. Our own run reproduces ORFS's `finish__power__total` (28.51 mW) to 1e-6 relative, which validates the setup.
2. **Activity from simulation:** zero-delay gate-level Icarus simulation of the *routed netlist* (same sha256 as the one analysed), three fixed-seed workloads (random INT8, 50 % zeros, all operands 127), 16 tiles of K = 32, 624 cycles, results checked against NumPy. `read_vcd -scope systolic_os` over the active window; 100 % of netlist pins received an activity.

## Results (results/power_activity.json, demo/assets/power_activity.png)
| workload | internal mW | switching mW | leakage mW | total mW | vs ORFS vectorless |
|---|---|---|---|---|---|
| ORFS default | 15.38 | 12.71 | 0.42 | 28.51 | 1.00 |
| random INT8 | 4.26 | 3.15 | 0.43 | 7.84 | 0.27 |
| 50 % zeros | 2.84 | 1.92 | 0.41 | 5.16 | 0.18 |
| all-max | 2.59 | 1.30 | 0.42 | 4.31 | 0.15 |

* Sparse data cuts dynamic power by 36 % versus random (a product with a zero operand is zero, so multiplier and accumulator nodes stay still); all-max, with constant operands, by 48 %.
* Leakage differs by 6 % across workloads, as expected for a mostly constant term.
* The vectorless estimate is 3.6x to 6.6x above any simulated workload: 0.1 transitions per cycle on every input is far more than a streaming array really toggles.

## Caveats
Zero-delay simulation has no glitches, so simulated switching power is a lower bound; 624 cycles at a 4.0 ns clock (not the 1.25 ns frontier clock); one design, one seed. The workload set is small and synthetic, not a trained network's activations.
