"""Longitudinal series extracted from the cross-sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .i18n import msg
from .parsing import Section, SurveyError


@dataclass
class Series:
    """One elevation-versus-station line (e.g. the centerline)."""

    name: str
    stations: np.ndarray      # absolute distance (m)
    labels: list              # K-labels as displayed
    z: np.ndarray
    interpolated: list
    role: str = ""            # "", "left", "right", "ideal": how the plots label the line

    def __len__(self) -> int:
        return len(self.z)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip()).upper()


def _at_axis(sec: Section):
    """Elevation at offset 0 by linear interpolation, or None if 0 is outside."""
    x = sec.offsets
    if x[0] <= 0.0 <= x[-1]:
        return float(np.interp(0.0, x, sec.elevations))
    return None


def extract_series(
    sections: Sequence[Section],
    name: str = "EJE",
    *,
    warnings: list | None = None,
    lang: str = "es",
) -> Series:
    """Pick one point of every section to build a longitudinal series.

    ``name`` is a point label (``EJE``), a side-qualified label (``BV IZQ``,
    ``SAR DER``), ``MIN`` (lowest point of each section) or ``EXT IZQ`` /
    ``EXT DER`` (left-most / right-most surveyed point of each section).  When a section has
    no ``EJE`` point (e.g. only ``BV, BV``) the value is interpolated at offset
    0, which is the centerline by construction.
    """
    warnings = warnings if warnings is not None else []
    norm = normalize_name(name)
    stations, labels, zs, interp = [], [], [], []
    n_interp = 0

    for sec in sections:
        z = None
        was_interp = False
        if norm == "MIN":
            z = min(sec.elevations)
        elif norm in ("EXT IZQ", "EXT DER"):
            z = sec.elevations[0] if norm == "EXT IZQ" else sec.elevations[-1]
        else:
            idx = [i for i, n in enumerate(sec.names) if n == norm]
            if not idx:  # plain family name such as "BV"
                idx = [i for i, d in enumerate(sec.descs) if d == norm]
                if len(idx) > 1:
                    raise SurveyError(msg(lang, "e_ambiguous", name=norm, label=sec.label))
            if idx:
                z = sec.elevations[idx[0]]
            elif norm == "EJE":
                z = _at_axis(sec)
                if z is not None:
                    was_interp = True
                    n_interp += 1
            if z is None:
                warnings.append(msg(lang, "w_series_missing", label=sec.label, name=norm))
                continue
        stations.append(sec.station)
        labels.append(sec.label)
        zs.append(float(z))
        interp.append(was_interp)

    if n_interp:
        warnings.append(msg(lang, "w_series_interp", name=norm, n=n_interp))
    if len(zs) < 2:
        raise SurveyError(msg(lang, "e_series_short", name=norm))
    return Series(name=norm, stations=np.asarray(stations, float), labels=labels,
                  z=np.asarray(zs, float), interpolated=interp)


def lowest_in_section(sec: Section) -> dict:
    """Lowest surveyed point of a section (cross-slope low point)."""
    i = min(range(len(sec.elevations)), key=lambda k: sec.elevations[k])
    axis = _at_axis(sec)
    return {
        "label": sec.label,
        "station": sec.station,
        "name": sec.names[i],
        "offset": sec.offsets[i],
        "z": sec.elevations[i],
        "below_axis": (axis - sec.elevations[i]) if axis is not None else None,
        "index": i,
    }


# ------------------------------------------------------------- road sides
SIDE_CANDIDATES = (("BV IZQ", "BV DER"), ("EXT IZQ", "EXT DER"))


def resolve_side_lines(
    sections: Sequence[Section],
    spec: str = "auto",
    *,
    exclude: Sequence[str] = (),
    warnings: list | None = None,
    lang: str = "es",
) -> list:
    """Left and right road-side lines built from the survey cross-sections.

    ``spec``:

    * ``"auto"`` - the road-edge points ``BV IZQ`` / ``BV DER`` when the sections
      have them, otherwise the outermost surveyed point on each side;
    * ``"none"`` - no side lines;
    * ``"<left>,<right>"`` - any two point names, e.g. ``"SAR IZQ,SAR DER"``.

    Names listed in ``exclude`` (e.g. the reference line) are not repeated.
    Returns a list with the left line first, then the right one (roles set).
    """
    warnings = warnings if warnings is not None else []
    key = re.sub(r"\s+", " ", str(spec).strip()).upper()
    if key in ("", "NONE", "NO", "NINGUNO"):
        return []

    if key == "AUTO":
        candidates = list(SIDE_CANDIDATES)
    else:
        parts = [p.strip() for p in str(spec).split(",") if p.strip()]
        if len(parts) != 2:
            raise SurveyError(msg(lang, "e_sides_spec", spec=spec))
        candidates = [(parts[0], parts[1])]

    skip = {normalize_name(n) for n in exclude}
    last_error = None
    for left, right in candidates:
        tmp: list = []
        try:
            lines = []
            for nm, role in ((left, "left"), (right, "right")):
                if normalize_name(nm) in skip:
                    continue
                ser = extract_series(sections, nm, warnings=tmp, lang=lang)
                ser.role = role
                lines.append(ser)
        except SurveyError as exc:              # candidate not usable: try the next one
            last_error = exc
            continue
        warnings.extend(tmp)
        return lines
    if key != "AUTO" and last_error is not None:
        raise last_error
    warnings.append(msg(lang, "w_no_sides"))
    return []
