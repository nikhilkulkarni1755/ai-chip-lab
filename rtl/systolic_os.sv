// systolic_os -- R x C output-stationary INT8 systolic array (default 4x4)
//
// Computes one R x C tile of  OUT = A * B  (A is R x K, B is K x C):
//
//   acc(i,j) = sum over k of A[i][k] * B[k][j]          (INT32, exact)
//
// * Each processing element PE(i,j) = one mac_int8 + operand registers.
//   It owns output element (i,j) for the whole computation ("output
//   stationary"); only the operands move: A values travel left -> right,
//   B values travel top -> bottom, one PE per clock.
// * Skewed feeding is done inside this module: row i of A is delayed by
//   i clocks and column j of B by j clocks, so A[i][k] and B[k][j] meet in
//   PE(i,j) exactly i+j clocks after step k was presented at the ports.
// * Protocol: pulse `clear` for one clock, then present K steps with
//   `in_valid` = 1 (gaps are allowed).  The result is complete when
//   `busy` = 0 (R+C-1 clocks after the last step) and stays on `acc_o`
//   until the next `clear`.  Operands presented while `clear` = 1 are dropped.
// * Single clock, no asynchronous reset; `clear` is the only reset.
`default_nettype none

module systolic_os #(
  parameter int R = 4,  // rows of PEs    (rows of A per tile)
  parameter int C = 4   // columns of PEs (columns of B per tile)
) (
  input  wire logic              clk,
  input  wire logic              clear,     // synchronous: zero accumulators, flush pipeline
  input  wire logic              in_valid,  // a_i / b_i carry step k
  input  wire logic [   R*8-1:0] a_i,       // a_i[8*i +: 8] = A[i][k]   (signed INT8)
  input  wire logic [   C*8-1:0] b_i,       // b_i[8*j +: 8] = B[k][j]   (signed INT8)
  output      logic              busy,      // an operand is at the ports or in flight
  output      logic [R*C*32-1:0] acc_o      // acc_o[32*(i*C+j) +: 32] = OUT[i][j]
);

  // Operands as they arrive at PE(i,j): A from the west, B from the north.
  // Column 0 / row 0 are fed by the skew registers.
  logic [R-1:0][C-1:0][7:0] a_w;
  logic [R-1:0][C-1:0][7:0] b_n;

  // --------------------------------------------------------------- valid
  // Step k reaches every PE on the anti-diagonal i+j = d exactly d clocks
  // after it was presented, so one shared delay line serves all PEs:
  // v_d[d] = in_valid delayed by d clocks.
  localparam int D = R + C - 1;  // number of anti-diagonals
  logic [D-1:0] v_d;
  assign v_d[0] = in_valid;
  if (D > 1) begin : g_valid
    logic [D-2:0] v_sr;
    always_ff @(posedge clk) v_sr <= clear ? '0 : v_d[D-2:0];
    assign v_d[D-1:1] = v_sr;
  end
  assign busy = |v_d;

  // ---------------------------------------------------------------- skew
  // Row i of A is delayed by i clocks.
  for (genvar i = 0; i < R; i++) begin : g_a_skew
    if (i == 0) begin : g_wire
      assign a_w[i][0] = a_i[8*i+:8];
    end else begin : g_dly
      logic [8*i-1:0] a_sr;
      logic [8*i+7:0] a_tap;
      assign a_tap = {a_sr, a_i[8*i+:8]};
      always_ff @(posedge clk) a_sr <= a_tap[8*i-1:0];
      assign a_w[i][0] = a_tap[8*i+:8];
    end
  end

  // Column j of B is delayed by j clocks.
  for (genvar j = 0; j < C; j++) begin : g_b_skew
    if (j == 0) begin : g_wire
      assign b_n[0][j] = b_i[8*j+:8];
    end else begin : g_dly
      logic [8*j-1:0] b_sr;
      logic [8*j+7:0] b_tap;
      assign b_tap = {b_sr, b_i[8*j+:8]};
      always_ff @(posedge clk) b_sr <= b_tap[8*j-1:0];
      assign b_n[0][j] = b_tap[8*j+:8];
    end
  end

  // ------------------------------------------------------------- PE grid
  // PE(i,j) = MAC + registers that hand A to the east neighbour and B to
  // the south neighbour.
  for (genvar i = 0; i < R; i++) begin : g_row
    for (genvar j = 0; j < C; j++) begin : g_col

      mac_int8 u_mac (
        .clk  (clk),
        .clear(clear),
        .valid(v_d[i+j]),
        .a    (a_w[i][j]),
        .b    (b_n[i][j]),
        .acc  (acc_o[32*(i*C+j)+:32])
      );

      if (j + 1 < C) begin : g_east
        logic [7:0] a_q;
        always_ff @(posedge clk) a_q <= a_w[i][j];
        assign a_w[i][j+1] = a_q;
      end

      if (i + 1 < R) begin : g_south
        logic [7:0] b_q;
        always_ff @(posedge clk) b_q <= b_n[i][j];
        assign b_n[i+1][j] = b_q;
      end

    end
  end

endmodule

`default_nettype wire
