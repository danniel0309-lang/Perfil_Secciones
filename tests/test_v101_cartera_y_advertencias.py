"""Regresiones de V10.1: cartera inmediata y pendientes no bloqueantes."""
from pathlib import Path
import ast
import csv

import numpy as np
import pytest

from app.rasante import calcular_rasante
from app.transversal import (ParametrosVia, calcular_via_bv,
                             guardar_cartera_preliminar_bv, guardar_cartera_vial_bv,
                             guardar_control_drenaje)
from app.sumideros import Sumidero, evaluar_sumideros

EJEMPLO = Path(__file__).resolve().parents[1]/'examples'/'secciones_ejemplo.csv'


def test_calcular_rasante_permite_generar_cartera_preliminar_sin_inventar_anchos(tmp_path):
    r=calcular_rasante(EJEMPLO,20,'constante')
    f=guardar_cartera_preliminar_bv(EJEMPLO,r,tmp_path/'cartera_ideal_tres_cotas.csv')
    with f.open(encoding='utf-8-sig',newline='') as fh:
        filas=list(csv.DictReader(fh))
    assert len(filas)==21
    assert filas[0]['EJE PROYECTO (m)']=='2540.0000'
    assert filas[0]['BV IZQ EXISTENTE (m)']=='2539.9610'
    assert filas[0]['BV DER EXISTENTE (m)']=='2539.9600'
    assert filas[0]['BV IZQ PROYECTO (m)']==''
    assert filas[0]['BV DER PROYECTO (m)']==''
    assert filas[0]['VOLUMEN CORTE HASTA SIGUIENTE (m3)']==''
    assert filas[0]['PAR IZQ EXISTENTE SIN MODIFICAR (m)']=='2539.7190'
    assert 'PRELIMINAR' in filas[0]['Estado']
    assert filas[-1]['PENDIENTE LONG EJE AL SIGUIENTE (%)']==''


def test_cartera_completa_y_drenaje_con_pendiente_insuficiente_no_bloquea(tmp_path):
    r=calcular_rasante(EJEMPLO,20,'constante')
    p=ParametrosVia(3.0,3.25,2.0)
    # Criterio deliberadamente mayor que la pendiente existente del eje
    via=calcular_via_bv(EJEMPLO,r,p,pendiente_minima_pct=10.0)
    assert via.resumen['area_planta_m2']==pytest.approx(2500.0)
    assert via.lineas_drenaje.advertencias
    f=guardar_cartera_vial_bv(via,EJEMPLO,tmp_path/'cartera_ideal_tres_cotas.csv')
    with f.open(encoding='utf-8-sig',newline='') as fh:
        filas=list(csv.DictReader(fh))
    assert all(fila['BV IZQ PROYECTO (m)'] for fila in filas)
    assert all(fila['EJE PROYECTO (m)'] for fila in filas)
    assert all(fila['BV DER PROYECTO (m)'] for fila in filas)
    assert all('REVISIÓN REQUERIDA' in fila['Estado control drenaje'] for fila in filas)
    assert any(float(fila['VOLUMEN CORTE HASTA SIGUIENTE (m3)']) >= 0 for fila in filas)
    csv_alertas=guardar_control_drenaje(via, [],tmp_path/'control_drenaje_vial.csv')
    assert 'ADVERTENCIA DE DRENAJE' in csv_alertas.read_text(encoding='utf-8-sig')


def test_sumidero_aguas_arriba_con_pendiente_incompatible_deja_cartera_y_alertas(tmp_path):
    # Terreno horizontal: la rejilla en la mitad queda POR ENCIMA del BV de bombeo.
    p=tmp_path/'secciones.csv'
    with p.open('w',newline='',encoding='utf-8') as fh:
        w=csv.writer(fh)
        w.writerow(['Abscisa','PAR','SAR','BV','EJE','BV','SAR','PAR'])
        for x in (0,10,20):
            w.writerow([f'K0+{x:03d}',99.7,99.8,100,100,100,99.8,99.7])
    ras=calcular_rasante(p,10,'constante')
    sumideros=[Sumidero('SUM-I',10,'IZQ',None,100.02),Sumidero('SUM-D',10,'DER',None,99.85)]
    via=calcular_via_bv(p,ras,ParametrosVia(2,2,2),sumideros)
    assert via.lineas_drenaje.advertencias
    assert any('no desciende lo suficiente' in a for a in via.lineas_drenaje.advertencias)
    cartera=guardar_cartera_vial_bv(via,p,tmp_path/'c.csv')
    with cartera.open(encoding='utf-8-sig',newline='') as fh:
        data=list(csv.DictReader(fh))
    assert len(data)==3
    assert 'REVISIÓN REQUERIDA' in data[1]['Estado control drenaje']


def test_rasante_boton_usa_generacion_completa_y_preliminar_en_main():
    raiz=Path(__file__).resolve().parents[1]
    arbol=ast.parse((raiz/'main.py').read_text())
    metodos=[n for n in ast.walk(arbol) if isinstance(n,ast.AsyncFunctionDef)
             and n.name=='disenar_rasante']
    assert len(metodos)==1
    llamadas=[n.func.id for n in ast.walk(metodos[0])
              if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert '_guardar_obra_completa' in llamadas
    # En V10.2 no se permite entregar solo la línea del eje como diseño
    # principal: los dos semianchos y los sumideros se leen antes de calcular.
    assert 'guardar_cartera_preliminar_bv' not in llamadas
    assert '_sumideros_del_formulario' in llamadas
