# ORFS design wrapper for rtl/systolic_os.sv (INT8 output-stationary systolic array), nangate45.
# Used by scripts/t2_run.sh nangate45 systolic_os <variant>; /lab is the bind-mounted lab dir inside the ORFS container.
export DESIGN_NAME = systolic_os
export PLATFORM    = nangate45

export VERILOG_FILES = /lab/rtl/mac_int8.sv /lab/rtl/systolic_os.sv
export SDC_FILE      = /lab/orfs/designs/nangate45/systolic_os/constraint.sdc

# Array size (R x C). Default 4x4 as in Task 1; overridable from the make command line for the memory fallback.
export R ?= 4
export C ?= 4
export VERILOG_TOP_PARAMS = R $(R) C $(C)

export CORE_UTILIZATION ?= 30
export PLACE_DENSITY_LB_ADDON = 0.20
export TNS_END_PERCENT = 100
export SYNTH_REPEATABLE_BUILD ?= 1
# SystemVerilog (packed multi-dim arrays, always_ff) via yosys-slang (no trailing comment: make keeps trailing spaces)
export SYNTH_HDL_FRONTEND = slang
