"""Convierte filas independientes de formularios en datos geométricos comprobables.

Ningún dato de campo ausente se interpola ni se inventa en este módulo.
"""
from __future__ import annotations

import math
from app.alcantarillado import Pozo, Tramo, Interferencia
from app.sumideros import Sumidero


def _numero(valor, etiqueta: str) -> float:
    try:
        n = float(str(valor if valor is not None else '').strip().replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError(f'{etiqueta}: introduce un número válido.') from None
    if not math.isfinite(n):
        raise ValueError(f'{etiqueta}: el valor debe ser finito.')
    return n


def _nombre(valor, etiqueta: str) -> str:
    nombre = str(valor or '').strip()
    if not nombre:
        raise ValueError(f'{etiqueta}: escribe un nombre.')
    return nombre


def crear_tramos_desde_pozos(pozos: list[dict], conexiones: list[dict]) -> list[Tramo]:
    """Cada pozo intermedio tiene cotas de ENTRADA y SALIDA independientes.

    Con N pozos consecutivos se generan N-1 tramos, conservando el sentido
    creciente de abscisas indicado por el usuario.
    """
    if not 2 <= len(pozos) <= 201:
        raise ValueError('Indica de 2 a 201 pozos para construir los tramos.')
    if len(conexiones) != len(pozos) - 1:
        raise ValueError('Debe existir una configuración por cada tramo entre pozos.')
    tramos = []
    for i, config in enumerate(conexiones):
        origen, destino = pozos[i], pozos[i+1]
        num = i+1
        # Un solo diámetro EXTERIOR por tramo: las cotas de batea se derivan
        # de las cotas de lomo exterior en cada pozo, sin pedir la batea.
        diametro_texto = str(config.get('diametro_exterior_pulg') or '').strip()
        diametro_m = None
        if not diametro_texto and not (
            str(origen.get('batea_salida') or '').strip() or
            str(destino.get('batea_entrada') or '').strip()
        ):
            raise ValueError(f'Tramo {num}: introduce el diámetro exterior en pulgadas.')
        if diametro_texto:
            diametro_pulg = _numero(diametro_texto, f'Tramo {num} diámetro exterior (pulg)')
            if diametro_pulg <= 0:
                raise ValueError(f'Tramo {num}: el diámetro exterior debe ser positivo.')
            diametro_m = diametro_pulg * 0.0254

        def lado(d: dict, indice: int, extremo: str, conexion: str) -> Pozo:
            etiqueta = f'Pozo {indice}'
            lomo = _numero(d.get('lomo_'+extremo), f'{etiqueta} lomo {extremo}')
            if diametro_m is not None:
                batea = lomo - diametro_m
            else:
                # Solo para proyectos/test anteriores que ya guardaron bateas.
                batea = _numero(d.get('batea_'+extremo), f'{etiqueta} batea {extremo}')
            return Pozo(
                _nombre(d.get('nombre'), etiqueta),
                _numero(d.get('abscisa'), f'{etiqueta} abscisa'),
                _numero(d.get('rasante'), f'{etiqueta} cota rasante'),
                lomo, batea, conexion,
            )
        tramo = Tramo(lado(origen, num, 'salida', 'salida'),
                      lado(destino, num+1, 'entrada', 'entrada'),
                      str(config.get('material') or ''), str(config.get('red') or ''))
        tramos.append(tramo)
    return tramos


def crear_sumideros_desde_filas(filas: list[dict]) -> list[Sumidero]:
    sumideros = []
    for i, fila in enumerate(filas, 1):
        if not any(str(fila.get(k) or '').strip() for k in
                   ('nombre', 'abscisa', 'rejilla')):
            continue
        etiqueta = f'Sumidero {i}'
        rasante = str(fila.get('rasante') or '').strip()
        desplazamiento = str(fila.get('desplazamiento') or '').strip()
        sumideros.append(Sumidero(
            _nombre(fila.get('nombre'), etiqueta),
            _numero(fila.get('abscisa'), f'{etiqueta} abscisa'),
            str(fila.get('costado') or '').upper(),
            _numero(desplazamiento, f'{etiqueta} offset') if desplazamiento else None,
            _numero(fila.get('rejilla'), f'{etiqueta} cota rejilla'),
            _numero(rasante, f'{etiqueta} cota rasante') if rasante else None,
        ))
    return sumideros


def crear_interferencias_desde_filas(filas: list[dict]) -> list[Interferencia]:
    cruces = []
    for i, fila in enumerate(filas, 1):
        if not any(str(fila.get(k) or '').strip() for k in
                   ('tramo', 'abscisa', 'superior', 'inferior', 'diametro', 'otro')):
            continue
        etiqueta = f'Interferencia {i}'
        num = _numero(fila.get('tramo'), f'{etiqueta} tramo')
        if not num.is_integer() or num < 1:
            raise ValueError(f'{etiqueta}: indica el número entero del tramo.')
        servicio = str(fila.get('servicio') or '').strip()
        if servicio.upper() == 'OTRO':
            servicio = _nombre(fila.get('otro'), f'{etiqueta} tipo de red')
        else:
            servicio = _nombre(servicio, f'{etiqueta} tipo de red')
        superior = _numero(fila.get('superior'), f'{etiqueta} cota lomo')
        diam_text = str(fila.get('diametro') or '').strip()
        if diam_text:
            diam = _numero(diam_text, f'{etiqueta} diámetro exterior (pulg)')
            if diam <= 0:
                raise ValueError(f'{etiqueta}: diámetro debe ser positivo.')
            inferior = superior - diam * 0.0254
        else:
            # Compatibilidad con formularios de la versión anterior.
            inferior = _numero(fila.get('inferior'), f'{etiqueta} cota inferior')
        cruces.append(Interferencia(int(num),
            _numero(fila.get('abscisa'), f'{etiqueta} abscisa'),
            servicio, superior, inferior))
    return cruces
