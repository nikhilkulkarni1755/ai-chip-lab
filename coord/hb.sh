#!/bin/bash
# Compact heartbeat view for the main agent.
cd "$HOME/ai-chip-lab"; source env.sh
sed -n 9p STATUS.md; ls results/.stages | tr '\n' ' '; echo
git log --oneline | head -2
sed -n '/^## Needs owner/,/^## Requests/p' COORDINATION.md | sed -n 2,5p | cut -c1-200
echo "load $(sysctl -n vm.loadavg) | arch $(grep -c '"cycles"' results/sweeps/arch.jsonl 2>/dev/null)/$(wc -l < results/sweeps/arch.jsonl) phys $(wc -l < results/sweeps/phys.jsonl) | disk $(df -g ~ | tail -1 | awk '{print $4}')G"
docker ps --format '{{.Names}} {{.RunningFor}}' | tr '\n' ';'; echo
tail -1 logs/40_sweeps/arch_sweep.log | cut -c1-100; tail -1 logs/40_sweeps/phys.log | cut -c1-100
ls -t logs/50_repro 2>/dev/null | head -2 | tr '\n' ' '; pgrep -f phys_sweep.py >/dev/null && echo "phys_sweep alive" || echo "phys_sweep NOT running"
