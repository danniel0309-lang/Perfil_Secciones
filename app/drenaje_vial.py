"""Prediseño de líneas longitudinales BV-I/EJE/BV-D y control geométrico.

NO hace diseño hidráulico de sumideros ni garantiza ausencia de empozamientos.
Se permiten puntos bajos interiores ÚNICAMENTE en el BV con sumidero registrado.
Cuando las cotas de rejilla no son compatibles con el bombeo o el criterio
longitudinal, los cálculos se entregan CON ADVERTENCIAS explícitas, NO como
solución drenante validada.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class LineasDisenadas:
    estaciones_m: np.ndarray
    eje_m: np.ndarray
    izquierdo_m: np.ndarray
    derecho_m: np.ndarray
    estaciones_control_m: np.ndarray
    izquierdo_control_m: np.ndarray
    derecho_control_m: np.ndarray
    sumideros: list
    pendiente_min_pct: float
    advertencias: list[str] = field(default_factory=list)


def _puntos_para_borde(estaciones: np.ndarray, cota_base: np.ndarray,
                       sumideros: list, lado: str, pendiente_min_pct: float):
    """Cota lineal entre extremos o cota por sumideros, sin mínimos sin salida.

    Un sumidero interior es un punto de cota baja; entre dos sumideros hay una
    divisoria (punto alto) cuyo nivel procede de la línea base, no de una norma.
    """
    xs = np.asarray(estaciones, dtype=float)
    zs = np.asarray(cota_base, dtype=float)
    drenajes = sorted((s for s in sumideros if s.costado.upper() == lado),
                      key=lambda s: s.abscisa_m)
    eps = 1e-8
    pendiente = pendiente_min_pct / 100.0
    advertencias = []
    if any(s.abscisa_m <= xs[0] or s.abscisa_m >= xs[-1] for s in drenajes):
        raise ValueError(f"Los sumideros del BV {lado} deben estar entre las abscisas extremas.")
    if any(b.abscisa_m - a.abscisa_m <= eps for a, b in zip(drenajes, drenajes[1:])):
        raise ValueError(f"Hay sumideros repetidos en la misma abscisa del BV {lado}.")
    if not drenajes:
        # Exigir una pendiente lineal: no suponer que la rasante suavizada
        # tiene salida de agua solo porque sea una curva continua.
        z = np.interp(xs, [xs[0], xs[-1]], [zs[0], zs[-1]])
        grado = 100.0 * abs((z[-1] - z[0]) / (xs[-1] - xs[0]))
        if grado <= 1e-7 or grado + 1e-7 < pendiente_min_pct:
            advertencias.append(
                f"BV {lado}: pendiente longitudinal {grado:.4f} %, "
                f"insuficiente para el criterio indicado ({pendiente_min_pct:.4f} %). "
                "RIESGO DE ENCHARCAMIENTO: comprobar salida, rediseñar cotas o introducir sumidero."
            )
        return z, [(float(xs[0]),float(z[0])),(float(xs[-1]),float(z[-1]))], advertencias

    puntos = [(float(xs[0]), float(zs[0]))]
    for i, drenaje in enumerate(drenajes):
        x = float(drenaje.abscisa_m)
        cota = float(drenaje.cota_rejilla_m)
        max_borde = float(np.interp(x, xs, zs))
        if cota > max_borde + 1e-7:
            advertencias.append(
                f"Sumidero {drenaje.nombre} del BV {lado}: rejilla {cota:.4f} m por encima "
                f"del BV correspondiente al bombeo nominal ({max_borde:.4f} m); "
                "revisar pendiente transversal o cota de rejilla."
            )
        if i:
            anterior = drenajes[i-1]
            medio = (float(anterior.abscisa_m) + x)/2
            alto = float(np.interp(medio, xs, zs))
            puntos.append((medio, alto))
        puntos.append((x, cota))
    puntos.append((float(xs[-1]),float(zs[-1])))
    for j, (a,b) in enumerate(zip(puntos, puntos[1:])):
        longitud = b[0]-a[0]
        if longitud <= 0:
            raise ValueError("Orden de sumideros incoherente.")
        grado = (b[1]-a[1])/longitud
        # inicio -> primera rejilla baja; rejilla -> cresta sube;
        # cresta -> rejilla baja; última rejilla -> extremo sube.
        baja_hacia_sumidero = j == 0 or (j % 2 == 0)
        if baja_hacia_sumidero and grado > -max(pendiente,eps) + eps/10:
            advertencias.append(
                f"BV {lado}: entre {a[0]:.2f} y {b[0]:.2f} m la pendiente hacia "
                "el sumidero no desciende lo suficiente. RIESGO DE ENCHARCAMIENTO; "
                "rediseñar cotas o sumideros."
            )
        if not baja_hacia_sumidero and grado < max(pendiente,eps) - eps/10:
            advertencias.append(
                f"BV {lado}: entre {a[0]:.2f} y {b[0]:.2f} m la pendiente "
                "desde el sumidero hacia el punto alto/extremo es incompatible; "
                "RIESGO DE ENCHARCAMIENTO."
            )
    # No permitir cotas por encima de la envolvente que permite el bombeo.
    x_check=np.unique(np.r_[xs, [k[0] for k in puntos]])
    y_check=np.interp(x_check, [k[0] for k in puntos], [k[1] for k in puntos])
    zmax=np.interp(x_check,xs,zs)
    if np.any(y_check > zmax + 1e-7):
        advertencias.append(
            f"BV {lado}: las cotas de sumideros exceden el bombeo nominal en alguna abscisa; "
            "se calculan cantidades, pero el drenaje transversal debe rediseñarse."
        )
    return np.interp(xs,[k[0] for k in puntos], [k[1] for k in puntos]), puntos, advertencias


def disenar_lineas(estaciones, cotas_eje, ancho_izq_m, ancho_der_m,
                   bombeo_pct, tipo_pendiente, sumideros=None,
                   pendiente_minima_pct=0.0, extremos_bv=None) -> LineasDisenadas:
    """Diseña BV-I, EJE, BV-D. Anchos introducidos por el usuario, no inferidos.

    Pendiente mínima es un criterio geométrico del usuario, NO un valor normativo.
    """
    xs=np.asarray(estaciones,dtype=float)
    eje=np.asarray(cotas_eje,dtype=float)
    if len(xs)<2 or np.any(np.diff(xs)<=0) or len(eje)!=len(xs):
        raise ValueError("Se requieren dos o más abscisas crecientes con cotas EJE.")
    vals=(ancho_izq_m,ancho_der_m,bombeo_pct,pendiente_minima_pct)
    if not np.all(np.isfinite(vals)) or min(ancho_izq_m,ancho_der_m)<=0 or pendiente_minima_pct<0:
        raise ValueError("Anchos positivos y pendiente longitudinal mínima no negativa obligatorios.")
    sumideros=list(sumideros or [])
    for s in sumideros:
        if s.costado.upper() not in {'IZQ','DER'}:
            raise ValueError("El costado de los sumideros debe ser IZQ o DER.")
        if not np.isfinite(s.cota_rejilla_m):
            raise ValueError("La cota de rejilla debe ser un número válido.")
        if tipo_pendiente=='derecha' and s.costado.upper()=='IZQ':
            raise ValueError("Con caída transversal a derecha, el BV izquierdo no recibe la escorrentía de la calzada.")
        if tipo_pendiente=='izquierda' and s.costado.upper()=='DER':
            raise ValueError("Con caída transversal a izquierda, el BV derecho no recibe la escorrentía de la calzada.")
    p=bombeo_pct/100.0
    if tipo_pendiente not in {'dos_aguas','derecha','izquierda'}:
        raise ValueError('Sentido de bombeo desconocido.')
    # Los extremos de cada BV son puntos fijos MEDIDOS, independientes
    # del EJE. No recalcular sus cotas a partir de un bombeo nominal.
    if extremos_bv is None:
        # Compatibilidad con el cálculo geométrico independiente antiguo.
        base_izq=eje+(-1 if tipo_pendiente!='derecha' else 1)*p*ancho_izq_m
        base_der=eje+(-1 if tipo_pendiente!='izquierda' else 1)*p*ancho_der_m
    else:
        li,ld,ri,rd=[float(c) for c in extremos_bv]
        if not np.all(np.isfinite([li,ld,ri,rd])):
            raise ValueError('Las cotas extremas BV deben ser finitas.')
        base_izq=np.interp(xs,[xs[0],xs[-1]],[li,ld])
        base_der=np.interp(xs,[xs[0],xs[-1]],[ri,rd])
    izq, puntos_izq, avisos_izq=_puntos_para_borde(xs,base_izq,sumideros,'IZQ',pendiente_minima_pct)
    der, puntos_der, avisos_der=_puntos_para_borde(xs,base_der,sumideros,'DER',pendiente_minima_pct)
    # Las incompatibilidades geométricas se informan, pero NO impiden
    # generar la cartera y los volúmenes. Es un prediseño NO APTO para
    # certificar el drenaje hasta corregir las advertencias.
    advertencias=avisos_izq+avisos_der
    # La continuidad de los extremos puede entrar en conflicto con el
    # bombeo elegido: advertirlo en vez de modificar los puntos anclados.
    pendientes_izq=100*(eje-izq)/ancho_izq_m
    pendientes_der=100*(eje-der)/ancho_der_m
    if tipo_pendiente=='dos_aguas':
        incompatible=np.any(pendientes_izq<=0) or np.any(pendientes_der<=0)
    elif tipo_pendiente=='derecha':
        incompatible=np.any(pendientes_izq>=0) or np.any(pendientes_der<=0)
    else:
        incompatible=np.any(pendientes_izq<=0) or np.any(pendientes_der>=0)
    if incompatible:
        advertencias.append(
            'El bombeo real cambia de sentido o es horizontal en alguna estación. '
            'Los extremos BV medidos se conservaron; revisar el diseño transversal y las descargas.'
        )
    if extremos_bv is not None:
        if not all(np.isclose([izq[0],izq[-1],der[0],der[-1]],
                              [li,ld,ri,rd],atol=1e-8,rtol=0)):
            raise AssertionError('No se conservaron los extremos medidos BV.')
    xs_control=np.unique(np.r_[xs,[k[0] for k in puntos_izq],[k[0] for k in puntos_der]])
    return LineasDisenadas(
        xs,eje,izq,der,xs_control,
        np.interp(xs_control,[k[0] for k in puntos_izq],[k[1] for k in puntos_izq]),
        np.interp(xs_control,[k[0] for k in puntos_der],[k[1] for k in puntos_der]),
        sumideros,pendiente_minima_pct,advertencias,
    )
