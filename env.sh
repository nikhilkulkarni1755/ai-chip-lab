# Source this in every script. Never edit shell profiles.
export LAB="$HOME/ai-chip-lab"
export PATH="$LAB/bin:$LAB/opt/lima/bin:$PATH"
export DOCKER_CONFIG="$LAB/docker-config"
export COLIMA_HOME="$LAB/.colima"
export LIMA_HOME="$LAB/.lima"
export PYTHONHASHSEED=0
export VM_CPUS=3 VM_MEM_GB=4 NUM_CORES=3
# infra: Colima only honours COLIMA_HOME if the directory already exists (else it falls back to ~/.colima).
mkdir -p "$COLIMA_HOME" "$LIMA_HOME" "$DOCKER_CONFIG" 2>/dev/null
# infra: Docker endpoint of the lab VM (set explicitly so no docker context / ~/.docker is needed).
export DOCKER_HOST="unix://$COLIMA_HOME/default/docker.sock"
# infra: portable timeout (no gtimeout on this Mac): lab_timeout <secs> cmd...
lab_timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }
