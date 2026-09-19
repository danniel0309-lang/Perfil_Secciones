"""Tests for perfil_vial (run with ``pytest perfil_vial/tests``)."""

from pathlib import Path

import numpy as np
import pytest

from perfil_vial import (
    SurveyError, extract_series, find_low_points, format_k, lowest_in_section, nice_step,
    parse_k_to_dist, parse_station, profile_scale, section_scale, token_to_real,
    valid_k_label, validate_stations,
)
from perfil_vial import (
    Pond, compute_ideal_profile, ponding_region, resolve_side_lines,
)
from perfil_vial.cli import run
from perfil_vial.parsing import parse_survey_text

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "secciones_ejemplo.csv"

HEADER = "Abscisa,PAR,SAR,BV,EJE,BV,SAR,PAR\n"


# ----------------------------------------------------------- ported helpers
def test_token_to_real():
    assert token_to_real("12.5") == 12.5
    assert token_to_real(" 12,5 ") == 12.5          # decimal comma (no dot present)
    assert token_to_real("1,234.5") is None         # both separators: LISP distof fails
    assert token_to_real("") is None
    assert token_to_real("abc") is None
    assert token_to_real("nan") is None and token_to_real("1_000") is None


def test_k_labels():
    assert valid_k_label("K0+005") and valid_k_label(" k1 + 230 ")
    assert not valid_k_label("K0") and not valid_k_label("0+005x") and not valid_k_label("")
    assert parse_k_to_dist("K1+230") == 1230.0
    assert parse_k_to_dist("k0+5") == 5.0
    assert parse_k_to_dist("bad") is None
    assert format_k(1230) == "K1+230" and format_k(5) == "K0+005"
    assert format_k(999.6) == "K1+000"               # rounded to whole metres
    assert format_k(-15) == "-K0+015"


def test_parse_station_variants():
    assert parse_station("K0+020") == 20.0
    assert parse_station("0+020") == 20.0
    assert parse_station("35,5") == 35.5
    assert parse_station("-5") is None               # negative distances rejected
    assert parse_station("Abscisa") is None


def test_nice_step():
    assert nice_step(0) == 1.0
    assert nice_step(5.0) == 1.0
    assert nice_step(10.0) == 2.0
    assert nice_step(25.0) == 5.0
    assert nice_step(4.62) == pytest.approx(1.0)
    assert nice_step(0.001) == pytest.approx(0.0002)
    assert nice_step(60.0) == 20.0                    # raw 12 -> frac 1.2 -> 2 * 10
    assert nice_step(0.9) == pytest.approx(0.2)       # raw 0.18 -> frac 1.8 -> 2 * 0.1


def test_profile_scale_matches_lisp_formulas():
    # 400 m profile, elevations 2535.779 .. 2540.421
    sc = profile_scale(400.0, 2535.779, 2540.421)
    assert sc.txt_h == 2.20                           # clamp(400/70, 0.70, 2.20)
    assert sc.target_grid_h == pytest.approx(max(400 * 0.285, sc.txt_h * 18))
    assert sc.v_exag == pytest.approx(sc.target_grid_h / sc.rng)
    assert sc.ref_z == pytest.approx(2535.0) and sc.top_z == pytest.approx(2541.0)
    assert sc.y(sc.ref_z) == 0.0
    assert sc.z_levels()[0] == sc.ref_z and sc.z_levels()[-1] == pytest.approx(sc.top_z)


def test_scale_clamps_and_degenerate_range():
    small = profile_scale(10.0, 100.0, 100.0)         # flat data -> rng floored to 0.001
    assert small.rng == 0.001 and small.txt_h == 0.70
    assert small.top_z > small.ref_z                  # never a zero-height grid
    big = section_scale(500.0, 0.0, 10.0)
    assert big.txt_h == 2.20
    assert section_scale(0.0, 1.0, 2.0).width == 0.001


# ------------------------------------------------------------------- parsing
def test_parse_header_labels_and_auto_offsets():
    text = HEADER + "K0+000,1,2,3,4,3,2,1\nK0+020,1,2,3,4.5,3,2,1\n"
    s = parse_survey_text(text)
    assert s.has_header and len(s.sections) == 2
    sec = s.sections[0]
    assert sec.offsets == [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]
    assert sec.names == ["PAR IZQ", "SAR IZQ", "BV IZQ", "EJE", "BV DER", "SAR DER", "PAR DER"]


def test_parse_without_header_uses_default_labels_and_semicolon_decimal_comma():
    text = "K0+000;10,1;10,2;10,3;10,4;10,3\nK0+020;10,1;10,2;10,3;10,45;10,3\n"
    s = parse_survey_text(text, sep=1.5)
    assert not s.has_header and s.delimiter == ";"
    sec = s.sections[0]
    assert sec.descs == ["PAR", "SAR", "BV", "EJE", "BV"]   # SC:LabelByCol
    assert sec.offsets == [-4.5, -3.0, -1.5, 0.0, 1.5]
    assert sec.elevations[0] == 10.1


def test_row_validation_skips_bad_rows_with_warnings():
    text = HEADER + (
        "K0+000,1,2,3,4,3,2,1\n"
        "BAD,1,2,3,4,3,2,1\n"                 # invalid station
        "K0+040,5,,,,,,\n"                     # only 1 elevation (< 2)
        "K0+060,1,2,x,4,3,2,1\n"               # stray text cell: warn, keep numeric
    )
    s = parse_survey_text(text)
    assert [sec.label for sec in s.sections] == ["K0+000", "K0+060"]
    joined = " ".join(s.warnings)
    assert "BAD" in joined and "K0+040" in joined and "no numéric" in joined


def test_max_points_limit():
    row = "K0+000," + ",".join(["1"] * 9) + "\n"
    with pytest.raises(SurveyError):
        parse_survey_text(row + row.replace("K0+000", "K0+010"))      # 9 > 8 -> all skipped
    s = parse_survey_text(row + row.replace("K0+000", "K0+010"), max_points=9)
    assert len(s.sections) == 2 and s.sections[0].descs[-1] == "P9"


def test_numeric_header_gives_explicit_offsets():
    text = "Abscisa,-3,-1,0,1,3\nK0+000,1,2,3,2,1\n"
    sec = parse_survey_text(text).sections[0]
    assert sec.offsets == [-3.0, -1.0, 0.0, 1.0, 3.0]


def test_manual_spacings_zero_at_eje():
    text = HEADER + "K0+000,1,2,3,4,3,2,1\n"
    sec = parse_survey_text(text, spacings=[1, 2, 3, 3, 2, 1]).sections[0]
    assert sec.offsets == [-6.0, -5.0, -3.0, 0.0, 3.0, 5.0, 6.0]
    with pytest.raises(SurveyError):                              # wrong count -> row skipped
        parse_survey_text(text, spacings=[1, 2])


def test_station_validation():
    good = parse_survey_text(HEADER + "K0+020,1,2,3,4,3,2,1\nK0+000,1,2,3,4,3,2,1\n").sections
    with pytest.raises(SurveyError, match="--sort"):
        validate_stations(good)
    assert [s.label for s in validate_stations(good, sort=True)] == ["K0+000", "K0+020"]
    dup = parse_survey_text(HEADER + "K0+000,1,2,3,4,3,2,1\nK0+000,1,2,3,4,3,2,1\n").sections
    with pytest.raises(SurveyError, match="duplicada"):
        validate_stations(dup, sort=True)
    with pytest.raises(SurveyError):
        validate_stations(good[:1])


def test_numeric_stations_get_k_labels():
    secs = parse_survey_text(HEADER + "0,1,2,3,4,3,2,1\n25,1,2,3,4,3,2,1\n").sections
    assert [s.label for s in secs] == ["K0+000", "K0+025"]


# ---------------------------------------------------------------- series
def test_extract_series_named_sides_and_interpolation():
    text = (
        "Abscisa,BV,EJE,BV\nK0+000,9,10,9\nK0+010,8.6,9.6,8.6\n"
        "Abscisa2\n"                                              # ignored (invalid station)
    )
    secs = parse_survey_text(text).sections
    assert list(extract_series(secs, "eje").z) == [10.0, 9.6]
    assert list(extract_series(secs, "BV IZQ").z) == [9.0, 8.6]
    with pytest.raises(SurveyError, match="ambiguo"):
        extract_series(secs, "BV")

    only_bv = parse_survey_text("A,BV,BV\nK0+000,9,9.2\nK0+010,8,8.4\n").sections
    warns = []
    s = extract_series(only_bv, "EJE", warnings=warns)           # no EJE -> interpolated at x=0
    assert s.interpolated == [True, True]
    assert list(s.z) == pytest.approx([9.1, 8.2]) and warns
    assert list(extract_series(only_bv, "MIN").z) == [9.0, 8.0]


def test_lowest_in_section():
    sec = parse_survey_text(HEADER + "K0+000,1,2,3,4,3,2,1.5\n").sections[0]
    low = lowest_in_section(sec)
    assert low["name"] == "PAR IZQ" and low["z"] == 1.0 and low["below_axis"] == 3.0


# ------------------------------------------------------------- low points
D = np.arange(0, 100, 10.0)


def test_single_sag():
    z = [10, 9, 8, 7.5, 8.5, 9.5, 10, 10.5, 11, 12]
    (lp,) = find_low_points(D, z)
    assert lp.station == 30 and lp.z == 7.5 and lp.id == 1
    assert lp.depth_prev == 0.5 and lp.depth_next == 1.0 and lp.depth_adjacent == 0.5
    assert lp.depth_mean == pytest.approx(0.75)
    assert lp.depth_crest == pytest.approx(2.5)               # left crest 10, right crest 12 -> min 10
    assert lp.grade_in == pytest.approx(-5.0) and lp.grade_out == pytest.approx(10.0)


def test_monotonic_profile_has_no_low_points():
    assert find_low_points(D, np.linspace(10, 5, 10)) == []
    assert find_low_points(D, np.linspace(5, 10, 10)) == []
    assert find_low_points([0.0, 10.0], [1.0, 2.0]) == []


def test_flat_bottom_is_one_point():
    z = [10, 9, 8, 8, 8, 9, 10, 11, 12, 13]
    (lp,) = find_low_points(D, z)
    assert lp.n_stations == 3 and lp.station == 20 and lp.end_label == "K0+040"
    assert lp.depth_adjacent == 1.0


def test_ends_only_when_requested_and_min_depth_filter():
    z = [5, 6, 7, 8, 9, 8, 7, 6, 7, 3]
    assert [lp.station for lp in find_low_points(D, z)] == [70]
    with_ends = find_low_points(D, z, include_ends=True)
    assert [lp.station for lp in with_ends] == [0, 70, 90]      # last station 3 < 7 too
    assert with_ends[2].is_boundary and with_ends[2].depth_next is None
    assert with_ends[0].is_boundary and with_ends[0].depth_prev is None
    assert with_ends[0].depth_crest is None
    assert find_low_points(D, z, min_depth=1.5) == []           # 70 has adjacent depth 1.0


def test_ids_follow_station_order_and_crest_walk_over_shoulder():
    z = [10, 8, 9, 7, 9.5, 11, 10, 12, 13, 14]
    lows = find_low_points(D, z)
    assert [lp.station for lp in lows] == [10, 30, 60]
    assert [lp.id for lp in lows] == [1, 2, 3]
    # PB2 (z=7): left crest is z=9 (station 20) -> spill level 9 -> depth 2
    assert lows[1].depth_crest == pytest.approx(2.0)


# --------------------------------------------------------------------- CLI
def test_cli_end_to_end(tmp_path, capsys):
    out = tmp_path / "out"
    code = run([str(SAMPLE), "-o", str(out), "--extra-lines", "BV IZQ,BV DER", "--lang", "en",
                "--dpi", "40", "--formats", "png"])
    assert code == 0
    for name in ("perfil_longitudinal_izquierdo.png", "perfil_longitudinal_derecho.png",
                 "secciones_p01.png", "puntos_bajos.png",
                 "puntos_bajos.csv", "secciones_minimos.csv", "informe_puntos_bajos.txt"):
        assert (out / name).exists(), name
    rows = (out / "puntos_bajos.csv").read_text().splitlines()
    assert len(rows) == 3 and rows[1].startswith("PB1,K0+140") and rows[2].startswith("PB2,K0+300")
    assert not (out / "perfil_longitudinal.png").exists()      # replaced by one sheet per side
    assert "LOW POINT REPORT" in capsys.readouterr().out


def test_cli_reports_errors(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("Abscisa,BV,BV\nnope,1,2\n")
    assert run([str(bad), "-o", str(tmp_path / "o")]) == 1
    assert "Error" in capsys.readouterr().err
    assert run([str(SAMPLE), "-o", str(tmp_path / "o"), "--line", "SAR"]) == 1   # ambiguous


# ------------------------------------------------------------- ideal line
def _n_interior_minima(z):
    return sum(1 for i in range(1, len(z) - 1) if z[i] < z[i - 1] and z[i] <= z[i + 1])


def test_ideal_has_no_low_points_and_follows_trend():
    z = np.array([5, 6, 7, 8, 9, 8, 7, 4.5, 7, 3.0])
    ideal = compute_ideal_profile(D, z)
    assert len(ideal.z) == len(z)
    assert find_low_points(D, ideal.z, include_ends=False) == []
    assert _n_interior_minima(ideal.z) == 0
    assert ideal.trend == "crest" and ideal.crest_index in (4, 5)


def test_ideal_equals_real_when_profile_is_already_valid():
    d = np.arange(0, 60, 10.0)
    z = np.array([10.0, 9.0, 8.0, 7.0, 6.0, 5.0])
    ideal = compute_ideal_profile(d, z)
    assert ideal.z == pytest.approx(z)
    assert ideal.trend == "down" and ideal.max_fill == pytest.approx(0) and ideal.rms == pytest.approx(0)


def test_ideal_sag_is_filled_and_diff_sign():
    d = np.arange(0, 50, 10.0)
    z = np.array([10.0, 8.0, 6.0, 8.0, 4.0])      # sag at 6 then rising bump: descending trend
    ideal = compute_ideal_profile(d, z, allow_crest=False)
    assert np.all(np.diff(ideal.z) <= 1e-9)        # monotone descending
    assert ideal.diff[2] > 0                       # the sag is filled (+)
    assert ideal.diff[3] < 0                       # the bump is cut (-)
    assert ideal.max_fill > 0 and ideal.max_cut > 0
    assert ideal.diff == pytest.approx(ideal.z - z)


def test_ideal_min_grade_enforced():
    d = np.arange(0, 50, 10.0)
    z = np.array([10.0, 9.9, 9.9, 9.9, 9.8])       # almost flat
    ideal = compute_ideal_profile(d, z, min_grade=0.01, allow_crest=False)
    slopes = np.diff(ideal.z) / np.diff(d)
    assert np.all(slopes <= -0.01 + 1e-9)
    auto = compute_ideal_profile(d, z, allow_crest=False)
    assert 0 <= auto.min_grade <= 0.005
    with pytest.raises(ValueError):
        compute_ideal_profile([0.0], [1.0])


def test_ideal_rising_profile():
    d = np.arange(0, 50, 10.0)
    ideal = compute_ideal_profile(d, np.array([1.0, 2.0, 1.5, 3.0, 4.0]))
    assert ideal.trend == "up"
    assert np.all(np.diff(ideal.z) >= -1e-9)


# ---------------------------------------------------------------- sides
def test_sides_auto_bv_ext_none_explicit():
    secs = parse_survey_text(HEADER + "K0+000,9,9.5,9.8,10,9.9,9.6,9.1\nK0+010,8,8.5,8.8,9,8.9,8.6,8.1\n").sections
    left, right = resolve_side_lines(secs, "auto", exclude=["EJE"])
    assert (left.role, right.role) == ("left", "right")
    assert list(left.z) == [9.8, 8.8] and list(right.z) == [9.9, 8.9]

    ext = parse_survey_text("A,X,Y,EJE,W\nK0+000,1,2,3,4\nK0+010,1.5,2.5,3.5,4.5\n").sections
    e_left, e_right = resolve_side_lines(ext, "auto", exclude=["EJE"])
    assert list(e_left.z) == [1.0, 1.5] and list(e_right.z) == [4.0, 4.5]

    assert resolve_side_lines(secs, "none") == []
    sar = resolve_side_lines(secs, "SAR IZQ,SAR DER", exclude=["EJE"])
    assert list(sar[0].z) == [9.5, 8.5] and list(sar[1].z) == [9.6, 8.6]
    with pytest.raises(SurveyError):
        resolve_side_lines(secs, "solo_uno")


# ---------------------------------------------------------------- ponds
def test_pond_full_and_capped_depth():
    d = np.arange(0, 60, 10.0)
    z = np.array([10.0, 8.0, 6.0, 8.0, 10.0, 12.0])
    lp = find_low_points(d, z)[0]
    pond = ponding_region(d, z, lp)
    assert isinstance(pond, Pond)
    assert pond.level == pytest.approx(10.0) and pond.depth == pytest.approx(4.0)
    assert pond.area == pytest.approx(80.0)
    assert pond.x_left == pytest.approx(0.0) and pond.x_right == pytest.approx(40.0)

    capped = ponding_region(d, z, lp, max_depth=1.0)
    assert capped.level == pytest.approx(7.0) and capped.depth == pytest.approx(1.0)
    assert capped.area == pytest.approx(5.0)
    assert capped.x_left == pytest.approx(15.0) and capped.x_right == pytest.approx(25.0)
    px, pz = capped.outline(d, z)
    assert max(pz) == pytest.approx(7.0) and min(pz) == pytest.approx(6.0)


def test_pond_none_for_boundary_low_point():
    d = np.arange(0, 40, 10.0)
    z = np.array([5.0, 6.0, 7.0, 8.0])
    lp = find_low_points(d, z, include_ends=True)[0]
    assert ponding_region(d, z, lp) is None


def test_cli_default_outputs_and_options(tmp_path, capsys):
    out = tmp_path / "o1"
    assert run([str(SAMPLE), "-o", str(out), "--dpi", "40", "--formats", "png",
                "--extra-lines", "BV IZQ,BV DER,PAR IZQ"]) == 0    # BV lines dedupe with auto sides
    assert (out / "perfil_ideal.csv").exists()
    header = (out / "puntos_bajos.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "water_level_m" in header and "pond_area_m2" in header
    ideal_rows = (out / "perfil_ideal.csv").read_text(encoding="utf-8").splitlines()
    assert len(ideal_rows) == 22
    report = (out / "informe_puntos_bajos.txt").read_text(encoding="utf-8")
    assert "LÍNEA IDEAL" in report and "BV IZQ" in report

    out2 = tmp_path / "o2"
    assert run([str(SAMPLE), "-o", str(out2), "--dpi", "40", "--formats", "png", "--no-ideal",
                "--sides", "none", "--no-water", "--water-depth", "0.5"]) == 0
    assert not (out2 / "perfil_ideal.csv").exists()
    assert "LÍNEA IDEAL" not in (out2 / "informe_puntos_bajos.txt").read_text(encoding="utf-8")
    capsys.readouterr()

    assert run([str(SAMPLE), "-o", str(tmp_path / "o3"), "--sides", "uno"]) == 1
    assert run([str(SAMPLE), "-o", str(tmp_path / "o4"), "--water-depth", "-1"]) == 1
    assert run([str(SAMPLE), "-o", str(tmp_path / "o5"), "--extra-lines",
                "PAR IZQ,PAR DER,SAR IZQ,SAR DER,X1"]) == 1        # too many / unknown line


def test_cli_one_longitudinal_sheet_per_side(tmp_path):
    out = tmp_path / "s"
    assert run([str(SAMPLE), "-o", str(out), "--dpi", "40", "--formats", "png,pdf"]) == 0
    for stem in ("perfil_longitudinal_izquierdo", "perfil_longitudinal_derecho"):
        assert (out / f"{stem}.png").exists() and (out / f"{stem}.pdf").exists()
    assert not (out / "perfil_longitudinal.png").exists()

    out2 = tmp_path / "n"                                       # no side lines: single sheet
    assert run([str(SAMPLE), "-o", str(out2), "--dpi", "40", "--formats", "png",
                "--sides", "none"]) == 0
    assert (out2 / "perfil_longitudinal.png").exists()
    assert not (out2 / "perfil_longitudinal_izquierdo.png").exists()


def test_plot_long_profile_shared_scale_and_side_content():
    from perfil_vial.plotting import plot_long_profile
    secs = parse_survey_text(HEADER + "K0+000,9,9.5,9.8,10,9.9,9.6,9.1\n"
                             "K0+010,8,8.5,8.8,9,12.9,8.6,8.1\nK0+020,7,7.5,7.8,8,7.9,7.6,7.1\n").sections
    main = extract_series(secs, "EJE")
    left, right = resolve_side_lines(secs, "auto", exclude=["EJE"])
    _, sc_l = plot_long_profile(main, [left], scale_extras=[left, right])
    _, sc_r = plot_long_profile(main, [right], scale_extras=[left, right])
    _, sc_own = plot_long_profile(main, [left])
    assert sc_l.v_exag == pytest.approx(sc_r.v_exag) and sc_l.zmax == pytest.approx(sc_r.zmax)
    assert sc_l.zmax == pytest.approx(12.9)          # the other side's elevations set the range
    assert sc_own.zmax < 12.9                       # default behaviour unchanged
