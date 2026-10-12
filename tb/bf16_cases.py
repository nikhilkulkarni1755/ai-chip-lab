"""Stimulus for the bf16 MAC: directed cases and deterministic random cases.

A case is a list of (a, b) bfloat16 bit patterns applied after one `clear`.
random_case(i) depends only on (SEED, i); some modes steer the next operands from
the accumulator value predicted by the golden model (ties, cancellation).
"""
import numpy as np

from bf16_golden import bf16, mac_step

SEED = 1234
MAX_STEPS = 16

ONE, MONE = bf16(0, 127, 0), bf16(1, 127, 0)
PZ, NZ = 0x0000, 0x8000
PINF, NINF = 0x7F80, 0xFF80
QNAN_BF, SNAN_BF, NEG_NAN_BF = 0x7FC0, 0x7F81, 0xFFC1
MAXN, MINN = bf16(0, 254, 0x7F), bf16(0, 1, 0)
SUB_MIN, SUB_MAX = 0x0001, 0x007F
ALMOST1 = bf16(0, 126, 0x7F)            # 1 - 2^-8


def p2(e, sign=0):
    """bf16 value (+/-) 2^e."""
    return bf16(sign, 127 + e, 0)


TWO_M_ULP = [(ONE | 0x7F, ONE), (p2(-7), ALMOST1), (p2(-15), ALMOST1)]      # acc = 2 - 2^-23
ONE_M_HALF_ULP = [(ALMOST1, ONE), (p2(-8), ALMOST1), (p2(-16), ALMOST1)]      # acc = 1 - 2^-24

DIRECTED = [
    ("zero_plus_zero", [(PZ, PZ)]),
    ("neg_zero_product", [(NZ, PZ), (NZ, ONE)]),
    ("exact_cancel_pos_zero", [(ONE, ONE), (MONE, ONE)]),
    ("exact_cancel_pos_zero_2", [(MONE, ONE), (ONE, ONE)]),
    ("flush_sum_neg_then_neg_zero", [(MINN, ONE), (bf16(1, 1, 1), ONE), (NZ, PZ), (NZ, ONE), (PZ, PZ)]),
    ("flush_sum_pos", [(bf16(1, 1, 0), ONE), (bf16(0, 1, 1), ONE)]),
    ("flush_product", [(MINN, p2(-1)), (MINN, MINN), (p2(-63), p2(-64), )]),
    ("min_normal", [(MINN, ONE), (MINN, ONE), (bf16(1, 1, 0), ONE)]),
    ("product_just_normal", [(p2(-63), p2(-63)), (bf16(0, 64, 0x7F), bf16(0, 63, 0x7F))]),
    ("subnormal_inputs", [(SUB_MIN, ONE), (SUB_MAX, MAXN), (ONE, SUB_MAX | 0x8000), (SUB_MAX, PINF)]),
    ("max_normal", [(MAXN, ONE), (MAXN, MONE)]),
    ("product_overflow", [(MAXN, MAXN)]),
    ("product_overflow_neg", [(MAXN, MAXN | 0x8000), (ONE, ONE)]),
    ("sum_overflow", [(MAXN, ALMOST1), (MAXN, ALMOST1)]),
    ("sum_overflow_neg", [(MAXN | 0x8000, ALMOST1), (MAXN | 0x8000, ALMOST1)]),
    ("sum_overflow_by_rounding", [(MAXN, ONE), (p2(127 - 8) | 0x7F, ONE), (p2(127 - 16) | 0x7F, ONE),
                                  (p2(127 - 24), ONE)]),
    ("pos_inf", [(ONE, PINF), (ONE, ONE), (MAXN, MAXN)]),
    ("neg_inf", [(NINF, ONE), (MONE, ONE), (NINF, ONE)]),
    ("inf_times_inf", [(PINF, NINF), (PINF, NINF)]),
    ("inf_minus_inf", [(PINF, ONE), (NINF, ONE), (ONE, ONE)]),
    ("inf_times_zero", [(PINF, PZ), (ONE, ONE)]),
    ("zero_times_inf", [(ONE, ONE), (NZ, NINF)]),
    ("nan_operand_a", [(QNAN_BF, ONE), (ONE, ONE), (PZ, PZ)]),
    ("nan_operand_b", [(ONE, ONE), (ONE, SNAN_BF)]),
    ("nan_negative", [(NEG_NAN_BF, PZ), (PINF, ONE)]),
    ("nan_sticky_through_inf", [(ONE, QNAN_BF), (PINF, ONE), (NINF, ONE)]),
    ("tie_to_even_down", [(ONE, ONE), (p2(-24), ONE)]),
    ("tie_to_even_up", [(ONE, ONE), (p2(-23), ONE), (p2(-24), ONE)]),
    ("tie_sub_to_even", [(ONE, ONE), (p2(-23), ONE), (p2(-24, 1), ONE), (p2(-24, 1), ONE), (p2(-25, 1), ONE)]),
    ("round_up_above_half", [(ONE, ONE), (p2(-24) | 0x40, ONE)]),
    ("round_down_below_half", [(ONE, ONE), (p2(-25) | 0x40, ONE)]),
    ("round_carry_to_next_exponent", TWO_M_ULP + [(p2(-24), ONE)]),
    ("align_27_or_more", [(ONE, ONE), (p2(-27), ONE), (p2(-40), ONE), (p2(-100), MONE)]),
    ("align_24_to_26", [(ONE, ONE), (p2(-25), ONE), (p2(-26) | 0x7F, MONE)]),
    ("carry_out", [(p2(0) | 0x40, ONE), (p2(0) | 0x40, ONE), (ALMOST1, ONE)]),
    ("cancel_left_8", [(ONE, ONE), (ALMOST1, MONE)]),
    ("cancel_left_23", [(ONE, ONE), (p2(-23), ONE), (MONE, ONE)]),
    ("cancel_left_24", ONE_M_HALF_ULP + [(MONE, ONE)]),
    ("cancel_left_16_exponents_differ", [(ALMOST1, ONE), (p2(-8), ALMOST1), (MONE, ONE)]),
    ("carry_out_far_aligned", TWO_M_ULP + [(p2(-10), ONE)]),
    ("big_minus_small_product", [(p2(10), p2(10)), (p2(-3) | 0x55, MONE | 0x2A)]),
    ("alternating_signs", [(ONE | 0x33, ONE | 0x55), (MONE | 0x33, ONE | 0x54), (ONE | 0x7F, ONE | 0x01),
                           (MONE | 0x01, ONE | 0x7F)]),
]

SPECIALS = {
    "zero": [PZ, NZ],
    "sub": [SUB_MIN, SUB_MAX, SUB_MIN | 0x8000, 0x0040],
    "inf": [PINF, NINF],
    "nan": [QNAN_BF, SNAN_BF, NEG_NAN_BF, 0x7FFF],
}


def _norm(rng, elo, ehi):
    return bf16(int(rng.integers(0, 2)), int(rng.integers(elo, ehi + 1)), int(rng.integers(0, 128)))


def _special(rng):
    cls = ("zero", "sub", "normal", "inf", "nan")[int(rng.integers(0, 5))]
    if cls == "normal":
        return _norm(rng, 100, 150)
    pool = SPECIALS[cls]
    return pool[int(rng.integers(0, len(pool)))]


def _pair_with_exp_sum(rng, total, sign, frac_a=0, frac_b=0):
    """Normal operands whose exponent fields add up to `total` (None if impossible)."""
    lo, hi = max(1, total - 254), min(254, total - 1)
    if lo > hi:
        return None
    ea = int(rng.integers(lo, hi + 1))
    return bf16(sign, ea, frac_a), bf16(0, total - ea, frac_b)


MODES = ["near", "near", "near", "wide", "bits", "special", "cancel", "tie", "tiny", "huge"]


def random_case(i):
    """Returns (mode name, [(a, b), ...]) for random case i."""
    rng = np.random.default_rng([SEED, i])
    mode = MODES[int(rng.integers(0, len(MODES)))]
    n = int(rng.integers(1, MAX_STEPS + 1))
    steps, acc = [], 0
    for k in range(n):
        a = b = None
        if mode == "wide":
            a, b = _norm(rng, 1, 254), _norm(rng, 1, 254)
        elif mode == "bits":
            a, b = int(rng.integers(0, 1 << 16)), int(rng.integers(0, 1 << 16))
        elif mode == "special":
            a, b = _special(rng), _special(rng)
        elif mode == "cancel" and steps and rng.random() < 0.6:
            pa, pb = steps[-1]
            a, b = pa, pb ^ 0x8000                     # minus the previous product ...
            if rng.random() < 0.5:
                b ^= int(rng.integers(1, 4))           # ... or almost
        elif mode == "tie":
            e = (acc >> 23) & 0xFF
            if 0 < e < 255 and rng.random() < 0.8:     # product = +/- 2^(E-24) (x 1, 1.5 or 0.75)
                kind = int(rng.integers(0, 4))
                pair = _pair_with_exp_sum(rng, e + 103 - (kind == 3), int(rng.integers(0, 2)),
                                          frac_a=0x40 if kind >= 2 else 0)
                if pair:
                    a, b = pair
        elif mode == "tiny":
            pair = _pair_with_exp_sum(rng, int(rng.integers(118, 141)), int(rng.integers(0, 2)),
                                      int(rng.integers(0, 128)), int(rng.integers(0, 128)))
            if steps and rng.random() < 0.4:
                pa, pb = steps[-1]
                pair = (pa, pb ^ 0x8000 ^ int(rng.integers(0, 4)))
            a, b = pair
        elif mode == "huge":
            a, b = _pair_with_exp_sum(rng, int(rng.integers(368, 384)), int(rng.integers(0, 2)),
                                      int(rng.integers(0, 128)), int(rng.integers(0, 128)))
        if a is None:
            a, b = _norm(rng, 119, 135), _norm(rng, 119, 135)
        steps.append((a, b))
        acc = mac_step(acc, a, b)
    return mode, steps
