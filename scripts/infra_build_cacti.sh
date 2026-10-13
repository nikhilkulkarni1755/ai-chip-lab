#!/bin/bash
# Build the pinned CACTI image (stage 63_sram_cacti) through the heavy-job lock, smoke-test it on one tiny cache
# config and write its reference to coord/images_cacti.env (CACTI_IMAGE=...). The reference is copied into
# coord/images.env by `scripts/infra_build_cacti.sh --publish` only (images.env is an input of other stages).
set -uo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; LOGD=logs/part2/63_sram_cacti; mkdir -p "$LOGD"
TAG="lab-cacti:20261012"
if [ "${1:-}" = "--publish" ]; then
  [ -s coord/images_cacti.env ] || { echo "no coord/images_cacti.env yet"; exit 2; }
  grep -v -e '^CACTI_IMAGE' -e '^# lab-cacti' coord/images.env > coord/images.env.tmp
  cat coord/images.env.tmp coord/images_cacti.env > coord/images.env; rm -f coord/images.env.tmp
  echo "published to coord/images.env:"; grep -A1 '^# lab-cacti' coord/images.env; exit 0
fi
scripts/with_lock.sh infra perl -e 'alarm shift; exec @ARGV' 540 \
  docker buildx build --platform linux/amd64 --progress=plain --load -t "$TAG" -f docker/lab-cacti/Dockerfile docker/lab-cacti \
  > "$LOGD/build.log" 2>&1 || { echo "CACTI image build FAILED (see $LOGD/build.log)"; tail -25 "$LOGD/build.log" | sed "s#$HOME#~#g"; exit 1; }
id=$(docker image inspect "$TAG" --format '{{.Id}}')
# smoke: CACTI's own cache.cfg reduced to a 64 kB, 1-way, 64-byte-block cache (tiny, runs in a second)
scripts/with_lock.sh infra perl -e 'alarm shift; exec @ARGV' 300 \
  docker run --rm --platform linux/amd64 "$TAG" bash -c '
    set -e; cd /opt/cacti; echo "CACTI commit $(cat CACTI_COMMIT)"; g++ --version | head -1
    sed -e "s/^-size (bytes) .*/-size (bytes) 65536/" -e "s/^-associativity .*/-associativity 1/" cache.cfg > /tmp/tiny.cfg
    grep -E "^-size|^-block size|^-associativity|^-technology" /tmp/tiny.cfg
    ./cacti -infile /tmp/tiny.cfg > /tmp/tiny.out 2>&1 || { tail -20 /tmp/tiny.out; exit 1; }
    grep -E "Access time|Cycle time|Total dynamic read energy|Total leakage power of a bank|Cache height x width|Technology size" /tmp/tiny.out
    grep -q "Access time (ns)" /tmp/tiny.out' > "$LOGD/smoke.txt" 2>&1; rc=$?
sed "s#$HOME#~#g" "$LOGD/smoke.txt"
[ $rc = 0 ] || { echo "CACTI smoke test FAILED"; exit 1; }
{ echo "# lab-cacti: CACTI 7 from github.com/HewlettPackard/cacti @ $(sed -n 's/^ARG CACTI_SHA=//p' docker/lab-cacti/Dockerfile), local build, image id $id"; echo "CACTI_IMAGE=$TAG"; } > coord/images_cacti.env
mkdir -p results/evidence; { echo "\$ scripts/infra_build_cacti.sh   (image $TAG, id $id)"; cat "$LOGD/smoke.txt"; } | sed "s#$HOME#~#g" > results/evidence/63_cacti_image_smoke.txt
echo "CACTI image OK: $TAG $id"
