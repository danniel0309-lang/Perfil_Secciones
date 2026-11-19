"""V10.5: cota batea derivada del lomo y diámetro exterior; cuatro capas."""
import csv
from pathlib import Path
import pytest
from app.formularios import crear_tramos_desde_pozos
from app.alcantarillado import ParametrosZanja, calcular_red, guardar_red_perfil_general, guardar_red_cartera


def entrada_tres_pozos():
    pozos = [
        {"nombre":"PZ-01","abscisa":"0","rasante":"103", "lomo_salida":"101.6"},
        {"nombre":"PZ-02","abscisa":"30","rasante":"102.6", "lomo_entrada":"101.3", "lomo_salida":"101.1"},
        {"nombre":"PZ-03","abscisa":"60","rasante":"102.2", "lomo_entrada":"100.83"},
    ]
    configuracion = [
        {"material":"PVC","red":"PLUVIAL","diametro_exterior_pulg":"8"},
        {"material":"CONCRETO","red":"PLUVIAL","diametro_exterior_pulg":"12"},
    ]
    return crear_tramos_desde_pozos(pozos, configuracion)


def test_no_pide_batea_y_deduce_dos_diametros():
    tramos=entrada_tres_pozos()
    assert len(tramos)==2
    assert tramos[0].inicio.cota_batea_exterior_m == pytest.approx(101.6-8*.0254)
    assert tramos[0].fin.cota_batea_exterior_m == pytest.approx(101.3-8*.0254)
    assert tramos[1].inicio.cota_batea_exterior_m == pytest.approx(101.1-12*.0254)
    assert tramos[1].fin.cota_batea_exterior_m == pytest.approx(100.83-12*.0254)
    assert tramos[0].fin.cota_batea_exterior_m != tramos[1].inicio.cota_batea_exterior_m


def test_calculo_dos_tramos_png_csv_con_rajon(tmp_path):
    parametros=ParametrosZanja(base_m=.3, subbase_m=.2, asfalto_m=.1, rajon_m=.2)
    resultado=calcular_red(entrada_tres_pozos(), parametros)
    assert resultado.tramos[0]['diametro_exterior_pulg'] == pytest.approx(8)
    assert resultado.tramos[1]['diametro_exterior_pulg'] == pytest.approx(12)
    assert resultado.cantidades['rajon_m3'] > 0
    grafico=guardar_red_perfil_general(resultado,tmp_path/'perfil_red_3_pozos.png')
    assert grafico.stat().st_size>5000
    cartera=guardar_red_cartera(resultado,tmp_path/'cartera.csv')
    with cartera.open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert 'RAJÓN (m)' in rows[0]
    assert rows[0]['COTA BATEA EXTERIOR teórica inicio (m)'] != ''
    assert rows[0]['COTA LOMO INSTALADO medida (m)'] == ''


def test_diametro_invalido_y_no_cambia_cotas_originales():
    with pytest.raises(ValueError,match='diámetro exterior debe ser positivo'):
        crear_tramos_desde_pozos([{'nombre':'P1'},{'nombre':'P2'}],
            [{'diametro_exterior_pulg':'-2','red':'PLUVIAL','material':'PVC'}])
    tramos=entrada_tres_pozos()
    assert tramos[1].inicio.cota_lomo_exterior_m == pytest.approx(101.1)
    assert tramos[0].fin.cota_lomo_exterior_m == pytest.approx(101.3)


def test_formulario_nuevo_exige_diametro_no_batea():
    with pytest.raises(ValueError, match='diámetro exterior en pulgadas'):
        crear_tramos_desde_pozos([{'nombre':'P1'}, {'nombre':'P2'}],
                                 [{'red':'PLUVIAL','material':'PVC','diametro_exterior_pulg':''}])
