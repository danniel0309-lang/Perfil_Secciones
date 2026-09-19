"""perfil_vial - longitudinal profile, cross-sections and low points from road surveys.

Python port and extension of the AutoLISP programs ``Perfil_long.lsp`` (PERFILTN)
and ``Seccion_long.lsp`` (SECCIONTN).  Run ``python -m perfil_vial --help``.
"""

from .geometry import Scale, nice_step, profile_scale, section_scale
from .ideal import IdealProfile, compute_ideal_profile
from .lowpoints import LowPoint, Pond, find_low_points, ponding_region
from .parsing import (
    Section, Survey, SurveyError, format_k, parse_k_to_dist, parse_station,
    read_survey, token_to_real, validate_stations, valid_k_label,
)
from .profile import Series, extract_series, lowest_in_section, resolve_side_lines

__all__ = [
    "IdealProfile", "LowPoint", "Pond", "Scale", "Section", "Series", "Survey", "SurveyError",
    "extract_series", "find_low_points", "format_k", "lowest_in_section", "nice_step",
    "parse_k_to_dist", "parse_station", "profile_scale", "read_survey", "section_scale",
    "token_to_real", "valid_k_label", "validate_stations",
    "compute_ideal_profile", "ponding_region", "resolve_side_lines",
]
