"""Command-line entry point: ``python -m perfil_vial datos.csv -o salida``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .i18n import msg
from .ideal import compute_ideal_profile
from .lowpoints import find_low_points, ponding_region
from .parsing import (
    SurveyError, parse_station, read_extra_points, read_survey, token_to_real,
    validate_stations, DEFAULT_SEP, MAX_POINTS,
)
from .plotting import plot_long_profile, plot_low_points, plot_sections, save_figures
from .profile import Series, extract_series, lowest_in_section, normalize_name, resolve_side_lines
from .report import (
    build_report, write_ideal_csv, write_low_points_csv, write_section_minima_csv,
)

MAX_LINES = 6   # side lines + extra lines drawn on the profile besides the reference


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="perfil_vial",
        description=(
            "Longitudinal profile, cross-sections and low points from a CSV of "
            "transversal road surveys (one row per station)."
        ),
    )
    p.add_argument("csv", help="input CSV: station + elevations across the road")
    p.add_argument("-o", "--out", default="salida_perfil", help="output folder")
    p.add_argument("--line", default="EJE",
                   help="reference line for the longitudinal profile: EJE (default), "
                        "'BV IZQ', 'SAR DER', ... or MIN (lowest point of each section)")
    p.add_argument("--sides", default="auto",
                   help="left and right road-side lines drawn on the profile: 'auto' "
                        "(default: BV IZQ / BV DER, else the outermost points), 'none', "
                        "or 'LEFT,RIGHT' (e.g. 'SAR IZQ,SAR DER')")
    p.add_argument("--extra-lines", default="",
                   help="comma-separated extra lines drawn on the profile, e.g. "
                        "'PAR IZQ,PAR DER' (at most 6 lines in total with --sides)")
    p.add_argument("--no-ideal", action="store_true",
                   help="do not compute/draw the ideal (sag-free) line")
    p.add_argument("--ideal-min-grade", type=float, default=None, metavar="PCT",
                   help="minimum longitudinal grade of the ideal line, in %% "
                        "(default: automatic, at most 0.5)")
    p.add_argument("--ideal-monotone", action="store_true",
                   help="force the ideal line to be monotone (no crest)")
    p.add_argument("--no-water", action="store_true",
                   help="do not paint the ponded water at the low points")
    p.add_argument("--water-depth", type=float, default=None, metavar="D",
                   help="maximum water depth drawn at each low point, m "
                        "(default: up to the spill level)")
    p.add_argument("--points", help="CSV with additional points: COTA, DESCRIPCION, ABSCISA")
    p.add_argument("--sep", type=float, default=DEFAULT_SEP,
                   help="uniform horizontal distance between section points, m (default 2.0)")
    p.add_argument("--spacings",
                   help="distances between consecutive section points, comma separated "
                        "(manual mode; zero at EJE). Overrides --sep")
    p.add_argument("--max-points", type=int, default=MAX_POINTS,
                   help="maximum elevations per section (default 8, as SECCIONTN)")
    p.add_argument("--select", default="all",
                   help="sections to draw: 'all' or a comma-separated list of stations")
    p.add_argument("--every", type=int, default=1, help="draw one section every N")
    p.add_argument("--cols", type=int, default=3, help="sections per row (default 3)")
    p.add_argument("--per-page", type=int, default=6, help="sections per sheet (default 6)")
    p.add_argument("--min-depth", type=float, default=0.0,
                   help="ignore low points shallower than this many metres (default 0)")
    p.add_argument("--include-ends", action="store_true",
                   help="also report the first/last station when it is a local minimum")
    p.add_argument("--sort", action="store_true",
                   help="sort sections by station instead of requiring increasing order")
    p.add_argument("--title", help="title of the longitudinal profile")
    p.add_argument("--lang", choices=("es", "en"), default="es")
    p.add_argument("--delimiter", help="CSV delimiter (auto-detected by default)")
    p.add_argument("--formats", default="png,pdf", help="png,pdf (default both)")
    p.add_argument("--dpi", type=int, default=150)
    return p


def _float_list(text: str, what: str) -> list:
    out = []
    for tok in text.split(","):
        v = token_to_real(tok)
        if v is None or v <= 0.0:
            raise SurveyError(f"{what}: invalid value '{tok.strip()}'")
        out.append(v)
    return out


def run(argv=None) -> int:
    args = _parser().parse_args(argv)
    lang = args.lang
    out_dir = Path(args.out)
    formats = tuple(f.strip().lower() for f in args.formats.split(",") if f.strip())

    try:
        spacings = _float_list(args.spacings, "--spacings") if args.spacings else None
        survey = read_survey(args.csv, sep=args.sep, spacings=spacings,
                             delimiter=args.delimiter, max_points=args.max_points, lang=lang)
        warnings = list(survey.warnings)
        sections = validate_stations(survey.sections, sort=args.sort, lang=lang)

        # 1) longitudinal series ------------------------------------------------
        main = extract_series(sections, args.line, warnings=warnings, lang=lang)
        sides = resolve_side_lines(sections, args.sides, exclude=[main.name],
                                   warnings=warnings, lang=lang)
        taken = {normalize_name(main.name)} | {normalize_name(x.name) for x in sides}
        extras = list(sides)
        for n in (n.strip() for n in args.extra_lines.split(",")):
            if n and normalize_name(n) not in taken:
                taken.add(normalize_name(n))
                extras.append(extract_series(sections, n, warnings=warnings, lang=lang))
        if len(extras) > MAX_LINES:
            raise SurveyError(msg(lang, "e_lines_limit", n=MAX_LINES, got=len(extras)))
        points = read_extra_points(args.points, lang=lang) if args.points else []

        # 3) low points ---------------------------------------------------------
        lows = find_low_points(main.stations, main.z, main.labels, min_depth=args.min_depth,
                               include_ends=args.include_ends)
        low_ids = {round(lp.station, 6): lp.id for lp in lows}
        if args.water_depth is not None and args.water_depth <= 0:
            raise SurveyError("--water-depth: value must be > 0")
        water = not args.no_water
        ponds = [pd for pd in (ponding_region(main.stations, main.z, lp, args.water_depth)
                               for lp in lows) if pd is not None]

        # ideal line (sag-free reference) ----------------------------------------
        ideal_prof = ideal = None
        if not args.no_ideal:
            if len(main) < 2:
                warnings.append(msg(lang, "w_no_ideal"))
            else:
                grade = None if args.ideal_min_grade is None else args.ideal_min_grade / 100.0
                ideal_prof = compute_ideal_profile(main.stations, main.z, min_grade=grade,
                                                   allow_crest=not args.ideal_monotone)
                ideal = Series(name="IDEAL", stations=main.stations, labels=list(main.labels),
                               z=ideal_prof.z, interpolated=[False] * len(main), role="ideal")

        # 2) drawings -----------------------------------------------------------
        # one longitudinal sheet per road side (left / right); all other lines and data
        # are repeated on each sheet and both share the same vertical scale.  Without
        # side lines there is a single sheet, as before.
        base_title = args.title or msg(lang, "profile_title")
        others = [x for x in extras if x.role not in ("left", "right")]
        sheets = [(x, "perfil_longitudinal_" + ("izquierdo" if x.role == "left" else "derecho"),
                   f"{base_title} - {msg(lang, 'title_left' if x.role == 'left' else 'title_right')}")
                  for x in extras if x.role in ("left", "right")]
        files = []
        scale = None
        if sheets:
            for side, stem, title in sheets:
                fig_lp, scale = plot_long_profile(
                    main, [side] + others, points, lows, ideal=ideal, water=water,
                    water_depth=args.water_depth, scale_extras=extras, title=title, lang=lang)
                files += save_figures([fig_lp], out_dir, stem, formats, args.dpi)
        else:
            fig_lp, scale = plot_long_profile(main, extras, points, lows, ideal=ideal,
                                              water=water, water_depth=args.water_depth,
                                              title=args.title, lang=lang)
            files += save_figures([fig_lp], out_dir, "perfil_longitudinal", formats, args.dpi)

        chosen = _select_sections(sections, args.select, args.every, warnings, lang)
        figs_sec = plot_sections(chosen, cols=args.cols, per_page=args.per_page, lang=lang,
                                 low_ids=low_ids)
        files += save_figures(figs_sec, out_dir, "secciones", formats, args.dpi)

        fig_low = plot_low_points(main, lows, ideal=ideal, water=water,
                                 water_depth=args.water_depth, lang=lang)
        files += save_figures([fig_low], out_dir, "puntos_bajos", ("png",), args.dpi)

        # 4) report -------------------------------------------------------------
        write_low_points_csv(out_dir / "puntos_bajos.csv", lows, ponds)
        write_section_minima_csv(out_dir / "secciones_minimos.csv",
                                 [lowest_in_section(s) for s in sections])
        files += [out_dir / "puntos_bajos.csv", out_dir / "secciones_minimos.csv"]
        if ideal_prof is not None:
            write_ideal_csv(out_dir / "perfil_ideal.csv", ideal_prof, main.labels)
            files.append(out_dir / "perfil_ideal.csv")
        report_path = out_dir / "informe_puntos_bajos.txt"
        files.append(report_path)
        report = build_report(main=main, lows=lows, scale=scale, survey=survey,
                              warnings=warnings, min_depth=args.min_depth,
                              include_ends=args.include_ends, files=files, lang=lang,
                              ideal=ideal_prof, ponds=ponds,
                              sides=[x.name for x in sides])
        report_path.write_text(report, encoding="utf-8")
    except (SurveyError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(report)
    return 0


def _select_sections(sections, select: str, every: int, warnings: list, lang: str) -> list:
    chosen = list(sections)
    if select.strip().lower() != "all":
        wanted = []
        by_station = {round(s.station, 6): s for s in sections}
        for tok in select.split(","):
            d = parse_station(tok)
            sec = by_station.get(round(d, 6)) if d is not None else None
            if sec is None:
                warnings.append(msg(lang, "w_select_missing", tok=tok.strip()))
            else:
                wanted.append(sec)
        chosen = sorted(wanted, key=lambda s: s.station)
    if every and every > 1:
        chosen = chosen[::every]
    return chosen


def main() -> None:  # pragma: no cover
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
