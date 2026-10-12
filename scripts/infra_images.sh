#!/bin/bash
# Stage 02_images end to end (resumable): pull the pinned ORFS image, build lab-sim, smoke, lock.
set -euo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; mkdir -p logs/02_images
ORFS_REF="${ORFS_REF:-openroad/orfs@sha256:573c1716efa0e286c4f641c26d343e20929d58d27fffbb22be2d0b93f09764f6}"  # tag 26Q3-600-g3a964e13f
if ! docker image inspect "$ORFS_REF" >/dev/null 2>&1; then
  scripts/with_lock.sh infra perl -e 'alarm shift; exec @ARGV' 2400 docker pull --platform linux/amd64 "$ORFS_REF" > logs/02_images/orfs_pull.log 2>&1
fi
touch coord/images.env
if ! grep -q "^ORFS_IMAGE=$ORFS_REF\$" coord/images.env; then
  grep -v -e '^ORFS_IMAGE' -e '^# ORFS' coord/images.env > coord/images.env.tmp || true
  { echo "# ORFS: tag 26Q3-600-g3a964e13f, pinned by registry index digest"; echo "ORFS_IMAGE=$ORFS_REF"; cat coord/images.env.tmp; } > coord/images.env; rm -f coord/images.env.tmp
fi
if ! grep -q '^LAB_SIM_IMAGE=' coord/images.env || ! docker image inspect "$(sed -n 's/^LAB_SIM_IMAGE=//p' coord/images.env)" >/dev/null 2>&1; then
  scripts/infra_build_lab_sim.sh
fi
docker/smoke.sh
scripts/infra_images_lock.sh
