#!/usr/bin/env bash
# Run a command in the lab-sim container with the lab mounted at /lab (a real executable so that
# scripts/with_lock.sh can exec it).  usage: scripts/t3_dk.sh <cmd...>
set -e
LAB="${LAB:-$HOME/ai-chip-lab}"
source "$LAB/env.sh"; source "$LAB/coord/images.env"
exec docker run --rm --platform linux/amd64 -e PYTHONHASHSEED=0 -e T3_SUMMARY -e T3_PLOTS -e T3_PASSES -e T3_LOCK -e T3_RESUME \
  -v "$LAB":/lab -w /lab "$LAB_SIM_IMAGE" "$@"
