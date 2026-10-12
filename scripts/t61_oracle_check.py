#!/usr/bin/env python3
"""bf16 MAC oracle cross-check: NumPy/ml_dtypes golden vs exact-rational reference.

usage: t61_oracle_check.py [min_steps=20000] [out.json]
Runs all directed cases and random cases 0.. until at least min_steps MAC steps were
compared; exit code 0 iff every accumulator value agrees bit-for-bit.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tb"))
from bf16_cases import DIRECTED, SEED, random_case  # noqa: E402
from bf16_golden import mac_step, mac_step_exact  # noqa: E402


def main():
    min_steps = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    steps = mism = cases = 0
    first = None
    seen = {}

    def run(name, seq):
        nonlocal steps, mism, first
        acc = 0
        for a, b in seq:
            g = mac_step(acc, a, b)
            e, info = mac_step_exact(acc, a, b)
            for k, v in info.items():
                if v is not None:
                    seen.setdefault(k, {}).setdefault(v, 0)
                    seen[k][v] += 1
            steps += 1
            if g != e:
                mism += 1
                first = first or {"case": name, "acc": hex(acc), "a": hex(a), "b": hex(b),
                                  "golden": hex(g), "exact": hex(e)}
            acc = g

    for name, seq in DIRECTED:
        run(name, seq)
    i = 0
    while steps < min_steps:
        run(f"random:{i}", random_case(i)[1])
        i += 1
        cases += 1
    out = {"seed": SEED, "directed_cases": len(DIRECTED), "random_cases": cases, "steps_compared": steps,
           "mismatches": mism, "first_mismatch": first,
           "classification_counts": {k: dict(sorted(v.items())) for k, v in sorted(seen.items())}}
    text = json.dumps(out, indent=1, sort_keys=True)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as f:
            f.write(text + "\n")
    print(text)
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
