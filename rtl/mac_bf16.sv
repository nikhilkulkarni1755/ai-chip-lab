// mac_bf16 -- floating-point multiply-accumulate cell: acc += a * b
//
// a, b : bfloat16  (1 sign, 8 exponent, 7 fraction bits; same exponent range as FP32)
// acc  : IEEE-754 binary32 (FP32) accumulator; synchronous `clear` (wins) and `valid`,
//        exactly like mac_int8.
//
// Arithmetic (the Python golden model model/bf16_golden.py applies the same rules):
//  * product: 8-bit x 8-bit significands -> at most 16 significant bits, so the
//    product is EXACT in FP32; no rounding happens in the multiplier.
//  * sum: FP32 addition, round-to-nearest-even.
//  * subnormals are flushed to zero: an input with exponent field 0 is read as zero
//    of the same sign, and a product or sum whose magnitude is below 2^-126 becomes
//    zero with the sign of the exact result.  (Cheaper than gradual underflow: no
//    denormalising shifter, no subnormal rounding.)
//  * overflow gives infinity; any NaN operand, inf * 0 and inf - inf give the
//    canonical quiet NaN 32'h7FC0_0000.
//  * zero signs follow IEEE 754: x + (-x) = +0, (-0) + (-0) = -0.
`default_nettype none

module mac_bf16 (
  input  wire logic        clk,
  input  wire logic        clear,  // synchronous: acc <= +0
  input  wire logic        valid,  // synchronous: acc <= acc + a*b
  input  wire logic [15:0] a,      // bfloat16
  input  wire logic [15:0] b,      // bfloat16
  output      logic [31:0] acc     // FP32
);

  localparam logic [31:0] QNAN = 32'h7FC0_0000;

  // ------------------------------------------------------------ multiply
  logic a_zero, a_inf, a_nan, b_zero, b_inf, b_nan;
  assign a_zero = (a[14:7] == 8'd0);  // zero or subnormal (flushed)
  assign a_inf  = (a[14:7] == 8'hFF) && (a[6:0] == 7'd0);
  assign a_nan  = (a[14:7] == 8'hFF) && (a[6:0] != 7'd0);
  assign b_zero = (b[14:7] == 8'd0);
  assign b_inf  = (b[14:7] == 8'hFF) && (b[6:0] == 7'd0);
  assign b_nan  = (b[14:7] == 8'hFF) && (b[6:0] != 7'd0);

  logic        p_sign;
  logic [15:0] p_sig;   // {1,fa} * {1,fb}: 2^14 <= p_sig < 2^16
  logic [ 9:0] p_exp0;  // ea + eb + carry of the significand product
  logic [23:0] p_man;   // normalised significand, hidden one at bit 23
  logic        p_ovf, p_unf, p_nan, p_inf, p_zero;
  logic [ 7:0] p_exp;   // biased FP32 exponent when the product is a normal number

  assign p_sign = a[15] ^ b[15];
  assign p_sig  = {1'b1, a[6:0]} * {1'b1, b[6:0]};
  assign p_exp0 = {2'b00, a[14:7]} + {2'b00, b[14:7]} + {9'd0, p_sig[15]};
  assign p_man  = p_sig[15] ? {p_sig, 8'd0} : {p_sig[14:0], 9'd0};
  // biased exponent = p_exp0 - 127: normal iff 1 <= p_exp0 - 127 <= 254
  assign p_unf  = (p_exp0 <= 10'd127);
  assign p_ovf  = (p_exp0 >= 10'd382);
  assign p_exp  = 8'(p_exp0 - 10'd127);
  assign p_nan  = a_nan | b_nan | (a_inf & b_zero) | (b_inf & a_zero);
  assign p_inf  = ~p_nan & (a_inf | b_inf | (~a_zero & ~b_zero & p_ovf));
  assign p_zero = ~p_nan & ~p_inf & (a_zero | b_zero | p_unf);

  // ------------------------------------------------------------- operands
  // x = accumulator, y = product; each as {sign, exponent, 24-bit significand}.
  logic        x_sign, x_zero, x_inf, x_nan;
  logic [ 7:0] x_exp;
  logic [23:0] x_man;
  assign x_sign = acc[31];
  assign x_zero = (acc[30:23] == 8'd0);
  assign x_inf  = (acc[30:23] == 8'hFF) && (acc[22:0] == 23'd0);
  assign x_nan  = (acc[30:23] == 8'hFF) && (acc[22:0] != 23'd0);
  assign x_exp  = x_zero ? 8'd0 : acc[30:23];
  assign x_man  = x_zero ? 24'd0 : {1'b1, acc[22:0]};

  logic [ 7:0] y_exp;
  logic [23:0] y_man;
  assign y_exp = p_zero ? 8'd0 : p_exp;
  assign y_man = p_zero ? 24'd0 : p_man;

  // --------------------------------------------------------------- align
  logic        x_big;
  logic        big_sign, small_sign;
  logic [ 7:0] big_exp, small_exp;
  logic [23:0] big_man, small_man;
  assign x_big      = ({x_exp, x_man} >= {y_exp, y_man});
  assign big_sign   = x_big ? x_sign : p_sign;
  assign small_sign = x_big ? p_sign : x_sign;
  assign big_exp    = x_big ? x_exp : y_exp;
  assign small_exp  = x_big ? y_exp : x_exp;
  assign big_man    = x_big ? x_man : y_man;
  assign small_man  = x_big ? y_man : x_man;

  logic [ 7:0] shift;      // exponent difference
  logic [ 4:0] shift_c;    // clamped to 31 (>= 27 already shifts everything out)
  logic [57:0] small_sh;   // {significand, guard, round, 0} followed by 31 bits that collect the sticky
  logic [26:0] small_al;   // aligned significand; bit 0 = sticky
  assign shift    = big_exp - small_exp;
  assign shift_c  = (shift > 8'd31) ? 5'd31 : shift[4:0];
  assign small_sh = {small_man, 3'b000, 31'd0} >> shift_c;
  assign small_al = {small_sh[57:32], small_sh[31] | (|small_sh[30:0])};

  // ---------------------------------------------------------- add / subtract
  logic        eff_sub;
  logic [27:0] sum;
  assign eff_sub = big_sign ^ small_sign;
  assign sum     = eff_sub ? ({1'b0, big_man, 3'b000} - {1'b0, small_al})
                           : ({1'b0, big_man, 3'b000} + {1'b0, small_al});

  // ------------------------------------------------------------ normalise
  logic [ 4:0] lz;         // leading zeros of sum[26:0]
  always_comb begin
    lz = 5'd27;
    for (int i = 0; i <= 26; i++) if (sum[i]) lz = 5'(26 - i);
  end

  logic        carry;      // sum needs a 1-bit right shift
  logic [26:0] norm;       // hidden one at bit 26, then 23 fraction bits, guard, round, sticky
  logic [ 9:0] norm_exp;   // may wrap below zero (flush) or reach >= 255 (overflow)
  assign carry    = sum[27];
  assign norm     = carry ? {sum[27:2], sum[1] | sum[0]} : (sum[26:0] << lz);
  assign norm_exp = carry ? ({2'b00, big_exp} + 10'd1) : ({2'b00, big_exp} - {5'd0, lz});

  // ---------------------------------------------------- round to nearest even
  logic        round_up;
  logic [23:0] frac_r;     // rounded fraction; bit 23 = carry into the exponent
  logic [ 9:0] res_exp;
  assign round_up = norm[2] & (norm[1] | norm[0] | norm[3]);
  assign frac_r   = {1'b0, norm[25:3]} + {23'd0, round_up};
  assign res_exp  = norm_exp + {9'd0, frac_r[23]};

  // --------------------------------------------------------------- result
  logic        sum_zero, sum_flush, sum_ovf;
  logic [30:0] sum_bits;   // exponent and fraction of a normal result
  assign sum_zero  = ~norm[26];  // no leading one found: exact cancellation
  assign sum_flush = ~carry & (norm_exp[9] | (norm_exp == 10'd0));  // magnitude below 2^-126
  assign sum_ovf   = ~res_exp[9] & (res_exp >= 10'd255);
  assign sum_bits  = {res_exp[7:0], frac_r[22:0]};

  logic [31:0] acc_next;
  always_comb begin
    if (x_nan | p_nan | (x_inf & p_inf & (x_sign ^ p_sign))) acc_next = QNAN;
    else if (x_inf) acc_next = {x_sign, 8'hFF, 23'd0};
    else if (p_inf) acc_next = {p_sign, 8'hFF, 23'd0};
    else if (x_zero & p_zero) acc_next = {x_sign & p_sign, 31'd0};
    else if (sum_zero) acc_next = 32'd0;  // exact cancellation: +0
    else if (sum_flush) acc_next = {big_sign, 31'd0};
    else if (sum_ovf) acc_next = {big_sign, 8'hFF, 23'd0};
    else acc_next = {big_sign, sum_bits};
  end

  always_ff @(posedge clk) begin
    if (clear) acc <= 32'd0;
    else if (valid) acc <= acc_next;
  end

endmodule

`default_nettype wire
