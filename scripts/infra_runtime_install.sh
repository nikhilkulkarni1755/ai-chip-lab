#!/bin/bash
# Stage 01_runtime (Route A), part 1: install Lima, Colima, static Docker CLI and buildx into the lab.
# No brew, no sudo. Versions were resolved from the GitHub releases API / download.docker.com on
# 2026-10-12 and are pinned here; override via env to upgrade. Every artifact is SHA256-verified
# against the publisher's checksum file where one exists. Writes downloads/runtime_artifacts.tsv.
set -euo pipefail
source "$HOME/ai-chip-lab/env.sh"
LIMA_VER="${LIMA_VER:-2.2.1}"
COLIMA_VER="${COLIMA_VER:-0.10.3}"
DOCKER_VER="${DOCKER_VER:-29.9.0}"
BUILDX_VER="${BUILDX_VER:-0.38.0}"
DL="$LAB/downloads"; mkdir -p "$DL" "$LAB/bin" "$LAB/opt" "$DOCKER_CONFIG/cli-plugins"
TSV="$DL/runtime_artifacts.tsv"; : > "$TSV"
fetch() { # url dest
  [ -s "$2" ] || curl -fsSL --retry 3 --max-time 900 -o "$2.part" "$1" && { [ -f "$2.part" ] && mv "$2.part" "$2" || true; }
}
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
record() { printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" >> "$TSV"; } # name version url sha256 verified_against

# --- Lima -----------------------------------------------------------------
B="https://github.com/lima-vm/lima/releases/download/v$LIMA_VER"
F="lima-$LIMA_VER-Darwin-x86_64.tar.gz"
fetch "$B/$F" "$DL/$F"; fetch "$B/SHA256SUMS" "$DL/lima-$LIMA_VER.SHA256SUMS"
want=$(awk -v f="$F" '$2==f{print $1}' "$DL/lima-$LIMA_VER.SHA256SUMS"); got=$(sha "$DL/$F")
[ -n "$want" ] && [ "$want" = "$got" ] || { echo "lima sha mismatch want=$want got=$got" >&2; exit 1; }
rm -rf "$LAB/opt/lima"; mkdir -p "$LAB/opt/lima"; tar -xzf "$DL/$F" -C "$LAB/opt/lima"
record lima "$LIMA_VER" "$B/$F" "$got" "$B/SHA256SUMS"

# --- Colima ---------------------------------------------------------------
B="https://github.com/abiosoft/colima/releases/download/v$COLIMA_VER"
F="colima-Darwin-x86_64"
fetch "$B/$F" "$DL/$F-$COLIMA_VER"; fetch "$B/$F.sha256sum" "$DL/$F-$COLIMA_VER.sha256sum"
want=$(awk '{print $1}' "$DL/$F-$COLIMA_VER.sha256sum"); got=$(sha "$DL/$F-$COLIMA_VER")
[ -n "$want" ] && [ "$want" = "$got" ] || { echo "colima sha mismatch want=$want got=$got" >&2; exit 1; }
install -m 0755 "$DL/$F-$COLIMA_VER" "$LAB/bin/colima"
record colima "$COLIMA_VER" "$B/$F" "$got" "$B/$F.sha256sum"

# --- Docker CLI (static). download.docker.com publishes no checksum file for static builds. ----
U="https://download.docker.com/mac/static/stable/x86_64/docker-$DOCKER_VER.tgz"
F="docker-$DOCKER_VER.tgz"
fetch "$U" "$DL/$F"; got=$(sha "$DL/$F")
rm -rf "$DL/docker-x"; mkdir -p "$DL/docker-x"; tar -xzf "$DL/$F" -C "$DL/docker-x"
install -m 0755 "$DL/docker-x/docker/docker" "$LAB/bin/docker"; rm -rf "$DL/docker-x"
record docker-cli "$DOCKER_VER" "$U" "$got" "none-published(computed-locally)"

# --- buildx plugin ----------------------------------------------------------
B="https://github.com/docker/buildx/releases/download/v$BUILDX_VER"
F="buildx-v$BUILDX_VER.darwin-amd64"
fetch "$B/$F" "$DL/$F"; fetch "$B/checksums.txt" "$DL/buildx-v$BUILDX_VER.checksums.txt"
want=$(awk -v f="$F" '{n=$2; sub(/^\*/,"",n)} n==f{print $1}' "$DL/buildx-v$BUILDX_VER.checksums.txt"); got=$(sha "$DL/$F")
if [ -n "$want" ]; then
  [ "$want" = "$got" ] || { echo "buildx sha mismatch want=$want got=$got" >&2; exit 1; }
  bx_src="$B/checksums.txt"
else
  # v0.38.0's checksums.txt lists no darwin/windows entries (those binaries are code-signed after the
  # checksummed build, so the provenance subject digest differs too). Verify instead against the
  # digest GitHub's release API reports for the asset AND Docker Inc's Developer ID signature.
  api="https://api.github.com/repos/docker/buildx/releases/tags/v$BUILDX_VER"
  want=$(curl -fsSL --max-time 60 "$api" | /usr/bin/python3 -I -c "import json,sys;print([a['digest'] for a in json.load(sys.stdin)['assets'] if a['name']=='$F'][0].split(':')[1])")
  [ "$want" = "$got" ] || { echo "buildx sha mismatch (api) want=$want got=$got" >&2; exit 1; }
  codesign --verify --strict "$DL/$F"
  cs=$(codesign -dv --verbose=2 "$DL/$F" 2>&1 || true)
  case "$cs" in *TeamIdentifier=9BNSXJN65R*) : ;; *) false ;; esac || { echo "buildx not signed by Docker Inc" >&2; exit 1; }
  bx_src="github-api-asset-digest($api)+codesign(Docker Inc 9BNSXJN65R); not listed in $B/checksums.txt"
fi
install -m 0755 "$DL/$F" "$DOCKER_CONFIG/cli-plugins/docker-buildx"
record docker-buildx "$BUILDX_VER" "$B/$F" "$got" "$bx_src"

xattr -dr com.apple.quarantine "$LAB/bin" "$LAB/opt/lima" "$DOCKER_CONFIG/cli-plugins" 2>/dev/null || true
echo "--- installed ---"; cat "$TSV"
limactl --version; colima version; docker --version; docker buildx version
