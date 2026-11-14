"""CSV reading and validation.

Ports the parsing/validation helpers of the two AutoLISP programs:

==========================================  ======================================
AutoLISP                                    Python
==========================================  ======================================
PF:TokenToReal / SC:TokenToReal             :func:`token_to_real`
PF:NormalizeKLabel / PF:ValidKLabel         :func:`normalize_k_label`, :func:`valid_k_label`
PF:ParseKToDist                             :func:`parse_k_to_dist`
PF:FormatK                                  :func:`format_k`
PF:BuildOffsetsFromKLabels                  station - first station (see plotting)
PF:StrictIncreasingP                        :func:`validate_stations`
SC:LabelByCol                               :func:`default_label_by_col`
SC:ExtractSectionFromRow                    :func:`parse_survey_text` (per row)
SC:AutoXValsFromCols                        auto offsets ``(col - ref_col) * sep``
SC:ManualXVals                              ``spacings`` option (zero at EJE)
==========================================  ======================================

CSV layout (one row = one cross-section)::

    Abscisa,PAR,SAR,BV,EJE,BV,SAR,PAR
    K0+000,100.212,100.254,100.301,100.352,100.301,100.254,100.212
    K0+020,...

* First column: station, either a K-label (``K0+005``, ``0+005``) or a numeric
  distance in metres.
* Remaining columns: elevations, ordered left -> right across the road.
* Header (optional): a text cell names the point (``EJE``, ``BV``, ``SAR``...);
  a numeric cell gives the transversal offset in metres.  Without a header the
  labels come from the column index exactly as in ``SC:LabelByCol``
  (PAR, SAR, BV, EJE, BV, SAR, PAR, P8).
* Empty cells are allowed (the column index is kept, as in the LISP).
* ``,`` ``;`` or tab delimiters are auto-detected; a decimal comma is accepted
  (``TokenToReal``) when the delimiter is ``;`` or tab.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from .i18n import msg

MIN_POINTS = 2        # SC:ExtractSectionFromRow: at least 2 elevations ...
MAX_POINTS = 8        # ... and at most 8
DEFAULT_SEP = 2.0     # "Distancia horizontal uniforme entre puntos <2.0>"
DEFAULT_REF_COL = 3   # column 3 (EJE) is the origin of the auto offsets

_NUM_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_K_RE = re.compile(r"^K(\d+)\+(\d+(?:\.\d+)?)$")
_KNOPREFIX_RE = re.compile(r"^\d+\+\d+(?:\.\d+)?$")


class SurveyError(ValueError):
    """Fatal data problem (the LISP prints a message and aborts)."""


# --------------------------------------------------------------------------- numbers
def token_to_real(tok) -> Optional[float]:
    """PF:TokenToReal: text -> float, accepting a decimal comma; ``None`` if invalid."""
    if tok is None:
        return None
    tok = str(tok).strip()
    if not tok:
        return None
    if "." not in tok and "," in tok:
        tok = tok.replace(",", ".")
    if not _NUM_RE.match(tok):
        return None
    return float(tok)


# ------------------------------------------------------------------------- K-labels
def normalize_k_label(s) -> str:
    """PF:NormalizeKLabel: upper-case and drop every blank."""
    return re.sub(r"\s+", "", str(s if s is not None else "")).upper()


def valid_k_label(s) -> bool:
    """PF:ValidKLabel: ``K<digits>+<digits>`` (meters may carry decimals here)."""
    return _K_RE.match(normalize_k_label(s)) is not None


def parse_k_to_dist(s) -> Optional[float]:
    """PF:ParseKToDist: ``K1+230`` -> 1230.0 (None if not a valid K-label)."""
    m = _K_RE.match(normalize_k_label(s))
    if not m:
        return None
    return 1000.0 * int(m.group(1)) + float(m.group(2))


def format_k(dist: float) -> str:
    """PF:FormatK: 1230.0 -> ``K1+230`` (rounded to whole metres)."""
    sgn = ""
    if dist < 0.0:
        sgn = "-"
        dist = abs(dist)
    d = math.floor(dist + 0.5)
    km = d // 1000
    mts = d - km * 1000
    return f"{sgn}K{km}+{mts:03d}"


def parse_station(tok) -> Optional[float]:
    """Station cell -> distance in metres, or ``None``.

    Accepts a K-label (``K0+005``), a K-label without the ``K`` (``0+005``) or a
    plain non-negative distance (``5`` / ``5,5``).
    """
    txt = str(tok if tok is not None else "").strip()
    d = parse_k_to_dist(txt)
    if d is not None:
        return d
    norm = normalize_k_label(txt)
    if _KNOPREFIX_RE.match(norm):
        return parse_k_to_dist("K" + norm)
    val = token_to_real(txt)
    if val is not None and val >= 0.0:
        return val
    return None


def station_label(tok, dist: float) -> str:
    """Label shown on the drawing: the K-label as typed, else ``format_k``."""
    if valid_k_label(tok):
        return normalize_k_label(tok)
    return format_k(dist)


def default_label_by_col(idx: int) -> str:
    """SC:LabelByCol."""
    table = ("PAR", "SAR", "BV", "EJE", "BV", "SAR", "PAR")
    return table[idx] if 0 <= idx < len(table) else f"P{idx + 1}"


# --------------------------------------------------------------------------- model
@dataclass
class Section:
    """One transversal section (one CSV row)."""

    label: str                 # station as displayed (K0+020)
    station: float             # absolute distance along the axis (m)
    offsets: list              # transversal offsets, EJE = 0 (m), increasing
    elevations: list
    descs: list                # raw point labels: EJE, BV, SAR, PAR ...
    cols: list                 # source column indices (0 = first elevation column)
    row: int                   # 1-based line number in the CSV
    names: list = field(default_factory=list)  # side-qualified: "BV IZQ", "EJE"...

    def __post_init__(self) -> None:
        if not self.names:
            self.names = _side_names(self.descs, self.offsets)

    def index_of(self, desc: str) -> Optional[int]:
        for i, d in enumerate(self.descs):
            if d == desc:
                return i
        return None


def _side_names(descs: Sequence[str], offsets: Sequence[float]) -> list:
    """Qualify repeated labels with IZQ/DER (SC:PointPromptName)."""
    eje = next((i for i, d in enumerate(descs) if d.upper() == "EJE"), None)
    out = []
    for i, (d, x) in enumerate(zip(descs, offsets)):
        du = d.upper()
        if du == "EJE":
            out.append("EJE")
            continue
        if eje is not None:
            side = "IZQ" if i < eje else "DER"
        else:
            side = "IZQ" if x < 0 else ("DER" if x > 0 else "")
        out.append(f"{du} {side}".strip())
    return out


@dataclass
class Survey:
    sections: list
    warnings: list
    delimiter: str
    has_header: bool
    source: str = ""


# ------------------------------------------------------------------------- reading
def sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:25])
    if ";" in sample:
        return ";"
    if "\t" in sample:
        return "\t"
    return ","


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_survey(path, **kw) -> Survey:
    """Read ``path`` (see :func:`parse_survey_text` for the keyword options)."""
    p = Path(path)
    survey = parse_survey_text(_read_text(p), **kw)
    survey.source = str(p)
    return survey


def _is_header(cells: Sequence[str]) -> bool:
    """First row is a header when its first cell is not a station."""
    first = cells[0].strip() if cells else ""
    if parse_station(first) is not None:
        return False
    if not re.search(r"\d", first):
        return True
    rest = [c.strip() for c in cells[1:] if c.strip()]
    return any(token_to_real(c) is None for c in rest)


def _cum_offsets(spacings: Sequence[float]) -> list:
    """SC:BuildCumOffsets."""
    out, acc = [0.0], 0.0
    for d in spacings:
        acc += d
        out.append(acc)
    return out


def parse_survey_text(
    text: str,
    *,
    sep: float = DEFAULT_SEP,
    spacings: Optional[Sequence[float]] = None,
    delimiter: Optional[str] = None,
    max_points: int = MAX_POINTS,
    lang: str = "es",
) -> Survey:
    """Parse the CSV text into validated :class:`Section` objects.

    Transversal offsets are resolved in this order (per section):

    1. numeric header cells (``-6,-4,-2,0,2,4,6``) -> used as they are;
    2. ``spacings`` (distances between consecutive points, as the "Manuales"
       option of SECCIONTN), zero placed at the EJE point;
    3. otherwise the uniform separation ``sep`` ("Automaticas"):
       ``x = (col - ref_col) * sep`` where ``ref_col`` is the EJE column of the
       header; with a header but no EJE, the middle of the labelled columns;
       with no header at all, column 3 (as SC:AutoXValsFromCols).
    """
    if sep is None or sep <= 0.0:
        sep = DEFAULT_SEP
    delim = delimiter or sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)

    rows = []
    for cells in reader:
        if not any(c.strip() for c in cells):
            continue
        rows.append((reader.line_num, [c.strip() for c in cells]))

    warnings: list = []
    col_labels: dict = {}
    col_offsets: dict = {}
    has_header = False
    if rows and _is_header(rows[0][1]):
        has_header = True
        for i, cell in enumerate(rows[0][1][1:]):
            if not cell:
                continue
            v = token_to_real(cell)
            if v is not None:
                col_offsets[i] = v
            else:
                col_labels[i] = re.sub(r"\s+", " ", cell).upper()
        rows = rows[1:]

    ref_col = next((i for i in sorted(col_labels) if col_labels[i] == "EJE"), None)
    if ref_col is None:
        if col_labels:
            # header names the points but has no EJE: centre the offsets on the labelled columns
            ref_col = (min(col_labels) + max(col_labels)) / 2.0
        else:
            ref_col = DEFAULT_REF_COL     # no header: column 3 is EJE (SC:AutoXValsFromCols)

    sections: list = []
    for line_no, cells in rows:
        st_tok = cells[0]
        dist = parse_station(st_tok)
        if dist is None:
            warnings.append(msg(lang, "w_skip_station", row=line_no, tok=st_tok))
            continue
        label = station_label(st_tok, dist)

        cols, vals, stray = [], [], []
        for i, cell in enumerate(cells[1:]):
            v = token_to_real(cell)
            if v is not None:
                cols.append(i)
                vals.append(v)
            elif cell:
                stray.append(cell)
        if stray:
            warnings.append(msg(lang, "w_stray", row=line_no, label=label, cells=", ".join(stray)))
        if not (MIN_POINTS <= len(vals) <= max_points):
            warnings.append(
                msg(lang, "w_skip_count", row=line_no, label=label, n=len(vals),
                    lo=MIN_POINTS, hi=max_points)
            )
            continue

        descs = [col_labels.get(c) or default_label_by_col(c) for c in cols]

        if col_offsets and all(c in col_offsets for c in cols):
            offsets = [col_offsets[c] for c in cols]
        else:
            if col_offsets:
                warnings.append(msg(lang, "w_offsets_partial", row=line_no, label=label))
            if spacings:
                if len(spacings) != len(cols) - 1:
                    warnings.append(
                        msg(lang, "w_spacings_len", row=line_no, label=label,
                            exp=len(cols) - 1, got=len(spacings))
                    )
                    continue
                cum = _cum_offsets(spacings)
                # SC:ManualXVals: zero at EJE; else at column 3; else unshifted
                zero_at = next((i for i, d in enumerate(descs) if d == "EJE"), None)
                if zero_at is None and DEFAULT_REF_COL in cols:
                    zero_at = cols.index(DEFAULT_REF_COL)
                shift = cum[zero_at] if zero_at is not None else 0.0
                offsets = [c - shift for c in cum]
            else:
                offsets = [(c - ref_col) * sep for c in cols]

        if any(b <= a for a, b in zip(offsets, offsets[1:])):
            warnings.append(msg(lang, "w_offsets_order", row=line_no, label=label))
            continue

        sections.append(
            Section(label=label, station=dist, offsets=offsets, elevations=vals,
                    descs=descs, cols=cols, row=line_no)
        )

    if not sections:
        raise SurveyError(msg(lang, "e_no_sections", lo=MIN_POINTS, hi=max_points))
    return Survey(sections=sections, warnings=warnings, delimiter=delim, has_header=has_header)


# --------------------------------------------------------------------- validation
def validate_stations(sections: Sequence[Section], *, sort: bool = False, lang: str = "es") -> list:
    """PF:StrictIncreasingP for the longitudinal axis.

    Stations must be unique and strictly increasing in file order.  With
    ``sort=True`` the sections are sorted first (duplicates are still an error).
    """
    secs = list(sections)
    seen: dict = {}
    for s in secs:
        seen.setdefault(round(s.station, 6), []).append(s)
    for group in seen.values():
        if len(group) > 1:
            raise SurveyError(
                msg(lang, "e_duplicate", label=group[0].label,
                    rows=", ".join(str(g.row) for g in group))
            )
    if sort:
        secs.sort(key=lambda s: s.station)
    else:
        for prev, cur in zip(secs, secs[1:]):
            if cur.station <= prev.station:
                raise SurveyError(
                    msg(lang, "e_order", row=cur.row, label=cur.label, prev=prev.label)
                )
    if len(secs) < 2:
        raise SurveyError(msg(lang, "e_min_stations"))
    return secs


@dataclass
class ExtraPoint:
    """Additional annotated point (COTA | DESCRIPCION | ABSCISA)."""

    z: float
    desc: str
    station: float


def read_extra_points(path, *, lang: str = "es") -> list:
    """Read the ``COTA, DESCRIPCION, ABSCISA`` rows used by PERFILTN for extra points."""
    text = _read_text(Path(path))
    delim = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    out = []
    for cells in reader:
        cells = [c.strip() for c in cells]
        if not any(cells):
            continue
        n = reader.line_num
        # skip a header row (non numeric cota)
        if n == 1 and token_to_real(cells[0]) is None:
            continue
        if len(cells) < 3:
            raise SurveyError(msg(lang, "e_points_row", row=n))
        z = token_to_real(cells[0])
        st = parse_station(cells[-1])
        if z is None or st is None:
            raise SurveyError(msg(lang, "e_points_row", row=n))
        desc = " ".join(c for c in cells[1:-1] if c) or "PUNTO"
        out.append(ExtraPoint(z=z, desc=desc, station=st))
    return out
