"""Contrato V10.2: cada BV tiene extremos propios; sumideros antes del diseño."""
from pathlib import Path
import ast
import csv

import numpy as np
import pytest

from app.rasante import calcular_rasante
from app.sumideros import Sumidero
from app.transversal import (
    ParametrosVia, calcular_via_bv, guardar_perfiles_originales_con_diseno,
    guardar_via_png, guardar_cartera_vial_bv,
)


def crear_csv(tmp_path):
    p=tmp_path/'secciones.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f)
        w.writerow(['Abscisa','PAR','SAR','BV','EJE','BV','SAR','PAR'])
        w.writerow(['K0+000',100.1,100.2,100.3,100.5,100.4,100.2,100.1])
        w.writerow(['K0+020',99.8,99.9,100.0,100.2,100.05,99.9,99.8])
        w.writerow(['K0+040',99.4,99.5,99.7,99.9,99.65,99.5,99.4])
    return p


def test_cada_linea_conserva_sus_extremos_medidos(tmp_path):
    p=crear_csv(tmp_path)
    via=calcular_via_bv(p,calcular_rasante(p,20,'constante'),ParametrosVia(3.0,3.5,2.0))
    for k_antes,k_despues in (
        ('bv_izq_antes_m','bv_izq_proyecto_m'),
        ('eje_antes_m','cota_eje_rodadura_m'),
        ('bv_der_antes_m','bv_der_proyecto_m'),
    ):
        for i in (0,-1):
            assert via.secciones[i][k_antes]==pytest.approx(via.secciones[i][k_despues])
    assert via.secciones[0]['bv_izq_proyecto_m']==pytest.approx(100.3)
    assert via.secciones[0]['bv_der_proyecto_m']==pytest.approx(100.4)
    assert via.secciones[-1]['bv_izq_proyecto_m']==pytest.approx(99.7)
    assert via.secciones[-1]['bv_der_proyecto_m']==pytest.approx(99.65)


def test_sumidero_no_abscisado_se_incluye_como_control_y_se_cubica(tmp_path):
    p=crear_csv(tmp_path)
    sump=Sumidero('S15',15,'IZQ',None,99.95)
    ras=calcular_rasante(p,20,'constante')
    sin=calcular_via_bv(p,ras,ParametrosVia(3,3,2))
    via=calcular_via_bv(p,ras,ParametrosVia(3,3,2),[sump])
    assert 15 in via.lineas_drenaje.estaciones_control_m
    assert float(np.interp(15,via.lineas_drenaje.estaciones_control_m,
                           via.lineas_drenaje.izquierdo_control_m))==pytest.approx(99.95)
    assert via.secciones[0]['bv_izq_proyecto_m']==sin.secciones[0]['bv_izq_proyecto_m']
    assert via.secciones[-1]['bv_izq_proyecto_m']==sin.secciones[-1]['bv_izq_proyecto_m']
    assert via.resumen['excavacion_m3']!=pytest.approx(sin.resumen['excavacion_m3'])


def test_secciones_y_perfiles_antes_despues_son_imagenes_reales(tmp_path):
    p=crear_csv(tmp_path)
    v=calcular_via_bv(p,calcular_rasante(p,20,'constante'),ParametrosVia(3,3,2))
    a,b=guardar_perfiles_originales_con_diseno(v,p,tmp_path)
    assert 'izquierdo' in a.name and 'derecho' in b.name
    assert all(f.stat().st_size>8000 for f in [a,b])
    for i in range(len(v.secciones)):
        ruta=guardar_via_png(v,tmp_path/f'transversal_diseno_{i+1:03d}.png',i)
        assert ruta.stat().st_size>5000
    cartera=guardar_cartera_vial_bv(v,p,tmp_path/'cartera.csv')
    with cartera.open(newline='',encoding='utf-8-sig') as file:
        filas=list(csv.DictReader(file))
    assert len(filas)==3
    for fila in (filas[0],filas[-1]):
        for item in ('BV IZQ','EJE','BV DER'):
            assert fila[f'{item} EXISTENTE (m)']==fila[f'{item} PROYECTO (m)']


def test_interfaz_sin_suavizado_ni_ubicacion_esquematica():
    txt=(Path(__file__).resolve().parents[1]/'main.py').read_text()
    tree=ast.parse(txt)
    assert 'VERSION_INTERFAZ = "10.7"' in txt
    assert 'ft.DropdownOption(key="suavizada"' not in txt
    assert 'Suavizado (%)' not in txt
    assert 'guardar_sumideros_png(' not in txt
    assert 'Ubicación planimétrica esquemática' not in txt
    assert 'guardar_perfiles_originales_con_diseno' in txt
    # La instancia de la lista de sumideros es anterior al botón calcular rasante.
    mostrar=next(x for x in ast.walk(tree) if isinstance(x,ast.FunctionDef) and x.name=='mostrar_vias')
    cuerpo=ast.get_source_segment(txt,mostrar)
    assert cuerpo.index('lista_sumideros') < cuerpo.index('boton_rasante')
