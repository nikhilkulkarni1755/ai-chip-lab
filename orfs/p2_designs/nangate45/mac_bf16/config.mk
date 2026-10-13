# ORFS design wrapper for rtl/mac_bf16.sv alone (one MAC cell), nangate45 -- stage 61_pe_bf16 (INT8 vs bf16 MAC).
# Run with: scripts/t2_run.sh nangate45 mac_bf16 p2_61 --config /lab/orfs/p2_designs/nangate45/mac_bf16/config.mk
# Same flow settings as orfs/designs/nangate45/systolic_os/config.mk; both MACs get identical settings and clock.
export DESIGN_NAME     = mac_bf16
export DESIGN_NICKNAME = mac_bf16
export PLATFORM        = nangate45

export VERILOG_FILES = /lab/rtl/mac_bf16.sv
export SDC_FILE      = /lab/orfs/p2_designs/nangate45/mac_bf16/constraint.sdc

export CORE_UTILIZATION ?= 30
export PLACE_DENSITY_LB_ADDON = 0.20
export TNS_END_PERCENT = 100
export SYNTH_REPEATABLE_BUILD ?= 1
export SYNTH_HDL_FRONTEND = slang
