"""Garantiza etiquetas por abscisa y cotas reales de espesores/pedientes."""
import ast
from pathlib import Path

import numpy as np
import pytest

from perfil_vial.parsing import read_survey
from app.transversal import ParametrosVia, anotaciones_geometria_seccion, guardar_via_png, calcular_via_bv
from app.rasante import calcular_rasante


def _etiquetado_de_main():
    """Extraer funciones puras sin requerir Flet en el entorno de pruebas."""
    principal = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(principal.read_text(encoding='utf-8'))
    helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {
        'etiquetas_abscisas_graficas', 'nombre_legible'}]
    assert len(helpers) == 2
    espacio = {'Path': Path, 'read_survey': read_survey, 'NOMBRES': {}}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), str(principal), 'exec'), espacio)
    return espacio['etiquetas_abscisas_graficas'], espacio['nombre_legible']


def test_selector_muestra_abscisa_real_para_21_secciones():
    indice, nombre = _etiquetado_de_main()
    origen = Path(__file__).resolve().parents[1] / 'examples/secciones_ejemplo.csv'
    etiquetas = indice(origen)
    assert len([k for k in etiquetas if k.startswith('transversal_diseno_')]) == 21
    assert nombre(Path('transversal_diseno_001.png'), etiquetas) == 'Sección diseñada · K0+000'
    assert nombre(Path('transversal_diseno_011.png'), etiquetas) == 'Sección diseñada · K0+200'
    assert nombre(Path('transversal_diseno_021.png'), etiquetas) == 'Sección diseñada · K0+400'
    assert 'K0+000 a K0+100' in nombre(Path('secciones_p01.png'), etiquetas)
    assert 'K0+360 a K0+400' in nombre(Path('secciones_p04.png'), etiquetas)
    assert 'K0+200' in nombre(Path('transversal_proyecto.png'), etiquetas)


def test_etiqueta_no_inventa_abscisa_sin_csv():
    indice, nombre = _etiquetado_de_main()
    assert indice(None) == {}
    assert indice(Path('/ruta/que/no/existe.csv')) == {}
    assert 'sin abscisa verificable' in nombre(Path('transversal_diseno_001.png'))


def test_pendientes_signadas_y_capas_reales():
    parametros = ParametrosVia(3, 4, 2, asfalto_m=.07, base_m=.18,
                              subbase_m=.22, rajon_m=.35)
    s = {'x_m': np.array([-3., 0., 4.]), 'rodadura_m': np.array([99.94, 100., 100.08])}
    a = anotaciones_geometria_seccion(s, parametros)
    assert a['pendiente_izquierda_pct'] == pytest.approx(-2.0)
    assert a['pendiente_derecha_pct'] == pytest.approx(2.0)
    assert a['capas_m'] == [('Asfalto', .07), ('Base granular', .18),
                           ('Subbase', .22), ('Rajón', .35)]


def test_cero_no_genera_cota_falsa():
    p = ParametrosVia(3,3,1,asfalto_m=.07,base_m=.25,subbase_m=0,rajon_m=0)
    a = anotaciones_geometria_seccion(
        {'x_m': [-3,0,3], 'rodadura_m':[10,10.1,10]},p)
    assert [x[0] for x in a['capas_m']] == ['Asfalto', 'Base granular']


def test_imagen_tiene_textos_cotas_y_pendientes(monkeypatch, tmp_path):
    import matplotlib.pyplot as plt
    ejemplo = Path(__file__).resolve().parents[1] / 'examples/secciones_ejemplo.csv'
    ras = calcular_rasante(ejemplo, 20, 'constante')
    p = ParametrosVia(3.2,3.4,2,asfalto_m=.08,base_m=.30,subbase_m=.22,rajon_m=.30)
    via = calcular_via_bv(ejemplo, ras, p)
    real_close = plt.close
    figs=[]
    monkeypatch.setattr(plt,'close',lambda f: figs.append(f))
    archivo=guardar_via_png(via,tmp_path/'seccion.png',10)
    assert archivo.stat().st_size > 30000
    assert figs
    textos = [t.get_text() for t in figs[0].axes[0].texts]
    assert any('EJE → BV IZQ' in t for t in textos)
    assert any('EJE → BV DER' in t for t in textos)
    assert any('Asfalto\n0.080 m' in t for t in textos)
    assert any('Base granular\n0.300 m' in t for t in textos)
    assert any('Subbase\n0.220 m' in t for t in textos)
    assert any('Rajón\n0.300 m' in t for t in textos)
    real_close(figs[0])
