"""Casos manualmente verificables: no dependen de Flet ni de datos inventados de campo."""
from pathlib import Path
import csv
import math
import numpy as np
import pytest

from app.transversal import (
    ParametrosVia, calcular_via, areas_exactas_lineales, cota_rodadura,
    guardar_cantidades_csv, guardar_via_csv,
)
from app.sumideros import Sumidero, evaluar_sumideros
from app.alcantarillado import (
    Pozo, Tramo, Interferencia, ParametrosZanja, calcular_red,
    guardar_red_tramos, guardar_red_cartera, guardar_red_cantidades,
)
from app.rasante import ResultadoRasante


def archivo_secciones(tmp_path: Path, alturas=(100,100), offsets=(-2,0,2)):
    ruta=tmp_path/'entrada.csv'
    with ruta.open('w',newline='',encoding='utf8') as f:
        w=csv.writer(f)
        w.writerow(['Abscisa']+[str(x) for x in offsets])
        for x,z in zip((0,10),alturas):w.writerow([f'K0+{x:03d}']+[z]*len(offsets))
    return ruta


def resultado_rasante(cotas):
    x=np.array([0.,10.]);z=np.array(cotas,dtype=float)
    return ResultadoRasante(x,z,z,x,z,z,np.zeros_like(x),np.diff(z)*10,'constante',80.,None)


def test_integracion_corte_y_relleno_con_cruce_exacta():
    c,r=areas_exactas_lineales(np.array([-1.,1.]),np.array([1.,-1.]),np.array([0.,0.]))
    assert c==pytest.approx(.5)
    assert r==pytest.approx(.5)


def test_via_cantidades_de_relleno_geometrico(tmp_path):
    archivo=archivo_secciones(tmp_path)
    p=ParametrosVia(2,2,0,base_m=0,asfalto_m=0)
    via=calcular_via(archivo,resultado_rasante([102,102]),p)
    assert via.resumen['relleno_geometrico_m3']==pytest.approx(80)
    assert via.resumen['excavacion_m3']==pytest.approx(0)
    assert len(via.secciones)==2
    assert guardar_via_csv(via,tmp_path/'via.csv').exists()


def test_via_volumen_capas_independiente_del_suministro(tmp_path):
    p=ParametrosVia(2,2,0,asfalto_m=.1,base_m=.8,subbase_m=.2,
                    incremento_suministro_pct=10)
    via=calcular_via(archivo_secciones(tmp_path),resultado_rasante([100,100]),p)
    assert via.resumen['asfalto_compactado_m3']==pytest.approx(4.)
    assert via.resumen['base_compactada_m3']==pytest.approx(32.)
    assert via.resumen['base_suministro_estimado_m3']==pytest.approx(35.2)
    assert guardar_cantidades_csv(via,tmp_path/'cantidad.csv').exists()


def test_via_un_costado_no_impone_eje_maximo():
    p=ParametrosVia(2,2,2,'derecha')
    assert cota_rodadura(100,-2,p)==pytest.approx(100.04)
    assert cota_rodadura(100,2,p)==pytest.approx(99.96)
    p2=ParametrosVia(2,2,2,'dos_aguas')
    assert cota_rodadura(100,-2,p2)==pytest.approx(99.96)
    assert cota_rodadura(100,2,p2)==pytest.approx(99.96)


def test_via_sin_extrapolacion_fuera_de_secciones(tmp_path):
    with pytest.raises(ValueError,match='no cubre'):
        calcular_via(archivo_secciones(tmp_path),resultado_rasante([100,100]),
                    ParametrosVia(3,3,2))


def test_sumidero_comparacion_rejilla_con_rodadura(tmp_path):
    v=calcular_via(archivo_secciones(tmp_path),resultado_rasante([100,100]),
                  ParametrosVia(2,2,2))
    s=Sumidero('S1',5,'DER',1,99.95)
    r=evaluar_sumideros(v,[s])[0]
    assert r['cota_rodadura_calculada_m']==pytest.approx(99.98)
    assert r['diferencia_rejilla_menos_rodadura_m']==pytest.approx(-.03)


def crear_tramo(x0=0,x1=11.7,material='PVC'):
    a=Pozo('P1',x0,100.,98.2,98.0,'salida')
    b=Pozo('P2',x1,99.,97.2,97.0,'entrada')
    return Tramo(a,b,material,'PLUVIAL')


def test_red_diametro_exterior_real_y_tubos():
    r=calcular_red([crear_tramo()],ParametrosZanja())
    a=r.tramos[0]
    assert a['diametro_exterior_m']==pytest.approx(.2)
    assert a['diametro_exterior_pulg']==pytest.approx(.2/.0254)
    assert a['ancho_zanja_m']==pytest.approx(.8)
    assert a['pendiente_batea_pct']==pytest.approx(100/11.7)
    assert a['tubos_completos_o_cortados']==2
    assert a['ultimo_tubo_m']==pytest.approx(5.85)
    assert a['excavacion_m3']==pytest.approx(.8*11.7*2.1)


def test_red_cartera_por_tubos_csv(tmp_path):
    r=calcular_red([crear_tramo()],ParametrosZanja())
    archivo=guardar_red_cartera(r,tmp_path/'cartera.csv')
    with archivo.open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==2
    assert float(rows[-1]['Longitud_efectiva_m'])==pytest.approx(5.85)
    assert guardar_red_tramos(r,tmp_path/'tramos.csv').exists()
    assert guardar_red_cantidades(r,tmp_path/'cantidades.csv').exists()


def test_red_interferencia_sobre_tubo_y_superposicion():
    cr=Interferencia(1,5.85,'gas',98.9,98.8)
    r=calcular_red([crear_tramo()],ParametrosZanja(),[cr])
    assert r.interferencias[0]['holgura_vertical_con_signo_m']==pytest.approx(1.1)
    cr2=Interferencia(1,5.85,'telecom',97.8,97.6)
    r2=calcular_red([crear_tramo()],ParametrosZanja(),[cr2])
    assert r2.interferencias[0]['holgura_vertical_con_signo_m']<0


def test_red_rechaza_diametros_inconsistentes():
    t=crear_tramo()
    mala=Pozo('P2',11.7,99,97.3,97,'entrada')
    with pytest.raises(ValueError,match='diámetros'):
        calcular_red([Tramo(t.inicio,mala)],ParametrosZanja())


def test_red_rechaza_flujo_invertido():
    t=crear_tramo()
    with pytest.raises(ValueError,match='SALIDA'):
        calcular_red([Tramo(Pozo('P1',0,100,98.2,98,'entrada'),t.fin)],ParametrosZanja())


def test_red_advertencia_pendiente_adversa():
    a=Pozo('P1',0,100,98.2,98,'salida')
    b=Pozo('P2',10,100,98.7,98.5,'entrada')
    r=calcular_red([Tramo(a,b)],ParametrosZanja())
    assert any('NO baja' in x for x in r.advertencias)


def test_validaciones_parametros():
    with pytest.raises(ValueError): ParametrosVia(2,2,33).validar()
    with pytest.raises(ValueError): ParametrosZanja(longitud_efectiva_tubo_m=0).validar()
    with pytest.raises(ValueError): ParametrosVia(2,2,2,tipo_pendiente='na').validar()
