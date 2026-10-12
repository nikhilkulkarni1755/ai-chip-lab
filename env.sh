# Source this in every script. Never edit shell profiles.
export LAB="$HOME/ai-chip-lab"
export PATH="$LAB/bin:$LAB/opt/lima/bin:$PATH"
export DOCKER_CONFIG="$LAB/docker-config"
export COLIMA_HOME="$LAB/.colima"
export LIMA_HOME="$LAB/.lima"
export PYTHONHASHSEED=0
export VM_CPUS=3 VM_MEM_GB=4 NUM_CORES=3
