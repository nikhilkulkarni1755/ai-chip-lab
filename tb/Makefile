# cocotb (2.x) Makefile flow for Task 1.  Driven by scripts/t1_run.sh:
#   make -C tb SIM=icarus|verilator SIM_BUILD=<dir> COCOTB_RESULTS_FILE=<xml>
TB_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
RTL_DIR := $(TB_DIR)../rtl

SIM ?= icarus
TOPLEVEL_LANG := verilog
VERILOG_SOURCES := $(RTL_DIR)/mac_int8.sv $(RTL_DIR)/systolic_os.sv
COCOTB_TOPLEVEL ?= systolic_os
COCOTB_TEST_MODULES ?= test_systolic
export PYTHONHASHSEED := 0
export COCOTB_RANDOM_SEED ?= 1234
export COCOTB_ANSI_OUTPUT := 0

ifeq ($(SIM),verilator)
  EXTRA_ARGS += -Wall --x-initial unique
  BUILD_ARGS += -j 2
endif
ifeq ($(SIM),icarus)
  ifneq ($(T1_VCD),)
    VERILOG_SOURCES += $(TB_DIR)t1_dump.sv
    COMPILE_ARGS += -s t1_dump
    PLUSARGS += +t1_vcd=$(T1_VCD)
  endif
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
