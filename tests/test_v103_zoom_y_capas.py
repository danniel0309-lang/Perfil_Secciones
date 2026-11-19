"""Pruebas de la visualización detallada V10.3."""
from pathlib import Path
import csv
import numpy as np
import pytest

from app.rasante import calcular_rasante
from app.transversal import (
    ParametrosVia, calcular_via_bv, guardar_via_png, superficies_capas,
)


def test_cuatro_capas_orden_y_espesor_reales():
    p = ParametrosVia(3.2, 3.4, 2.0, asfalto_m=.09, base_m=.25,
                      subbase_m=.22, rajon_m=.35)
    rodadura = np.array([2535.01, 2535.12, 2534.97])
    capas = superficies_capas(rodadura, p)
    assert [c[0] for c in capas] == ['Asfalto', 'Base granular', 'Subbase', 'Rajón']
    assert [c[3] for c in capas] == pytest.approx([.09, .25, .22, .35])
    np.testing.assert_allclose(capas[0][1], rodadura)
    for actual, siguiente in zip(capas[:-1], capas[1:]):
        np.testing.assert_allclose(actual[2], siguiente[1])
    np.testing.assert_allclose(capas[-1][2], rodadura - p.capas_m)


def test_espesores_cero_no_inventan_capas():
    p = ParametrosVia(3, 3, 2, asfalto_m=.08, base_m=.8, subbase_m=0, rajon_m=0)
    capas = superficies_capas(np.array([100., 99.9, 99.8]), p)
    assert [c[0] for c in capas] == ['Asfalto', 'Base granular']


def test_exporta_seccion_grande_con_capas(tmp_path):
    csv_entrada = tmp_path / 'secciones.csv'
    with csv_entrada.open('w', newline='', encoding='utf8') as f:
        w = csv.writer(f)
        w.writerow(['Abscisa','PAR','SAR','BV','EJE','BV','SAR','PAR'])
        w.writerow(['K0+000',101.2,101.1,101,101.05,100.95,100.9,100.8])
        w.writerow(['K0+020',100.6,100.6,100.5,100.55,100.45,100.4,100.3])
    p = ParametrosVia(3.0, 3.1, 2.0, asfalto_m=.1,base_m=.2,subbase_m=.15,rajon_m=.3)
    rasante = calcular_rasante(csv_entrada,20,'constante')
    via = calcular_via_bv(csv_entrada,rasante,p)
    original_excavacion = via.resumen['excavacion_m3']
    png = guardar_via_png(via, tmp_path/'seccion.png', 0)
    assert png.stat().st_size > 20_000
    # El graficador no puede cambiar áreas, volúmenes o cotas de obra.
    assert via.resumen['excavacion_m3'] == original_excavacion
    from PIL import Image
    with Image.open(png) as img:
        assert img.width >= 2300
        assert img.height >= 1200


def test_interfaz_tiene_visor_interactivo_y_controles_zoom():
    codigo = (Path(__file__).resolve().parents[1]/'main.py').read_text()
    assert 'VERSION_INTERFAZ = "10.7"' in codigo
    assert 'ft.InteractiveViewer(' in codigo
    assert 'await visor_grafica.zoom(1.35)' in codigo
    assert 'await visor_grafica.reset()' in codigo
    assert '＋ AMPLIAR' in codigo
