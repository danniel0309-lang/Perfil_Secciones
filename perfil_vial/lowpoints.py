"""Low-point (sag) detection on a longitudinal series.

A low point is a strict local minimum of the elevation series: both neighbouring
stations are higher.  Flat bottoms (several consecutive stations with the same
elevation) are treated as one point.  For each low point we report

* the elevation drop to the **adjacent stations** (the previous and next one);
  ``depth_adjacent`` is the smaller of the two, i.e. the conservative value;
* the depth to the **spill level** (``depth_crest``): walking away from the sag
  in both directions while the ground keeps rising gives the two bounding
  crests; water ponds up to the lower one before overflowing.  This is the
  quantity that matters for drainage design;
* the grades entering and leaving the sag (%).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .parsing import format_k


@dataclass
class LowPoint:
    id: int
    index: int                 # index of the first station of the flat bottom
    end_index: int             # index of the last station of the flat bottom
    station: float
    label: str
    end_label: str
    z: float
    n_stations: int
    prev_station: Optional[float]
    prev_label: Optional[str]
    prev_z: Optional[float]
    next_station: Optional[float]
    next_label: Optional[str]
    next_z: Optional[float]
    depth_prev: Optional[float]
    depth_next: Optional[float]
    depth_adjacent: float
    depth_mean: float
    left_crest_index: int
    right_crest_index: int
    depth_crest: Optional[float]
    grade_in: Optional[float]   # % entering the sag (negative = descending)
    grade_out: Optional[float]  # % leaving the sag (positive = ascending)
    is_boundary: bool


def find_low_points(
    dist: Sequence[float],
    z: Sequence[float],
    labels: Optional[Sequence[str]] = None,
    *,
    min_depth: float = 0.0,
    include_ends: bool = False,
    tol: float = 1e-6,
) -> list:
    """Return the low points of the series, ordered by station.

    ``min_depth`` filters on ``depth_adjacent`` (metres).  ``include_ends`` also
    reports the first/last station when it is lower than its only neighbour
    (flagged ``is_boundary``).  ``tol`` is the elevation difference under which
    two consecutive stations count as equal.
    """
    d = np.asarray(dist, float)
    y = np.asarray(z, float)
    n = len(y)
    if labels is None:
        labels = [format_k(v) for v in d]
    if n < 3 and not (include_ends and n == 2):
        return []

    # flat runs (start, end)
    runs = []
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(y[j + 1] - y[i]) <= tol:
            j += 1
        runs.append((i, j))
        i = j + 1

    found = []
    for k, (s, e) in enumerate(runs):
        v = y[s]
        has_left, has_right = k > 0, k < len(runs) - 1
        left_higher = has_left and y[runs[k - 1][0]] > v
        right_higher = has_right and y[runs[k + 1][0]] > v
        if has_left and has_right:
            if not (left_higher and right_higher):
                continue
            boundary = False
        elif include_ends and has_right and right_higher:      # first station
            boundary = True
        elif include_ends and has_left and left_higher:        # last station
            boundary = True
        else:
            continue

        ip = s - 1 if has_left else None
        inx = e + 1 if has_right else None
        depth_prev = (y[ip] - v) if ip is not None else None
        depth_next = (y[inx] - v) if inx is not None else None
        cand = [x for x in (depth_prev, depth_next) if x is not None]
        depth_adj = min(cand)
        if depth_adj < min_depth:
            continue

        # bounding crests: climb while the ground keeps rising
        lc = rc = None
        if ip is not None:
            j = ip
            while j > 0 and y[j - 1] > y[j] + tol:
                j -= 1
            lc = j
        if inx is not None:
            j = inx
            while j < n - 1 and y[j + 1] > y[j] + tol:
                j += 1
            rc = j
        crest_z = [y[c] for c in (lc, rc) if c is not None]
        depth_crest = (min(crest_z) - v) if len(crest_z) == 2 else None

        grade_in = ((v - y[ip]) / (d[s] - d[ip]) * 100.0) if ip is not None else None
        grade_out = ((y[inx] - y[e]) / (d[inx] - d[e]) * 100.0) if inx is not None else None

        found.append(
            LowPoint(
                id=0, index=s, end_index=e, station=float(d[s]), label=labels[s],
                end_label=labels[e], z=float(v), n_stations=e - s + 1,
                prev_station=float(d[ip]) if ip is not None else None,
                prev_label=labels[ip] if ip is not None else None,
                prev_z=float(y[ip]) if ip is not None else None,
                next_station=float(d[inx]) if inx is not None else None,
                next_label=labels[inx] if inx is not None else None,
                next_z=float(y[inx]) if inx is not None else None,
                depth_prev=None if depth_prev is None else float(depth_prev),
                depth_next=None if depth_next is None else float(depth_next),
                depth_adjacent=float(depth_adj),
                depth_mean=float(np.mean(cand)),
                left_crest_index=lc if lc is not None else s,
                right_crest_index=rc if rc is not None else e,
                depth_crest=None if depth_crest is None else float(depth_crest),
                grade_in=grade_in, grade_out=grade_out, is_boundary=boundary,
            )
        )

    for n_id, lp in enumerate(sorted(found, key=lambda p: p.station), start=1):
        lp.id = n_id
    return sorted(found, key=lambda p: p.station)


# ------------------------------------------------------------------- ponding
@dataclass
class Pond:
    """Water that would collect in a sag (flat surface between two shores)."""

    lp_id: int
    level: float            # water surface elevation (m)
    bottom: float           # lowest ground elevation of the sag (m)
    depth: float            # level - bottom (m)
    x_left: float           # station where the surface meets the ground on the left
    x_right: float          # ... and on the right
    i_lo: int               # first / last profile stations that are under water
    i_hi: int
    length: float           # x_right - x_left (m)
    area: float             # water area in the longitudinal section (m^2)
    full: bool              # True when the water reaches the spill level

    def outline(self, dist: Sequence[float], z: Sequence[float]):
        """Ground polyline under the water: shore, submerged stations, shore."""
        xs = [self.x_left] + [float(v) for v in dist[self.i_lo:self.i_hi + 1]] + [self.x_right]
        zs = [self.level] + [float(v) for v in z[self.i_lo:self.i_hi + 1]] + [self.level]
        return xs, zs


def ponding_region(
    dist: Sequence[float],
    z: Sequence[float],
    lp: LowPoint,
    max_depth: Optional[float] = None,
) -> Optional[Pond]:
    """Water body that collects at low point ``lp``.

    Water fills the sag up to the **spill level** (the lower of the two bounding
    crests).  ``max_depth`` limits the water depth (a shallow puddle instead of a
    full basin).  Low points at the ends of the profile have no spill level, so
    they hold no pond (``None``).
    """
    if lp.depth_crest is None or lp.depth_crest <= 0.0:
        return None
    d = np.asarray(dist, float)
    y = np.asarray(z, float)
    depth = lp.depth_crest if max_depth is None else min(lp.depth_crest, max(max_depth, 0.0))
    if depth <= 0.0:
        return None
    level = lp.z + depth

    lo = lp.index
    while lo > 0 and y[lo - 1] < level:
        lo -= 1
    hi = lp.end_index
    while hi < len(y) - 1 and y[hi + 1] < level:
        hi += 1

    if lo > 0:      # crossing between station lo-1 (>= level) and lo (< level)
        x_left = d[lo - 1] + (level - y[lo - 1]) * (d[lo] - d[lo - 1]) / (y[lo] - y[lo - 1])
    else:
        x_left = d[0]
    if hi < len(y) - 1:
        x_right = d[hi] + (level - y[hi]) * (d[hi + 1] - d[hi]) / (y[hi + 1] - y[hi])
    else:
        x_right = d[-1]

    xs = np.concatenate(([x_left], d[lo:hi + 1], [x_right]))
    gz = np.concatenate(([level], y[lo:hi + 1], [level]))
    area = float(np.sum((level - gz[1:] + level - gz[:-1]) / 2.0 * np.diff(xs)))
    return Pond(
        lp_id=lp.id, level=float(level), bottom=float(lp.z), depth=float(depth),
        x_left=float(x_left), x_right=float(x_right), i_lo=int(lo), i_hi=int(hi),
        length=float(x_right - x_left), area=area,
        full=bool(depth >= lp.depth_crest - 1e-12),
    )
