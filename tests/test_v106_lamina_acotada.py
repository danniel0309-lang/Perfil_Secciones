"""V10.6: lámina equivalente a referencia, cotas sin mediciones inventadas."""
from pathlib import Path
import pytest
import matplotlib.pyplot as plt
from app.formularios import crear_tramos_desde_pozos
from app.alcantarillado import (calcular_red, guardar_red_png,
                               guardar_red_perfil_general, ParametrosZanja,
                               Interferencia)
from app.lamina_alcantarillado import cobertura_tuberia, cobertura_cruce


def preparar():
    pozos = [
        dict(nombre='PZ-01',abscisa='0',rasante='103',lomo_salida='101.6'),
        dict(nombre='PZ-02',abscisa='30',rasante='102.6',lomo_entrada='101.3',lomo_salida='101.1'),
        dict(nombre='PZ-03',abscisa='60',rasante='102.2',lomo_entrada='100.83'),
    ]
    tramos = [dict(material='PVC',red='PLUVIAL',diametro_exterior_pulg='8'),
              dict(material='CONCRETO',red='PLUVIAL',diametro_exterior_pulg='12')]
    datos=crear_tramos_desde_pozos(pozos,tramos)
    cruce=Interferencia(1,12,'GAS',101.95,101.95-2*.0254)
    return calcular_red(datos, ParametrosZanja(asfalto_m=.1,base_m=.3,subbase_m=.2,rajon_m=.2), [cruce])


def test_distancias_verticales_medidas_en_cotas_no_simbolos():
    r=preparar()
    assert cobertura_tuberia(r.tramos[0],0)==pytest.approx(103-101.6)
    assert cobertura_tuberia(r.tramos[0],.5)==pytest.approx(1.35)
    assert cobertura_tuberia(r.tramos[1],1)==pytest.approx(102.2-100.83)
    assert cobertura_cruce(r,r.interferencias[0])==pytest.approx((103-.4*.4)-101.95)


def test_lamina_tres_pozos_tabla_leyenda_cruce_dimensiones(tmp_path,monkeypatch):
    r=preparar()
    captured={}
    original=plt.Figure.savefig
    def guardar(self,*args,**kwargs):
        textos=[t.get_text() for ax in self.axes for t in ax.texts]
        captured['texts']=textos
        captured['tables']=[tb for ax in self.axes for tb in ax.tables]
        captured['patches']=[p for ax in self.axes for p in ax.patches]
        return original(self,*args,**kwargs)
    monkeypatch.setattr(plt.Figure,'savefig',guardar)
    archivo=guardar_red_perfil_general(r,tmp_path/'perfil_general.png')
    assert archivo.stat().st_size>200_000
    texto=' '.join(captured['texts'])
    assert 'PZ-01' in texto and 'PZ-02' in texto and 'PZ-03' in texto
    assert 'RASANTE → LOMO' in texto
    assert 'RASANTE → CRUCE' in texto
    assert 'PENDIENTE' in texto and 'PVC' in texto and 'CONCRETO' in texto
    assert 'RAJÓN' in texto and 'ASFALTO' in texto
    assert 'Cota rasante/tapa' in texto and 'Lomo entrada' in texto and 'Lomo salida' in texto
    assert 'Cota batea:' not in texto
    assert len(captured['tables']) == 1
    celdas=captured['tables'][0].get_celld()
    assert celdas[(1,1)].get_text().get_text()=='PZ-01 → PZ-02'
    assert celdas[(2,1)].get_text().get_text()=='PZ-02 → PZ-03'
    assert len(captured['patches'])>30


def test_perfil_por_tramo_conserva_tabla_y_pozo_dos(tmp_path):
    r=preparar()
    for k in range(2):
        f=guardar_red_png(r,tmp_path/f'tramo{k}.png',k)
        assert f.stat().st_size>80_000


def test_sin_cruces_no_inventa_cruces(tmp_path,monkeypatch):
    r=preparar();r.interferencias=[]
    captured=[]
    original=plt.Figure.savefig
    def guardar(self,*args,**kwargs):
        captured.extend(t.get_text() for ax in self.axes for t in ax.texts)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(plt.Figure,'savefig',guardar)
    guardar_red_perfil_general(r,tmp_path/'sin_cruces.png')
    assert not any('RASANTE → CRUCE' in t for t in captured)
