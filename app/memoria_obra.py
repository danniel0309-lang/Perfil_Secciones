"""Memoria Word de prediseño vial o de redes usando plantilla docxtpl.

El informe replica cantidades calculadas, sin proclamar cumplimiento normativo.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
from docx.shared import Cm

RAIZ=Path(__file__).resolve().parent.parent
PLANTILLA=RAIZ/'plantillas'/'memoria_obra.docx'


def _csv_filas(archivo: Path) -> tuple[list[str],list[list[str]]]:
    with archivo.open('r',newline='',encoding='utf-8-sig') as f:
        lector=csv.reader(f)
        filas=list(lector)
    if not filas:
        raise ValueError(f'Archivo vacío: {archivo.name}')
    return filas[0],filas[1:]


def crear_memoria_obra(carpeta: str | Path, nombre_proyecto: str,
                       tipo: str='auto', plantilla: str | Path=PLANTILLA) -> bytes:
    """Devuelve archivo DOCX completo, o error sin sustituir datos originales."""
    try:
        from docxtpl import DocxTemplate, InlineImage
    except ImportError as exc:
        raise RuntimeError('Falta docxtpl; ejecuta: python -m pip install -r requirements.txt') from exc
    carpeta=Path(carpeta)
    if tipo=='auto':
        tipo='red' if (carpeta/'red_cantidades.csv').is_file() else 'via'
    if tipo not in ('via','red'):
        raise ValueError('Tipo debe ser vía o red.')
    if tipo=='red':
        archivo_cantidades=carpeta/'red_cantidades.csv'
        archivo_cartera=carpeta/'red_tramos.csv'
        archivo_grafica=next(iter(sorted(carpeta.glob('red_perfil_tramo_*.png'))), None)
        archivo_nota=carpeta/'red_resumen.txt'
        titulo='Memoria geométrica de alcantarillado'
        metodo=('Tramos independientes entre pozo de SALIDA y pozo de ENTRADA, '
                'con cotas EXTERIORES de batea/lomo; diámetros medidos convertidos a pulgadas '
                'sin seleccionar dimensiones comerciales. Volumen de zanja prismático y cama, '
                'pavimento y rellenos teóricos. Verificar hidráulica, cargas, normativa y obra.')
    else:
        archivo_cantidades=carpeta/'cantidades_via.csv'
        archivo_cartera=carpeta/'volumenes_movimiento_tierras.csv'
        archivo_grafica=carpeta/'transversal_proyecto.png'
        archivo_nota=carpeta/'resumen_via.txt'
        titulo='Memoria de prediseño de vía y cantidades geométricas'
        metodo=('Rasante con extremos fijos, plataforma transversal y comparación '
                'terreno–subrasante. Integración de áreas de corte/relleno entre secciones '
                'medidas mediante el método de áreas extremas. No hay taludes ni validación normativa.')
    if not archivo_cantidades.is_file() or not archivo_cartera.is_file():
        raise FileNotFoundError('Calcula primero las cantidades y carteras del módulo elegido.')
    if not archivo_grafica or not archivo_grafica.is_file():
        raise FileNotFoundError('No se encontró la gráfica del modelo para insertar en Word.')
    _,cantidades=_csv_filas(archivo_cantidades)
    headers,cartera=_csv_filas(archivo_cartera)
    if not cantidades:
        raise ValueError('No existen cantidades para incluir en Word.')
    observaciones=archivo_nota.read_text(encoding='utf8').splitlines() if archivo_nota.is_file() else []
    # Vista verificable de primeras filas; la cartera íntegra sigue exportable en CSV/Excel.
    filas_cartera=[]
    for fila in cartera[:20]:
        filas_cartera.append({'identificador': fila[0] if fila else '',
                              'detalle': ' · '.join(f'{col}={val}' for col,val in zip(headers[1:5],fila[1:5]))})
    plantilla=Path(plantilla)
    if not plantilla.is_file():
        raise FileNotFoundError(f'No existe la plantilla de Word: {plantilla}')
    with TemporaryDirectory(prefix='pv_informe_') as temporal:
        plantilla_doc=DocxTemplate(str(plantilla))
        ctx={
            'titulo': titulo,
            'nombre_proyecto': nombre_proyecto.strip() or 'Proyecto sin nombre',
            'fecha': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'tipo': tipo.upper(),
            'metodo': metodo,
            'fuente_cartera': archivo_cartera.name,
            'fuente_cantidades': archivo_cantidades.name,
            'cantidades': [{'concepto':f[0], 'cantidad':f[1], 'unidad':f[2] if len(f)>2 else ''}
                           for f in cantidades],
            'filas_cartera':filas_cartera,
            'observaciones':[{'texto':linea} for linea in observaciones if linea.strip()][:26],
            'grafica':InlineImage(plantilla_doc,str(archivo_grafica),width=Cm(14.8)),
        }
        plantilla_doc.render(ctx)
        destino=Path(temporal)/'memoria_obra.docx'
        plantilla_doc.save(str(destino))
        return destino.read_bytes()
