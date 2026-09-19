"""Grid scaling and vertical exaggeration.

Direct port of the layout maths shared by ``Perfil_long.lsp`` (PERFILTN) and
``Seccion_long.lsp`` (SECCIONTN):

* ``PF:NiceStep`` / ``SC:NiceStep``   -> :func:`nice_step`
* text-height clamp, row heights      -> :func:`profile_scale`, :func:`section_scale`
* ``targetGridH`` / ``vExag``         -> :attr:`Scale.v_exag`
* ``refZ`` / ``topZ`` grid limits     -> :attr:`Scale.ref_z`, :attr:`Scale.top_z`

Units are "drawing units" = metres horizontally (1:1). A point with elevation
``z`` sits at ``y = (z - ref_z) * v_exag`` above the grid base, so ``v_exag`` is
literally the vertical exaggeration of the drawing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def clamp(v: float, lo: float, hi: float) -> float:
    """PF:Clamp -> ``(max a (min b v))``."""
    return max(lo, min(hi, v))


def floor_int(v: float) -> int:
    """PF:FloorInt (true floor, also for negative values)."""
    return math.floor(v)


def nice_step(rng: float) -> float:
    """PF:NiceStep - a 1/2/5/10 x 10^n step giving roughly five grid intervals."""
    if rng <= 0.0:
        return 1.0
    raw = rng / 5.0
    exp = floor_int(math.log10(raw))
    base = 10.0 ** exp
    frac = raw / base
    eps = 1e-9  # guard against 2.0000000000000004 style float noise
    if frac <= 1.0 + eps:
        return 1.0 * base
    if frac <= 2.0 + eps:
        return 2.0 * base
    if frac <= 5.0 + eps:
        return 5.0 * base
    return 10.0 * base


@dataclass(frozen=True)
class Scale:
    """All derived layout numbers of one profile / section drawing."""

    width: float        # horizontal extent of the plotted data (m)
    zmin: float
    zmax: float
    rng: float          # max(zmax - zmin, 0.001)
    step: float         # elevation grid step (m)
    ref_z: float        # elevation of the grid base
    top_z: float        # elevation of the grid top
    n_steps: int        # number of grid intervals between ref_z and top_z
    txt_h: float        # base text height (drawing units)
    data_h: float       # data text height
    title_h: float
    left_w: float       # width of the left label column
    right_w: float      # width of the right margin
    row_title_h: float
    row_cota_h: float
    row_abs_h: float    # longitudinal profile only (0 otherwise)
    row_dist_h: float   # cross-section only (0 otherwise)
    row_desc_h: float   # cross-section only (0 otherwise)
    target_grid_h: float
    v_exag: float

    def y(self, z: float) -> float:
        """Height above the grid base of elevation ``z``."""
        return (z - self.ref_z) * self.v_exag

    @property
    def grid_h(self) -> float:
        return (self.top_z - self.ref_z) * self.v_exag

    def z_levels(self) -> list[float]:
        """Elevations of the horizontal grid lines (ref_z .. top_z)."""
        return [self.ref_z + k * self.step for k in range(self.n_steps + 1)]


def _grid(zmin: float, zmax: float) -> tuple[float, float, float, float, int]:
    """Return ``(rng, step, ref_z, top_z, n_steps)`` exactly as the LISP does.

    ``refZ`` is ``zmin`` floored to a multiple of the step; ``topZ`` is the first
    ``refZ + k*step`` that is >= ``zmax``.  A degenerate zero-height grid (data
    exactly on a grid line) is avoided by forcing at least one interval.
    """
    rng = max(zmax - zmin, 0.001)
    step = nice_step(rng)
    ref_z = step * floor_int(zmin / step)
    n = max(math.ceil((zmax - ref_z) / step - 1e-9), 1)
    return rng, step, ref_z, ref_z + n * step, n


def profile_scale(width: float, zmin: float, zmax: float) -> Scale:
    """Scaling of the longitudinal profile (PERFILTN)."""
    if width <= 0.0:
        raise ValueError("profile width must be positive")
    rng, step, ref_z, top_z, n = _grid(zmin, zmax)
    txt_h = clamp(width / 70.0, 0.70, 2.20)
    target = max(width * 0.285, txt_h * 18.0)
    return Scale(
        width=width, zmin=zmin, zmax=zmax, rng=rng, step=step,
        ref_z=ref_z, top_z=top_z, n_steps=n,
        txt_h=txt_h, data_h=txt_h * 0.85, title_h=txt_h * 1.55,
        left_w=txt_h * 9.20, right_w=txt_h * 1.70,
        row_title_h=txt_h * 2.40, row_cota_h=txt_h * 6.10,
        row_abs_h=txt_h * 6.50, row_dist_h=0.0, row_desc_h=0.0,
        target_grid_h=target, v_exag=target / rng,
    )


def section_scale(width: float, zmin: float, zmax: float) -> Scale:
    """Scaling of one cross-section (SECCIONTN / SC:DrawOneSection)."""
    width = max(width, 0.001)
    rng, step, ref_z, top_z, n = _grid(zmin, zmax)
    txt_h = clamp(width / 60.0, 0.70, 2.20)
    target = max(width * 0.350, txt_h * 18.0)
    return Scale(
        width=width, zmin=zmin, zmax=zmax, rng=rng, step=step,
        ref_z=ref_z, top_z=top_z, n_steps=n,
        txt_h=txt_h, data_h=txt_h * 0.85, title_h=txt_h * 1.50,
        left_w=txt_h * 9.20, right_w=txt_h * 9.20,
        row_title_h=txt_h * 2.40, row_cota_h=txt_h * 6.10,
        row_abs_h=0.0, row_dist_h=txt_h * 4.385714, row_desc_h=txt_h * 5.571429,
        target_grid_h=target, v_exag=target / rng,
    )
