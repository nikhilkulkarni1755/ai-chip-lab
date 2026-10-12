#!/bin/bash
# Build the lab-sim image (heavy job: takes the lock) and write LAB_SIM_IMAGE to coord/images.env.
set -uo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; mkdir -p logs/02_images
TAG="${LAB_SIM_TAG:-lab-sim:$(date +%Y%m%d)}"
# LAB_SIM_NOLOCK=1 skips the heavy-job lock (only with an explicit exception from main, for cache-hit rebuilds)
LOCK="scripts/with_lock.sh infra"; [ "${LAB_SIM_NOLOCK:-0}" = 1 ] && LOCK=""
$LOCK perl -e 'alarm shift; exec @ARGV' 3000 \
  docker buildx build --platform linux/amd64 --progress=plain --load \
    -t "$TAG" -t lab-sim:latest -f docker/lab-sim/Dockerfile docker 2>&1 | sed -l "s#$HOME#~#g" | tee logs/02_images/lab_sim_build.log | grep -E '^#[0-9]+ (DONE|ERROR|CACHED)|ERROR|error:' ; st=("${PIPESTATUS[@]}")
[ "${st[0]}" = 0 ] || { echo "lab-sim build FAILED (see logs/02_images/lab_sim_build.log)" >&2; exit 1; }
id=$(docker image inspect "$TAG" --format '{{.Id}}')
touch coord/images.env
grep -v '^LAB_SIM_IMAGE' coord/images.env > coord/images.env.tmp || true
grep -v '^# lab-sim' coord/images.env.tmp > coord/images.env || true
{ echo "# lab-sim: local build, image id $id (also tagged lab-sim:latest)"; echo "LAB_SIM_IMAGE=$TAG"; } >> coord/images.env
rm -f coord/images.env.tmp
echo "built $TAG $id"
