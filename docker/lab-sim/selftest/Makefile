# usage (inside lab-sim): make SIM=icarus | make SIM=verilator
SIM ?= icarus
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(CURDIR)/mac_probe.sv
COCOTB_TOPLEVEL = mac_probe
COCOTB_TEST_MODULES = test_probe
SIM_BUILD = /tmp/selftest_$(SIM)
COCOTB_RESULTS_FILE = /tmp/selftest_$(SIM)/results.xml
include $(shell cocotb-config --makefiles)/Makefile.sim
