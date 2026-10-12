#!/bin/bash
# Compact heartbeat view for the main agent (Part 2).
cd "$HOME/ai-chip-lab"; source env.sh
echo "$(date '+%H:%M') $(sed -n '/Elapsed/p' STATUS.md | cut -c3-40)"
echo "running: $(ls results/.stages | grep running | tr '\n' ' ')| new: $(ls results/.stages | grep -vE '^(0|10_|20_|30_|40_|50_|60_demo)' | grep -v running | tr '\n' ' ')"
git log --format='%h %s' part2-green | head -3 | cut -c1-110
sed -n '/^## Needs owner (Part 2)/,/^## Requests (Part 2)/p' COORDINATION.md | sed -n 2,5p | grep -v '^$' | cut -c1-200
echo "lock: $(head -1 coord/heavy.lock.d/owner 2>/dev/null | cut -c1-100) | waiting: $(ls coord/heavy.waiting.d 2>/dev/null | tr '\n' ' ')"
echo "load $(sysctl -n vm.loadavg) | arch $(wc -l < results/sweeps/arch.jsonl) phys $(wc -l < results/sweeps/phys.jsonl) | disk $(df -g ~ | tail -1 | awk '{print $4}')G | containers: $(docker ps --format '{{.Names}}' | tr '\n' ' ')"
grep -E "^[0-9-]+ [0-9:]+ (LOCK|FREE)" logs/part2/lock.log 2>/dev/null | tail -4 | cut -c1-120 | sed "s#$HOME#~#g"
