// Formal harness for mac_int8 (SymbiYosys, see mac.sby).
//
// Property (checked every clock against the values one clock earlier):
//   clear          -> acc == 0
//   valid & !clear -> acc == past(acc) + sext(past(a)) * sext(past(b))   (mod 2^32)
//   otherwise      -> acc == past(acc)                                    (hold)
//
// The reference product is written independently of the `*` in the design:
// a Baugh-Wooley style sum of shifted partial products of the sign-extended
// multiplicand, where the multiplier's sign bit has weight -2^7 (the exact
// product of two INT8 values always fits in 16 bits, then it is sign-extended).  The solver
// therefore has to prove the design's multiplier, not just match two
// identical expressions.  Inputs are unconstrained and the initial
// accumulator value is arbitrary, so the result holds from any state.
module mac_formal (
  input logic              clk,
  input logic              clear,
  input logic              valid,
  input logic signed [7:0] a,
  input logic signed [7:0] b
);
  logic signed [31:0] acc;

  mac_int8 dut (
    .clk  (clk),
    .clear(clear),
    .valid(valid),
    .a    (a),
    .b    (b),
    .acc  (acc)
  );

  function automatic logic [31:0] ref_mul(input logic [7:0] x, input logic [7:0] y);
    logic [15:0] xs;
    logic [15:0] p;
    integer      i;
    begin
      xs = {{8{x[7]}}, x};
      p  = 16'd0;
      for (i = 0; i < 7; i = i + 1) begin
        if (y[i]) p = p + (xs << i);
      end
      if (y[7]) p = p - (xs << 7);
      ref_mul = {{16{p[15]}}, p};
    end
  endfunction

  logic        past_valid = 1'b0;
  logic        clear_q, valid_q;
  logic [ 7:0] a_q, b_q;
  logic [31:0] acc_q;

  always_ff @(posedge clk) begin
    past_valid <= 1'b1;
    clear_q    <= clear;
    valid_q    <= valid;
    a_q        <= a;
    b_q        <= b;
    acc_q      <= acc;
  end

  always_ff @(posedge clk) begin
    if (past_valid) begin
      if (clear_q) p_clear : assert (acc == 32'sd0);
      else if (valid_q) p_mac : assert (acc == acc_q + ref_mul(a_q, b_q));
      else p_hold : assert (acc == acc_q);
    end
    // reachability (cover mode): the interesting situations really occur
    c_neg_acc : cover (past_valid && valid_q && !clear_q && acc[31] && !acc_q[31]);
    c_min_min : cover (past_valid && valid_q && !clear_q && a_q == 8'h80 && b_q == 8'h80 &&
                       acc_q == 32'd0 && acc == 32'd16384);
    c_wrap : cover (past_valid && valid_q && !clear_q && !acc_q[31] && acc[31] &&
                    !a_q[7] && !b_q[7]);
  end
endmodule
