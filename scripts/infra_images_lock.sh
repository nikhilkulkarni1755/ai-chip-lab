#!/bin/bash
# Rewrite the `images:` section of versions.lock from the live registry/daemon state and the last
# smoke run (logs/02_images/smoke.txt), and save the smoke table as evidence. No value is hand-typed
# except the pins that also live in docker/lab-sim/Dockerfile (they are read from that file).
set -euo pipefail
source "$HOME/ai-chip-lab/env.sh"
cd "$LAB"; source coord/images.env
smoke=logs/02_images/smoke.txt
grep -q '^== smoke: .* PASS' "$smoke" || { echo "smoke has not passed; not locking" >&2; exit 1; }
DF=docker/lab-sim/Dockerfile
arg() { sed -n "s/^ARG $1=//p" "$DF" | head -1; }
tmp=$(mktemp)
awk '/^images:/{exit} {print}' versions.lock > "$tmp"
{
  echo "images:   # owner: infra, stage 02_images, recorded $(date '+%F %T %Z')"
  echo "  orfs:"
  echo "    ref: \"$ORFS_IMAGE\""
  echo "    tag: \"26Q3-600-g3a964e13f\"   # newest-but-5-commits tag that still ships rules-base.json + checkMetadata.py (see COORDINATION.md Decision 6)"
  echo "    repo_digests: \"$(docker image inspect "$ORFS_IMAGE" --format '{{join .RepoDigests " "}}')\""
  echo "    image_id: \"$(docker image inspect "$ORFS_IMAGE" --format '{{.Id}}')\""
  echo "    size_bytes: $(docker image inspect "$ORFS_IMAGE" --format '{{.Size}}')"
  echo "    flow_dir: /OpenROAD-flow-scripts/flow"
  echo "  lab_sim:"
  echo "    ref: \"$LAB_SIM_IMAGE\"   # local build; also lab-sim:latest"
  echo "    image_id: \"$(docker image inspect "$LAB_SIM_IMAGE" --format '{{.Id}}')\""
  echo "    size_bytes: $(docker image inspect "$LAB_SIM_IMAGE" --format '{{.Size}}')"
  echo "    dockerfile_sha256: $(shasum -a 256 "$DF" | awk '{print $1}')"
  echo "    requirements_lock_sha256: $(shasum -a 256 docker/requirements.lock | awk '{print $1}')"
  echo "    base: \"$(arg UBUNTU_REF)\""
  echo "    oss_cad_suite: {date: \"$(arg OSS_CAD_DATE)\", url: \"https://github.com/YosysHQ/oss-cad-suite-build/releases/download/$(arg OSS_CAD_DATE)/$(arg OSS_CAD_FILE)\", sha256: $(arg OSS_CAD_SHA256)}"
  echo "    verible: {version: \"$(arg VERIBLE_VER)\", url: \"https://github.com/chipsalliance/verible/releases/download/$(arg VERIBLE_VER)/verible-$(arg VERIBLE_VER)-linux-static-x86_64.tar.gz\", sha256: $(arg VERIBLE_SHA256)}"
  echo "    uv: {version: \"$(arg UV_VER)\", url: \"https://github.com/astral-sh/uv/releases/download/$(arg UV_VER)/uv-x86_64-unknown-linux-gnu.tar.gz\", sha256: $(arg UV_SHA256)}"
  echo "    python: \"$(arg PYTHON_VER)\"   # uv-managed CPython (python-build-standalone)"
  echo "    checksums_verified_by: \"Dockerfile ADD --checksum (BuildKit fails the build on mismatch); values are the GitHub release-API asset digests\""
  echo "    apt: \"$(docker run --rm --platform linux/amd64 "$LAB_SIM_IMAGE" dpkg-query -W -f '${Package}=${Version} ' make g++ git perl ca-certificates curl time)\""
  echo "  timeloop: \"SKIPPED — optional (TASK.md §3); see COORDINATION.md Decisions for the reason\""
  echo "  smoke: |   # docker/smoke.sh output, verbatim (home path scrubbed)"
  sed 's/^/    /' "$smoke"
} | sed "s#$HOME#~#g" >> "$tmp"
mv "$tmp" versions.lock
mkdir -p results/evidence; cp "$smoke" results/evidence/02_images_smoke.txt
echo "versions.lock images section written; evidence saved"
