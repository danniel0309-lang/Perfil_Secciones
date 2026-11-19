"""Pruebas del contrato de ingeniería V10: ancho REAL, triple cartera, drenaje."""
from pathlib import Path
import csv
import numpy as np
import pytest

from app.rasante import calcular_rasante
from app.transversal import (ParametrosVia, calcular_via_bv, guardar_cartera_vial_bv,
                             guardar_perfil_tres_cotas_png, guardar_control_drenaje,
                             guardar_cantidades_csv)
from app.sumideros import Sumidero, evaluar_sumideros

EJEMPLO = Path(__file__).resolve().parents[1] / 'examples' / 'secciones_ejemplo.csv'


def csv_minimo(tmp_path, cotas=(100,100), estaciones=(0,20)):
    p=tmp_path/'secciones.csv'
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['Abscisa','PAR','SAR','BV','EJE','BV','SAR','PAR'])
        for x,c in zip(estaciones,cotas):
            w.writerow([f'K0+{x:03d}',c-0.2,c-0.1,c,c,c,c-0.1,c-0.2])
    return p


def test_ancho_indicado_no_se_infiere_y_capas_dependen_de_el(tmp_path):
    p=csv_minimo(tmp_path,(100,99))
    ras=calcular_rasante(p,20,'constante')
    prm=ParametrosVia(3.5,4,2,asfalto_m=.1,base_m=.8,subbase_m=0,rajon_m=0)
    res=calcular_via_bv(p,ras,prm)
    assert res.resumen['ancho_total_m']==pytest.approx(7.5)
    assert res.resumen['area_planta_m2']==pytest.approx(150)
    assert res.resumen['asfalto_compactado_m3']==pytest.approx(15)
    assert res.resumen['base_compactada_m3']==pytest.approx(120)
    assert res.secciones[0]['bv_izq_offset_m']==pytest.approx(-3.5)
    assert res.secciones[0]['bv_der_offset_m']==pytest.approx(4)
    # El diseño conserva los BV medidos en el primer y último punto.
    assert res.secciones[0]['bv_izq_proyecto_m']==pytest.approx(100)
    assert res.secciones[0]['bv_der_proyecto_m']==pytest.approx(100)
    assert res.secciones[-1]['bv_izq_proyecto_m']==pytest.approx(99)
    assert res.secciones[-1]['bv_der_proyecto_m']==pytest.approx(99)


def test_cartera_encabeza_con_tres_cotas_y_conserva_par_sar(tmp_path):
    ras=calcular_rasante(EJEMPLO,20,'constante')
    res=calcular_via_bv(EJEMPLO,ras,ParametrosVia(3,3.25,2))
    p=guardar_cartera_vial_bv(res,EJEMPLO,tmp_path/'cartera.csv')
    with p.open(encoding='utf-8-sig',newline='') as f:
        filas=list(csv.DictReader(f))
    assert len(filas)==21
    assert float(filas[0]['BV IZQ EXISTENTE (m)'])==pytest.approx(2539.961)
    assert float(filas[0]['EJE EXISTENTE (m)'])==pytest.approx(2540)
    assert float(filas[0]['BV DER EXISTENTE (m)'])==pytest.approx(2539.96)
    assert float(filas[0]['BV IZQ PROYECTO (m)'])==pytest.approx(2539.961)
    assert float(filas[0]['EJE PROYECTO (m)'])==pytest.approx(2540)
    assert float(filas[0]['BV DER PROYECTO (m)'])==pytest.approx(2539.96)
    assert float(filas[0]['PAR IZQ EXISTENTE SIN MODIFICAR (m)'])==pytest.approx(2539.719)
    assert float(filas[0]['PAR DER EXISTENTE SIN MODIFICAR (m)'])==pytest.approx(2539.717)
    assert float(filas[0]['PENDIENTE LONG BV IZQ AL SIGUIENTE (%)']) < 0
    assert float(filas[0]['PENDIENTE LONG BV DER AL SIGUIENTE (%)']) < 0
    assert res.resumen['area_planta_m2']==pytest.approx(6.25*400)
    assert guardar_perfil_tres_cotas_png(res,tmp_path/'perfil.png').stat().st_size>3000
    cantidades=guardar_cantidades_csv(res,tmp_path/'cantidades.csv')
    with cantidades.open(encoding='utf-8-sig',newline='') as f:
        by_name={row['Concepto']:row for row in csv.DictReader(f)}
    assert by_name['ancho_total_m']['Unidad']=='m'


def test_sin_sumideros_bordes_lineales_y_sin_minimo(tmp_path):
    p=csv_minimo(tmp_path,(100,99))
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2))
    assert res.secciones[0]['pendiente_bv_izq_hasta_siguiente_pct']==pytest.approx(-5.)
    assert res.secciones[0]['pendiente_bv_der_hasta_siguiente_pct']==pytest.approx(-5.)


def test_sin_sumideros_extremos_horizontales_no_finge_drenaje(tmp_path):
    p=csv_minimo(tmp_path)
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2))
    assert res.lineas_drenaje.advertencias
    assert any('RIESGO DE ENCHARCAMIENTO' in a for a in res.lineas_drenaje.advertencias)
    assert res.resumen['area_planta_m2']==pytest.approx(80)


def test_dos_sumideros_interiores_son_minimos_controlados_y_cubicados(tmp_path):
    p=csv_minimo(tmp_path)
    s=[Sumidero('S-I',10,'IZQ',None,99.85),Sumidero('S-D',10,'DER',None,99.85)]
    res=calcular_via_bv(p,calcular_rasante(p,20),
                       ParametrosVia(2,2,2,asfalto_m=0,base_m=0),s)
    assert res.lineas_drenaje.estaciones_control_m.tolist()==[0.,10.,20.]
    assert np.interp(10,res.lineas_drenaje.estaciones_control_m,
                     res.lineas_drenaje.izquierdo_control_m)==pytest.approx(99.85)
    # Con extremos BV medidos 100.0 m, el corte cambia respecto al
    # modelo antiguo que forzaba 99.96 m en ambos extremos.
    assert res.resumen['excavacion_m3']==pytest.approx(3.0,rel=1e-4)
    assert res.secciones[0]['vol_corte_hasta_siguiente_m3']==pytest.approx(3.0,rel=1e-4)
    resultados=evaluar_sumideros(res,s)
    assert all(abs(x['diferencia_rejilla_menos_rodadura_m'])<1e-8 for x in resultados)
    drenaje=guardar_control_drenaje(res,resultados,tmp_path/'control.csv')
    texto=drenaje.read_text(encoding='utf-8-sig')
    assert 'S-I' in texto and 'S-D' in texto


def test_cota_rejilla_incompatible_se_rechaza(tmp_path):
    p=csv_minimo(tmp_path)
    s=[Sumidero('S-I',10,'IZQ',None,100.03),Sumidero('S-D',10,'DER',None,99.85)]
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2),s)
    assert any('rejilla' in a for a in res.lineas_drenaje.advertencias)
    assert res.resumen['area_planta_m2']==pytest.approx(80)


def test_sumidero_en_un_borde_no_soluciona_el_otro(tmp_path):
    p=csv_minimo(tmp_path)
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2),
                        [Sumidero('S-I',10,'IZQ',None,99.85)])
    assert any('BV DER' in a for a in res.lineas_drenaje.advertencias)


def test_criterio_longitudinal_es_editable_y_no_normativo(tmp_path):
    p=csv_minimo(tmp_path,(100,99.9))
    # Pendiente 0.5% sí, pero si el diseñador requiere 1% no es admisible.
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2),
                       pendiente_minima_pct=1.)
    assert any('insuficiente' in a for a in res.lineas_drenaje.advertencias)
    assert res.resumen['area_planta_m2']==pytest.approx(80)


def test_un_bombeo_solo_hacia_derecha_respeta_sentido(tmp_path):
    p=csv_minimo(tmp_path,(100,99))
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,3,2,'derecha'))
    # El bombeo que choca con los BV fijos debe informarse, no mover los extremos.
    assert res.secciones[0]['bv_izq_proyecto_m']==pytest.approx(100.0)
    assert res.secciones[0]['bv_der_proyecto_m']==pytest.approx(100.0)
    assert any('bombeo real' in a.lower() for a in res.lineas_drenaje.advertencias)


def test_dos_sumideros_por_borde_con_divisoria_y_control(tmp_path):
    p=csv_minimo(tmp_path,(100,100),estaciones=(0,40))
    sumps=[Sumidero(f'S{lado}{x}',x,lado,None,99.85)
           for lado in ('IZQ','DER') for x in (10,30)]
    res=calcular_via_bv(p,calcular_rasante(p,40),
                       ParametrosVia(2,2,2,asfalto_m=0,base_m=0),sumps)
    xx=res.lineas_drenaje.estaciones_control_m
    assert xx.tolist()==[0.,10.,20.,30.,40.]
    zi=res.lineas_drenaje.izquierdo_control_m
    assert zi[1]==pytest.approx(99.85)
    assert zi[3]==pytest.approx(99.85)
    assert zi[2]>zi[1] and zi[2]>zi[3]
    assert res.resumen['excavacion_m3']>0


def test_cartera_tiene_pendientes_transversales_reales(tmp_path):
    p=csv_minimo(tmp_path,(100,100))
    sumps=[Sumidero('SI',10,'IZQ',None,99.85),Sumidero('SD',10,'DER',None,99.85)]
    res=calcular_via_bv(p,calcular_rasante(p,20),ParametrosVia(2,2,2,base_m=0,asfalto_m=0),sumps)
    ruta=guardar_cartera_vial_bv(res,p,tmp_path/'triple.csv')
    with ruta.open(encoding='utf-8-sig',newline='') as f:
        filas=list(csv.DictReader(f))
    # Los valores son los REALES a partir de los BV anclados del CSV,
    # no el bombeo nominal introducido en el formulario.
    assert float(filas[0]['PENDIENTE TRANS REAL EJE A BV IZQ (%)'])==pytest.approx(0.)
    assert float(filas[0]['PENDIENTE TRANS REAL EJE A BV DER (%)'])==pytest.approx(0.)
    assert 'VOLUMEN CORTE HASTA SIGUIENTE (m3)' in filas[0]
