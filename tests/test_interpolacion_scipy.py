"""Verificaciones reproducibles de SciPy y memoria docxtpl."""
from pathlib import Path
from zipfile import ZipFile
import io

import numpy as np
import pytest

from app.modelo import muestrear_eje, guardar_muestreo_csv, guardar_muestreo_png

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "secciones_ejemplo.csv"


def test_muestreo_conserva_observaciones():
    r = muestrear_eje(SAMPLE, 3)
    assert len(r.estaciones_campo) == 21
    assert r.estaciones_malla[0] == r.estaciones_campo[0]
    assert r.estaciones_malla[-1] == r.estaciones_campo[-1]
    for x, z in zip(r.estaciones_campo, r.cotas_campo):
        idx = np.flatnonzero(np.isclose(r.estaciones_malla, x, rtol=0, atol=1e-7))
        assert len(idx) == 1
        assert r.cotas_interpoladas[idx[0]] == pytest.approx(z, abs=1e-8)
    assert r.estaciones_malla[0] >= r.estaciones_campo[0]
    assert r.estaciones_malla[-1] <= r.estaciones_campo[-1]


def test_caso_lineal_resuelto_a_mano(tmp_path):
    csv = tmp_path / 'lineal.csv'
    csv.write_text('Abscisa,PAR,SAR,BV,EJE,BV,SAR,PAR\n'
                   'K0+000,8,9,9,10,9,9,8\n'
                   'K0+010,10,11,11,12,11,11,10\n')
    r = muestrear_eje(csv, 5.0)
    indice = np.where(r.estaciones_malla == 5.0)[0][0]
    # 10.0 + (12.0 - 10.0) * (5/10) = 11.0 m
    assert r.cotas_interpoladas[indice] == pytest.approx(11.0)
    assert r.pendiente_por_intervalo_pct[0] == pytest.approx(20.0)


def test_rechaza_malla_invalida():
    with pytest.raises(ValueError):
        muestrear_eje(SAMPLE, 0)
    with pytest.raises(ValueError):
        muestrear_eje(SAMPLE, float('nan'))
    with pytest.raises(ValueError):
        muestrear_eje(SAMPLE, 0.000001)


def test_archivos_resultado(tmp_path):
    r = muestrear_eje(SAMPLE, 3)
    csv = guardar_muestreo_csv(r, tmp_path / 'interpolacion.csv')
    png = guardar_muestreo_png(r, tmp_path / 'interpolacion.png')
    assert csv.is_file() and png.is_file()
    assert 'INTERPOLADA' in csv.read_text(encoding='utf-8-sig')
    assert 'MEDIDA' in csv.read_text(encoding='utf-8-sig')
    assert png.stat().st_size > 1000


def test_memoria_docxtpl_si_esta_instalado():
    pytest.importorskip('docxtpl')
    from app.memoria import crear_memoria
    data = crear_memoria(SAMPLE, 'Ensayo verificable', 3)
    assert data[:2] == b'PK'
    with ZipFile(io.BytesIO(data)) as z:
        xml = z.read('word/document.xml').decode('utf-8')
        assert 'Ensayo verificable' in xml
        assert 'K0+000' in xml
        assert 'w:tbl' in xml
        assert '{{' not in xml and '{%' not in xml
        assert any(name.startswith('word/media/') for name in z.namelist())
