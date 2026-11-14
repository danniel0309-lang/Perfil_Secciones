"""Pruebas de SQLite, independientes de Flet y del motor gráfico."""

import csv
from pathlib import Path

import pytest

from app.db import (
    inicializar_db, guardar_proyecto, listar_proyectos, listar_calculos,
    obtener_calculo, eliminar_proyecto, extraer_calculo, resumen_comparacion,
)


@pytest.fixture
def datos(tmp_path):
    db = tmp_path / "db" / "pruebas.db"
    csv_entrada = tmp_path / "ejemplo.csv"
    csv_entrada.write_text("ABSCISA,EJE\n0,2500\n3,2499\n", encoding="utf-8")
    resultados = tmp_path / "salida"
    resultados.mkdir()
    (resultados / "puntos_bajos.csv").write_text("ID,Abscisa\nPB1,3\n", encoding="utf-8")
    (resultados / "perfil_longitudinal.png").write_bytes(b"PNGFALSO_PARATEST")
    return db, csv_entrada, resultados


def test_crea_tablas_y_guarda_proyecto(datos):
    db, entrada, resultados = datos
    inicializar_db(db)
    pid, cid = guardar_proyecto("Carrera 1", "Nivelación", entrada, resultados, db)
    proyectos = listar_proyectos("Carrera", db)
    assert len(proyectos) == 1
    assert proyectos[0]["id"] == pid
    assert proyectos[0]["total_calculos"] == 1
    calculos = listar_calculos(pid, db)
    assert len(calculos) == 1
    assert calculos[0]["id"] == cid


def test_abrir_restauracion_no_depende_de_salida(datos, tmp_path):
    db, entrada, resultados = datos
    inicializar_db(db)
    _, cid = guardar_proyecto("Prueba", "", entrada, resultados, db)
    entrada.unlink()
    (resultados / "perfil_longitudinal.png").unlink()
    recuperado = obtener_calculo(cid, db)
    assert recuperado is not None
    csv_nuevo, salida_nueva = extraer_calculo(recuperado, tmp_path / "restauracion")
    assert csv_nuevo.read_text() == "ABSCISA,EJE\n0,2500\n3,2499\n"
    assert (salida_nueva / "perfil_longitudinal.png").read_bytes() == b"PNGFALSO_PARATEST"


def test_buscar_parametrizado_y_eliminar_con_cascada(datos):
    db, entrada, resultados = datos
    inicializar_db(db)
    pid, cid = guardar_proyecto("Prueba de red", "tramo especial", entrada, resultados, db)
    assert len(listar_proyectos("especial", db)) == 1
    assert listar_proyectos("' OR 1=1 --", db) == []
    assert eliminar_proyecto(pid, db)
    assert obtener_calculo(cid, db) is None
    assert not eliminar_proyecto(pid, db)


def test_comparacion_entre_calculos_guardados(datos):
    db, entrada, resultados = datos
    inicializar_db(db)
    _, a = guardar_proyecto("A", "", entrada, resultados, db)
    (resultados / "puntos_bajos.csv").write_text(
        "ID,Abscisa\nPB1,3\nPB2,6\n", encoding="utf-8"
    )
    _, b = guardar_proyecto("B", "", entrada, resultados, db)
    comparar = resumen_comparacion(a, b, db)
    assert comparar["puntos_bajos_a"] == 1
    assert comparar["puntos_bajos_b"] == 2


def test_rechazar_proyecto_sin_nombre(datos):
    db, entrada, resultados = datos
    inicializar_db(db)
    with pytest.raises(ValueError, match="nombre"):
        guardar_proyecto("  ", "", entrada, resultados, db)
