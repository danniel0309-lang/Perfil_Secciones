"""Cobertura de correcciones V9 con cotas de ejemplo, no normas inventadas."""
import csv
from pathlib import Path
import numpy as np
import pytest
from app.rasante import calcular_rasante
from app.transversal import (ParametrosVia, calcular_via_bv,
    guardar_cartera_vial_bv, guardar_control_drenaje)
from app.formularios import (crear_sumideros_desde_filas, crear_interferencias_desde_filas)
from app.alcantarillado import (Pozo, Tramo, ParametrosZanja, calcular_red,
    guardar_red_perfil_general, guardar_red_cartera)

EJEMPLO = Path(__file__).resolve().parents[1] / 'examples' / 'secciones_ejemplo.csv'


def test_cartera_via_preserva_original_y_modifica_solo_bv_eje(tmp_path):
    ras=calcular_rasante(EJEMPLO,20, 'constante')
    via=calcular_via_bv(EJEMPLO,ras,ParametrosVia(6,6,2))
    assert len(via.secciones)==21
    assert via.secciones[0]['ancho_calzada_m']==pytest.approx(12) # ancho explícito 6+6
    archivo=guardar_cartera_vial_bv(via,EJEMPLO,tmp_path/'cartera.csv')
    with archivo.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==21
    assert rows[0]['PAR IZQ EXISTENTE SIN MODIFICAR (m)'] != ''
    assert rows[0]['SAR DER EXISTENTE SIN MODIFICAR (m)'] != ''
    assert rows[0]['BV IZQ PROYECTO (m)'] != ''
    assert float(rows[0]['EJE PROYECTO (m)'])==pytest.approx(2540.0)
    assert via.resumen['area_planta_m2']==pytest.approx(12*400)
    assert via.resumen['excavacion_m3']>=0
    assert via.resumen['relleno_geometrico_m3']>=0
    assert guardar_control_drenaje(via,[],tmp_path/'drenaje.csv').exists()


def test_bv_requeridos_no_inventa_ubicacion(tmp_path):
    p=tmp_path/'mal.csv'
    p.write_text('Abscisa,PAR,EJE,PAR\nK0+000,100,100,100\nK0+010,99,99,99\n')
    ras=calcular_rasante(p,10)
    with pytest.raises(ValueError,match='BV'):
        calcular_via_bv(p,ras,ParametrosVia(6,6,2))


def test_sumidero_sin_offset_usa_bv_y_rejilla(tmp_path):
    from app.sumideros import evaluar_sumideros
    ras=calcular_rasante(EJEMPLO,20)
    via=calcular_via_bv(EJEMPLO,ras,ParametrosVia(6,6,2))
    entrada=crear_sumideros_desde_filas([{'nombre':'S-01','abscisa':'20',
                                         'costado':'DER','rejilla':'2539.5'}])
    assert entrada[0].desplazamiento_m is None
    salida=evaluar_sumideros(via,entrada)
    assert salida[0]['desplazamiento_m']==pytest.approx(6)
    assert salida[0]['cota_rasante_reportada_m']==pytest.approx(2539.5)


def test_cruce_por_lomo_diametro_se_dibuja_y_cartera(tmp_path):
    t=Tramo(Pozo('P1',0,101,99.2,99,'salida'),
            Pozo('P2',20,100,98.2,98,'entrada'),'PVC','PLUVIAL')
    cr=crear_interferencias_desde_filas([{'tramo':'1','abscisa':'10',
        'servicio':'AGUA POTABLE','superior':'100','diametro':'4'}])
    assert cr[0].cota_inferior_m==pytest.approx(100-4*.0254)
    r=calcular_red([t],ParametrosZanja(),cr)
    assert r.interferencias[0]['diametro_exterior_pulg']==pytest.approx(4)
    assert guardar_red_perfil_general(r,tmp_path/'perfil.png').stat().st_size>2000
    cartera=guardar_red_cartera(r,tmp_path/'cartera.csv')
    with cartera.open(encoding='utf-8-sig',newline='') as f:
        filas=list(csv.DictReader(f))
    assert len(filas)==4
    assert 'COTA LOMO INSTALADO medida (m)' in filas[0]
    assert filas[0]['COTA LOMO INSTALADO medida (m)']==''
