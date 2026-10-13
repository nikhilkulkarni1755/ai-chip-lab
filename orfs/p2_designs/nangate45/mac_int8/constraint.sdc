# Clock = 1.25 ns: the closure clock of the INT8 MAC array (sweep B frontier of systolic_os on nangate45,
# results/sweeps/phys.jsonl: 1.25 ns closes, 1.20 ns does not).  Fixed before the first run of this stage.
current_design mac_int8

set clk_name core_clock
set clk_port_name clk
set clk_period 1.25
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]

create_clock -name $clk_name -period $clk_period $clk_port
set clk_io_name vclk_$clk_name
create_clock -name $clk_io_name -period $clk_period

set non_clock_inputs [all_inputs -no_clocks]

set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
