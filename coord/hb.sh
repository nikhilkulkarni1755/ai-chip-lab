#!/bin/bash
# Compact heartbeat view for the main agent (Part 2).
cd "$HOME/ai-chip-lab"; source env.sh
date '+%H:%M'; sed -n 7,12p STATUS.md | cut -c1-200
git log --oneline part2-green | head -3
sed -n '/^## Needs owner (Part 2)/,/^## Requests (Part 2)/p' COORDINATION.md | sed -n 2,6p | cut -c1-200
echo "lock: $(cat coord/heavy.lock.d/owner 2>/dev/null | cut -c1-110) | waiting: $(ls coord/heavy.waiting.d 2>/dev/null | tr '\n' ' ')"
echo "load $(sysctl -n vm.loadavg) | arch $(wc -l < results/sweeps/arch.jsonl) phys $(wc -l < results/sweeps/phys.jsonl) | disk $(df -g ~ | tail -1 | awk '{print $4}')G | containers: $(docker ps --format '{{.Names}}' | tr '\n' ' ')"
tail -3 logs/part2/lock.log 2>/dev/null | cut -c1-130
