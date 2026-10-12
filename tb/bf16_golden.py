"""Golden model for rtl/mac_bf16.sv:  acc(FP32) <- acc + a(bf16) * b(bf16).

Two independent implementations of the same rules (see the header of mac_bf16.sv):

  mac_step(acc, a, b)        the oracle: ml_dtypes.bfloat16 decodes the operands, the
                             product is formed exactly in float64, the addition is
                             NumPy float32 (IEEE round-to-nearest-even), then the
                             flush-to-zero / overflow / NaN rules are applied.
  mac_step_exact(acc, a, b)  a cross-check that uses only integers and
                             fractions.Fraction (exact rational arithmetic and an
                             explicit round-half-to-even); it also returns the
                             classification used for functional coverage.

All values are bit patterns: a, b are 16-bit ints (bfloat16), acc is a 32-bit int (FP32).
Rules: subnormal inputs are zero; |product| or |sum| below 2^-126 becomes zero with the
sign of the exact result; magnitude >= 2^128 becomes infinity; any NaN, inf*0, inf-inf
gives the canonical quiet NaN 0x7FC00000.
"""
from fractions import Fraction

import ml_dtypes
import numpy as np

QNAN = 0x7FC00000
MIN_NORMAL = Fraction(1, 2**126)
OVERFLOW = Fraction(2**128)
_F32_MIN_NORMAL = np.float64(2.0**-126)


# ----------------------------------------------------------------- oracle
def bf16_to_float64(bits):
    """bfloat16 bit pattern -> float64, subnormals flushed to (signed) zero."""
    x = np.array([bits], dtype=np.uint16).view(ml_dtypes.bfloat16).astype(np.float64)[0]
    if x != 0 and abs(x) < _F32_MIN_NORMAL:
        x = np.copysign(0.0, x)
    return x


def f32_from_bits(bits):
    return np.array([bits], dtype=np.uint32).view(np.float32)[0]


def f32_bits(x):
    return int(np.array([x], dtype=np.float32).view(np.uint32)[0])


def mac_step(acc, a, b):
    with np.errstate(all="ignore"):
        fa, fb = bf16_to_float64(a), bf16_to_float64(b)
        if np.isnan(fa) or np.isnan(fb) or (np.isinf(fa) and fb == 0) or (np.isinf(fb) and fa == 0):
            return QNAN
        p = fa * fb                                    # exact: <= 16 significant bits
        if p != 0 and abs(p) < _F32_MIN_NORMAL:
            p = np.copysign(0.0, p)                    # product flushed
        p32 = np.float32(p)                            # exact, or infinity on overflow
        x = f32_from_bits(acc)
        if x != 0 and abs(np.float64(x)) < _F32_MIN_NORMAL:
            x = np.float32(np.copysign(0.0, x))        # (never happens after clear)
        s = np.float32(x + p32)                        # FP32 add, round-to-nearest-even
        if np.isnan(s):
            return QNAN
        if s != 0 and abs(np.float64(s)) < _F32_MIN_NORMAL:
            s = np.float32(np.copysign(0.0, s))        # sum flushed
        return f32_bits(s)


# ------------------------------------------------------- exact cross-check
def _unpack(bits, ebits, fbits):
    sign = (bits >> (ebits + fbits)) & 1
    e = (bits >> fbits) & ((1 << ebits) - 1)
    f = bits & ((1 << fbits) - 1)
    if e == (1 << ebits) - 1:
        return sign, ("nan" if f else "inf"), None, e
    if e == 0:
        return sign, ("sub" if f else "zero"), Fraction(0), e
    bias = (1 << (ebits - 1)) - 1
    mag = Fraction((1 << fbits) | f) * Fraction(2) ** (e - bias - fbits)
    return sign, "normal", mag, e


def _pack_fp32(sign, mag):
    """Exact positive magnitude -> (bits, rounding class, overflowed). mag >= 2^-126."""
    e = mag.numerator.bit_length() - mag.denominator.bit_length()
    if Fraction(2) ** e > mag:
        e -= 1                                          # 2^e <= mag < 2^(e+1)
    scaled = mag / Fraction(2) ** (e - 23)              # in [2^23, 2^24)
    m = scaled.numerator // scaled.denominator
    rem = scaled - m
    if rem == 0:
        rnd = "exact"
    elif rem < Fraction(1, 2):
        rnd = "down"
    elif rem > Fraction(1, 2):
        rnd = "up"
        m += 1
    elif m & 1:
        rnd = "tie_up"
        m += 1
    else:
        rnd = "tie_down"
    if m == 1 << 24:
        m >>= 1
        e += 1
    if e > 127:
        return (sign << 31) | (0xFF << 23), rnd, True
    return (sign << 31) | ((e + 127) << 23) | (m & 0x7FFFFF), rnd, False


def _ilog2(mag):
    e = mag.numerator.bit_length() - mag.denominator.bit_length()
    return e - 1 if Fraction(2) ** e > mag else e


def mac_step_exact(acc, a, b):
    """Returns (acc_next bits, info) with info = coverage classification of the step."""
    sa, ca, ma, _ = _unpack(a, 8, 7)
    sb, cb, mb, _ = _unpack(b, 8, 7)
    sx, cx, mx, _ = _unpack(acc, 8, 23)
    info = {"a": ca, "b": cb, "acc_in": "zero" if cx == "sub" else cx, "product": None, "add": "special",
            "align": None, "norm": None, "round": None, "result": None}
    sp = sa ^ sb
    az, bz = ca in ("zero", "sub"), cb in ("zero", "sub")
    xz = cx in ("zero", "sub")
    # product
    if ca == "nan" or cb == "nan" or (ca == "inf" and bz) or (cb == "inf" and az):
        info["product"] = "nan"
        pc, pm = "nan", None
    elif ca == "inf" or cb == "inf":
        info["product"] = "inf_operand"
        pc, pm = "inf", None
    elif az or bz:
        info["product"] = "zero_operand"
        pc, pm = "zero", Fraction(0)
    else:
        pm = ma * mb
        if pm < MIN_NORMAL:
            info["product"] = "flushed"
            pc, pm = "zero", Fraction(0)
        elif pm >= OVERFLOW:
            info["product"] = "overflow_inf"
            pc, pm = "inf", None
        else:
            info["product"] = "normal"
            pc = "normal"
    # sum
    if cx == "nan" or pc == "nan" or (cx == "inf" and pc == "inf" and sx != sp):
        info["result"] = "nan"
        return QNAN, info
    if cx == "inf":
        info["result"] = "-inf" if sx else "+inf"
        return (sx << 31) | 0x7F800000, info
    if pc == "inf":
        info["result"] = "-inf" if sp else "+inf"
        return (sp << 31) | 0x7F800000, info
    xm = Fraction(0) if xz else mx
    if xz and pc == "zero":
        info["add"] = "both_zero"
        s = sx & sp
        info["result"] = "-0" if s else "+0"
        return s << 31, info
    if xz or pc == "zero":
        info["add"] = "one_zero"
    else:
        info["add"] = "eff_sub" if sx != sp else "eff_add"
        d = abs(_ilog2(xm) - _ilog2(pm))
        info["align"] = ("0" if d == 0 else "1" if d == 1 else "2..3" if d <= 3 else "4..8" if d <= 8
                         else "9..23" if d <= 23 else "24..26" if d <= 26 else ">=27")
    total = (-xm if sx else xm) + (-pm if sp else pm)
    if total == 0:
        info["norm"] = "cancel_to_zero"
        info["result"] = "+0"
        return 0, info
    sign = 1 if total < 0 else 0
    mag = abs(total)
    if info["add"] in ("eff_add", "eff_sub"):
        shift = _ilog2(mag) - max(_ilog2(xm), _ilog2(pm))
        info["norm"] = ("carry_out" if shift == 1 else "none" if shift == 0 else "left1" if shift == -1
                        else "left2..8" if shift >= -8 else "left9..23" if shift >= -23 else "left>=24")
    if mag < MIN_NORMAL:
        info["result"] = "flushed_sum"
        return sign << 31, info
    bits, rnd, ovf = _pack_fp32(sign, mag)
    info["round"] = rnd
    info["result"] = "overflow_sum" if ovf else "normal"
    return bits, info


def bf16(sign, exp, frac):
    """Build a bfloat16 bit pattern from its fields."""
    return ((sign & 1) << 15) | ((exp & 0xFF) << 7) | (frac & 0x7F)
