"""Ideal (rasante) line: the profile the road would have without low points.

The ideal line is computed from the surveyed profile itself:

* it may only **rise and then fall** (one crest at most): a function of that
  shape has no interior local minimum, so it has no sags;
* among all such functions it is the **least-squares closest** to the real
  profile (an isotonic / unimodal regression, solved exactly with the
  pool-adjacent-violators algorithm), so it follows the general trend of the
  data: a descending road gives a descending ideal line, a hill gives a crest;
* on the stretches that must be corrected it keeps a **minimum longitudinal
  grade** (default: 0.5 %, but never more than half of the mean grade of the
  trend, so a gently sloping road is not distorted) so water always drains.

Where the real profile already has no sags and enough grade the ideal line
coincides with it.  ``ideal - real`` is the fill (+) or cut (-) that would be
needed at each station.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

DEFAULT_MAX_MIN_GRADE = 0.005   # 0.5 % cap for the automatic minimum grade
AUTO_GRADE_FRACTION = 0.5       # ... and never more than half of the trend grade


# ----------------------------------------------------------------------- PAVA
def _block_sse(s: float, q: float, c: int) -> float:
    return max(q - s * s / c, 0.0)


def _prefix_sse(u: np.ndarray) -> np.ndarray:
    """SSE of the non-decreasing isotonic fit of every prefix ``u[:k]`` (k = 0..n).

    Incremental pool-adjacent-violators: O(n) amortised for all prefixes.
    """
    n = len(u)
    out = np.zeros(n + 1)
    S, Q, C = [], [], []          # block sums, sums of squares, counts
    total = 0.0
    for i in range(n):
        v = float(u[i])
        s, q, c = v, v * v, 1
        while C and S[-1] / C[-1] > s / c:            # previous block mean is higher
            ps, pq, pc = S.pop(), Q.pop(), C.pop()
            total -= _block_sse(ps, pq, pc)
            s, q, c = s + ps, q + pq, c + pc
        S.append(s), Q.append(q), C.append(c)
        total += _block_sse(s, q, c)
        out[i + 1] = max(total, 0.0)
    return out


def _isotonic_fit(u: np.ndarray) -> np.ndarray:
    """Non-decreasing least-squares fit of ``u`` (pool adjacent violators)."""
    S, C = [], []
    for v in map(float, u):
        s, c = v, 1
        while C and S[-1] / C[-1] > s / c:
            s, c = s + S.pop(), c + C.pop()
        S.append(s), C.append(c)
    return np.repeat(np.array(S) / np.array(C), C) if len(u) else np.zeros(0)


# ---------------------------------------------------------------- unimodal fit
def _unimodal_fit(x: np.ndarray, z: np.ndarray, g: float, allow_crest: bool):
    """Best rise-then-fall fit with slopes >= +g on the rise and <= -g on the fall.

    Returns ``(fit, m)`` where the rising part is ``fit[:m+1]`` and the falling
    part ``fit[m+1:]`` (``m == -1``: only falling; ``m == n-1``: only rising).
    The two parts are fitted independently; the segment between stations ``m``
    and ``m+1`` joins them, so the polyline is continuous and unimodal.
    """
    n = len(z)
    up = z - g * x                       # non-decreasing  <=>  slope >= +g
    dn_rev = (z + g * x)[::-1]           # falling side, reversed order: non-decreasing
    pre_l = _prefix_sse(up)              # pre_l[k]: rising fit of the first k stations
    pre_r = _prefix_sse(dn_rev)          # pre_r[c]: falling fit of the last c stations

    candidates = [-1, n - 1] if not allow_crest else [-1, n - 1] + list(range(0, n - 1))
    best_m, best = None, np.inf
    for m in candidates:
        sse = pre_l[m + 1] + pre_r[n - 1 - m]
        if sse < best - 1e-12:
            best, best_m = sse, m
    m = int(best_m)

    fit = np.empty(n)
    if m >= 0:                                       # rising part
        fit[: m + 1] = _isotonic_fit(up[: m + 1]) + g * x[: m + 1]
    if m < n - 1:                                    # falling part
        v = _isotonic_fit((-z - g * x)[m + 1:])      # v = -f - g x is non-decreasing
        fit[m + 1:] = -v - g * x[m + 1:]
    return fit, m


@dataclass
class IdealProfile:
    """Result of :func:`compute_ideal_profile` (all elevations in metres)."""

    dist: np.ndarray
    real: np.ndarray
    z: np.ndarray               # ideal elevations
    min_grade: float            # minimum grade enforced (m/m, positive)
    trend: str                  # "down" | "up" | "crest"
    crest_index: Optional[int]  # station index of the crest when trend == "crest"
    mean_grade: float           # mean absolute grade of the ideal line (m/m)
    max_fill: float             # largest (ideal - real) > 0: material to add
    max_cut: float              # largest (real - ideal) > 0: material to remove
    rms: float

    @property
    def diff(self) -> np.ndarray:
        """``ideal - real``: positive = fill, negative = cut."""
        return self.z - self.real


def compute_ideal_profile(
    dist: Sequence[float],
    z: Sequence[float],
    *,
    min_grade: Optional[float] = None,
    allow_crest: bool = True,
) -> IdealProfile:
    """Ideal, sag-free profile that follows the trend of ``z`` (see module doc).

    ``min_grade`` is in m/m (0.005 = 0.5 %).  ``None`` selects it automatically:
    ``min(0.5 %, 0.5 * mean grade of the trend)``.  ``allow_crest=False``
    forces a purely monotone line.
    """
    x = np.asarray(dist, float)
    y = np.asarray(z, float)
    if len(y) < 2:
        raise ValueError("at least 2 stations are required")
    if np.any(np.diff(x) <= 0):
        raise ValueError("stations must be strictly increasing")
    x = x - x[0]
    length = float(x[-1])

    if min_grade is None:
        base, _ = _unimodal_fit(x, y, 0.0, allow_crest)          # trend without grade limit
        trend_grade = float(np.abs(np.diff(base)).sum() / length)
        g = min(DEFAULT_MAX_MIN_GRADE, AUTO_GRADE_FRACTION * trend_grade)
    else:
        g = max(float(min_grade), 0.0)
    if g < 1e-9:
        g = 0.0

    fit, m = _unimodal_fit(x, y, g, allow_crest)
    n = len(y)
    if m == -1:
        trend, crest = "down", None
    elif m == n - 1:
        trend, crest = "up", None
    else:
        crest = m if fit[m] >= fit[m + 1] else m + 1
        trend = "crest"
    diff = fit - y
    return IdealProfile(
        dist=np.asarray(dist, float), real=y, z=fit, min_grade=g, trend=trend,
        crest_index=crest, mean_grade=float(np.abs(np.diff(fit)).sum() / length),
        max_fill=float(max(diff.max(), 0.0)), max_cut=float(max((-diff).max(), 0.0)),
        rms=float(np.sqrt(np.mean(diff ** 2))),
    )
