// Tiny signed multiply-accumulate used only to self-test the lab-sim image (cocotb + both simulators).
module mac_probe (
  input  logic               clk,
  input  logic               clear,
  input  logic               valid,
  input  logic signed [7:0]  a,
  input  logic signed [7:0]  b,
  output logic signed [31:0] acc
);
  always_ff @(posedge clk) begin
    if (clear)      acc <= '0;
    else if (valid) acc <= acc + 32'(a * b);
  end
endmodule
