"""V10.7: cartera por tubo y rótulos anclados a puntos reales."""
from __future__ import annotations

import csv
from math import isclose

from app.alcantarillado import calcular_red, guardar_red_cartera, ParametrosZanja
from app.formularios import crear_tramos_desde_pozos
from app.lamina_alcantarillado import guardar_lamina_red
import matplotlib.pyplot as plt


def escenario():
    pozos=[
        {"nombre":"PZ1","abscisa":"0","rasante":"102","lomo_salida":"100.5"},
        {"nombre":"PZ2","abscisa":"30","rasante":"101.3", "lomo_entrada":"100.05", "lomo_salida":"99.8"},
        {"nombre":"PZ3","abscisa":"60","rasante":"100.7","lomo_entrada":"99.3"},
    ]
    tubos=[
        {"material":"PVC","red":"PLUVIAL","diametro_exterior_pulg":"8"},
        {"material":"CONCRETO","red":"PLUVIAL","diametro_exterior_pulg":"12"},
    ]
    return calcular_red(crear_tramos_desde_pozos(pozos,tubos), ParametrosZanja(
        cama_triturado_m=.10,base_m=.3,asfalto_m=.1,subbase_m=.2,rajon_m=.2))


def test_cartera_por_tubo_todas_las_cotas_y_prof_excav(tmp_path):
    resultado=escenario()
    archivo=guardar_red_cartera(resultado,tmp_path/'por_tubo.csv')
    with archivo.open(encoding='utf-8-sig',newline='') as f:
        filas=list(csv.DictReader(f))
    assert len(filas)==12  # 6 tubos de 5,85m por cada tramo de 30 m
    for fila in filas:
        assert fila['COTA LOMO INSTALADO medida (m)']==''
        assert fila['FECHA INSTALACIÓN']==''
        for extremo in ('inicio','final'):
            lomo=float(fila[f'COTA LOMO EXTERIOR teórica {extremo} (m)'])
            batea=float(fila[f'COTA BATEA EXTERIOR teórica {extremo} (m)'])
            triturado_superior=float(fila[f'COTA SUPERIOR TRITURADO teórica {extremo} (m)'])
            triturado_inferior=float(fila[f'COTA INFERIOR TRITURADO teórica {extremo} (m)'])
            fondo=float(fila[f'COTA FONDO EXCAVACIÓN teórica {extremo} (m)'])
            profundidad=float(fila[f'PROFUNDIDAD EXCAVACIÓN teórica {extremo} (m)'])
            rasante=float(fila[f'COTA TERRENO / RASANTE {extremo} (m)'])
            diametro=float(fila['DIÁMETRO EXTERIOR (pulg)'])*.0254
            assert isclose(lomo-batea,diametro,abs_tol=.0002)
            assert isclose(batea,triturado_superior,abs_tol=.00011)
            assert isclose(triturado_inferior,fondo,abs_tol=.00011)
            assert isclose(fondo,batea-.10,abs_tol=.00011)
            assert isclose(profundidad,rasante-fondo,abs_tol=.00011)
    # Conexiones intermedias independientes; lomo de entrada no igual a salida
    assert float(filas[5]['COTA LOMO EXTERIOR teórica final (m)'])==100.05
    assert float(filas[6]['COTA LOMO EXTERIOR teórica inicio (m)'])==99.8
    assert float(filas[-1]['LONGITUD INSTALACIÓN (m)']) < 5.85


def test_lamina_rotulos_lomo_ancorados_a_niveles_y_cota_tapa(tmp_path,monkeypatch):
    resultado=escenario()
    anotaciones=[]
    original=plt.Figure.savefig
    def captura(self,*args,**kwargs):
        for ax in self.axes:
            anotaciones.extend([a for a in ax.texts if hasattr(a,'xy')])
        return original(self,*args,**kwargs)
    monkeypatch.setattr(plt.Figure,'savefig',captura)
    archivo=guardar_lamina_red(resultado,tmp_path/'perfil.png')
    assert archivo.stat().st_size>50_000
    rotulos=[a for a in anotaciones if a.get_text().startswith('Lomo ')]
    assert len(rotulos)==4 # primer pozo salida, intermedio entrada/salida, último entrada
    assert {a.get_text() for a in rotulos}=={
        'Lomo salida: 100,500 m','Lomo entrada: 100,050 m',
        'Lomo salida: 99,800 m','Lomo entrada: 99,300 m'}
    assert sorted(round(a.xy[1],3) for a in rotulos)==[99.3,99.8,100.05,100.5]
    tapas=[a for a in anotaciones if a.get_text().startswith('Cota rasante/tapa:')]
    assert len(tapas)==3
    assert sorted(round(a.xy[1],3) for a in tapas)==[100.7,101.3,102]
    assert not any('Cota batea:' in a.get_text() for a in anotaciones)
