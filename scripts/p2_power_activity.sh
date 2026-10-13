#!/bin/bash
# P2.1 stage 60_power_activity: activity-based power of the routed nangate45 systolic_os for three fixed-seed workloads.
#   scripts/p2_power_activity.sh            (needs results/power_vcd/{random,sparse50,allmax}.{vcd,json} from scripts/t1_power_vcd.sh)
# One lock hold for all OpenROAD analyses (a few minutes); the summary/plot step is native and light.
set -u
LAB="$HOME/ai-chip-lab"; cd "$LAB" || exit 2; source env.sh; source coord/images.env
mkdir -p logs/part2/60_power_activity results/power_activity
for w in random sparse50 allmax; do
  [ -s results/power_vcd/$w.vcd ] && [ -s results/power_vcd/$w.json ] || { echo "missing results/power_vcd/$w.{vcd,json}: run scripts/t1_power_vcd.sh first"; exit 2; }
done
mkdir -p results/power_activity/raw
# one lock hold per step (each hold well under 10 min); a step whose log already has a power report is skipped (resumable)
for step in vectorless random sparse50 allmax repeat; do
  case $step in vectorless) f=vectorless;; repeat) f=random.window.repeat;; *) f=$step.whole;; esac
  grep -q "@@POWER-END" "results/power_activity/raw/$f.log" 2>/dev/null && { echo "skip $step (done)"; continue; }
  scripts/with_lock.sh pnr docker run --rm --platform linux/amd64 --cpus 2 -v "$LAB":/lab -w /lab "$ORFS_IMAGE" \
    bash /lab/scripts/p2_power_modes.sh $step 2>&1 | tee -a logs/part2/60_power_activity/modes.log
done
"$LAB/.venv-pnr/bin/python" scripts/p2_power_summary.py
