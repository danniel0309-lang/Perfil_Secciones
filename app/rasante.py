"""Prediseño longitudinal de rasante con extremos anclados a cotas de campo.

No representa curvas verticales, dimensionamiento hidráulico ni volúmenes.
Las cotas de terreno interpoladas son estimaciones y se identifican como tales.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import LinearConstraint, minimize

from app.modelo import etiqueta_abscisa, muestrear_eje


@dataclass
class ResultadoRasante:
    estaciones_medidas_m: np.ndarray
    cotas_medidas_m: np.ndarray
    cotas_proyecto_en_estaciones_m: np.ndarray
    estaciones_evaluadas_m: np.ndarray
    cotas_terreno_evaluadas_m: np.ndarray
    cotas_rasante_evaluadas_m: np.ndarray
    diferencia_proyecto_menos_terreno_m: np.ndarray
    pendientes_tramos_pct: np.ndarray
    metodo: str
    suavizado_pct: float
    pendiente_maxima_pct: float | None

    @property
    def pendiente_media_pct(self) -> float:
        x, z = self.estaciones_medidas_m, self.cotas_proyecto_en_estaciones_m
        return 100.0 * (z[-1] - z[0]) / (x[-1] - x[0])

    @property
    def corte_maximo_eje_m(self) -> float:
        return float(np.max(np.maximum(-self.diferencia_proyecto_menos_terreno_m, 0.0)))

    @property
    def relleno_maximo_eje_m(self) -> float:
        return float(np.max(np.maximum(self.diferencia_proyecto_menos_terreno_m, 0.0)))


def calcular_rasante(
    csv_entrada: str | Path,
    paso_m: float = 3.0,
    metodo: str = "constante",
    suavizado_pct: float = 80.0,
    pendiente_maxima_pct: float | None = None,
) -> ResultadoRasante:
    """Calcula rasante preliminar sin modificar los datos de origen.

    - 'constante': recta entre la primera y la última cota EJE medida.
    - 'suavizada': minimiza desviación respecto al terreno y cambios de grado
      mediante optimización cuadrática con SciPy SLSQP y extremos fijos.
    - pendiente_maxima_pct limita el valor ABSOLUTO de la pendiente de cada tramo.

    El análisis es longitudinal del eje; las diferencias verticales NO son volúmenes.
    """
    if metodo not in {"constante", "suavizada"}:
        raise ValueError("Método desconocido: selecciona constante o suavizada.")
    if not np.isfinite(suavizado_pct) or not 0 <= suavizado_pct <= 100:
        raise ValueError("El suavizado debe estar entre 0 y 100 %.")
    if pendiente_maxima_pct is not None:
        if not np.isfinite(pendiente_maxima_pct) or pendiente_maxima_pct <= 0:
            raise ValueError("La pendiente máxima debe ser mayor que cero.")

    terreno = muestrear_eje(csv_entrada, paso_m)
    x = terreno.estaciones_campo.copy()
    y = terreno.cotas_campo.copy()
    n = len(x)
    longitud = x[-1] - x[0]
    dx = np.diff(x)
    pendiente_media_pct = 100.0 * (y[-1] - y[0]) / longitud
    if pendiente_maxima_pct is not None and abs(pendiente_media_pct) > pendiente_maxima_pct + 1e-9:
        raise ValueError(
            f"Extremos incompatibles: requieren al menos {abs(pendiente_media_pct):.3f} % "
            f"de pendiente absoluta y el límite indicado es {pendiente_maxima_pct:.3f} %."
        )

    recta = y[0] + (y[-1] - y[0]) * (x - x[0]) / longitud
    z = recta.copy()

    if metodo == "suavizada" and n > 2 and suavizado_pct < 100:
        # G * z = pendientes por tramo (m/m); D * z = cambios de pendiente.
        G = np.zeros((n - 1, n), dtype=float)
        for i, distancia in enumerate(dx):
            G[i, i] = -1.0 / distancia
            G[i, i + 1] = 1.0 / distancia
        referencia = float(np.median(dx))
        D = np.diff(G, axis=0) * referencia
        w = suavizado_pct / 100.0
        A = (1.0 - w) / n * np.eye(n) + w / (n - 2) * (D.T @ D)
        b = (1.0 - w) / n * y

        def objetivo(centro: np.ndarray) -> float:
            v = np.concatenate(([y[0]], centro, [y[-1]]))
            return float(v @ A @ v - 2.0 * b @ v)

        def gradiente(centro: np.ndarray) -> np.ndarray:
            v = np.concatenate(([y[0]], centro, [y[-1]]))
            return 2.0 * (A @ v - b)[1:-1]

        restricciones = []
        if pendiente_maxima_pct is not None:
            # La matriz actúa SOLO sobre las cotas interiores.
            max_g = pendiente_maxima_pct / 100.0
            base = G[:, 0] * y[0] + G[:, -1] * y[-1]
            restricciones = [LinearConstraint(G[:, 1:-1], -max_g - base, max_g - base)]

        res = minimize(
            objetivo, recta[1:-1], jac=gradiente, method="SLSQP",
            constraints=restricciones, options={"maxiter": 3000, "ftol": 1e-10},
        )
        if not res.success or not np.all(np.isfinite(res.x)):
            raise RuntimeError(f"SciPy no logró converger en el ajuste: {res.message}")
        z = np.concatenate(([y[0]], res.x, [y[-1]]))

    # Evaluación del proyecto por interpolación lineal ENTRE vértices del diseño.
    x_malla = terreno.estaciones_malla.copy()
    z_proyecto = np.interp(x_malla, x, z)
    z_terreno = terreno.cotas_interpoladas.copy()
    pendientes_pct = 100.0 * np.diff(z) / dx

    if pendiente_maxima_pct is not None and np.max(np.abs(pendientes_pct)) > pendiente_maxima_pct + 1e-5:
        raise RuntimeError("La solución supera la pendiente máxima indicada.")
    if z[0] != y[0] or z[-1] != y[-1]:
        raise AssertionError("Las cotas extremas no se conservaron.")
    return ResultadoRasante(
        estaciones_medidas_m=x,
        cotas_medidas_m=y,
        cotas_proyecto_en_estaciones_m=z,
        estaciones_evaluadas_m=x_malla,
        cotas_terreno_evaluadas_m=z_terreno,
        cotas_rasante_evaluadas_m=z_proyecto,
        diferencia_proyecto_menos_terreno_m=z_proyecto - z_terreno,
        pendientes_tramos_pct=pendientes_pct,
        metodo=metodo,
        suavizado_pct=float(suavizado_pct),
        pendiente_maxima_pct=pendiente_maxima_pct,
    )


def guardar_rasante_csv(resultado: ResultadoRasante, destino: str | Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    x, yt, zp, d = (
        resultado.estaciones_evaluadas_m, resultado.cotas_terreno_evaluadas_m,
        resultado.cotas_rasante_evaluadas_m, resultado.diferencia_proyecto_menos_terreno_m,
    )
    with destino.open("w", newline="", encoding="utf-8-sig") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow([
            "Abscisa", "Distancia_m", "Cota_terreno_EJE_m", "Origen_terreno",
            "Cota_rasante_proyecto_m", "Diferencia_rasante_menos_terreno_m",
            "Corte_vertical_eje_m", "Relleno_vertical_eje_m",
            "Pendiente_proyecto_al_siguiente_punto_pct",
        ])
        for i, (xi, ti, zi, di) in enumerate(zip(x, yt, zp, d)):
            es_medida = bool(np.any(np.isclose(resultado.estaciones_medidas_m, xi, atol=1e-7, rtol=0)))
            pendiente = "" if i == len(x) - 1 else f"{100*(zp[i+1]-zi)/(x[i+1]-xi):.4f}"
            escritor.writerow([
                etiqueta_abscisa(float(xi)), f"{xi:.3f}", f"{ti:.4f}",
                "MEDIDA" if es_medida else "INTERPOLADA",
                f"{zi:.4f}", f"{di:.4f}", f"{max(-di, 0):.4f}",
                f"{max(di, 0):.4f}", pendiente,
            ])
    return destino


def guardar_rasante_png(resultado: ResultadoRasante, destino: str | Path) -> Path:
    import matplotlib.pyplot as plt

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    x = resultado.estaciones_evaluadas_m
    t = resultado.cotas_terreno_evaluadas_m
    r = resultado.cotas_rasante_evaluadas_m
    fig, ax = plt.subplots(figsize=(11.7, 6.2))
    ax.plot(x, t, lw=1.9, label="Terreno EJE: medido + interpolado")
    ax.scatter(resultado.estaciones_medidas_m, resultado.cotas_medidas_m,
               s=14, zorder=3, label="Cotas EJE medidas")
    ax.plot(x, r, lw=2.3, label="Rasante de proyecto (preliminar)")
    ax.fill_between(x, t, r, where=t > r, alpha=0.19, label="Corte vertical en eje")
    ax.fill_between(x, t, r, where=r > t, alpha=0.19, label="Relleno vertical en eje")
    ax.set(title="Rasante longitudinal | comparación con terreno EJE",
           xlabel="Abscisa (m)", ylabel="Elevación (m)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    ax.text(0.01, -0.19,
            "Estimación preliminar del eje: NO representa áreas, volúmenes ni curvas verticales.",
            transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(destino, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return destino


def guardar_resumen_txt(resultado: ResultadoRasante, destino: str | Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    x, y, z = (resultado.estaciones_medidas_m, resultado.cotas_medidas_m,
               resultado.cotas_proyecto_en_estaciones_m)
    lineas = [
        "PERFIL VIAL | PREDISEÑO DE RASANTE LONGITUDINAL",
        f"Método: {resultado.metodo}",
        f"Suavizado (si aplica): {resultado.suavizado_pct:.1f} %",
        f"Pendiente máxima indicada: {resultado.pendiente_maxima_pct:.3f} %" if resultado.pendiente_maxima_pct is not None else "Pendiente máxima: SIN LÍMITE INDICADO",
        f"Abscisa inicial: {etiqueta_abscisa(x[0])}, cota EJE medida: {y[0]:.4f} m",
        f"Abscisa final: {etiqueta_abscisa(x[-1])}, cota EJE medida: {y[-1]:.4f} m",
        f"Pendiente media entre extremos: {resultado.pendiente_media_pct:.4f} %",
        f"Pendiente mínima de tramos de proyecto: {np.min(resultado.pendientes_tramos_pct):.4f} %",
        f"Pendiente máxima de tramos de proyecto: {np.max(resultado.pendientes_tramos_pct):.4f} %",
        f"Máximo corte vertical en eje: {resultado.corte_maximo_eje_m:.4f} m",
        f"Máximo relleno vertical en eje: {resultado.relleno_maximo_eje_m:.4f} m",
        "SIGNO: diferencia = rasante - terreno. Positiva = relleno, negativa = corte.",
        "Las cotas inicial y final permanecen idénticas a los valores EJE medidos.",
        "Las cotas intermedias de terreno en la malla se estiman mediante SciPy PCHIP.",
        "El método suavizado minimiza desviación vertical y cambios de pendiente (SLSQP).",
        "ALCANCE: prediseño, no comprueba drenaje ni exigencias normativas.",
        "NO se calculan áreas, volúmenes de corte/relleno ni curvas verticales.",
    ]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return destino
