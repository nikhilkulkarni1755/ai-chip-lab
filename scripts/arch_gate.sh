#!/usr/bin/env bash
# Sweep A gate accounting (stage 41_sweeps_finish, part A): waits for the sweep deadline in budget_part2.json, lets the driver
# finish, then writes results/sweeps/arch_summary.json, heatmaps and the marker. Native, light (no container).
set -u
LAB="${LAB:-$HOME/ai-chip-lab}"; cd "$LAB"; source env.sh
PY="$LAB/.venv-arch/bin/python3"
dl=$(python3 -c "import json;print(int(json.load(open('budget_part2.json'))['deadline_sweeps_stop_epoch']))")
while [ "$(date +%s)" -lt "$dl" ] && [ ! -e coord/arch_gate.now ]; do sleep 30; done
for i in $(seq 1 20); do pgrep -f 'sweeps/arch_sweep.py' >/dev/null || break; sleep 30; done
mkdir -p results/evidence logs/part2/41_sweeps_finish
"$PY" sweeps/arch_summary.py > results/evidence/41_sweep_A_accounting.txt 2>&1
"$PY" sweeps/arch_plots.py >> results/evidence/41_sweep_A_accounting.txt 2>&1
{ echo "driver still running at accounting time: $(pgrep -f 'sweeps/arch_sweep.py' >/dev/null && echo yes || echo no)"; date; } >> results/evidence/41_sweep_A_accounting.txt
echo "41_sweeps_finish_A: sweep A accounted at $(date +%T); see results/sweeps/arch_summary.json and results/evidence/41_sweep_A_accounting.txt" > results/.stages/41_sweeps_finish_A.done
git add results/sweeps/arch.jsonl results/sweeps/arch_summary.json results/evidence/41_sweep_A_accounting.txt results/.stages/41_sweeps_finish_A.done demo/assets/sweepA_*.png 2>/dev/null
git commit -q -m "sweep A: gate accounting (every planned point done, errored with diagnosis, or cut with reason), heatmaps, marker 41_sweeps_finish_A

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>" -- results/sweeps/arch.jsonl results/sweeps/arch_summary.json results/evidence/41_sweep_A_accounting.txt results/.stages/41_sweeps_finish_A.done demo/assets 2>&1 | tail -1
