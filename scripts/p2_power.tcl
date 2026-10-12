# P2.1 activity-based power on the ROUTED nangate45 systolic_os (pinned OpenROAD inside the pinned ORFS image).
# Env: P2P_MODE = vectorless | vcd ; for vcd: P2P_VCD, P2P_SCOPE (VCD scope, '/'-separated), optional P2P_T0/P2P_T1 (seconds).
# Reads exactly what the ORFS finish stage reads: Liberty, 6_final.odb, 6_final.sdc, 6_final.spef.
# Output markers on stdout are parsed by scripts/p2_power_summary.py.
set base /lab/orfs/work/results/nangate45/systolic_os/base
read_liberty /OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
read_db $base/6_final.odb
read_sdc $base/6_final.sdc
source /OpenROAD-flow-scripts/flow/platforms/nangate45/setRC.tcl   ;# as ORFS load_design does
read_spef $base/6_final.spef
puts "@@TOTALPINS [llength [get_pins -hierarchical *]]"
if {$::env(P2P_MODE) eq "vcd"} {
  set args [list -scope $::env(P2P_SCOPE)]
  if {[info exists ::env(P2P_T0)] && $::env(P2P_T0) ne ""} { lappend args -begin_time $::env(P2P_T0) -end_time $::env(P2P_T1) }
  puts "@@READ_VCD $args $::env(P2P_VCD)"
  read_vcd {*}$args $::env(P2P_VCD)
  puts "@@ANNOT-BEGIN"
  report_activity_annotation
  puts "@@ANNOT-END"
  puts "@@UNANNOT-BEGIN"
  report_activity_annotation -report_unannotated
  puts "@@UNANNOT-END"
}
puts "@@POWER-BEGIN"
report_power -digits 8
puts "@@POWER-END"
exit
