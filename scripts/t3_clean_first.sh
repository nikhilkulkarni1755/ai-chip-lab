#!/usr/bin/env bash
# Decision P2-10: clean Task 3 cheap-set FIRST pass for `make repro`, on frozen committed inputs.
#   scripts/t3_clean_first.sh        (host process; per-job locks inside t3_run.sh; the caller must NOT hold the lock)
# Replaces results/t3 with a fresh run of bundled ws/os/is + fit + 3 CALC runs, generated (incl. roofline2.json and the
# summary) inside the container by the same scheduler as the repro rerun. No criterion-A job is started (T3_JOBS=cheap), so the
# probe state is "not_run" in this pass and in the repro rerun alike; the probe itself is kept in results/evidence/31_a_probe*.
# The superseded Part 1 synthetic roofline (roofline.json + its .done) is carried over unchanged from the earlier run.
set -euo pipefail
LAB="${LAB:-$HOME/ai-chip-lab}"; cd "$LAB"
if [ -n "$(git status --porcelain -- arch docker/requirements.lock model scripts/t3_run.sh)" ]; then echo "t3 inputs have uncommitted changes; refusing"; exit 3; fi
[ -e results/t3/roofline.json ] || { echo "results/t3/roofline.json missing"; exit 4; }
rm -rf results/t3.partial results/t3.rerun.tmp
mkdir -p results/t3.partial/.jobs
cp results/t3/roofline.json results/t3.partial/roofline.json
cp results/t3/.jobs/roofline_synthetic.done results/t3.partial/.jobs/
T3_RESUME=1 T3_LOCK=1 T3_JOBS=cheap T3_PASSES=1 T3_PLOTS=0 scripts/t3_run.sh results/t3
