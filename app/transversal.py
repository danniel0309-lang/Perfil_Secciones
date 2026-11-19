"""Prediseño transversal de vía, cubicación geométrica y capas.

Alcance: plataforma sin taludes de corte/relleno; método de áreas extremas
entre secciones medidas. No incluye sobreanchos, drenaje, peraltes, estabilidad,
encuentros o comprobaciones reglamentarias. No altera los datos topográficos.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv

import numpy as np
from perfil_vial.parsing import read_survey
from app.rasante import ResultadoRasante
from app.modelo import etiqueta_abscisa


@dataclass(frozen=True)
class ParametrosVia:
    ancho_izq_m: float
    ancho_der_m: float
    bombeo_pct: float
    tipo_pendiente: str = "dos_aguas"  # dos_aguas, derecha, izquierda
    asfalto_m: float = 0.08
    base_m: float = 0.80
    subbase_m: float = 0.0
    rajon_m: float = 0.0
    incremento_suministro_pct: float = 0.0

    def validar(self):
        valores = [self.ancho_izq_m, self.ancho_der_m, self.bombeo_pct,
                   self.asfalto_m, self.base_m, self.subbase_m, self.rajon_m,
                   self.incremento_suministro_pct]
        if not all(np.isfinite(v) for v in valores):
            raise ValueError("Los parámetros deben ser números finitos.")
        if min(self.ancho_izq_m, self.ancho_der_m) <= 0:
            raise ValueError("Los semianchos izquierdo y derecho deben ser positivos.")
        if self.bombeo_pct < 0 or self.bombeo_pct > 30:
            raise ValueError("La pendiente transversal debe estar entre 0 y 30 %.")
        if any(v < 0 for v in (self.asfalto_m, self.base_m, self.subbase_m, self.rajon_m)):
            raise ValueError("Los espesores de las capas no pueden ser negativos.")
        if not 0 <= self.incremento_suministro_pct <= 100:
            raise ValueError("El incremento de suministro debe estar entre 0 y 100 %.")
        if self.tipo_pendiente not in {"dos_aguas", "derecha", "izquierda"}:
            raise ValueError("Modo transversal desconocido.")

    @property
    def ancho_m(self):
        return self.ancho_izq_m + self.ancho_der_m

    @property
    def capas_m(self):
        return self.asfalto_m + self.base_m + self.subbase_m + self.rajon_m


@dataclass
class ResultadoVia:
    parametros: ParametrosVia
    estaciones_m: np.ndarray
    secciones: list[dict]
    resumen: dict[str, float]


def cota_rodadura(cota_eje_m: float, offset_m: np.ndarray | float, parametros: ParametrosVia):
    """Cota de rodadura, X<0 izquierda, X>0 derecha.

    dos_aguas: eje es la cumbrera; derecha: baja a derecha;
    izquierda: baja a izquierda. En un agua el eje NO es máximo necesariamente.
    """
    o = np.asarray(offset_m, dtype=float)
    p = parametros.bombeo_pct / 100.0
    if parametros.tipo_pendiente == "dos_aguas":
        z = cota_eje_m - p * np.abs(o)
    elif parametros.tipo_pendiente == "derecha":
        z = cota_eje_m - p * o
    else:
        z = cota_eje_m + p * o
    return float(z) if o.ndim == 0 else z


def areas_exactas_lineales(offsets: np.ndarray, terreno: np.ndarray,
                           subrasante: np.ndarray) -> tuple[float, float]:
    """Integra áreas verticales por segmentos lineales, separando intersecciones."""
    d = subrasante - terreno
    dif_i, dif_f = d[:-1], d[1:]
    dx = np.diff(offsets)
    # Donde cambia el signo se añade el punto de cruce exacto, por tramo.
    corte, relleno = 0.0, 0.0
    for a, b, h, l in zip(dif_i, dif_f, dx, offsets[:-1]):
        if a * b < 0:
            f = abs(a) / (abs(a) + abs(b))
            puntos = [(a, 0.0), (0.0, h * f), (b, h)]
            for (v1, x1), (v2, x2) in zip(puntos[:-1], puntos[1:]):
                delta = (v1 + v2) * (x2 - x1) / 2.0
                relleno += max(delta, 0)
                corte += max(-delta, 0)
        else:
            delta = (a + b) * h / 2.0
            relleno += max(delta, 0)
            corte += max(-delta, 0)
    return float(corte), float(relleno)


def calcular_via(csv_entrada: str | Path, rasante: ResultadoRasante,
                 parametros: ParametrosVia) -> ResultadoVia:
    parametros.validar()
    survey = read_survey(csv_entrada)
    estaciones_r = rasante.estaciones_medidas_m
    cotas_r = rasante.cotas_proyecto_en_estaciones_m
    secciones = []
    for sec in survey.sections:
        x = np.asarray(sec.offsets, dtype=float)
        z = np.asarray(sec.elevations, dtype=float)
        if np.any(np.diff(x) <= 0) or not np.all(np.isfinite(z)):
            raise ValueError(f"La sección {sec.label} tiene datos transversales inválidos.")
        izq, der = -parametros.ancho_izq_m, parametros.ancho_der_m
        if x[0] > izq + 1e-9 or x[-1] < der - 1e-9:
            raise ValueError(
                f"La sección {sec.label} no cubre la plataforma [{izq:.2f}, {der:.2f}] m. "
                "Reduce el ancho o completa el levantamiento; no se extrapolan cotas."
            )
        if sec.station < estaciones_r[0] or sec.station > estaciones_r[-1]:
            raise ValueError(f"Estación {sec.label} fuera del intervalo de rasante.")
        x_eval = np.unique(np.concatenate(([izq, 0.0, der], x[(x > izq) & (x < der)])))
        z_terreno = np.interp(x_eval, x, z)
        cota_eje = float(np.interp(sec.station, estaciones_r, cotas_r))
        rodadura = np.asarray(cota_rodadura(cota_eje, x_eval, parametros))
        subrasante = rodadura - parametros.capas_m
        area_corte, area_relleno = areas_exactas_lineales(x_eval, z_terreno, subrasante)
        secciones.append({
            "abscisa": sec.label, "estacion_m": float(sec.station),
            "cota_eje_rodadura_m": cota_eje,
            "x_m": x_eval, "terreno_m": z_terreno,
            "rodadura_m": rodadura, "subrasante_m": subrasante,
            "area_corte_m2": area_corte, "area_relleno_m2": area_relleno,
        })
    if len(secciones) < 2:
        raise ValueError("Se requieren al menos dos secciones para cubicación.")
    estaciones = np.array([s["estacion_m"] for s in secciones])
    if np.any(np.diff(estaciones) <= 0):
        raise ValueError("Las estaciones de las secciones no son crecientes.")
    ds = np.diff(estaciones)
    cortes = np.array([s["area_corte_m2"] for s in secciones])
    rellenos = np.array([s["area_relleno_m2"] for s in secciones])
    corte_m3 = float(np.sum((cortes[:-1] + cortes[1:]) * ds / 2.0))
    relleno_m3 = float(np.sum((rellenos[:-1] + rellenos[1:]) * ds / 2.0))
    superficie_m2 = parametros.ancho_m * float(estaciones[-1] - estaciones[0])
    factor = 1 + parametros.incremento_suministro_pct / 100.0
    resumen = {
        "longitud_m": float(estaciones[-1] - estaciones[0]),
        "area_planta_m2": superficie_m2,
        "excavacion_m3": corte_m3,
        "relleno_geometrico_m3": relleno_m3,
        "asfalto_compactado_m3": superficie_m2 * parametros.asfalto_m,
        "base_compactada_m3": superficie_m2 * parametros.base_m,
        "subbase_compactada_m3": superficie_m2 * parametros.subbase_m,
        "rajon_geometrico_m3": superficie_m2 * parametros.rajon_m,
        "asfalto_suministro_estimado_m3": superficie_m2 * parametros.asfalto_m * factor,
        "base_suministro_estimado_m3": superficie_m2 * parametros.base_m * factor,
        "subbase_suministro_estimado_m3": superficie_m2 * parametros.subbase_m * factor,
        "rajon_suministro_estimado_m3": superficie_m2 * parametros.rajon_m * factor,
    }
    return ResultadoVia(parametros, estaciones, secciones, resumen)


def guardar_via_csv(r: ResultadoVia, destino: str | Path) -> Path:
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Abscisa", "Distancia_m", "Cota_eje_rodadura_m", "Area_corte_m2",
                    "Area_relleno_m2", "Vol_corte_hasta_siguiente_m3", "Vol_relleno_hasta_siguiente_m3"])
        for i, s in enumerate(r.secciones):
            ds = r.secciones[i+1]["estacion_m"] - s["estacion_m"] if i+1 < len(r.secciones) else 0
            v_c = ds*(s["area_corte_m2"]+r.secciones[i+1]["area_corte_m2"])/2 if ds else 0
            v_f = ds*(s["area_relleno_m2"]+r.secciones[i+1]["area_relleno_m2"])/2 if ds else 0
            w.writerow([s["abscisa"], f'{s["estacion_m"]:.3f}', f'{s["cota_eje_rodadura_m"]:.4f}',
                        f'{s["area_corte_m2"]:.4f}', f'{s["area_relleno_m2"]:.4f}',
                        f'{v_c:.4f}', f'{v_f:.4f}'])
    return destino


def guardar_cantidades_csv(r: ResultadoVia, destino: str | Path) -> Path:
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Concepto", "Cantidad", "Unidad", "Método / alcance"])
        for key, val in r.resumen.items():
            unidad = ("m2" if key == "area_planta_m2"
                      else "m" if key == "longitud_m" or key.startswith("ancho_")
                      else "m3")
            aclaracion = ("Plataforma sin taludes; áreas extremas" if key in {"excavacion_m3", "relleno_geometrico_m3"}
                          else "Volumen teórico de capa" if "compactad" in key or "geometrico" in key
                          else "Volumen teórico × (1 + factor editable/100); no es ensayo Proctor")
            w.writerow([key, f"{val:.4f}", unidad, aclaracion])
    return destino


def superficies_capas(rodadura_m: np.ndarray, parametros: ParametrosVia):
    """Superficies de las capas (desde arriba hacia abajo), sin inventar espesores.

    Devuelve nombre, techo, fondo y espesor. Cada techo coincide con el
    fondo de la capa precedente. Una capa de espesor cero no se dibuja.
    Las superficies siguen la polilínea BV IZQ - EJE - BV DER, no un ancho ficticio.
    """
    parametros.validar()
    techo = np.asarray(rodadura_m, dtype=float)
    if techo.ndim != 1 or techo.size < 2 or not np.all(np.isfinite(techo)):
        raise ValueError("La rodadura requiere al menos dos cotas finitas.")
    capas = (
        ("Asfalto", parametros.asfalto_m),
        ("Base granular", parametros.base_m),
        ("Subbase", parametros.subbase_m),
        ("Rajón", parametros.rajon_m),
    )
    resultado = []
    for nombre, espesor in capas:
        fondo = techo - espesor
        if espesor > 0:
            resultado.append((nombre, techo.copy(), fondo.copy(), espesor))
        techo = fondo
    return resultado


def anotaciones_geometria_seccion(seccion: dict, parametros: ParametrosVia) -> dict:
    """Pendientes REALES de EJE hacia cada BV y espesores indicados.

    Una pendiente negativa significa descenso desde el EJE hasta el BV.
    Los espesores son verticales y se miden en metros. No se usa el bombeo
    nominal para rotular una sección que cambió por sumideros o extremos fijos.
    """
    x = np.asarray(seccion["x_m"], dtype=float)
    z = np.asarray(seccion["rodadura_m"], dtype=float)
    indices_eje = np.flatnonzero(np.isclose(x, 0, atol=1e-8, rtol=0))
    if len(indices_eje) != 1 or len(x) < 3 or x[0] >= 0 or x[-1] <= 0:
        raise ValueError("La sección debe contener BV izquierda, EJE y BV derecha.")
    eje = int(indices_eje[0])
    pendientes = (
        100.0 * (z[0] - z[eje]) / (0.0 - x[0]),
        100.0 * (z[-1] - z[eje]) / (x[-1] - 0.0),
    )
    espesores = [(nombre, espesor) for nombre, _, _, espesor in superficies_capas(z, parametros)]
    return {"pendiente_izquierda_pct": float(pendientes[0]),
            "pendiente_derecha_pct": float(pendientes[1]),
            "capas_m": espesores}


def guardar_via_png(r: ResultadoVia, destino: str | Path, indice: int | None = None) -> Path:
    """Sección grande con estratigrafía de proyecto, colores y achurados.

    Las capas son prismas de espesor vertical constante según los datos
    ingresados por el usuario. No se representa una capa cuyo espesor sea cero.
    No se modifica la cubicación: es únicamente una visualización descriptiva.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    s = r.secciones[len(r.secciones) // 2 if indice is None else indice]
    x = np.asarray(s['x_m'], dtype=float)
    terreno = np.asarray(s['terreno_m'], dtype=float)
    rodadura = np.asarray(s['rodadura_m'], dtype=float)
    subrasante = np.asarray(s['subrasante_m'], dtype=float)
    parametros = r.parametros
    capas = superficies_capas(rodadura, parametros)

    # Los colores y los achurados son convenciones gráficas de esta aplicación,
    # no una clasificación obligatoria de materiales ni una norma de dibujo.
    estilos = {
        'Asfalto': ('#373c47', '////', '#242934'),
        'Base granular': ('#dec68c', '...', '#90713f'),
        'Subbase': ('#dfb880', 'xx', '#a27139'),
        'Rajón': ('#a6b4c4', 'OO', '#516577'),
    }
    fig, ax = plt.subplots(figsize=(18.8, 10.0), dpi=170)
    # Reservar un panel lateral PARA las cotas de capas, no encimarlas.
    fig.subplots_adjust(bottom=.25, top=.85, left=.07, right=.74)
    anotaciones = anotaciones_geometria_seccion(s, parametros)

    # El terreno y las superficies se representan en cotas absolutas;
    # Matplotlib adapta el eje vertical para distinguir capas delgadas.
    ax.fill_between(x, terreno, subrasante, where=terreno >= subrasante,
                    color='#f2d9c4', alpha=.68, interpolate=True, zorder=1)
    ax.fill_between(x, terreno, subrasante, where=terreno < subrasante,
                    color='#d3ead8', alpha=.8, interpolate=True, zorder=1)

    for nombre, superior, inferior, espesor in reversed(capas):
        color, hatch, borde = estilos[nombre]
        ax.fill_between(x, inferior, superior, facecolor=color, edgecolor=borde,
                        hatch=hatch, lw=.6, alpha=.94, zorder=3)
        ax.plot(x, inferior, color=borde, lw=.9, zorder=4)

    ax.plot(x, terreno, 'o--', lw=2.1, ms=6.5, color='#1d526c',
            label='Terreno existente (CSV)', zorder=7)
    ax.plot(x, rodadura, 'o-', lw=2.8, ms=6.5, color='#0a66b0',
            label='Rodadura de proyecto', zorder=8)
    ax.plot(x, subrasante, '--', lw=1.9, color='#984d1e',
            label='Subrasante (fondo de las capas)', zorder=7)

    # Referencias BV/EJE/BV, sin fingir offsets reales de PAR y SAR.
    nombres = ('BV IZQ', 'EJE', 'BV DER')
    for i, (xi, antes, despues, nombre) in enumerate(zip(x, terreno, rodadura, nombres)):
        corrimiento = ((10, 18), (0, 18), (-10, 18))[i]
        alineacion = ('left', 'center', 'right')[i]
        ax.annotate(f'{nombre}\nAntes: {antes:.3f} m\nProyecto: {despues:.3f} m',
                    (xi, despues), xytext=corrimiento, textcoords='offset points',
                    ha=alineacion, va='bottom', fontsize=9, zorder=15,
                    bbox=dict(boxstyle='round,pad=.35', fc='white', ec='#cbd4df', alpha=.94))

    # Pendientes transversales medidas SOBRE la rodadura (signo hacia cada BV).
    # Los extremos de cada flecha coinciden con EJE y BV, no con posiciones
    # esquemáticas. Los rótulos no ocultan las bandas de materiales.
    eje_i = int(np.flatnonzero(np.isclose(x, 0.0, atol=1e-8, rtol=0))[0])
    eje_x, eje_z = float(x[eje_i]), float(rodadura[eje_i])
    max_original = float(max(np.max(terreno), np.max(rodadura)))
    min_proyecto = float(min(np.min(subrasante), np.min(terreno)))
    rango_grafico = max(max_original - min_proyecto, 0.5)
    elevacion_flecha = max(.06, rango_grafico * .065)
    for borde_x, borde_z, lado, clave in (
        (float(x[0]), float(rodadura[0]), 'IZQ', 'pendiente_izquierda_pct'),
        (float(x[-1]), float(rodadura[-1]), 'DER', 'pendiente_derecha_pct'),
    ):
        valor = anotaciones[clave]
        medio_x = (eje_x + borde_x) / 2
        medio_z = (eje_z + borde_z) / 2
        ax.annotate('', xy=(borde_x, borde_z + elevacion_flecha),
                    xytext=(eje_x, eje_z + elevacion_flecha),
                    arrowprops=dict(arrowstyle='-|>', color='#164c76', lw=1.6,
                                    mutation_scale=14), zorder=12)
        ax.annotate(f'EJE → BV {lado}: {valor:+.2f} %',
                    xy=(medio_x, medio_z + elevacion_flecha),
                    xytext=(medio_x, max_original + max(.12, rango_grafico * .13)),
                    ha='center', va='bottom', fontsize=10.5, weight='bold',
                    color='#123951', zorder=16,
                    bbox=dict(boxstyle='round,pad=.36', fc='#f0f7fb',
                              ec='#88a5bb', alpha=.98),
                    arrowprops=dict(arrowstyle='-', color='#69899f', lw=.9))

    # Cotas verticales reales en el borde derecho de cada capa. La flecha
    # doble termina en el techo y fondo del material. Para espesores pequeños
    # el rótulo queda en el panel lateral y usa una línea guía independiente.
    x_cota = float(x[-1]) + parametros.ancho_m * .07
    ax.text(1.035, .93, 'ESPESORES DE CAPAS', transform=ax.transAxes,
            ha='left', va='center', fontsize=12, weight='bold',
            color='#183153', clip_on=False)
    for numero, (nombre, superior, inferior, espesor) in enumerate(capas):
        c_super = float(superior[-1]); c_inferior = float(inferior[-1])
        c_media = (c_super + c_inferior) / 2
        color, hatch, borde = estilos[nombre]
        # Líneas auxiliares en cada frontera material.
        for z_cota in (c_super, c_inferior):
            ax.plot([float(x[-1]), x_cota + parametros.ancho_m * .025],
                    [z_cota, z_cota], color=borde, lw=.85,
                    alpha=.85, clip_on=False, zorder=13)
        ax.annotate('', xy=(x_cota, c_super), xytext=(x_cota, c_inferior),
                    annotation_clip=False,
                    arrowprops=dict(arrowstyle='<->', mutation_scale=8,
                                    color=borde, lw=1.7), zorder=13)
        ax.annotate(f'{nombre}\n{espesor:.3f} m (vertical)',
                    xy=(x_cota, c_media), xycoords='data',
                    xytext=(1.035, .83 - numero * .145),
                    textcoords=ax.transAxes, fontsize=10.5,
                    color='white' if nombre == 'Asfalto' else '#15293b',
                    ha='left', va='center',
                    annotation_clip=False, zorder=20,
                    bbox=dict(boxstyle='round,pad=.45', fc=color, ec=borde,
                              alpha=.95),
                    arrowprops=dict(arrowstyle='-', color=borde, lw=1.25,
                                    connectionstyle='angle3,angleA=0,angleB=90'))
    if not capas:
        ax.text(1.035, .83, 'Sin espesores definidos',
                transform=ax.transAxes, ha='left', va='top', fontsize=10,
                color='#52657B', clip_on=False)

    manejadores = [
        Line2D([0], [0], color='#1d526c', marker='o', linestyle='--', lw=2,
               label='Terreno medido'),
        Line2D([0], [0], color='#0a66b0', lw=2.7, label='Rodadura de proyecto'),
        Line2D([0], [0], color='#984d1e', linestyle='--', lw=2,
               label='Subrasante'),
        Patch(fc='#f2d9c4', ec='#caa27c', label='Excavación (área de corte)'),
        Patch(fc='#d3ead8', ec='#78a888', label='Relleno (área de aporte)'),
    ]
    for nombre, ancho in (('Asfalto', parametros.asfalto_m),
                          ('Base granular', parametros.base_m),
                          ('Subbase', parametros.subbase_m),
                          ('Rajón', parametros.rajon_m)):
        color, hatch, borde = estilos[nombre]
        etiqueta = f'{nombre} · {ancho:.2f} m' if ancho else f'{nombre} · 0 m (no definido)'
        manejadores.append(Patch(facecolor=color, edgecolor=borde, hatch=hatch,
                                 label=etiqueta))
    fig.legend(handles=manejadores, loc='lower center', bbox_to_anchor=(.5,.105),
               ncol=3, frameon=True, fontsize=10)

    rango = float(max(np.max(terreno), np.max(rodadura)) -
                  min(np.min(terreno), np.min(subrasante)))
    margen = max(.30, rango * .34)
    ax.set_ylim(float(min(np.min(terreno), np.min(subrasante))) - margen * .65,
                float(max(np.max(terreno), np.max(rodadura))) + margen)
    ax.set_xlim(float(x[0]) - .3, x_cota + parametros.ancho_m * .035)
    ax.set_xticks(x, [f'{xi:+.2f} m' if xi else 'EJE · 0.00 m' for xi in x])
    ax.set_xlabel('Distancia horizontal respecto al EJE (m)', fontsize=12)
    ax.set_ylabel('Cota (m) · escala vertical ampliada para lectura', fontsize=12)
    ax.set_title(f'SECCIÓN {s["abscisa"]}  |  TERRENO Y CAPAS DEL PAVIMENTO',
                 fontsize=17, weight='bold', pad=16)
    ax.grid(alpha=.18, zorder=0)
    fig.text(.5, .024,
             'Flechas: pendientes reales hacia BV (signo + sube, − baja); cotas de espesor vertical. '
             'No se incluyen taludes ni distancias reales PAR/SAR.',
             ha='center', fontsize=9, color='#364d62')
    fig.savefig(destino, dpi=180, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return destino


def guardar_perfiles_originales_con_diseno(via: ResultadoVia, csv_entrada: str | Path,
                                           carpeta: str | Path) -> tuple[Path, Path]:
    """Reproduce las mediciones originales BV/SAR/PAR en cada costado y
    superpone la línea BV proyectada, sin dibujar encima de píxeles del PNG.
    Así todas las curvas utilizan las mismas abscisas y cotas del CSV.
    """
    import matplotlib.pyplot as plt
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    original=read_survey(csv_entrada).sections
    x=via.estaciones_m
    if len(original)!=len(via.secciones):
        raise ValueError('El número de secciones de campo y proyecto no coincide.')
    archivos=[]
    for costado,indice,clave,color,nombre in (
        ('izquierdo',0,'bv_izq_proyecto_m','#176b9e','IZQUIERDO'),
        ('derecho',-1,'bv_der_proyecto_m','#b34f31','DERECHO'),
    ):
        cotas_bv=[];cotas_sar=[];cotas_par=[]
        for sec in original:
            mapa={nombre:[] for nombre in ('BV IZQ','BV DER','SAR IZQ','SAR DER','PAR IZQ','PAR DER')}
            for nom,val in zip(sec.names,sec.elevations):
                if nom in mapa: mapa[nom].append(float(val))
            sufijo='IZQ' if costado=='izquierdo' else 'DER'
            for nombre_col,lista in [('BV',cotas_bv),('SAR',cotas_sar),('PAR',cotas_par)]:
                cotas=mapa[nombre_col+' '+sufijo]
                lista.append(cotas[0] if len(cotas)==1 else float('nan'))
        cotas_proy=np.array([sec[clave] for sec in via.secciones])
        fig,ax=plt.subplots(figsize=(14,7.2))
        ax.plot(x,cotas_par,':',color='#aaaaaa',lw=1.1,label='PAR medido')
        ax.plot(x,cotas_sar,'--',color='#8390a1',lw=1.4,label='SAR medido')
        ax.plot(x,cotas_bv,'o-',color='#63676b',lw=1.7,ms=3.6,label='BV EXISTENTE (CSV)')
        ax.plot(x,cotas_proy,'-',color=color,lw=2.5,label='BV PROYECTO (sobrepuesto)')
        lineas=getattr(via,'lineas_drenaje',None)
        if lineas is not None:
            for sump in lineas.sumideros:
                if (sump.costado.upper()=='IZQ') == (costado=='izquierdo'):
                    ax.scatter([sump.abscisa_m],[sump.cota_rejilla_m],s=65,
                               marker='v',color='#19836d',zorder=5)
                    ax.annotate(sump.nombre,(sump.abscisa_m,sump.cota_rejilla_m),
                                xytext=(4,9),textcoords='offset points',fontsize=8)
        ax.set(title=f'Perfil longitudinal del costado {nombre} | EXISTENTE + PROYECTO',
               xlabel='Abscisa (m)',ylabel='Cota (m)')
        ax.grid(alpha=.25);ax.legend(ncol=2,fontsize=9)
        fig.text(.06,.018,'Datos originales del CSV conservados; proyecto BV anclado a primera y última cota BV. '
                 'Verificar pendientes y evacuación de aguas.',fontsize=8)
        fig.tight_layout(rect=(0,.04,1,1))
        ruta=carpeta/f'perfil_longitudinal_{costado}_comparativo.png'
        fig.savefig(ruta,dpi=145);plt.close(fig)
        archivos.append(ruta)
    return archivos[0],archivos[1]


def guardar_via_resumen(r: ResultadoVia, destino: str | Path) -> Path:
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    p = r.parametros
    lineas = [
        "PERFIL VIAL | CANTIDADES GEOMÉTRICAS DE PREDISEÑO",
        f"Semiancho izquierdo: {p.ancho_izq_m:.3f} m, derecho: {p.ancho_der_m:.3f} m",
        f"Pendiente transversal: {p.bombeo_pct:.3f} %; configuración: {p.tipo_pendiente}",
        f"Capas: asfalto {p.asfalto_m:.3f} m, base {p.base_m:.3f} m, subbase {p.subbase_m:.3f} m, rajón {p.rajon_m:.3f} m",
        f"Incremento supuesto de suministro (NO es el grado Proctor): {p.incremento_suministro_pct:.2f} %",
        "Los volúmenes de corte/relleno son geométricos por secciones extremas, sin taludes ni obras complementarias.",
        "Las capas son prismas uniformes: no contemplan peraltes, alabeos, alcorques, andenes ni desperdicios salvo el incremento explícito.",
        "Las cotas medidas no se modifican. El diseño NO constituye aprobación normativa.",
        "", "RESUMEN",
    ]
    lineas += [f"{k}: {v:.4f}" for k, v in r.resumen.items()]
    alertas=getattr(getattr(r,'lineas_drenaje',None),'advertencias',[])
    lineas += ['', 'ESTADO DEL DRENAJE: '+('REVISIÓN REQUERIDA' if alertas else 'Sin alertas geométricas; NO verificado hidráulicamente')]
    lineas += [f'ADVERTENCIA: {a}' for a in alertas]
    destino.write_text("\n".join(lineas)+"\n", encoding="utf-8")
    return destino


def guardar_balance_png(r: ResultadoVia, destino: str | Path) -> Path:
    import matplotlib.pyplot as plt
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    x = r.estaciones_m
    corte = np.array([s["area_corte_m2"] for s in r.secciones])
    relleno = np.array([s["area_relleno_m2"] for s in r.secciones])
    fig,ax=plt.subplots(figsize=(11.7,5.8))
    ax.plot(x,corte,label="Área de corte (m²)",lw=2)
    ax.plot(x,relleno,label="Área de relleno (m²)",lw=2)
    ax.set(xlabel="Abscisa (m)",ylabel="Área transversal (m²)",
           title="Áreas transversales de movimiento de tierras · sin taludes")
    ax.grid(alpha=.3);ax.legend()
    fig.tight_layout();fig.savefig(destino,dpi=150);plt.close(fig)
    return destino

# --------------------------------------------------------------------------- V10 COTAS BV–EJE–BV Y DRENAJE

def _cotas_bv_eje(sec):
    """Extrae nombres y cotas medidos; no interpreta desplazamientos ficticios."""
    valores = {}
    for n, v in zip(sec.names, sec.elevations):
        if n in {"BV IZQ", "EJE", "BV DER"}:
            if n in valores:
                raise ValueError(f"Cotas duplicadas para {n} en {sec.label}.")
            valores[n] = float(v)
    if set(valores) != {"BV IZQ", "EJE", "BV DER"}:
        raise ValueError(f"Sección {sec.label}: se necesitan BV IZQ, EJE y BV DER.")
    return valores["BV IZQ"], valores["EJE"], valores["BV DER"]


def _puntos_bv(sec):
    """Compatibilidad con los lectores anteriores. Su offset NO mide ancho real."""
    izq = [(x, z) for x,z,nombre in zip(sec.offsets,sec.elevations,sec.names) if nombre == 'BV IZQ']
    der = [(x, z) for x,z,nombre in zip(sec.offsets,sec.elevations,sec.names) if nombre == 'BV DER']
    if len(izq)!=1 or len(der)!=1:
        raise ValueError(f'Faltan BV IZQ o BV DER en {sec.label}.')
    return izq[0],der[0]


def semianchos_bv_del_csv(csv_entrada: str | Path) -> tuple[float,float]:
    """Solo consulta offsets nominales del lector; NO usar para cubicación.

    Si las cabeceras del CSV son descripciones, los offsets se generan por
    separación de columnas y NO representan el ancho físico de la vía.
    """
    secciones=read_survey(csv_entrada).sections
    if not secciones:
        raise ValueError('No hay secciones en el CSV.')
    (xl,_),(xr,_) = _puntos_bv(secciones[0])
    return -float(xl),float(xr)


def _area_en_estacion(ground_izq, ground_eje, ground_der, design_izq, design_eje,
                      design_der, parametros):
    x=np.array([-parametros.ancho_izq_m,0.,parametros.ancho_der_m],dtype=float)
    terrain=np.array([ground_izq,ground_eje,ground_der],dtype=float)
    road=np.array([design_izq,design_eje,design_der],dtype=float)
    bottom=road-parametros.capas_m
    cut,fill=areas_exactas_lineales(x,terrain,bottom)
    return x,terrain,road,bottom,cut,fill


def calcular_via_bv(csv_entrada: str | Path, rasante: ResultadoRasante,
                    parametros: ParametrosVia, sumideros=None,
                    pendiente_minima_pct: float=0.) -> ResultadoVia:
    """Tres rasantes BV IZQ/EJE/BV DER con anchos obligatorios del usuario.

    Movimiento de tierras por polilíneas de tres puntos cada abscisa, sin
    supuestos sobre el ancho del CSV. El método de áreas extremas integra
    también las estaciones de sumideros interpolando el terreno ENTRE mediciones.
    Los puntos intermedios se etiquetan como estimados, no como medidos.
    """
    from app.drenaje_vial import disenar_lineas
    parametros.validar()
    survey=read_survey(csv_entrada)
    secciones_csv=survey.sections
    xs=np.asarray([s.station for s in secciones_csv],dtype=float)
    if len(xs)<2 or np.any(np.diff(xs)<=0):
        raise ValueError('El CSV requiere dos o más abscisas crecientes.')
    datos=np.asarray([_cotas_bv_eje(s) for s in secciones_csv],dtype=float)
    ejep=np.interp(xs,rasante.estaciones_medidas_m,rasante.cotas_proyecto_en_estaciones_m)
    lineas=disenar_lineas(xs,ejep,parametros.ancho_izq_m,parametros.ancho_der_m,
                         parametros.bombeo_pct,parametros.tipo_pendiente,
                         sumideros,pendiente_minima_pct,
                         extremos_bv=(datos[0,0],datos[-1,0],datos[0,2],datos[-1,2]))
    sec_out=[]
    for i,sec in enumerate(secciones_csv):
        left,eje,right=datos[i]
        x,terrain,road,bottom,cut,fill=_area_en_estacion(
            left,eje,right,lineas.izquierdo_m[i],ejep[i],lineas.derecho_m[i],parametros)
        sec_out.append({
            'abscisa':sec.label, 'estacion_m':float(xs[i]),
            'cota_eje_rodadura_m':float(ejep[i]),
            'bv_izq_offset_m':-parametros.ancho_izq_m,
            'bv_der_offset_m':parametros.ancho_der_m,
            'bv_izq_antes_m':float(left), 'eje_antes_m':float(eje),
            'bv_der_antes_m':float(right),
            'bv_izq_proyecto_m':float(lineas.izquierdo_m[i]),
            'bv_der_proyecto_m':float(lineas.derecho_m[i]),
            'ancho_calzada_m':float(parametros.ancho_m),
            'pendiente_trans_izq_real_pct':100*(ejep[i]-lineas.izquierdo_m[i])/parametros.ancho_izq_m,
            'pendiente_trans_der_real_pct':100*(ejep[i]-lineas.derecho_m[i])/parametros.ancho_der_m,
            'x_m':x, 'terreno_m':terrain, 'rodadura_m':road,
            'subrasante_m':bottom,
            'area_corte_m2':cut, 'area_relleno_m2':fill,
            'origen':'MEDIDA: cotas existentes / CALCULADA: cotas proyecto',
            'vol_corte_hasta_siguiente_m3':0.,
            'vol_relleno_hasta_siguiente_m3':0.,
        })
    # Integramos a través de las abscisas de control, incluyendo sumideros.
    x_control=lineas.estaciones_control_m
    area_cut=[];area_fill=[]
    for i,xq in enumerate(x_control):
        ground=np.array([np.interp(xq,xs,datos[:,j]) for j in range(3)])
        proyecto=np.array([lineas.izquierdo_control_m[i],
                           np.interp(xq,xs,ejep),lineas.derecho_control_m[i]])
        *_,c,f=_area_en_estacion(*ground,*proyecto,parametros)
        area_cut.append(c);area_fill.append(f)
    delta=np.diff(x_control)
    cut_segments=(np.asarray(area_cut[:-1])+np.asarray(area_cut[1:]))*delta/2
    fill_segments=(np.asarray(area_fill[:-1])+np.asarray(area_fill[1:]))*delta/2
    for i,sec in enumerate(sec_out[:-1]):
        mask=(x_control[:-1]>=xs[i]-1e-8)&(x_control[1:]<=xs[i+1]+1e-8)
        sec['vol_corte_hasta_siguiente_m3']=float(np.sum(cut_segments[mask]))
        sec['vol_relleno_hasta_siguiente_m3']=float(np.sum(fill_segments[mask]))
        ds=xs[i+1]-xs[i]
        for campo,clave in [('bv_izq_proyecto_m','pendiente_bv_izq_hasta_siguiente_pct'),
                            ('cota_eje_rodadura_m','pendiente_eje_hasta_siguiente_pct'),
                            ('bv_der_proyecto_m','pendiente_bv_der_hasta_siguiente_pct')]:
            sec[clave]=100*(sec_out[i+1][campo]-sec[campo])/ds
    area=float(parametros.ancho_m*(xs[-1]-xs[0]))
    factor=1+parametros.incremento_suministro_pct/100
    resumen={
        'longitud_m':float(xs[-1]-xs[0]), 'ancho_izquierdo_m':parametros.ancho_izq_m,
        'ancho_derecho_m':parametros.ancho_der_m, 'ancho_total_m':parametros.ancho_m,
        'area_planta_m2':area,
        'excavacion_m3':float(np.sum(cut_segments)),
        'relleno_geometrico_m3':float(np.sum(fill_segments)),
        'asfalto_compactado_m3':area*parametros.asfalto_m,
        'base_compactada_m3':area*parametros.base_m,
        'subbase_compactada_m3':area*parametros.subbase_m,
        'rajon_geometrico_m3':area*parametros.rajon_m,
        'asfalto_suministro_estimado_m3':area*parametros.asfalto_m*factor,
        'base_suministro_estimado_m3':area*parametros.base_m*factor,
        'subbase_suministro_estimado_m3':area*parametros.subbase_m*factor,
        'rajon_suministro_estimado_m3':area*parametros.rajon_m*factor,
    }
    result=ResultadoVia(parametros,xs,sec_out,resumen)
    result.lineas_drenaje=lineas
    result.volumenes_estaciones_control={
        'abscisas_m':x_control,'corte_m2':area_cut,'relleno_m2':area_fill,
        'origen':('MEDIDA' if np.any(np.isclose(xs,xq,atol=1e-7,rtol=0))
                  else 'INTERPOLADA' for xq in x_control),
    }
    return result


def _descartar_fila_planta(sec):
    """No cambia ninguna cota original PAR/SAR ni inventa proyecto fuera de BV."""
    return {n:float(v) for n,v in zip(sec.names,sec.elevations)}


def guardar_cartera_vial_bv(via: ResultadoVia, csv_entrada: str | Path, destino: str | Path):
    """Cartera IDEAL: triple cotas en primer plano, volúmenes y resto del CSV."""
    original=read_survey(csv_entrada)
    destino=Path(destino);destino.parent.mkdir(parents=True,exist_ok=True)
    otros=[]
    for sec in original.sections:
        for nombre in sec.names:
            if nombre not in {'BV IZQ','EJE','BV DER'} and nombre not in otros:
                otros.append(nombre)
    trio=['BV IZQ','EJE','BV DER']
    enc=['Abscisa','Distancia_m','Ancho EJE-BV IZQ_m','Ancho EJE-BV DER_m']
    enc += [f'{n} EXISTENTE (m)' for n in trio]
    enc += [f'{n} PROYECTO (m)' for n in trio]
    enc += [f'{n} DIFERENCIA (m)' for n in trio]
    enc += [f'PENDIENTE LONG {n} AL SIGUIENTE (%)' for n in trio]
    enc += ['PENDIENTE TRANS REAL EJE A BV IZQ (%)',
            'PENDIENTE TRANS REAL EJE A BV DER (%)']
    enc += ['AREA CORTE (m2)','AREA RELLENO (m2)',
            'VOLUMEN CORTE HASTA SIGUIENTE (m3)','VOLUMEN RELLENO HASTA SIGUIENTE (m3)']
    enc += [f'{n} EXISTENTE SIN MODIFICAR (m)' for n in otros]
    enc += ['Origen cotas existentes','Estado control drenaje','Alcance']
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(enc)
        for sec,s in zip(original.sections,via.secciones):
            antes=_descartar_fila_planta(sec)
            proy=[s['bv_izq_proyecto_m'],s['cota_eje_rodadura_m'],s['bv_der_proyecto_m']]
            existentes=[antes[n] for n in trio]
            pend=[s.get(k,'') for k in (
                'pendiente_bv_izq_hasta_siguiente_pct',
                'pendiente_eje_hasta_siguiente_pct',
                'pendiente_bv_der_hasta_siguiente_pct')]
            row=[sec.label,f'{s["estacion_m"]:.3f}',f'{via.parametros.ancho_izq_m:.3f}',
                 f'{via.parametros.ancho_der_m:.3f}']
            row += [f'{v:.4f}' for v in existentes]+[f'{v:.4f}' for v in proy]
            row += [f'{(n-o):.4f}' for n,o in zip(proy,existentes)]
            row += [f'{p:.4f}' if p!='' else '' for p in pend]
            row += [f'{s["pendiente_trans_izq_real_pct"]:.4f}',
                    f'{s["pendiente_trans_der_real_pct"]:.4f}']
            row += [f'{s["area_corte_m2"]:.4f}',f'{s["area_relleno_m2"]:.4f}',
                    f'{s["vol_corte_hasta_siguiente_m3"]:.4f}',
                    f'{s["vol_relleno_hasta_siguiente_m3"]:.4f}']
            row += [f'{antes[n]:.4f}' if n in antes else '' for n in otros]
            alertas=getattr(getattr(via,'lineas_drenaje',None),'advertencias',[])
            estado=('REVISIÓN REQUERIDA: '+str(len(alertas))+' advertencia(s) geométricas'
                    if alertas else 'Sin alertas geométricas; drenaje hidráulico NO verificado')
            row += ['COTAS DE CAMPO', estado,
                    'Prediseño BV-EJE-BV: ancho introducido; materiales entre bordes; '
                    'pendiente transversal real puede diferir de la nominal al ajustar sumideros; '
                    'sin taludes ni diseño hidráulico de sumideros.']
            writer.writerow(row)
    return destino


def guardar_cartera_preliminar_bv(csv_entrada: str | Path,
                                 rasante: ResultadoRasante,
                                 destino: str | Path) -> Path:
    """Al calcular solo EJE, genera cartera provisional sin inventar anchos/BV.

    Las tres cotas EXISTENTES se conservan; EJE PROYECTO sí es conocido.
    BV de proyecto, pendientes transversales y volúmenes permanecen vacíos
    hasta que se introduzcan anchos/bombeo y se haga el cálculo completo.
    """
    originales=read_survey(csv_entrada).sections
    x=np.asarray(rasante.estaciones_medidas_m,dtype=float)
    z=np.asarray(rasante.cotas_proyecto_en_estaciones_m,dtype=float)
    destino=Path(destino); destino.parent.mkdir(parents=True,exist_ok=True)
    otros=[]
    for sec in originales:
        for nombre in sec.names:
            if nombre not in {'BV IZQ','EJE','BV DER'} and nombre not in otros:
                otros.append(nombre)
    encabezados=[
        'Abscisa','Distancia_m','BV IZQ EXISTENTE (m)', 'EJE EXISTENTE (m)',
        'BV DER EXISTENTE (m)', 'BV IZQ PROYECTO (m)','EJE PROYECTO (m)',
        'BV DER PROYECTO (m)', 'PENDIENTE LONG BV IZQ AL SIGUIENTE (%)',
        'PENDIENTE LONG EJE AL SIGUIENTE (%)',
        'PENDIENTE LONG BV DER AL SIGUIENTE (%)',
        'AREA CORTE (m2)','AREA RELLENO (m2)',
        'VOLUMEN CORTE HASTA SIGUIENTE (m3)',
        'VOLUMEN RELLENO HASTA SIGUIENTE (m3)',
    ] + [f'{nombre} EXISTENTE SIN MODIFICAR (m)' for nombre in otros] + [
        'Estado', 'Observaciones',
    ]
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f); w.writerow(encabezados)
        for i, sec in enumerate(originales):
            izq,eje,der=_cotas_bv_eje(sec)
            est=float(sec.station)
            z_eje=float(np.interp(est,x,z))
            pend=(100*(float(np.interp(float(originales[i+1].station),x,z))-z_eje)
                  /(float(originales[i+1].station)-est)
                  if i+1<len(originales) else '')
            antes=_descartar_fila_planta(sec)
            row=[sec.label,f'{est:.3f}',f'{izq:.4f}',f'{eje:.4f}',f'{der:.4f}',
                 '',f'{z_eje:.4f}','', '', f'{pend:.4f}' if pend!='' else '',
                 '','','','','']
            row.extend(f'{antes[n]:.4f}' if n in antes else '' for n in otros)
            row += ['PRELIMINAR: falta diseño BV y cubicación',
                    'Introduce ambos anchos EJE-BV y el bombeo; después calcula la vía completa.']
            w.writerow(row)
    return destino


def guardar_perfil_tres_cotas_png(via: ResultadoVia, destino: str | Path) -> Path:
    import matplotlib.pyplot as plt
    destino=Path(destino); destino.parent.mkdir(parents=True,exist_ok=True)
    x=via.estaciones_m
    sec=via.secciones
    fig,ax=plt.subplots(figsize=(13.5,7.8))
    lineas=[
        ('BV izquierda','bv_izq_antes_m','bv_izq_proyecto_m','#2375BE'),
        ('EJE','eje_antes_m','cota_eje_rodadura_m','#292C32'),
        ('BV derecha','bv_der_antes_m','bv_der_proyecto_m','#D45B22'),
    ]
    for nombre,antes,despues,color in lineas:
        ax.plot(x,[s[antes] for s in sec],ls='--',lw=1.5,alpha=.65,
                label=f'{nombre} · existente',color=color)
        ax.plot(x,[s[despues] for s in sec],lw=2.2,label=f'{nombre} · proyecto',color=color)
    drenaje=getattr(via,'lineas_drenaje',None)
    if drenaje:
        for sump in drenaje.sumideros:
            ax.scatter([sump.abscisa_m],[sump.cota_rejilla_m],color='#17644A',s=55,zorder=6)
            ax.annotate(sump.nombre,(sump.abscisa_m,sump.cota_rejilla_m),
                        xytext=(4,8),textcoords='offset points',fontsize=8)
    ax.set(title='Diseño longitudinal: BV izquierda · EJE · BV derecha (3 cotas por abscisa)',
           xlabel='Abscisa (m)',ylabel='Elevación (m)')
    ax.grid(alpha=.28);ax.legend(ncol=2,fontsize=8)
    alertas=getattr(drenaje,'advertencias',[]) if drenaje is not None else []
    nota=(f'ATENCIÓN: {len(alertas)} advertencia(s) geométricas de drenaje. Revisar control_drenaje_vial.csv.'
          if alertas else 'Sin alertas geométricas; capacidad y salida hidráulica NO verificadas.')
    fig.text(.07,.015,'Cotas existentes medidas; proyecto geométrico con anchos introducidos. '
             + nota,fontsize=8)
    fig.tight_layout(rect=(0,.035,1,1));fig.savefig(destino,dpi=145);plt.close(fig)
    return destino


def guardar_control_drenaje(via: ResultadoVia, sumideros: list[dict], destino: str | Path):
    """Pendientes BV en todos los subtramos, hasta cada sumidero y extremo."""
    destino=Path(destino);destino.parent.mkdir(parents=True,exist_ok=True)
    lineas=getattr(via,'lineas_drenaje',None)
    if lineas is None:
        raise ValueError('Primero debes calcular las tres líneas de diseño.')
    x=lineas.estaciones_control_m
    izquierda=lineas.izquierdo_control_m
    derecha=lineas.derecho_control_m
    eje=np.interp(x,via.estaciones_m,[s['cota_eje_rodadura_m'] for s in via.secciones])
    sumideros_existentes={(s['costado'],round(s['abscisa_m'],6)):s['nombre'] for s in sumideros}
    with destino.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f)
        w.writerow(['Abscisa desde','Abscisa hasta','Pendiente BV IZQ (%)',
                    'Pendiente EJE (%)','Pendiente BV DER (%)',
                    'Destino de drenaje','Observaciones geométricas'])
        for i in range(len(x)-1):
            dx=x[i+1]-x[i]
            grades=[100*(z[i+1]-z[i])/dx for z in [izquierda,eje,derecha]]
            destino_agua=[]
            for lado,g in [('IZQ',grades[0]),('DER',grades[2])]:
                menor=x[i+1] if g<0 else x[i]
                local=sumideros_existentes.get((lado,round(float(menor),6)))
                destino_agua.append(f'{lado}: sumidero {local}' if local else
                                    f'{lado}: hacia {menor:.3f} m, comprobar salida')
            obs=[]
            if any(abs(g)<1e-8 for g in (grades[0],grades[2])):
                obs.append('RIESGO: tramo BV horizontal')
            if lineas.pendiente_min_pct and any(abs(g)+1e-6 < lineas.pendiente_min_pct for g in (grades[0],grades[2])):
                obs.append('RIESGO: pendiente BV inferior al criterio indicado')
            w.writerow([f'{x[i]:.3f}',f'{x[i+1]:.3f}']+
                       [f'{g:.4f}' for g in grades]+['; '.join(destino_agua),
                       '; '.join(obs) or 'Geometría verificada; pendiente y capacidad hidráulica NO verificadas'])
        w.writerow([])
        w.writerow(['ESTADO DEL PREDISEÑO','CON ADVERTENCIAS' if lineas.advertencias else 'SIN ALERTAS GEOMÉTRICAS',
                    'No constituye comprobación hidráulica de capacidad ni descarga'])
        for mensaje in lineas.advertencias:
            w.writerow(['ADVERTENCIA DE DRENAJE', mensaje])
        w.writerow([])
        w.writerow(['SUMIDEROS REGISTRADOS','Costado','Rejilla (m)',
                    'BV proyectado (m)','Diferencia rejilla menos BV (m)'])
        for s in sumideros:
            w.writerow([s['nombre'],s['costado'],s['cota_rejilla_m'],
                        f'{s["cota_rodadura_calculada_m"]:.4f}',
                        f'{s["diferencia_rejilla_menos_rodadura_m"]:.4f}'])
    return destino
