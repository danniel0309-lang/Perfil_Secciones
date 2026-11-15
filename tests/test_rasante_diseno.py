"""Pruebas para el prediseño longitudinal de la rasante sin modificar mediciones."""
import csv
from pathlib import Path

import numpy as np
import pytest

from app.rasante import (
    calcular_rasante, guardar_rasante_csv, guardar_rasante_png, guardar_resumen_txt,
)

EJEMPLO = Path(__file__).resolve().parents[1] / 'examples' / 'secciones_ejemplo.csv'


def test_pendiente_constante_conserva_extremos_y_no_muta_muestra():
    antes = EJEMPLO.read_bytes()
    r = calcular_rasante(EJEMPLO, 3, 'constante')
    assert EJEMPLO.read_bytes() == antes
    assert r.cotas_proyecto_en_estaciones_m[0] == r.cotas_medidas_m[0]
    assert r.cotas_proyecto_en_estaciones_m[-1] == r.cotas_medidas_m[-1]
    assert np.ptp(r.pendientes_tramos_pct) < 1e-8
    assert r.corte_maximo_eje_m >= 0
    assert r.relleno_maximo_eje_m >= 0


def test_ajuste_suavizado_conserva_extremos_y_no_equivale_a_terreno():
    r = calcular_rasante(EJEMPLO, 3, 'suavizada', 80)
    assert r.cotas_proyecto_en_estaciones_m[0] == r.cotas_medidas_m[0]
    assert r.cotas_proyecto_en_estaciones_m[-1] == r.cotas_medidas_m[-1]
    assert np.any(np.abs(r.cotas_proyecto_en_estaciones_m[1:-1] - r.cotas_medidas_m[1:-1]) > 1e-4)
    assert np.all(np.isfinite(r.cotas_rasante_evaluadas_m))


def test_ajuste_con_limite_pendiente_efectivo():
    r = calcular_rasante(EJEMPLO, 3, 'suavizada', 65, 2.0)
    assert np.max(np.abs(r.pendientes_tramos_pct)) <= 2.00001
    assert r.cotas_proyecto_en_estaciones_m[0] == r.cotas_medidas_m[0]
    assert r.cotas_proyecto_en_estaciones_m[-1] == r.cotas_medidas_m[-1]


def test_extremos_que_requieren_una_pendiente_superior_al_limite():
    r = calcular_rasante(EJEMPLO, 3, 'constante')
    with pytest.raises(ValueError, match='Extremos incompatibles'):
        calcular_rasante(EJEMPLO, 3, 'suavizada', 80, abs(r.pendiente_media_pct) / 2)


def test_diferencia_vertical_indica_corte_y_relleno():
    r = calcular_rasante(EJEMPLO)
    assert np.allclose(r.diferencia_proyecto_menos_terreno_m,
                       r.cotas_rasante_evaluadas_m - r.cotas_terreno_evaluadas_m)
    assert np.any(r.diferencia_proyecto_menos_terreno_m > 0)
    assert np.any(r.diferencia_proyecto_menos_terreno_m < 0)


def test_exportaciones_etiquetan_terreno_y_no_dicen_volumen(tmp_path):
    r = calcular_rasante(EJEMPLO)
    c = guardar_rasante_csv(r, tmp_path / 'rasante_proyecto.csv')
    p = guardar_rasante_png(r, tmp_path / 'rasante_proyecto.png')
    t = guardar_resumen_txt(r, tmp_path / 'rasante_resumen.txt')
    with c.open(encoding='utf-8-sig', newline='') as f:
        filas = list(csv.DictReader(f))
    assert filas[0]['Origen_terreno'] == 'MEDIDA'
    assert any(f['Origen_terreno'] == 'INTERPOLADA' for f in filas)
    assert filas[-1]['Pendiente_proyecto_al_siguiente_punto_pct'] == ''
    assert p.stat().st_size > 3000
    assert 'NO se calculan áreas, volúmenes' in t.read_text(encoding='utf-8')


@pytest.mark.parametrize('metodo,suavizado,limite', [
    ('otra', 80, None), ('suavizada', -1, None),
    ('suavizada', 101, None), ('suavizada', 40, 0),
    ('constante', float('nan'), None),
])
def test_parametros_invalidos(metodo, suavizado, limite):
    with pytest.raises(ValueError):
        calcular_rasante(EJEMPLO, 3, metodo, suavizado, limite)


def test_invalida_falta_eje(tmp_path):
    archivo = tmp_path / 'sin_eje.csv'
    archivo.write_text('Abscisa,PAR,SAR,BV,CL,BV,SAR,PAR\nK0+000,1,1,1,1,1,1,1\nK0+020,2,2,2,2,2,2,2\n')
    with pytest.raises(ValueError, match='Falta cota EJE'):
        calcular_rasante(archivo)


def test_tramos_no_uniformes_con_limite(tmp_path):
    archivo = tmp_path / 'nonuniform.csv'
    archivo.write_text('Abscisa,PAR,SAR,BV,EJE,BV,SAR,PAR\n'
                       'K0+000,10,10,10,10,10,10,10\n'
                       'K0+003,11,11,11,11,11,11,11\n'
                       'K0+013,9,9,9,9,9,9,9\n'
                       'K0+100,10.3,10.3,10.3,10.3,10.3,10.3,10.3\n')
    r = calcular_rasante(archivo, 2, 'suavizada', 75, 5)
    assert np.max(np.abs(r.pendientes_tramos_pct)) < 5.00001
    assert r.cotas_proyecto_en_estaciones_m[-1] == pytest.approx(10.3)
