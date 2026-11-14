"""Modelo de muestreo longitudinal: NumPy y SciPy, independiente de Flet.

El muestreo PCHIP estima cotas intermedias del terreno EJE. No diseña ni
certifica una rasante, ni asegura drenaje; no extrapola fuera del levantamiento.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv

import numpy as np
from scipy.interpolate import PchipInterpolator

from perfil_vial.parsing import read_survey


@dataclass
class MuestreoEje:
    estaciones_campo: np.ndarray
    cotas_campo: np.ndarray
    estaciones_malla: np.ndarray
    cotas_interpoladas: np.ndarray
    pendiente_por_intervalo_pct: np.ndarray
    paso_m: float


def muestrear_eje(csv_entrada: str | Path, paso_m: float = 3.0) -> MuestreoEje:
    """Interpola el eje a un paso en metros y conserva estaciones de campo.

    Las cotas interpoladas son estimaciones, no observaciones topográficas.
    El interpolador PCHIP preserva la forma sin imponer pendientes de diseño.
    """
    if not np.isfinite(paso_m) or paso_m <= 0:
        raise ValueError("El intervalo de muestreo debe ser positivo y finito.")
    levantamiento = read_survey(csv_entrada)
    if len(levantamiento.sections) < 2:
        raise ValueError("Se necesitan al menos dos secciones válidas.")
    estaciones, cotas = [], []
    for sec in levantamiento.sections:
        indice = sec.index_of("EJE")
        if indice is None:
            raise ValueError(f"Falta cota EJE en {sec.label}.")
        estaciones.append(float(sec.station))
        cotas.append(float(sec.elevations[indice]))
    x = np.asarray(estaciones, dtype=float)
    y = np.asarray(cotas, dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Las cotas y abscisas deben ser finitas.")
    if np.any(np.diff(x) <= 0):
        raise ValueError("Las abscisas deben estar ordenadas y ser estrictamente crecientes.")
    # Límite de seguridad para no bloquear la interfaz con mallas excesivas.
    if (x[-1] - x[0]) / paso_m > 100_000:
        raise ValueError("Intervalo demasiado pequeño: más de 100 000 evaluaciones.")
    muestra = x[0] + paso_m * np.arange(int(np.floor((x[-1] - x[0]) / paso_m)) + 1)
    muestra = np.unique(np.concatenate((muestra, x, [x[-1]])))
    muestra = muestra[(muestra >= x[0]) & (muestra <= x[-1])]
    interpolador = PchipInterpolator(x, y, extrapolate=False)
    zm = np.asarray(interpolador(muestra), dtype=float)
    gradientes = 100.0 * np.diff(zm) / np.diff(muestra)
    return MuestreoEje(x, y, muestra, zm, gradientes, paso_m)


def etiqueta_abscisa(x: float) -> str:
    km = int(x // 1000)
    metros = x - km * 1000
    return f"K{km}+{metros:06.2f}" if not float(x).is_integer() else f"K{km}+{int(round(metros)):03d}"


def guardar_muestreo_csv(resultado: MuestreoEje, destino: str | Path) -> Path:
    """Exporta las cotas con marca MEDIDA o INTERPOLADA."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # La coincidencia se resuelve con tolerancia solo para abscisas de coma flotante.
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Abscisa", "Distancia_m", "Cota_EJE_m", "Origen"])
        for x, z in zip(resultado.estaciones_malla, resultado.cotas_interpoladas):
            es_medida = bool(np.any(np.isclose(resultado.estaciones_campo, x, atol=1e-7, rtol=0)))
            w.writerow([etiqueta_abscisa(float(x)), f"{x:.3f}", f"{z:.4f}", "MEDIDA" if es_medida else "INTERPOLADA"])
    return destino


def guardar_muestreo_png(resultado: MuestreoEje, destino: str | Path) -> Path:
    """Grafica técnica con nombre, unidades, título y leyenda."""
    import matplotlib.pyplot as plt

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11.7, 5.8))
    ax.plot(resultado.estaciones_malla, resultado.cotas_interpoladas,
            label="Estimación PCHIP (SciPy)", lw=1.9)
    ax.scatter(resultado.estaciones_campo, resultado.cotas_campo,
               label="Cotas medidas EJE", s=20, zorder=3)
    ax.set(xlabel="Abscisa (m)", ylabel="Elevación (m)",
           title="Eje de vía: cotas medidas e interpolación PCHIP")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return destino
