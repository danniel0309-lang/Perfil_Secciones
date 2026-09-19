"""Small message catalogue (Spanish default, English optional).

The AutoLISP originals label their drawings in Spanish (ABSCISAS, COTA TN,
DISTANCIA, DESCRIPCION ...), so Spanish is the default here as well.
"""

from __future__ import annotations

MESSAGES = {
    "es": {
        # --- parsing / validation ------------------------------------------------
        "w_skip_station": "Fila {row}: abscisa inválida '{tok}'; fila omitida.",
        "w_skip_count": (
            "Fila {row} ({label}): {n} cotas válidas (se requieren entre {lo} y {hi}); "
            "fila omitida."
        ),
        "w_stray": "Fila {row} ({label}): celda(s) no numérica(s) ignorada(s): {cells}.",
        "w_offsets_partial": (
            "Fila {row} ({label}): la cabecera no define distancias para todas las "
            "columnas con dato; se usa la separación uniforme."
        ),
        "w_spacings_len": (
            "Fila {row} ({label}): se esperaban {exp} distancias entre puntos y se "
            "recibieron {got}; fila omitida."
        ),
        "w_offsets_order": (
            "Fila {row} ({label}): las distancias transversales no son estrictamente "
            "crecientes; fila omitida."
        ),
        "w_series_missing": "Sección {label}: no tiene punto '{name}'; se omite del perfil.",
        "w_series_interp": (
            "Serie '{name}': {n} sección(es) sin ese punto; cota interpolada en el "
            "desplazamiento 0."
        ),
        "e_no_sections": (
            "No se detectaron filas válidas (abscisa + entre {lo} y {hi} cotas)."
        ),
        "e_duplicate": "Abscisa duplicada {label} (filas {rows}).",
        "e_order": (
            "La abscisa de la fila {row} ({label}) no es mayor que la anterior "
            "({prev}). Ordene el archivo o use --sort."
        ),
        "e_min_stations": "Se necesitan al menos 2 secciones para el perfil longitudinal.",
        "e_ambiguous": (
            "El nombre '{name}' es ambiguo en la sección {label}; use '{name} IZQ' o "
            "'{name} DER'."
        ),
        "e_series_short": "La serie '{name}' tiene menos de 2 estaciones válidas.",
        "e_zero_width": "La longitud horizontal del perfil es inválida.",
        "e_points_row": (
            "Puntos adicionales, fila {row}: se requieren COTA, DESCRIPCION y ABSCISA "
            "válidas."
        ),
        "w_select_missing": "La abscisa seleccionada '{tok}' no existe en los datos.",
        # --- plots ---------------------------------------------------------------
        "abscissas": "ABSCISAS",
        "cota_tn": "COTA TN",
        "cota_prefix": "COTA",
        "distance": "DISTANCIA",
        "description": "DESCRIPCION",
        "profile_title": "PERFIL LONGITUDINAL",
        "sections_title": "SECCIONES TRANSVERSALES",
        "vexag": "Exag. vertical ×{v:.1f}",
        "low_point": "Punto bajo",
        "extra_point": "Punto adicional",
        "section_low": "Punto más bajo de la sección",
        "axis_zero": "Eje (x = 0)",
        "lowpts_title": "PUNTOS BAJOS DEL PERFIL LONGITUDINAL",
        "ylabel_elev": "Cota (m)",
        "ylabel_depth": "Profundidad (m)",
        "depth_adj": "Respecto a estaciones adyacentes",
        "depth_crest": "Hasta la cota de rebose",
        "ponding": "Zona de posible empozamiento",
        "no_low": "No se detectaron puntos bajos con los parámetros dados.",
        "page": "Hoja {i}/{n}",
        # --- report --------------------------------------------------------------
        "r_title": "INFORME DE PUNTOS BAJOS - PERFIL LONGITUDINAL",
        "r_file": "Archivo",
        "r_line": "Línea de referencia",
        "r_stations": "Estaciones",
        "r_length": "Longitud",
        "r_params": "Parámetros de detección",
        "r_min_depth": "Profundidad mínima",
        "r_ends": "Extremos incluidos",
        "r_yes": "sí",
        "r_no": "no",
        "r_scale": "Escala del perfil",
        "r_vexag": "Exageración vertical",
        "r_step": "Paso de cuadrícula (cota)",
        "r_ref": "Cota de referencia / tope",
        "r_zrange": "Rango de cotas",
        "r_lowest": "Cota mínima del tramo",
        "r_highest": "Cota máxima del tramo",
        "r_found": "PUNTOS BAJOS DETECTADOS",
        "r_none": "Ninguno con los parámetros dados.",
        "r_deepest": "Punto más profundo (hasta la cota de rebose)",
        "r_cols": "ID|Abscisa|Cota (m)|Anterior|Siguiente|Prof.adyac|Prof.rebose|Pend.ent%|Pend.sal%",
        "r_note_depth": (
            "Prof.adyac = menor diferencia de cota con las estaciones vecinas; "
            "Prof.rebose = diferencia hasta la menor de las dos crestas que encierran "
            "la depresión (nivel al que el agua desbordaría)."
        ),
        "r_note_plateau": "(->K...) = tramo plano de varias estaciones consecutivas con la misma cota.",
        "r_note_boundary": "* punto en un extremo del tramo (solo un vecino).",
        "r_validation": "VALIDACIÓN DE DATOS",
        "r_rows": "Secciones válidas leídas",
        "r_no_warn": "Sin advertencias.",
        "r_sections_min": "Puntos más bajos por sección transversal",
        "r_sections_min_file": "ver secciones_minimos.csv",
        "r_files": "ARCHIVOS GENERADOS",
        "r_na": "n/d",
    },
    "en": {
        "w_skip_station": "Row {row}: invalid station '{tok}'; row skipped.",
        "w_skip_count": (
            "Row {row} ({label}): {n} valid elevations (need between {lo} and {hi}); "
            "row skipped."
        ),
        "w_stray": "Row {row} ({label}): non-numeric cell(s) ignored: {cells}.",
        "w_offsets_partial": (
            "Row {row} ({label}): header does not define offsets for every populated "
            "column; falling back to uniform spacing."
        ),
        "w_spacings_len": (
            "Row {row} ({label}): expected {exp} point spacings but got {got}; "
            "row skipped."
        ),
        "w_offsets_order": (
            "Row {row} ({label}): transversal offsets are not strictly increasing; "
            "row skipped."
        ),
        "w_series_missing": "Section {label}: no '{name}' point; left out of the profile.",
        "w_series_interp": (
            "Series '{name}': {n} section(s) lack that point; elevation interpolated "
            "at offset 0."
        ),
        "e_no_sections": "No valid rows found (station + {lo} to {hi} elevations).",
        "e_duplicate": "Duplicate station {label} (rows {rows}).",
        "e_order": (
            "Station in row {row} ({label}) is not greater than the previous one "
            "({prev}). Sort the file or use --sort."
        ),
        "e_min_stations": "At least 2 sections are needed for a longitudinal profile.",
        "e_ambiguous": (
            "Name '{name}' is ambiguous in section {label}; use '{name} IZQ' or "
            "'{name} DER'."
        ),
        "e_series_short": "Series '{name}' has fewer than 2 valid stations.",
        "e_zero_width": "The horizontal length of the profile is invalid.",
        "e_points_row": (
            "Additional points, row {row}: a valid ELEVATION, DESCRIPTION and STATION "
            "are required."
        ),
        "w_select_missing": "Selected station '{tok}' does not exist in the data.",
        "abscissas": "STATIONS",
        "cota_tn": "GROUND ELEV.",
        "cota_prefix": "ELEV.",
        "distance": "OFFSET",
        "description": "POINT",
        "profile_title": "LONGITUDINAL PROFILE",
        "sections_title": "CROSS-SECTIONS",
        "vexag": "Vertical exag. ×{v:.1f}",
        "low_point": "Low point",
        "extra_point": "Additional point",
        "section_low": "Lowest point of section",
        "axis_zero": "Centerline (x = 0)",
        "lowpts_title": "LOW POINTS OF THE LONGITUDINAL PROFILE",
        "ylabel_elev": "Elevation (m)",
        "ylabel_depth": "Depth (m)",
        "depth_adj": "Relative to adjacent stations",
        "depth_crest": "Up to spill level",
        "ponding": "Possible ponding zone",
        "no_low": "No low points found with the given parameters.",
        "page": "Sheet {i}/{n}",
        "r_title": "LOW POINT REPORT - LONGITUDINAL PROFILE",
        "r_file": "File",
        "r_line": "Reference line",
        "r_stations": "Stations",
        "r_length": "Length",
        "r_params": "Detection parameters",
        "r_min_depth": "Minimum depth",
        "r_ends": "Profile ends included",
        "r_yes": "yes",
        "r_no": "no",
        "r_scale": "Profile scale",
        "r_vexag": "Vertical exaggeration",
        "r_step": "Grid step (elevation)",
        "r_ref": "Reference / top elevation",
        "r_zrange": "Elevation range",
        "r_lowest": "Lowest elevation of the reach",
        "r_highest": "Highest elevation of the reach",
        "r_found": "LOW POINTS FOUND",
        "r_none": "None with the given parameters.",
        "r_deepest": "Deepest point (to spill level)",
        "r_cols": "ID|Station|Elev (m)|Previous|Next|Adj.depth|Spill depth|In grade%|Out grade%",
        "r_note_depth": (
            "Adj.depth = smaller elevation difference to the neighbouring stations; "
            "Spill depth = difference up to the lower of the two crests enclosing the "
            "sag (level at which water would overflow)."
        ),
        "r_note_plateau": "(->K...) = flat run of several consecutive stations with the same elevation.",
        "r_note_boundary": "* point at an end of the reach (only one neighbour).",
        "r_validation": "DATA VALIDATION",
        "r_rows": "Valid sections read",
        "r_no_warn": "No warnings.",
        "r_sections_min": "Lowest point of each cross-section",
        "r_sections_min_file": "see secciones_minimos.csv",
        "r_files": "GENERATED FILES",
        "r_na": "n/a",
    },
}


# --- costados, línea ideal y charcos (v0.2) ------------------------------------
MESSAGES["es"].update({
    "e_sides_spec": (
        "--sides debe ser 'auto', 'none' o dos nombres separados por coma "
        "(izquierdo,derecho); se recibió '{spec}'."
    ),
    "e_lines_limit": (
        "Se pueden dibujar como máximo {n} líneas adicionales en el perfil "
        "(costados + --extra-lines); se pidieron {got}."
    ),
    "w_no_sides": "No se pudieron construir las líneas de los costados de la vía.",
    "title_left": "COSTADO IZQUIERDO",
    "title_right": "COSTADO DERECHO",
    "w_no_ideal": "Se necesitan al menos 2 estaciones para calcular la línea ideal.",
    "side_left": "Costado izq.",
    "side_right": "Costado der.",
    "ideal_line": "Rasante ideal (sin puntos bajos)",
    "cota_ideal": "IDEAL",
    "water": "Agua acumulada",
    "water_full": "rebose",
    "water_part": "parcial",
    "r_sides": "Costados dibujados",
    "r_ideal": "LÍNEA IDEAL (RASANTE SIN PUNTOS BAJOS)",
    "r_trend": "Tendencia",
    "r_trend_down": "descendente",
    "r_trend_up": "ascendente",
    "r_trend_crest": "sube hasta {label} y luego baja",
    "r_ideal_grade": "Pendiente mínima aplicada",
    "r_ideal_mean": "Pendiente media de la línea ideal",
    "r_ideal_fill": "Relleno máximo (ideal sobre la real)",
    "r_ideal_cut": "Corte máximo (ideal bajo la real)",
    "r_ideal_rms": "Desviación cuadrática media",
    "r_ideal_note": "Diferencia ideal - real por estación en perfil_ideal.csv (+ relleno, - corte).",
    "r_ponds": "EMPOZAMIENTO (AGUA ACUMULADA)",
    "r_pond_cols": "ID|Nivel agua (m)|Prof. (m)|Longitud (m)|Área (m²)|Llenado",
    "r_pond_note": (
        "Superficie plana a la cota de rebose (o fondo + profundidad máxima indicada). "
        "El área es la del plano longitudinal (m²), no un volumen."
    ),
})
MESSAGES["en"].update({
    "e_sides_spec": (
        "--sides must be 'auto', 'none' or two comma-separated names "
        "(left,right); got '{spec}'."
    ),
    "e_lines_limit": (
        "At most {n} additional lines can be drawn on the profile "
        "(sides + --extra-lines); {got} requested."
    ),
    "w_no_sides": "The road-side lines could not be built.",
    "title_left": "LEFT SIDE",
    "title_right": "RIGHT SIDE",
    "w_no_ideal": "At least 2 stations are needed to compute the ideal line.",
    "side_left": "Left side",
    "side_right": "Right side",
    "ideal_line": "Ideal grade line (no low points)",
    "cota_ideal": "IDEAL",
    "water": "Ponded water",
    "water_full": "spill",
    "water_part": "partial",
    "r_sides": "Side lines drawn",
    "r_ideal": "IDEAL LINE (GRADE LINE WITHOUT LOW POINTS)",
    "r_trend": "Trend",
    "r_trend_down": "descending",
    "r_trend_up": "ascending",
    "r_trend_crest": "rises to {label} then falls",
    "r_ideal_grade": "Minimum grade applied",
    "r_ideal_mean": "Mean grade of the ideal line",
    "r_ideal_fill": "Maximum fill (ideal above real)",
    "r_ideal_cut": "Maximum cut (ideal below real)",
    "r_ideal_rms": "Root-mean-square deviation",
    "r_ideal_note": "Ideal - real per station in perfil_ideal.csv (+ fill, - cut).",
    "r_ponds": "PONDING (ACCUMULATED WATER)",
    "r_pond_cols": "ID|Water level (m)|Depth (m)|Length (m)|Area (m²)|Fill",
    "r_pond_note": (
        "Flat surface at the spill level (or bottom + the given maximum depth). "
        "Area is that of the longitudinal plane (m²), not a volume."
    ),
})


def msg(lang: str, key: str, **kw) -> str:
    """Return the message ``key`` in ``lang`` formatted with ``kw``."""
    table = MESSAGES.get(lang) or MESSAGES["es"]
    text = table.get(key) or MESSAGES["es"][key]
    return text.format(**kw) if kw else text
