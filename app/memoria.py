"""Memoria de cálculo .docx con docxtpl: plantilla + bucle + InlineImage.

Se importa docxtpl dentro de la función para poder presentar un error claro
cuando faltan dependencias sin impedir abrir la GUI.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from docx.shared import Cm

from app.modelo import muestrear_eje, guardar_muestreo_png, etiqueta_abscisa

BASE_DIR = Path(__file__).resolve().parent.parent
PLANTILLA = BASE_DIR / "plantillas" / "memoria.docx"


def crear_memoria(csv_entrada: str | Path, nombre_proyecto: str, paso_m: float = 3.0,
                  plantilla: Path = PLANTILLA) -> bytes:
    """Genera la memoria con cotas observadas, interpolación y gráfica.

    Devuelve bytes .docx para el cuadro de guardar de Flet.
    """
    try:
        from docxtpl import DocxTemplate, InlineImage
    except ImportError as exc:
        raise RuntimeError('Falta docxtpl. Ejecuta: python -m pip install -r requirements.txt') from exc
    csv_entrada = Path(csv_entrada)
    datos = muestrear_eje(csv_entrada, float(paso_m))
    ini, fin = datos.estaciones_campo[0], datos.estaciones_campo[-1]
    pendiente = 100.0 * (datos.cotas_campo[-1] - datos.cotas_campo[0]) / (fin - ini)
    filas = [
        {"abscisa": etiqueta_abscisa(float(x)), "distancia": f"{x:.2f}", "cota": f"{z:.3f}"}
        for x, z in zip(datos.estaciones_campo, datos.cotas_campo)
    ]
    plantilla = Path(plantilla)
    if not plantilla.is_file():
        raise FileNotFoundError(f"Falta la plantilla docxtpl: {plantilla}")
    with TemporaryDirectory(prefix="pv_memoria_") as tmp:
        png = guardar_muestreo_png(datos, Path(tmp) / "interpolacion_eje.png")
        doc = DocxTemplate(str(plantilla))
        contexto = {
            "proyecto": nombre_proyecto.strip() or "Análisis topográfico sin nombre",
            "fuente": csv_entrada.name,
            "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "total_medidas": len(datos.estaciones_campo),
            "inicial": etiqueta_abscisa(float(ini)),
            "final": etiqueta_abscisa(float(fin)),
            "paso": f"{datos.paso_m:.2f}",
            "total_estimadas": len(datos.estaciones_malla),
            "cota_min": f"{min(datos.cotas_campo):.3f}",
            "cota_max": f"{max(datos.cotas_campo):.3f}",
            "pendiente_media": f"{pendiente:+.3f}",
            "filas": filas,
            "grafica": InlineImage(doc, str(png), width=Cm(15.6)),
            "validacion": "Cotas EJE y abscisas válidas; interpolación dentro del rango medido.",
        }
        doc.render(contexto)
        resultado = Path(tmp) / 'memoria_calculo.docx'
        doc.save(str(resultado))
        return resultado.read_bytes()
