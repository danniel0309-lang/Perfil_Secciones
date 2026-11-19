"""Registro y contraste geométrico de sumideros existentes con la rodadura de proyecto."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import numpy as np
from app.transversal import ResultadoVia, cota_rodadura
from app.modelo import etiqueta_abscisa

@dataclass(frozen=True)
class Sumidero:
    nombre: str
    abscisa_m: float
    costado: str  # IZQ o DER
    desplazamiento_m: float | None  # por defecto se infiere de BV del CSV
    cota_rejilla_m: float
    cota_rasante_reportada_m: float | None = None


def evaluar_sumideros(via: ResultadoVia, entradas: list[Sumidero]) -> list[dict]:
    xs = via.estaciones_m
    zz = np.array([s['cota_eje_rodadura_m'] for s in via.secciones])
    resultados = []
    for s in entradas:
        if not s.nombre.strip() or s.costado not in {'IZQ','DER'}:
            raise ValueError("Cada sumidero requiere nombre y costado IZQ o DER.")
        vals = [s.abscisa_m, s.cota_rejilla_m]
        if not all(np.isfinite(x) for x in vals) or (s.desplazamiento_m is not None and (not np.isfinite(s.desplazamiento_m) or s.desplazamiento_m < 0)):
            raise ValueError(f"Datos no válidos del sumidero {s.nombre}.")
        if s.cota_rasante_reportada_m is not None and not np.isfinite(s.cota_rasante_reportada_m):
            raise ValueError("La cota de rasante reportada debe ser finita.")
        if not xs[0] <= s.abscisa_m <= xs[-1]:
            raise ValueError(f"Sumidero {s.nombre} fuera de la abscisa del proyecto.")
        # Ubicación sobre BV con ANCHO REAL introducido por el usuario.
        # Las cotas BV varían a lo largo: deben interpolarse las líneas diseñadas,
        # no reconstruirse con un bombeo fijo a partir del EJE.
        campo_cota = 'bv_izq_proyecto_m' if s.costado == 'IZQ' else 'bv_der_proyecto_m'
        if any(campo_cota not in sec for sec in via.secciones):
            # Compatibilidad con el módulo original calcular_via(), que no
            # incorpora cotas específicas de BV.
            if s.desplazamiento_m is None:
                desplazamiento=(via.parametros.ancho_izq_m if s.costado=='IZQ'
                                else via.parametros.ancho_der_m)
            else:
                desplazamiento=s.desplazamiento_m
            offset=desplazamiento*(-1 if s.costado=='IZQ' else 1)
            rasante=cota_rodadura(float(np.interp(s.abscisa_m,xs,zz)),offset,via.parametros)
            resultados.append({
                'nombre':s.nombre.strip(),'abscisa_m':s.abscisa_m,'costado':s.costado,
                'desplazamiento_m':abs(offset),'cota_rejilla_m':s.cota_rejilla_m,
                'cota_rodadura_calculada_m':rasante,
                'diferencia_rejilla_menos_rodadura_m':s.cota_rejilla_m-rasante,
                'cota_rasante_reportada_m':s.cota_rasante_reportada_m if s.cota_rasante_reportada_m is not None else s.cota_rejilla_m,
            })
            continue
        borde = float(np.interp(s.abscisa_m, xs, [sec[campo_cota] for sec in via.secciones]))
        eje = float(np.interp(s.abscisa_m, xs, zz))
        ancho = via.parametros.ancho_izq_m if s.costado == 'IZQ' else via.parametros.ancho_der_m
        desplazamiento = ancho if s.desplazamiento_m is None else s.desplazamiento_m
        if desplazamiento > ancho + 1e-8:
            raise ValueError(f'Sumidero {s.nombre}: desplazamiento supera el ancho del costado.')
        offset = desplazamiento * (-1 if s.costado == 'IZQ' else 1)
        rasante = eje + (borde-eje) * desplazamiento / ancho
        # La cota debe evaluarse exactamente en la abscisa del sumidero:
        # si no es estación medida, el diseño contiene un nodo adicional.
        if s.desplazamiento_m is None and getattr(via,'lineas_drenaje',None) is not None:
            lineas=via.lineas_drenaje
            values=(lineas.izquierdo_control_m if s.costado=='IZQ' else lineas.derecho_control_m)
            rasante=float(np.interp(s.abscisa_m,lineas.estaciones_control_m,values))
        resultados.append({
            'nombre': s.nombre.strip(), 'abscisa_m': s.abscisa_m, 'costado': s.costado,
            'desplazamiento_m': abs(offset), 'cota_rejilla_m': s.cota_rejilla_m,
            'cota_rodadura_calculada_m': rasante,
            'diferencia_rejilla_menos_rodadura_m': s.cota_rejilla_m - rasante,
            'cota_rasante_reportada_m': s.cota_rasante_reportada_m if s.cota_rasante_reportada_m is not None else s.cota_rejilla_m,
        })
    return resultados


def guardar_sumideros_csv(datos: list[dict], destino: str | Path) -> Path:
    destino = Path(destino); destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['Nombre', 'Abscisa_m', 'Costado', 'Desplazamiento_m', 'Cota_rejilla_m',
                    'Cota_rodadura_proyecto_m', 'Rejilla_menos_rodadura_m', 'Cota_rasante_reportada_m'])
        for x in datos:
            w.writerow([x['nombre'], f"{x['abscisa_m']:.3f}", x['costado'],
                        f"{x['desplazamiento_m']:.3f}", f"{x['cota_rejilla_m']:.4f}",
                        f"{x['cota_rodadura_calculada_m']:.4f}",
                        f"{x['diferencia_rejilla_menos_rodadura_m']:.4f}",
                        '' if x['cota_rasante_reportada_m'] is None else f"{x['cota_rasante_reportada_m']:.4f}"])
    return destino


def guardar_sumideros_png(datos: list[dict], destino: str | Path) -> Path:
    import matplotlib.pyplot as plt
    destino = Path(destino); destino.parent.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(10,5.8))
    for s in datos:
        y = s['desplazamiento_m']*(-1 if s['costado']=='IZQ' else 1)
        ax.scatter([s['abscisa_m']],[y],s=60)
        ax.annotate(s['nombre'],(s['abscisa_m'],y),xytext=(4,5),textcoords='offset points',fontsize=8)
    ax.axhline(0,color='grey',ls='--',lw=1,label='Eje vial')
    ax.set(xlabel='Abscisa (m)',ylabel='Offset transversal (m): IZQ - / DER +',
           title='Ubicación planimétrica esquemática de sumideros')
    ax.grid(alpha=.25);ax.legend()
    fig.tight_layout();fig.savefig(destino,dpi=150);plt.close(fig)
    return destino
