"""Regresiones de V9.1: BV reales del lector, sin controles ocultos."""
from pathlib import Path
import pytest
from app.transversal import semianchos_bv_del_csv

EJEMPLO = Path(__file__).resolve().parents[1] / 'examples' / 'secciones_ejemplo.csv'

def test_semianchos_bv_se_obtienen_del_csv():
    izquierdo, derecho = semianchos_bv_del_csv(EJEMPLO)
    assert izquierdo == pytest.approx(2.0)
    assert derecho == pytest.approx(2.0)

def test_sin_bv_reporta_error(tmp_path):
    archivo=tmp_path/'sin_bv.csv'
    archivo.write_text('Abscisa,PAR,EJE,PAR\nK0+000,99,100,99\nK0+020,98,99,98\n')
    with pytest.raises(ValueError, match='BV'):
        semianchos_bv_del_csv(archivo)
