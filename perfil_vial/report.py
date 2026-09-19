"""Text / CSV summary of the low points."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Sequence

from .geometry import Scale
from .i18n import msg
from .ideal import IdealProfile
from .lowpoints import LowPoint, Pond
from .parsing import Survey
from .profile import Series


def _f(v, nd=3, signed=False):
    if v is None:
        return "-"
    return f"{v:+.{nd}f}" if signed else f"{v:.{nd}f}"


def low_points_rows(lows: Sequence[LowPoint], ponds: Sequence[Pond] = ()) -> list:
    """Dictionaries with one entry per low point (used for the CSV)."""
    by_id = {pd.lp_id: pd for pd in ponds}
    rows = []
    for lp in lows:
        pd = by_id.get(lp.id)
        rows.append({
            "id": f"PB{lp.id}",
            "station": lp.label,
            "station_m": f"{lp.station:.3f}",
            "end_station": lp.end_label,
            "n_stations": lp.n_stations,
            "elevation_m": f"{lp.z:.3f}",
            "prev_station": lp.prev_label or "",
            "prev_elevation_m": _f(lp.prev_z) if lp.prev_z is not None else "",
            "next_station": lp.next_label or "",
            "next_elevation_m": _f(lp.next_z) if lp.next_z is not None else "",
            "depth_prev_m": _f(lp.depth_prev) if lp.depth_prev is not None else "",
            "depth_next_m": _f(lp.depth_next) if lp.depth_next is not None else "",
            "depth_adjacent_m": f"{lp.depth_adjacent:.3f}",
            "depth_mean_m": f"{lp.depth_mean:.3f}",
            "depth_to_spill_m": _f(lp.depth_crest) if lp.depth_crest is not None else "",
            "grade_in_pct": _f(lp.grade_in, 2, True) if lp.grade_in is not None else "",
            "grade_out_pct": _f(lp.grade_out, 2, True) if lp.grade_out is not None else "",
            "boundary": "yes" if lp.is_boundary else "no",
            "water_level_m": f"{pd.level:.3f}" if pd else "",
            "water_depth_m": f"{pd.depth:.3f}" if pd else "",
            "pond_length_m": f"{pd.length:.1f}" if pd else "",
            "pond_area_m2": f"{pd.area:.2f}" if pd else "",
        })
    return rows


def write_low_points_csv(path, lows: Sequence[LowPoint], ponds: Sequence[Pond] = ()) -> None:
    rows = low_points_rows(lows, ponds)
    fields = list(rows[0].keys()) if rows else [
        "id", "station", "station_m", "end_station", "n_stations", "elevation_m",
        "prev_station", "prev_elevation_m", "next_station", "next_elevation_m",
        "depth_prev_m", "depth_next_m", "depth_adjacent_m", "depth_mean_m",
        "depth_to_spill_m", "grade_in_pct", "grade_out_pct", "boundary",
        "water_level_m", "water_depth_m", "pond_length_m", "pond_area_m2"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_ideal_csv(path, ideal: IdealProfile, labels: Sequence[str]) -> None:
    """Real vs ideal elevation per station; diff = ideal - real (+ fill, - cut)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["station", "station_m", "real_elevation_m", "ideal_elevation_m",
                    "diff_m"])
        for lab, d, zr, zi in zip(labels, ideal.dist, ideal.real, ideal.z):
            w.writerow([lab, f"{d:.3f}", f"{zr:.3f}", f"{zi:.3f}", f"{zi - zr:+.3f}"])


def write_section_minima_csv(path, minima: Sequence[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["station", "station_m", "lowest_point", "offset_m", "elevation_m",
                    "below_axis_m"])
        for m in minima:
            w.writerow([m["label"], f"{m['station']:.3f}", m["name"], f"{m['offset']:.2f}",
                        f"{m['z']:.3f}",
                        "" if m["below_axis"] is None else f"{m['below_axis']:.3f}"])


def build_report(
    *,
    main: Series,
    lows: Sequence[LowPoint],
    scale: Scale,
    survey: Survey,
    warnings: Sequence[str],
    min_depth: float,
    include_ends: bool,
    files: Sequence[str] = (),
    lang: str = "es",
    ideal: Optional[IdealProfile] = None,
    ponds: Sequence[Pond] = (),
    sides: Sequence[str] = (),
) -> str:
    """Human-readable summary of the analysis."""
    t = lambda k, **kw: msg(lang, k, **kw)  # noqa: E731
    z, labels = main.z, main.labels
    i_min, i_max = int(z.argmin()), int(z.argmax())
    length = float(main.stations[-1] - main.stations[0])
    bar = "=" * 78
    L = [bar, t("r_title"), bar, ""]
    L.append(f"{t('r_file'):<28}: {survey.source or t('r_na')}")
    L.append(f"{t('r_line'):<28}: {main.name}")
    L.append(f"{t('r_stations'):<28}: {len(z)}  ({labels[0]} - {labels[-1]})")
    L.append(f"{t('r_length'):<28}: {length:.1f} m")
    if sides:
        L.append(f"{t('r_sides'):<28}: {', '.join(sides)}")
    L.append("")
    L.append(t("r_params"))
    L.append(f"  {t('r_min_depth'):<26}: {min_depth:.3f} m")
    L.append(f"  {t('r_ends'):<26}: {t('r_yes') if include_ends else t('r_no')}")
    L.append("")
    L.append(t("r_scale"))
    L.append(f"  {t('r_vexag'):<26}: x{scale.v_exag:.2f}")
    L.append(f"  {t('r_step'):<26}: {scale.step:g} m")
    L.append(f"  {t('r_ref'):<26}: {scale.ref_z:.3f} / {scale.top_z:.3f} m")
    L.append(f"  {t('r_zrange'):<26}: {scale.zmin:.3f} - {scale.zmax:.3f} m")
    L.append("")
    L.append(f"{t('r_lowest')}: {z[i_min]:.3f} m  @ {labels[i_min]}")
    L.append(f"{t('r_highest')}: {z[i_max]:.3f} m  @ {labels[i_max]}")
    L.append("")
    L.append(f"{t('r_found')}: {len(lows)}")
    L.append("-" * 78)
    if not lows:
        L.append(t("r_none"))
    else:
        hdr = t("r_cols").split("|")
        table = []
        for lp in lows:
            st = lp.label + (f"(->{lp.end_label})" if lp.n_stations > 1 else "")
            prev = f"{lp.prev_label} {lp.prev_z:.3f}" if lp.prev_z is not None else "-"
            nxt = f"{lp.next_label} {lp.next_z:.3f}" if lp.next_z is not None else "-"
            star = "*" if lp.is_boundary else ""
            table.append([f"PB{lp.id}{star}", st, f"{lp.z:.3f}", prev, nxt,
                          f"{lp.depth_adjacent:.3f}", _f(lp.depth_crest),
                          _f(lp.grade_in, 2, True), _f(lp.grade_out, 2, True)])
        widths = [max(len(h), *(len(r[i]) for r in table)) + 2 for i, h in enumerate(hdr)]
        L.append("".join(h.ljust(w) for h, w in zip(hdr, widths)).rstrip())
        for r in table:
            L.append("".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
        L.append("")
        L.append(t("r_note_depth"))
        if any(lp.n_stations > 1 for lp in lows):
            L.append(t("r_note_plateau"))
        if any(lp.is_boundary for lp in lows):
            L.append(t("r_note_boundary"))
        with_crest = [lp for lp in lows if lp.depth_crest is not None]
        if with_crest:
            dp = max(with_crest, key=lambda p: p.depth_crest)
            L.append("")
            L.append(f"{t('r_deepest')}: PB{dp.id} @ {dp.label}  "
                     f"z = {dp.z:.3f} m, {dp.depth_crest:.3f} m")
    if ponds:
        L.append("")
        L.append(t("r_ponds"))
        L.append("-" * 78)
        hdr = t("r_pond_cols").split("|")
        rows = [[f"PB{pd.lp_id}", f"{pd.level:.3f}", f"{pd.depth:.3f}", f"{pd.length:.1f}",
                 f"{pd.area:.2f}", t("water_full") if pd.full else t("water_part")]
                for pd in ponds]
        widths = [max(len(h), *(len(r[i]) for r in rows)) + 2 for i, h in enumerate(hdr)]
        L.append("".join(h.ljust(w) for h, w in zip(hdr, widths)).rstrip())
        L.extend("".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)
        L.append(t("r_pond_note"))
    if ideal is not None:
        trend = {"down": t("r_trend_down"), "up": t("r_trend_up")}.get(
            ideal.trend, t("r_trend_crest", label=labels[ideal.crest_index or 0]))
        L.append("")
        L.append(t("r_ideal"))
        L.append("-" * 78)
        L.append(f"  {t('r_trend'):<40}: {trend}")
        L.append(f"  {t('r_ideal_grade'):<40}: {ideal.min_grade * 100:.2f} %")
        L.append(f"  {t('r_ideal_mean'):<40}: {ideal.mean_grade * 100:.2f} %")
        L.append(f"  {t('r_ideal_fill'):<40}: {ideal.max_fill:.3f} m")
        L.append(f"  {t('r_ideal_cut'):<40}: {ideal.max_cut:.3f} m")
        L.append(f"  {t('r_ideal_rms'):<40}: {ideal.rms:.3f} m")
        L.append(t("r_ideal_note"))
    L.append("")
    L.append(t("r_validation"))
    L.append("-" * 78)
    L.append(f"{t('r_rows')}: {len(survey.sections)}")
    if warnings:
        L.extend(f"  ! {w}" for w in warnings)
    else:
        L.append(t("r_no_warn"))
    L.append(f"{t('r_sections_min')}: {t('r_sections_min_file')}")
    if files:
        L.append("")
        L.append(t("r_files"))
        L.append("-" * 78)
        L.extend(f"  {Path(f).name}" for f in files)
    return "\n".join(L) + "\n"
