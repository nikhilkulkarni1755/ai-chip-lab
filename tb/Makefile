# cocotb (2.x) Makefile flow for Task 1.  Driven by scripts/t1_run.sh:
#   make -C tb SIM=icarus|verilator SIM_BUILD=<dir> COCOTB_RESULTS_FILE=<xml>
TB_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
RTL_DIR := $(TB_DIR)../rtl

SIM ?= icarus
TOPLEVEL_LANG := verilog
# RTL by default.  Gate-level simulation (scripts/t1_routed.sh): T1_GATE_NETLIST is
# a netlist with top module systolic_os, T1_GATE_CELLS the Verilog cell models.
# T1_SOURCES (space-separated files in rtl/, or in T61_RTL_DIR) selects another RTL design,
# e.g. mac_bf16.sv with COCOTB_TOPLEVEL=mac_bf16 COCOTB_TEST_MODULES=test_mac_bf16.
ifneq ($(T1_SOURCES),)
  VERILOG_SOURCES := $(addprefix $(or $(T61_RTL_DIR),$(RTL_DIR))/,$(T1_SOURCES))
  T1_VERILATOR_WARN := -Wall
else ifeq ($(T1_GATE_NETLIST),)
  VERILOG_SOURCES := $(RTL_DIR)/mac_int8.sv $(RTL_DIR)/systolic_os.sv
  T1_VERILATOR_WARN := -Wall
else
  VERILOG_SOURCES := $(T1_GATE_CELLS) $(T1_GATE_NETLIST)
  T1_VERILATOR_WARN := -Wno-fatal -Wno-lint -Wno-style
endif
COCOTB_TOPLEVEL ?= systolic_os
COCOTB_TEST_MODULES ?= test_systolic
export PYTHONHASHSEED := 0
export COCOTB_RANDOM_SEED ?= 1234
export COCOTB_ANSI_OUTPUT := 0

ifeq ($(SIM),verilator)
  EXTRA_ARGS += $(T1_VERILATOR_WARN) --x-initial unique $(T1_VERILATOR_EXTRA)
  # T1_TRACE=1: Verilator writes dump.vcd (all signals) into the directory make runs in
  ifneq ($(T1_TRACE),)
    EXTRA_ARGS += --trace
  endif
endif
ifeq ($(SIM),icarus)
  ifneq ($(T1_VCD),)
    VERILOG_SOURCES += $(TB_DIR)t1_dump.sv
    COMPILE_ARGS += -s t1_dump
    PLUSARGS += +t1_vcd=$(T1_VCD)
  endif
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
