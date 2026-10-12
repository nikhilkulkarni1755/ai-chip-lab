"""Analytical cycle model of SCALE-Sim v3.0.0 systolic arrays (pure GEMM, M x K x N on R x C).

Derived by reading scalesim/compute/systolic_compute_{os,ws,is}.py.  SCALE-Sim maps a GEMM
(ifmap M x K, filter K x N, ofmap M x N) onto the array as follows:

  dataflow | spatial rows (R) | spatial cols (C) | streamed time T | folds
  ---------+------------------+------------------+-----------------+--------------------------
  os       | M                | N                | K               | ceil(M/R) * ceil(N/C)
  ws       | K                | N                | M               | ceil(K/R) * ceil(N/C)
  is       | K                | M                | N               | ceil(K/R) * ceil(M/C)

Each fold occupies  T + a*R + b*C + c  cycles (a skewed operand stream of T lines, plus array
fill and drain).  Reading the demand-matrix construction gives
   os : (T-1 + R) + (C-1) lines  -> T + R + C - 2
   ws : R (weight load) + T + (C-1) drain + (R-1) skew -> T + 2R + C - 2
   is : same as ws with the roles of M and N swapped
and the last cycle index is reported, so total = folds*(T + aR + bC + c) - 1.
`derived_params()` returns those a,b,c,d; `fit()` re-estimates them from simulator output by
least squares, so the derivation is checked, not assumed.
"""
import math
import numpy as np

DATAFLOWS = ("os", "ws", "is")


def ceil_div(a, b):
    return -(-a // b)


def shape_map(df, M, N, K, R, C):
    """-> (folds, T): number of folds and streamed time dimension for the dataflow."""
    if df == "os":
        return ceil_div(M, R) * ceil_div(N, C), K
    if df == "ws":
        return ceil_div(K, R) * ceil_div(N, C), M
    if df == "is":
        return ceil_div(K, R) * ceil_div(M, C), N
    raise ValueError(df)


def derived_params(df):
    """(a, b, c, d) read off the SCALE-Sim source."""
    return {"os": (1, 1, -2, -1), "ws": (2, 1, -2, -1), "is": (2, 1, -2, -1)}[df]


def predict(df, M, N, K, R, C, params=None):
    a, b, c, d = params if params is not None else derived_params(df)
    F, T = shape_map(df, M, N, K, R, C)
    return F * (T + a * R + b * C + c) + d


def naive_predict(df, M, N, K, R, C, k):
    """The task's first-cut model: cycles = folds * (K + k), one constant k.
    folds uses the dataflow's own tiling, but the streamed length is taken to be K."""
    F, _ = shape_map(df, M, N, K, R, C)
    return F * (K + k)


def fit(df, rows):
    """rows: list of dict(M,N,K,R,C,cycles). Least-squares fit of (a,b,c,d) in
    cycles = F*T + a*F*R + b*F*C + c*F + d.  Returns (a,b,c,d) floats and the design rank."""
    A, y = [], []
    for r in rows:
        F, T = shape_map(df, r["M"], r["N"], r["K"], r["R"], r["C"])
        A.append([F * r["R"], F * r["C"], F, 1.0])
        y.append(r["cycles"] - F * T)
    A, y = np.array(A, float), np.array(y, float)
    sol, _, rank, _ = np.linalg.lstsq(A, y, rcond=None)
    return tuple(float(x) for x in sol), int(rank)


def fit_naive_k(df, rows):
    """Best single constant k in cycles = folds*(K+k) (least squares)."""
    num = den = 0.0
    for r in rows:
        F, _ = shape_map(df, r["M"], r["N"], r["K"], r["R"], r["C"])
        num += F * (r["cycles"] - F * r["K"])
        den += F * F
    return num / den


def compute_only_cycles(df, M, N, K, R, C):
    """Stall-free prediction for a real layer (used by the roofline)."""
    return predict(df, M, N, K, R, C)


def conv_to_gemm(h, w, fh, fw, ch, nf, stride):
    """SCALE-Sim's own conv->GEMM mapping (topology_utils.py: ofmap = ceil((H-Fh+s)/s)).
    Returns (M, N, K) = (ofmap pixels, filters, window size)."""
    oh = -(-(h - fh + stride) // stride)
    ow = -(-(w - fw + stride) // stride)
    return oh * ow, nf, fh * fw * ch


def load_topology(path, gemm=False):
    """-> list of dict(name, M, N, K, ifmap_bytes, filter_bytes, ofmap_bytes) (word = 1 byte)."""
    out = []
    with open(path) as f:
        next(f)
        for line in f:
            p = [x.strip() for x in line.strip().split(",") if x.strip() != ""]
            if not p:
                continue
            if gemm:
                M, N, K = (int(x) for x in p[1:4])
                out.append(dict(name=p[0], M=M, N=N, K=K, ifmap_bytes=M * K,
                                filter_bytes=K * N, ofmap_bytes=M * N))
            else:
                h, w, fh, fw, ch, nf, s = (int(x) for x in p[1:8])
                M, N, K = conv_to_gemm(h, w, fh, fw, ch, nf, s)
                out.append(dict(name=p[0], M=M, N=N, K=K, ifmap_bytes=h * w * ch,
                                filter_bytes=fh * fw * ch * nf, ofmap_bytes=M * N))
    return out
