#!/bin/bash
# Build the lab-sim image (heavy job: takes the lock) and write LAB_SIM_IMAGE to coord/images.env.
set -euo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; mkdir -p logs/02_images
TAG="lab-sim:$(date +%Y%m%d)"
scripts/with_lock.sh infra perl -e 'alarm shift; exec @ARGV' 3000 \
  docker buildx build --platform linux/amd64 --progress=plain --load \
    -t "$TAG" -t lab-sim:latest -f docker/lab-sim/Dockerfile docker 2>&1 | sed -l "s#$HOME#~#g" | tee logs/02_images/lab_sim_build.log | grep -E '^#[0-9]+ (DONE|ERROR|CACHED)|ERROR|error:' || true
id=$(docker image inspect "$TAG" --format '{{.Id}}')
touch coord/images.env
grep -v '^LAB_SIM_IMAGE' coord/images.env > coord/images.env.tmp || true
grep -v '^# lab-sim' coord/images.env.tmp > coord/images.env || true
{ echo "# lab-sim: local build, image id $id (also tagged lab-sim:latest)"; echo "LAB_SIM_IMAGE=$TAG"; } >> coord/images.env
rm -f coord/images.env.tmp
echo "built $TAG $id"
