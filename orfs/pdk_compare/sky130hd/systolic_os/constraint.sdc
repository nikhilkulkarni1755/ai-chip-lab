# Starting clock (rewritten per point by scripts/p2_pdk_compare.py); conservative clock for the INT8 MAC array on sky130hd (MAC = 8x8 mult + 32-bit accumulate).
# `set clk_period` is rewritten by sweeps/phys_sweep.py for the clock sweep.
current_design systolic_os

set clk_name core_clock
set clk_port_name clk
set clk_period 8.0
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]

create_clock -name $clk_name -period $clk_period $clk_port
set clk_io_name vclk_$clk_name
create_clock -name $clk_io_name -period $clk_period

set non_clock_inputs [all_inputs -no_clocks]

set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
