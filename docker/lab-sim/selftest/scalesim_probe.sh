#!/bin/bash
# Runs INSIDE lab-sim: one real SCALE-Sim run (bundled TPU-like config, bundled alexnet_part topology).
B=/lab/arch/bundled; out=$(mktemp -d); cd /tmp
python -m scalesim.scale -c $B/configs/google.cfg -t $B/topologies/conv_nets/alexnet_part.csv \
  -l $B/layouts/conv_nets/test.csv -p "$out" > /tmp/scalesim_probe.log 2>&1; rc=$?
f=$(find "$out" -name COMPUTE_REPORT.csv | head -1)
if [ "$rc" = 0 ] && [ -s "$f" ]; then
  echo "OK    scalesim run          google.cfg + alexnet_part: $(($(wc -l < "$f") - 1)) layers, COMPUTE_REPORT.csv sha256 $(sha256sum "$f" | cut -c1-16)…"
else
  echo "FAIL  scalesim run          exit=$rc: $(grep -E 'Error|ERROR' /tmp/scalesim_probe.log | tail -1)"; tail -6 /tmp/scalesim_probe.log; exit 1
fi
