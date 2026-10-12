#!/bin/bash
# Stage 02_images smoke test (run on the host): prints the version of every required tool in both
# pinned images. Exit 0 only if every required tool reports. Output is also saved (path-scrubbed)
# to results/evidence/02_images_smoke.txt and embedded into versions.lock by scripts/infra_images_lock.sh.
set -uo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; source coord/images.env
out="logs/02_images/smoke.txt"; mkdir -p logs/02_images results/evidence
rc=0
# every container job goes through the heavy-job lock (Part 2 rule); timeout applies to the docker client
LOCKED="$LAB/scripts/with_lock.sh infra perl -e alarm(shift);exec(@ARGV) "
{
  echo "== lab-sim: $LAB_SIM_IMAGE ($(docker image inspect "$LAB_SIM_IMAGE" --format '{{.Id}}'))"
  $LOCKED 600 docker run --rm --platform linux/amd64 -v "$LAB:/lab" -w /lab "$LAB_SIM_IMAGE" bash docker/smoke_lab_sim.sh || rc=1
  echo "== orfs: $ORFS_IMAGE"
  $LOCKED 600 docker run --rm --platform linux/amd64 -v "$LAB:/lab" "$ORFS_IMAGE" bash /lab/docker/smoke_orfs.sh || rc=1
} 2>&1 | sed "s#$HOME#~#g" | tee "$out.tmp"
rc=${PIPESTATUS[0]}
ok=$(grep -c '^OK ' "$out.tmp"); miss=$(grep -c '^MISS ' "$out.tmp")
echo "== smoke: $ok OK, $miss MISSING -> $([ "$rc" = 0 ] && [ "$miss" = 0 ] && echo PASS || echo FAIL)" | tee -a "$out.tmp"
mv "$out.tmp" "$out"
[ "$rc" = 0 ] && [ "$miss" = 0 ]
