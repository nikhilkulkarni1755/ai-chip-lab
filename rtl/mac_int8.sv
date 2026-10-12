// mac_int8 -- multiply-accumulate cell: acc += a * b
//
// Signed INT8 x INT8 product (always fits in 16 bits) accumulated into a
// signed INT32 register.  `clear` and `valid` are synchronous; `clear` wins.
// The accumulator wraps modulo 2^32 exactly like NumPy int32 arithmetic.
// (It cannot actually wrap before 131072 products of -128 * -128.)
`default_nettype none

module mac_int8 (
  input  wire logic               clk,
  input  wire logic               clear,  // synchronous: acc <= 0
  input  wire logic               valid,  // synchronous: acc <= acc + a*b
  input  wire logic signed [ 7:0] a,
  input  wire logic signed [ 7:0] b,
  output      logic signed [31:0] acc
);

  logic signed [15:0] prod;
  assign prod = a * b;

  always_ff @(posedge clk) begin
    if (clear) acc <= '0;
    else if (valid) acc <= acc + 32'(prod);
  end

endmodule

`default_nettype wire
