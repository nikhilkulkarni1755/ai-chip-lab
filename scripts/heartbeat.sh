#!/bin/bash
# 1-minute heartbeat: refresh STATUS.md, append to logs/run.log. Exits at the final deadline.
LAB="$HOME/ai-chip-lab"; END=$(python3 -c "import json;print(json.load(open('$LAB/budget.json'))['deadline_final_epoch'])")
while [ "$(date +%s)" -lt "$((END+1800))" ]; do
  "$LAB/scripts/status.sh"; echo "$(date '+%F %T') heartbeat $(ls $LAB/results/.stages 2>/dev/null | tr '\n' ' ')" >> "$LAB/logs/run.log"; sleep 60
done
