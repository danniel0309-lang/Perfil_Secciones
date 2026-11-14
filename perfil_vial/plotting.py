"""Matplotlib renderings.

The longitudinal profile and the cross-sections are drawn the way the AutoLISP
programs draw them: a framed sheet with a table of stations / offsets /
descriptions / elevations underneath a dashed grid.  Everything is laid out in
*drawing units* (1 unit = 1 m horizontally, ``v_exag`` units per metre of
elevation vertically) on an axes whose aspect is exactly 1:1, so the vertical
exaggeration printed on the sheet is the true one.  Text heights are converted
from drawing units to points with the sheet's points-per-unit factor.

Figures are built with :class:`matplotlib.figure.Figure` directly (no pyplot),
so nothing depends on a GUI backend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter

from .geometry import Scale, clamp, profile_scale, section_scale
from .i18n import msg
from .lowpoints import LowPoint, Pond, ponding_region
from .parsing import ExtraPoint, Section, SurveyError, format_k
from .profile import Series, lowest_in_section

# --- palette (validated categorical order + neutral ink, light surface) -----------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#b9b7ae"
FRAME = "#3a3a38"
C_MAIN = "#2a78d6"                       # reference line (blue)
C_SERIES = ["#eb6834", "#4a3aa7", "#eda100", "#e87ba4", "#1baf7a", "#8a5a2b"]
C_LEFT, C_RIGHT = C_SERIES[0], C_SERIES[1]   # left / right road-side lines
C_IDEAL = "#008300"                      # ideal line (dashed green, not used by other series)
C_LOW = "#e34948"                        # low points / warnings
C_WATER = "#3fb6e8"                      # ponded water body
C_WATER_EDGE = "#1a86bd"                 # water surface line
IDEAL_DASH = (0, (7.0, 3.5))
DASH = (0, (3.0, 2.5))
FONT_K = 0.85                            # em size = FONT_K * drawing text height


# ----------------------------------------------------------------------- canvas
class Canvas:
    """Thin helper to draw in drawing units on a 1:1 axes."""

    def __init__(self, total_w: float, total_h: float, margin: float, w_in: float):
        ext_w, ext_h = total_w + 2 * margin, total_h + 2 * margin
        self.ppu = w_in * 72.0 / ext_w                    # points per drawing unit
        self.fig = Figure(figsize=(w_in, ext_h * self.ppu / 72.0), facecolor=SURFACE)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(-margin, total_w + margin)
        self.ax.set_ylim(-margin, total_h + margin)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.axis("off")

    def fs(self, h: float) -> float:
        return max(h * self.ppu * FONT_K, 1.0)

    def line(self, xs, ys, color=FRAME, lw=0.9, ls="-", z=2, **kw):
        self.ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=z,
                     solid_capstyle="butt", **kw)

    def hline(self, x1, x2, y, **kw):
        self.line([x1, x2], [y, y], **kw)

    def vline(self, x, y1, y2, **kw):
        self.line([x, x], [y1, y2], **kw)

    def rect(self, x1, y1, x2, y2, color=FRAME, lw=1.1):
        self.ax.add_patch(Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False,
                                    ec=color, lw=lw, zorder=3))

    def text(self, x, y, s, h, rot=0, ha="center", va="center", color=INK,
             weight="normal", z=6):
        self.ax.text(x, y, s, fontsize=self.fs(h), rotation=rot, ha=ha, va=va,
                     color=color, fontweight=weight, zorder=z, clip_on=False)

    def marker(self, x, y, marker, size_units, color, z=8, **kw):
        self.ax.plot([x], [y], marker=marker, ms=max(size_units * self.ppu, 2.0),
                     color=color, ls="none", zorder=z, clip_on=False, **kw)


def _legend_layout(items: Sequence[tuple], h: float, max_w: float) -> list:
    """Wrap legend items into rows: returns ``[[(x, item), ...], ...]``."""
    sw, gap = 3.0 * h, 3.0 * h
    rows, x = [[]], 0.0
    for it in items:
        w = sw + 0.6 * h + 0.58 * h * len(it[2])
        if x > 0.0 and x + w > max_w:
            rows.append([])
            x = 0.0
        rows[-1].append((x, it))
        x += w + gap
    return rows


def _draw_legend(cv: Canvas, rows: list, x0: float, y_top: float, h: float, row_h: float) -> None:
    """Manual legend. Item kinds: line | dash | ideal | tri | x | ring | water."""
    sw = 3.0 * h
    for r, row in enumerate(rows):
        y = y_top - row_h * (r + 0.5)
        for dx, (kind, color, label) in row:
            x = x0 + dx
            if kind == "line":
                cv.hline(x, x + sw, y, color=color, lw=1.8, z=6)
            elif kind == "dash":
                cv.hline(x, x + sw, y, color=color, lw=1.0, ls=DASH, z=6)
            elif kind == "ideal":
                cv.hline(x, x + sw, y, color=color, lw=2.0, ls=IDEAL_DASH, z=6)
            elif kind == "tri":
                cv.marker(x + sw / 2, y, "v", 1.1 * h, color, mec=SURFACE, mew=0.6)
            elif kind == "x":
                cv.marker(x + sw / 2, y, "x", 1.0 * h, color, mew=1.2)
            elif kind == "ring":
                cv.marker(x + sw / 2, y, "o", 1.1 * h, "none", mec=color, mew=1.3)
            elif kind == "water":
                cv.ax.add_patch(Rectangle((x, y - 0.5 * h), sw, h, fc=color, ec=C_WATER_EDGE,
                                          lw=0.7, alpha=0.6, zorder=6))
            cv.text(x + sw + 0.6 * h, y, label, h, ha="left", color=INK2)


def _legend_row(cv: Canvas, x: float, y: float, h: float, items: Sequence[tuple]) -> None:
    """Single-row legend centred vertically on ``y`` (used by the sections sheets)."""
    _draw_legend(cv, [[(dx, it) for dx, it in row] for row in _legend_layout(items, h, 1e9)],
                 x, y + h * 1.4, h, 2.8 * h)


# ------------------------------------------------------------------- water body
def _paint_water(ax, xs, ground, bottom, level, *, sheen: float, n_layers: int = 10,
                 alpha: float = 0.09, z: float = 3.0) -> None:
    """Paint a body of water above the ground polyline ``(xs, ground)``.

    Everything is in the coordinates of ``ax``.  The water is drawn as stacked
    translucent layers so it looks darker where it is deeper, with a flat surface
    line at ``level`` and a thin light band just under the surface (sheen).
    """
    xs = np.asarray(xs, float)
    g = np.asarray(ground, float)
    for j in range(1, n_layers + 1):
        top = bottom + (level - bottom) * j / n_layers
        ax.fill_between(xs, g, top, where=g < top, interpolate=True, color=C_WATER,
                        alpha=alpha, lw=0, zorder=z)
    ax.fill_between(xs, np.maximum(g, level - sheen), level, where=g < level, interpolate=True,
                    color="white", alpha=0.35, lw=0, zorder=z + 0.1)
    ax.plot([xs[0], xs[-1]], [level, level], color=C_WATER_EDGE, lw=1.1, zorder=z + 0.2,
            solid_capstyle="butt")


def _line_colors(extras: Sequence[Series]) -> list:
    """Left/right side lines keep fixed colours; other extra lines take the next slots."""
    out, nxt = [], 2
    for se in extras:
        if se.role == "left":
            out.append(C_LEFT)
        elif se.role == "right":
            out.append(C_RIGHT)
        else:
            out.append(C_SERIES[nxt % len(C_SERIES)])
            nxt += 1
    return out


# ---------------------------------------------------------------- longitudinal
def _seg_lines(xs, ys):
    """Split a line at None values -> list of (xs, ys) runs."""
    runs, cx, cy = [], [], []
    for x, y in zip(xs, ys):
        if y is None:
            if cx:
                runs.append((cx, cy))
            cx, cy = [], []
        else:
            cx.append(x)
            cy.append(y)
    if cx:
        runs.append((cx, cy))
    return runs


def _align(series: Series, stations) -> list:
    """Values of ``series`` at ``stations`` (None where the series has no station)."""
    lk = {round(float(s), 6): float(v) for s, v in zip(series.stations, series.z)}
    return [lk.get(round(float(s), 6)) for s in stations]


def plot_long_profile(
    main: Series,
    extras: Sequence[Series] = (),
    points: Sequence[ExtraPoint] = (),
    lows: Sequence[LowPoint] = (),
    *,
    ideal: Optional[Series] = None,
    water: bool = True,
    water_depth: Optional[float] = None,
    scale_extras: Optional[Sequence[Series]] = None,
    title: Optional[str] = None,
    lang: str = "es",
    max_width_in: float = 60.0,
    min_font_pt: float = 7.0,
) -> tuple:
    """Draw the longitudinal profile sheet (port of PERFILTN).

    ``extras`` are additional lines from the survey (e.g. the left/right road
    sides, ``role`` = "left"/"right").  ``ideal`` is the sag-free ideal grade
    line, drawn dashed on the same scale.  With ``water`` a body of water is
    painted at every low point (up to the spill level, or ``water_depth`` m).
    ``scale_extras`` are the lines whose elevations set the vertical range of the
    sheet (default: ``extras``); pass the lines of every companion sheet (e.g. the
    other road side) so that several sheets share the same scale.

    Returns ``(figure, scale)``; ``scale`` carries the vertical exaggeration,
    grid step and reference elevations that were used.
    """
    t = lambda k, **kw: msg(lang, k, **kw)  # noqa: E731
    extras = list(extras)[:6]                      # "lineas de tendencia [0-6]"

    first = float(main.stations[0])
    xoff = main.stations - first                   # PF:BuildOffsetsFromKLabels
    n = len(xoff)
    ex_vals = [_align(se, main.stations) for se in extras]
    scale_vals = ex_vals if scale_extras is None else [_align(se, main.stations)
                                                       for se in scale_extras]
    ideal_vals = _align(ideal, main.stations) if ideal is not None else None
    colors = _line_colors(extras)
    pt_x = [p.station - first for p in points]

    xmin = min([float(xoff.min())] + pt_x)         # xMinData / xMaxData include extras
    xmax = max([float(xoff.max())] + pt_x)
    prof_w = xmax - xmin
    if prof_w <= 0.0:
        raise SurveyError(t("e_zero_width"))

    all_z = list(map(float, main.z)) + [v for row in scale_vals for v in row if v is not None] \
        + [p.z for p in points] + ([v for v in ideal_vals if v is not None] if ideal_vals else [])
    sc = profile_scale(prof_w, min(all_z), max(all_z))

    n_rows = 1 + len(extras) + (1 if ideal_vals else 0)
    x_grid0 = sc.left_w
    x_plot_right = x_grid0 + prof_w
    x_right = x_plot_right + sc.right_w
    y_abs_top = sc.row_abs_h
    y_gb = y_abs_top + n_rows * sc.row_cota_h            # grid base
    y_gt = y_gb + sc.grid_h                              # grid top
    y_top = y_gt + sc.row_title_h

    dx_min = float(np.diff(xoff).min()) if n > 1 else sc.data_h
    h = min(sc.data_h, 0.8 * dx_min)                    # keep rotated labels from overlapping

    # ponds (computed first: the legend depends on whether any exists)
    ponds = []
    if water:
        for lp in lows:
            pond = ponding_region(main.stations, main.z, lp, water_depth)
            if pond is not None:
                ponds.append(pond)

    # legend layout (wrapped) ------------------------------------------------------
    def _side_label(se: Series) -> str:
        if se.role == "left":
            return f"{t('side_left')} ({se.name})"
        if se.role == "right":
            return f"{t('side_right')} ({se.name})"
        return se.name

    items = [("line", C_MAIN, main.name)]
    items += [("line", colors[k], _side_label(se)) for k, se in enumerate(extras)]
    if ideal_vals:
        items.append(("ideal", C_IDEAL, t("ideal_line")))
    if lows:
        items.append(("tri", C_LOW, t("low_point")))
    if ponds:
        items.append(("water", C_WATER, t("water")))
    if points:
        items.append(("x", INK2, t("extra_point")))
    vex_txt = t("vexag", v=sc.v_exag)
    leg_rows = _legend_layout(items, h, x_right - 0.58 * h * len(vex_txt) - 3.0 * h)
    leg_row_h = 2.8 * h
    legend_h = len(leg_rows) * leg_row_h + 0.6 * h
    total_w, total_h = x_right, y_top + legend_h

    margin = 2.0 * sc.txt_h
    ext_w = total_w + 2 * margin
    w_in = clamp(ext_w * (min_font_pt / (FONT_K * h)) / 72.0, 6.0, max_width_in)
    cv = Canvas(total_w, total_h, margin, w_in)

    def X(v):
        return x_grid0 + (v - xmin)

    def Y(z):
        return y_gb + sc.y(z)

    # frame and table rules
    cv.rect(0, 0, x_right, y_top)
    cv.hline(0, x_right, y_abs_top)
    for k in range(1, n_rows + 1):
        cv.hline(0, x_right, y_abs_top + k * sc.row_cota_h)
    cv.vline(x_grid0, y_gb, y_gt)

    # dashed grid
    levels = sc.z_levels()
    for zl in levels:
        cv.hline(x_grid0, x_plot_right, Y(zl), color=GRID, lw=0.5, ls=DASH, z=1)
        cv.text(x_grid0 - 0.6 * sc.txt_h, Y(zl), f"{zl:.3f}", h, ha="right", color=INK2)
    for xo in xoff:
        cv.vline(X(xo), y_gb, y_gt, color=GRID, lw=0.5, ls=DASH, z=1)
    cv.vline(x_plot_right, y_gb, y_gt)

    # water at the low points (under the profile lines)
    for pond in ponds:
        pxs, pzs = pond.outline(main.stations, main.z)
        _paint_water(cv.ax, [X(v - first) for v in pxs], [Y(v) for v in pzs],
                     Y(pond.bottom), Y(pond.level), sheen=0.5 * sc.txt_h)
        mid = X((pond.x_left + pond.x_right) / 2.0 - first)
        cv.text(mid, Y(pond.level) + 1.1 * sc.txt_h, f"{pond.depth:.3f} m", h, color=INK,
                weight="bold")
    # series
    xs = [X(v) for v in xoff]
    for k, row in enumerate(ex_vals):
        for rx, ry in _seg_lines(xs, [None if v is None else Y(v) for v in row]):
            cv.line(rx, ry, color=colors[k], lw=1.6, z=4)
    cv.line(xs, [Y(v) for v in main.z], color=C_MAIN, lw=1.8, z=5, marker="o", ms=2.6,
            mfc=C_MAIN, mec=C_MAIN)
    if ideal_vals:
        for rx, ry in _seg_lines(xs, [None if v is None else Y(v) for v in ideal_vals]):
            cv.line(rx, ry, color=C_IDEAL, lw=2.0, ls=IDEAL_DASH, z=6)

    # additional annotation points
    for p in points:
        px, py = X(p.station - first), Y(p.z)
        cv.marker(px, py, "x", 1.1 * sc.txt_h, INK2, mew=1.3)
        cv.text(px + 0.8 * sc.txt_h, py + 0.45 * sc.txt_h, f"{p.desc} {p.z:.3f}", h * 0.95,
                ha="left", color=INK)

    # low points
    low_at = {}
    for lp in lows:
        px, py = X(lp.station - first), Y(lp.z)
        low_at[round(lp.station, 6)] = lp
        cv.marker(px, py, "v", 1.5 * sc.txt_h, C_LOW, mec=SURFACE, mew=0.8, z=9)
        cv.text(px, py - 1.7 * sc.txt_h, f"PB{lp.id}", h, color=C_LOW, weight="bold")

    # table: stations, elevations
    for xo, lab, st in zip(xoff, main.labels, main.stations):
        lp = low_at.get(round(float(st), 6))
        cv.text(X(xo), sc.row_abs_h / 2, lab, h, rot=90,
                color=C_LOW if lp else INK2, weight="bold" if lp else "normal")
    series_rows = [(main.name, C_MAIN, [float(v) for v in main.z], None)] + [
        (se.name, colors[k], ex_vals[k], None) for k, se in enumerate(extras)
    ]
    if ideal_vals:
        series_rows.append((t("cota_ideal"), C_IDEAL, ideal_vals, IDEAL_DASH))
    for r, (nm, col, vals, dash) in enumerate(series_rows):
        base = y_abs_top + r * sc.row_cota_h
        for xo, v in zip(xoff, vals):
            cv.text(X(xo), base + sc.row_cota_h / 2, "" if v is None else f"{v:.3f}", h,
                    rot=90, color=INK)
        cv.hline(sc.left_w * 0.2, sc.left_w * 0.8, base + sc.row_cota_h * 0.74,
                 color=col, lw=2.0, ls=dash or "-", z=6)
        cv.text(sc.left_w / 2, base + sc.row_cota_h * 0.42, f"{t('cota_prefix')} {nm}", h)
    cv.text(sc.left_w / 2, sc.row_abs_h / 2, t("abscissas"), h)

    # title, legend, exaggeration
    cv.text(total_w / 2, y_gt + sc.row_title_h / 2, title or t("profile_title"), sc.title_h,
            weight="bold")
    _draw_legend(cv, leg_rows, 0.0, total_h, h, leg_row_h)
    cv.text(total_w, total_h - leg_row_h / 2, vex_txt, h, ha="right", color=INK2)
    return cv.fig, sc


# ------------------------------------------------------------------ cross-sections
@dataclass
class _Block:
    sec: Section
    sc: Scale
    w: float
    h: float
    hh: float                 # effective data text height
    low_id: Optional[int]


def _make_block(sec: Section, low_id: Optional[int]) -> _Block:
    xs = sec.offsets
    sec_w = max(xs[-1] - xs[0], 0.001)
    sc = section_scale(sec_w, min(sec.elevations), max(sec.elevations))
    w = sc.left_w + sec_w + sc.right_w
    h = sc.row_dist_h + sc.row_desc_h + sc.row_cota_h + sc.grid_h + sc.row_title_h
    dx_min = min(b - a for a, b in zip(xs, xs[1:]))
    return _Block(sec, sc, w, h, min(sc.data_h, 0.8 * dx_min), low_id)


def _draw_block(cv: Canvas, b: _Block, bx: float, by: float, lang: str) -> None:
    """Draw one cross-section with its lower-left corner at (bx, by) (SC:DrawOneSection)."""
    t = lambda k, **kw: msg(lang, k, **kw)  # noqa: E731
    sec, sc, hh = b.sec, b.sc, b.hh
    xs = sec.offsets
    xmin, xmax = xs[0], xs[-1]
    x_grid0 = bx + sc.left_w
    x_plot_right = x_grid0 + sc.width
    x_right = x_plot_right + sc.right_w
    y_dist_top = by + sc.row_dist_h
    y_desc_top = y_dist_top + sc.row_desc_h
    y_gb = y_desc_top + sc.row_cota_h
    y_gt = y_gb + sc.grid_h
    y_top = y_gt + sc.row_title_h

    def X(v):
        return x_grid0 + (v - xmin)

    def Y(z):
        return y_gb + sc.y(z)

    cv.rect(bx, by, x_right, y_top)
    for yy in (y_dist_top, y_desc_top, y_gb):
        cv.hline(bx, x_right, yy)
    cv.vline(x_grid0, y_gb, y_gt)

    for zl in sc.z_levels():
        cv.hline(x_grid0, x_plot_right, Y(zl), color=GRID, lw=0.5, ls=DASH, z=1)
        cv.text(x_grid0 - 0.6 * sc.txt_h, Y(zl), f"{zl:.3f}", hh, ha="right", color=INK2)
        cv.text(x_plot_right + 0.6 * sc.txt_h, Y(zl), f"{zl:.3f}", hh, ha="left", color=INK2)
    for xv in xs:
        cv.vline(X(xv), y_gb, y_gt, color=GRID, lw=0.5, ls=DASH, z=1)
    cv.vline(x_plot_right, y_gb, y_gt)
    if xmin <= 0.0 <= xmax:                            # centerline axis (yellow in the LISP)
        cv.vline(X(0.0), y_gb, y_gt, color=INK2, lw=0.9, ls=(0, (6, 2, 1, 2)), z=2)

    px = [X(v) for v in xs]
    cv.line(px, [Y(z) for z in sec.elevations], color=C_MAIN, lw=1.8, z=5,
            marker="o", ms=3.0, mfc=C_MAIN, mec=C_MAIN)
    low = lowest_in_section(sec)
    cv.marker(px[low["index"]], Y(low["z"]), "o", 1.5 * sc.txt_h, "none", mec=C_LOW, mew=1.4, z=9)

    for xv, ds, z in zip(xs, sec.descs, sec.elevations):
        cv.text(X(xv), by + sc.row_dist_h / 2, f"{xv:.1f}", hh, rot=90, color=INK)
        cv.text(X(xv), y_dist_top + sc.row_desc_h / 2, ds, hh, rot=90, color=INK2)
        cv.text(X(xv), y_desc_top + sc.row_cota_h / 2, f"{z:.3f}", hh, rot=90, color=INK)
    cv.text(bx + sc.left_w / 2, by + sc.row_dist_h / 2, t("distance"), hh)
    cv.text(bx + sc.left_w / 2, y_dist_top + sc.row_desc_h / 2, t("description"), hh)
    cv.text(bx + sc.left_w / 2, y_desc_top + sc.row_cota_h / 2, t("cota_tn"), hh)

    title = sec.label or "-"
    if b.low_id is not None:
        title += f"   ▼ PB{b.low_id}"
    cv.text((bx + x_right) / 2, y_gt + sc.row_title_h / 2, title, sc.title_h, weight="bold",
            color=C_LOW if b.low_id is not None else INK)


def plot_sections(
    sections: Sequence[Section],
    *,
    cols: int = 3,
    per_page: int = 6,
    hgap: float = 5.0,
    vgap: float = 5.0,
    max_page_w_in: float = 24.0,
    min_font_pt: float = 7.5,
    lang: str = "es",
    low_ids: Optional[dict] = None,
    title: Optional[str] = None,
) -> list:
    """Draw cross-sections in a grid (port of SECCIONTN), one figure per page."""
    t = lambda k, **kw: msg(lang, k, **kw)  # noqa: E731
    low_ids = low_ids or {}
    cols = max(1, int(cols))
    per_page = max(cols, int(math.ceil(per_page / cols) * cols))
    blocks = [_make_block(s, low_ids.get(round(s.station, 6))) for s in sections]
    pages = [blocks[i:i + per_page] for i in range(0, len(blocks), per_page)]

    figs = []
    for pi, page in enumerate(pages, start=1):
        rows = [page[i:i + cols] for i in range(0, len(page), cols)]
        row_h = [max(b.h for b in r) for r in rows]
        row_w = [sum(b.w for b in r) + hgap * (len(r) - 1) for r in rows]
        ref_txt = float(np.median([b.sc.txt_h for b in page]))
        ref_hh = float(np.median([b.hh for b in page]))
        header_h = 6.5 * ref_txt
        total_w = max(row_w)
        total_h = sum(row_h) + vgap * (len(rows) - 1) + header_h
        margin = 2.0 * ref_txt
        ext_w = total_w + 2 * margin
        w_in = clamp(ext_w * (min_font_pt / (FONT_K * ref_hh)) / 72.0, 6.0, max_page_w_in)
        cv = Canvas(total_w, total_h, margin, w_in)

        y_cursor = total_h - header_h
        for r, rh in zip(rows, row_h):
            x_cursor = 0.0
            for b in r:
                _draw_block(cv, b, x_cursor, y_cursor - b.h, lang)   # top-aligned in the row
                x_cursor += b.w + hgap
            y_cursor -= rh + vgap

        cv.text(0.0, total_h - 1.6 * ref_txt, title or t("sections_title"), 1.5 * ref_txt,
                ha="left", weight="bold")
        cv.text(total_w, total_h - 1.6 * ref_txt, t("page", i=pi, n=len(pages)), ref_hh,
                ha="right", color=INK2)
        _legend_row(cv, 0.0, total_h - 4.6 * ref_txt, ref_hh, [
            ("line", C_MAIN, t("cota_tn")),
            ("ring", C_LOW, t("section_low")),
            ("dash", INK2, t("axis_zero")),
        ])
        figs.append(cv.fig)
    return figs


# ---------------------------------------------------------------- low-point chart
def _spill_span(d, z, lo, hi, s, e, spill):
    """Stations where the profile crosses the spill level on each side of a sag."""
    x_from, x_to = float(d[lo]), float(d[hi])
    for k in range(lo, s + 1):                       # descending side
        if z[k] < spill:
            if k > lo:
                x_from = float(np.interp(spill, [z[k], z[k - 1]], [d[k], d[k - 1]]))
            break
    for k in range(hi, e - 1, -1):                   # ascending side
        if z[k] < spill:
            if k < hi:
                x_to = float(np.interp(spill, [z[k], z[k + 1]], [d[k], d[k + 1]]))
            break
    return x_from, x_to


def plot_low_points(
    main: Series,
    lows: Sequence[LowPoint],
    *,
    ideal: Optional[Series] = None,
    water: bool = True,
    water_depth: Optional[float] = None,
    title: Optional[str] = None,
    lang: str = "es",
) -> Figure:
    """Plain (non-CAD) chart: profile with the sags marked + depth per low point."""
    t = lambda k, **kw: msg(lang, k, **kw)  # noqa: E731
    fig = Figure(figsize=(12, 8), facecolor=SURFACE)
    ax1, ax2 = fig.subplots(2, 1, gridspec_kw={"height_ratios": [3, 1.5]})
    d, z = main.stations, main.z

    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=INK2, labelsize=9)
        ax.grid(axis="y", color=GRID, lw=0.5, alpha=0.7)
        ax.set_axisbelow(True)

    # water bodies first so the profile line sits on top
    n_ponds = 0
    if water:
        span = float(np.max(z) - np.min(z)) or 1.0
        for lp in lows:
            pond = ponding_region(d, z, lp, water_depth)
            if pond is None:
                continue
            n_ponds += 1
            pxs, pzs = pond.outline(d, z)
            _paint_water(ax1, pxs, pzs, pond.bottom, pond.level, sheen=0.02 * span)
            ax1.annotate(f"{pond.depth:.3f} m", ((pond.x_left + pond.x_right) / 2, pond.level),
                         xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                         fontsize=8.5, color=INK, fontweight="bold")

    ax1.plot(d, z, color=C_MAIN, lw=2.0, marker="o", ms=3.2, label=f"{main.name}", zorder=4)
    if ideal is not None:
        ax1.plot(ideal.stations, ideal.z, color=C_IDEAL, lw=2.0, ls=IDEAL_DASH,
                 label=t("ideal_line"), zorder=5)
    if lows:
        ax1.scatter([lp.station for lp in lows], [lp.z for lp in lows], marker="v", s=90,
                    color=C_LOW, edgecolor=SURFACE, linewidth=1.0, zorder=6, label=t("low_point"))
        for lp in lows:
            ax1.annotate(f"PB{lp.id}", (lp.station, lp.z), xytext=(0, -16),
                         textcoords="offset points", ha="center", fontsize=9,
                         color=C_LOW, fontweight="bold")
    fmt = FuncFormatter(lambda v, _: format_k(v))
    ax1.xaxis.set_major_formatter(fmt)
    ax1.set_ylabel(t("ylabel_elev"), color=INK2)
    ax1.set_title(title or t("lowpts_title"), loc="left", color=INK, fontsize=13,
                  fontweight="bold")
    handles, labels = ax1.get_legend_handles_labels()
    if n_ponds:
        handles.append(Patch(facecolor=C_WATER, edgecolor=C_WATER_EDGE, alpha=0.6))
        labels.append(t("water"))
    ax1.legend(handles, labels, frameon=False, loc="best", fontsize=9, labelcolor=INK2)
    lo_all = [float(np.min(z))] + ([float(np.min(ideal.z))] if ideal is not None else [])
    hi_all = [float(np.max(z))] + ([float(np.max(ideal.z))] if ideal is not None else [])
    ymin, ymax = min(lo_all), max(hi_all)
    pad = max((ymax - ymin) * 0.12, 0.01)
    ax1.set_ylim(ymin - pad, ymax + pad)

    if lows:
        pos = np.arange(len(lows))
        adj = [lp.depth_adjacent for lp in lows]
        cre = [lp.depth_crest if lp.depth_crest is not None else 0.0 for lp in lows]
        wd = 0.26
        b1 = ax2.bar(pos - wd / 2, adj, wd, color=C_MAIN, label=t("depth_adj"))
        b2 = ax2.bar(pos + wd / 2, cre, wd, color=C_SERIES[0], label=t("depth_crest"))
        for bars in (b1, b2):
            for r in bars:
                ax2.annotate(f"{r.get_height():.3f}", (r.get_x() + r.get_width() / 2, r.get_height()),
                             xytext=(0, 3), textcoords="offset points", ha="center",
                             fontsize=8, color=INK2)
        ax2.set_xticks(pos)
        ax2.set_xticklabels([f"PB{lp.id}\n{lp.label}" for lp in lows], color=INK2, fontsize=9)
        ax2.set_ylabel(t("ylabel_depth"), color=INK2)
        ax2.set_xlim(-0.7, len(lows) - 0.3)
        ax2.set_ylim(0, max(max(adj), max(cre), 0.001) * 1.2)
        ax2.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="lower center",
                   bbox_to_anchor=(0.5, 1.02), ncol=2)
    else:
        ax2.axis("off")
        ax2.text(0.5, 0.5, t("no_low"), ha="center", va="center", color=INK2, fontsize=11,
                 transform=ax2.transAxes)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.94, bottom=0.09, hspace=0.35)
    return fig


# ------------------------------------------------------------------------- output
def save_figures(figs: Sequence[Figure], out_dir, stem: str, formats=("png", "pdf"),
                 dpi: int = 150) -> list:
    """Save one figure or a list of pages; returns the written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    figs = list(figs)
    if "png" in formats:
        for i, f in enumerate(figs, start=1):
            name = f"{stem}.png" if len(figs) == 1 else f"{stem}_p{i:02d}.png"
            f.savefig(out_dir / name, dpi=dpi, facecolor=SURFACE)
            written.append(out_dir / name)
    if "pdf" in formats:
        with PdfPages(out_dir / f"{stem}.pdf") as pdf:
            for f in figs:
                pdf.savefig(f, facecolor=SURFACE)
        written.append(out_dir / f"{stem}.pdf")
    return written
