#!/bin/bash
# Stage 01_runtime (Route A), part 2: start the Colima VM (Virtualization.framework) and verify docker.
# Idempotent: if the VM is already running it only re-verifies.
set -euo pipefail
source "$HOME/ai-chip-lab/env.sh"
VM_DISK_GB="${VM_DISK_GB:-60}"   # sparse data disk; 60 GiB max keeps >=30 GB host headroom on 92 GB free
export XDG_CACHE_HOME="$LAB/.cache"   # keep Colima's image download cache inside the lab
mkdir -p "$XDG_CACHE_HOME" "$LAB/logs/01_runtime"
if ! colima status >/dev/null 2>&1; then
  lab_timeout 1500 colima start --vm-type vz --arch x86_64 \
    --cpus "$VM_CPUS" --memory "$VM_MEM_GB" --disk "$VM_DISK_GB" \
    --mount "$LAB:w" --mount-type virtiofs \
    --runtime docker --ssh-config=false --activate=false
fi
colima status
# container jobs go through the heavy-job lock (Part 2 rule), each under a client-side timeout
scripts_lock() { "$LAB/scripts/with_lock.sh" infra perl -e 'alarm shift; exec @ARGV' "$@"; }
scripts_lock 300 docker run --rm hello-world
# the lab must be writable from inside a container
t="$LAB/logs/01_runtime/.mount_probe.$$"
scripts_lock 120 docker run --rm --platform linux/amd64 -v "$LAB:/lab" -w /lab hello-world >/dev/null
lab_timeout 120 colima ssh -- sh -c "echo ok > '$t' && cat '$t'"
[ "$(cat "$t")" = ok ] && rm -f "$t" && echo "MOUNT_RW_OK $LAB"
docker version --format 'client={{.Client.Version}} server={{.Server.Version}} os={{.Server.Os}}/{{.Server.Arch}}'
docker info --format 'ncpu={{.NCPU}} mem={{.MemTotal}} kernel={{.KernelVersion}} os={{.OperatingSystem}} driver={{.Driver}}'
