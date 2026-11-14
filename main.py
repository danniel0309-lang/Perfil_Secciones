"""Perfil Vial | visor selectivo y exportacion de resultados.

Compatible con Flet 1.0.4. Conserva el motor original `perfil_vial`.
Los calculos de ingenieria no se modifican en este archivo.

Nuevas dependencias para exportar tablas: openpyxl y python-docx.
"""

import asyncio
import csv
import io
import tempfile
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import matplotlib

matplotlib.use("Agg")

import flet as ft
from perfil_vial.cli import run as ejecutar_perfiles
from app.db import (
    inicializar_db, guardar_proyecto, listar_proyectos, listar_calculos,
    obtener_calculo, eliminar_proyecto, extraer_calculo, resumen_comparacion,
)


RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salida"

AZUL = "#183153"
AZUL_CLARO = "#E8F0FC"
FONDO = "#F4F7FC"
BLANCO = "#FFFFFF"
GRIS = "#52657B"
BORDE = "#DCE5F0"
VERDE = "#146B50"

NOMBRES = {
    "perfil_longitudinal_izquierdo": "Perfil longitudinal · costado izquierdo",
    "perfil_longitudinal_derecho": "Perfil longitudinal · costado derecho",
    "perfil_longitudinal": "Perfil longitudinal general",
    "puntos_bajos": "Puntos bajos y empozamientos",
    "perfil_ideal": "Cartera de rasante ideal",
    "secciones_minimos": "Mínimos de secciones transversales",
    "informe_puntos_bajos": "Informe de puntos bajos",
}


def nombre_legible(archivo: Path) -> str:
    if archivo.stem.startswith("secciones_p"):
        return f"Sección transversal {archivo.stem.split('_')[-1].upper()}"
    return NOMBRES.get(archivo.stem, archivo.stem.replace("_", " ").capitalize())


def orden_grafica(archivo: Path):
    nombre = archivo.stem
    if nombre == "perfil_longitudinal_izquierdo":
        return (0, nombre)
    if nombre == "perfil_longitudinal_derecho":
        return (1, nombre)
    if nombre == "perfil_longitudinal":
        return (2, nombre)
    if nombre.startswith("secciones_p"):
        return (3, nombre)
    if nombre == "puntos_bajos":
        return (4, nombre)
    return (5, nombre)


def leer_tabla(archivo: Path):
    """Devuelve encabezados y filas; no altera cotas, abscisas ni datos de campo."""
    if archivo.suffix.lower() == ".txt":
        lineas = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
        return ["Línea", "Contenido"], [[str(i), linea] for i, linea in enumerate(lineas, 1)]

    texto = archivo.read_text(encoding="utf-8-sig", errors="replace")
    muestra = texto[:8192]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t")
        separador = dialecto.delimiter
    except csv.Error:
        separador = ","

    filas = list(csv.reader(io.StringIO(texto), delimiter=separador))
    if not filas:
        return ["Sin datos"], []
    encabezados = filas[0]
    largo = len(encabezados)
    datos = [(fila + [""] * largo)[:largo] for fila in filas[1:]]
    return encabezados, datos


def excel_numero(valor: str):
    """Convierte cifras decimales a número sin alterar abscisas ni identificadores."""
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", valor.strip()):
        try:
            return float(valor) if "." in valor else int(valor)
        except ValueError:
            pass
    return valor


def generar_excel(archivo: Path) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    encabezados, filas = leer_tabla(archivo)
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Resultados"
    hoja.append(encabezados)
    for fila in filas:
        hoja.append([excel_numero(celda) for celda in fila])
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="183153")
        celda.alignment = Alignment(wrap_text=True)
    for indice, columna in enumerate(hoja.columns, 1):
        valores = [str(c.value or "") for c in list(columna)[:150]]
        maximo = max((len(v) for v in valores), default=12)
        hoja.column_dimensions[get_column_letter(indice)].width = min(max(maximo + 2, 13), 45)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def generar_word(archivo: Path) -> bytes:
    """Exporta tabla o informe a Word; no sustituye la memoria docxtpl del curso."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt

    encabezados, filas = leer_tabla(archivo)
    doc = Document()
    doc.add_heading("PERFIL VIAL | Datos e informe", 0)
    doc.add_paragraph(f"Fuente: {archivo.name}")
    doc.add_paragraph("Los datos corresponden al archivo generado por el programa.")

    if archivo.suffix.lower() == ".txt":
        for _, linea in filas:
            parrafo = doc.add_paragraph(linea)
            for fragmento in parrafo.runs:
                fragmento.font.size = Pt(8)
    else:
        if len(encabezados) > 7:
            seccion = doc.sections[0]
            seccion.orientation = WD_ORIENT.LANDSCAPE
            seccion.page_width, seccion.page_height = Cm(29.7), Cm(21)
        tabla = doc.add_table(rows=1, cols=len(encabezados))
        tabla.style = "Table Grid"
        for i, titulo in enumerate(encabezados):
            tabla.rows[0].cells[i].text = titulo
        for fila in filas:
            celdas = tabla.add_row().cells
            for i, dato in enumerate(fila):
                celdas[i].text = str(dato)
    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


def exportar_pdf_graficas(archivos: list[Path]) -> bytes:
    """Compone un PDF multipágina con los PNG seleccionados, sin recalcular perfiles."""
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    salida = io.BytesIO()
    with PdfPages(salida) as documento:
        for archivo in archivos:
            imagen = mpimg.imread(archivo)
            alto, ancho = imagen.shape[:2]
            figura, eje = plt.subplots(figsize=(11.7, 8.3))
            eje.imshow(imagen, aspect="equal")
            eje.axis("off")
            figura.suptitle(nombre_legible(archivo), fontsize=13, fontweight="bold")
            figura.tight_layout(rect=[0, 0, 1, 0.95])
            documento.savefig(figura, dpi=180)
            plt.close(figura)
    return salida.getvalue()


def comprimir_png(archivos: list[Path]) -> bytes:
    salida = io.BytesIO()
    with ZipFile(salida, "w", ZIP_DEFLATED) as paquete:
        for archivo in archivos:
            paquete.write(archivo, arcname=archivo.name)
    return salida.getvalue()


def tarjeta(contenido: ft.Control):
    return ft.Container(content=contenido, bgcolor=BLANCO, padding=18, border_radius=12)


def main(page: ft.Page):
    inicializar_db()  # CREATE TABLE IF NOT EXISTS en el primer inicio.
    page.title = "Perfil Vial | Ingeniería Civil"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = FONDO
    page.padding = 20

    csv_entrada = None
    carpeta_resultados = SALIDA
    temporales_historial = []  # Mantiene las carpetas de historial mientras la ventana siga abierta.
    graficas = []
    documentos = []
    marcas = {}

    aviso = ft.Text("Selecciona un CSV para comenzar.", color=GRIS)
    archivo_entrada = ft.Text("Ningún archivo seleccionado", color=GRIS)
    resumen = ft.Text("", color=GRIS)
    generar = ft.Button("CALCULAR PERFILES Y SECCIONES", disabled=True)
    selector_grafica = ft.Dropdown(label="Gráfica para visualizar", width=440, options=[])
    imagen = ft.Image(src="", width=880, height=480, fit=ft.BoxFit.CONTAIN, visible=False)
    titulo_vista = ft.Text("Selecciona una gráfica", size=17, weight=ft.FontWeight.BOLD, color=AZUL)
    lista_seleccion = ft.Column(controls=[], spacing=3)
    contador_seleccion = ft.Text("0 gráficas seleccionadas", color=GRIS)
    tipo_grafica = ft.Dropdown(
        label="Formato de exportación",
        value="png",
        width=265,
        options=[ft.DropdownOption(key="png", text="PNG (ZIP si hay varias)"),
                 ft.DropdownOption(key="pdf", text="PDF multipágina")],
    )
    selector_datos = ft.Dropdown(label="Cartera o informe", width=450, options=[])
    vista_datos = ft.Column(controls=[])
    tipo_datos = ft.Dropdown(
        label="Formato de exportación",
        value="xlsx",
        width=220,
        options=[ft.DropdownOption(key="xlsx", text="Excel (.xlsx)"),
                 ft.DropdownOption(key="docx", text="Word (.docx)"),
                 ft.DropdownOption(key="csv", text="CSV (.csv)")],
    )
    aviso_guardar = ft.Text("", color=VERDE)
    nombre_proyecto = ft.TextField(label="Nombre del proyecto", width=340)
    descripcion_proyecto = ft.TextField(label="Descripción (opcional)", width=440)
    aviso_historial = ft.Text("", color=GRIS)
    buscar_proyecto = ft.TextField(label="Buscar por nombre o descripción", width=390)
    lista_historial = ft.Column(controls=[], spacing=9)
    comparacion_resultado = ft.Text("", color=AZUL)
    comparacion_a = ft.Dropdown(label="Proyecto A", width=300, options=[])
    comparacion_b = ft.Dropdown(label="Proyecto B", width=300, options=[])
    guardar_boton = ft.Button("GUARDAR PROYECTO EN HISTORIAL", disabled=True)
    panel = ft.Column(controls=[], expand=True, scroll=ft.ScrollMode.AUTO, spacing=14)

    def limpiar_resultados():
        nonlocal graficas, documentos, marcas
        graficas = []
        documentos = []
        marcas = {}
        lista_seleccion.controls.clear()
        selector_grafica.options = []
        selector_grafica.value = None
        imagen.visible = False
        selector_datos.options = []
        selector_datos.value = None
        vista_datos.controls.clear()
        resumen.value = ""
        aviso_guardar.value = ""

    async def elegir_entrada(e):
        nonlocal csv_entrada, carpeta_resultados
        try:
            elegidos = await ft.FilePicker().pick_files(
                dialog_title="Seleccionar archivo topográfico CSV",
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv"],
            )
            if not elegidos:
                return
            if not elegidos[0].path:
                aviso.value = "No se obtuvo la ruta del archivo."
                page.update()
                return
            csv_entrada = Path(elegidos[0].path)
            carpeta_resultados = SALIDA
            guardar_boton.disabled = True
            archivo_entrada.value = csv_entrada.name
            aviso.value = "Archivo cargado. Puedes iniciar el cálculo."
            generar.disabled = False
            limpiar_resultados()
        except Exception as exc:
            aviso.value = f"No se pudo seleccionar el archivo: {exc}"
        page.update()

    def mostrar_grafica(e=None):
        if not selector_grafica.value:
            imagen.visible = False
            page.update()
            return
        ruta = next((p for p in graficas if p.name == selector_grafica.value), None)
        if ruta and ruta.is_file():
            try:
                imagen.src = ruta.read_bytes()
                imagen.visible = True
                titulo_vista.value = nombre_legible(ruta)
            except OSError as exc:
                imagen.visible = False
                aviso.value = f"No se pudo leer la gráfica: {exc}"
        page.update()

    selector_grafica.on_select = mostrar_grafica

    def actualizar_marcadas(e=None):
        total = sum(bool(c.value) for c in marcas.values())
        contador_seleccion.value = f"{total} de {len(graficas)} gráficas seleccionadas"
        page.update()

    def marcar_todas(e=None):
        for control in marcas.values():
            control.value = True
        actualizar_marcadas()

    def limpiar_marcas(e=None):
        for control in marcas.values():
            control.value = False
        actualizar_marcadas()

    def mostrar_documento(e=None):
        vista_datos.controls.clear()
        ruta = next((p for p in documentos if p.name == selector_datos.value), None)
        if ruta is None:
            vista_datos.controls.append(ft.Text("Selecciona un archivo de datos."))
            page.update()
            return
        try:
            columnas, filas = leer_tabla(ruta)
            if ruta.suffix.lower() == ".txt":
                contenido = "\n".join(fila[1] for fila in filas[:55])
                vista_datos.controls.append(ft.Text(contenido, size=12, color=AZUL))
            else:
                # La vista previa evita saturar la ventana; el archivo exportado está completo.
                columnas_visibles = columnas[:10]
                tabla = ft.DataTable(
                    columns=[ft.DataColumn(ft.Text(c, weight=ft.FontWeight.BOLD))
                             for c in columnas_visibles],
                    rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(x)[:80]))
                                            for x in fila[:10]])
                          for fila in filas[:18]],
                )
                vista_datos.controls.append(ft.Row(controls=[tabla], scroll=ft.ScrollMode.AUTO))
            vista_datos.controls.append(
                ft.Text(f"Vista previa: {min(18, len(filas)) if ruta.suffix.lower() == '.csv' else min(55, len(filas))} de {len(filas)} filas. "
                        "La exportación incluye todos los datos.", color=GRIS, size=12)
            )
        except Exception as exc:
            vista_datos.controls.append(ft.Text(f"No se pudo leer {ruta.name}: {exc}"))
        page.update()

    selector_datos.on_select = mostrar_documento

    def cargar_resultados():
        nonlocal graficas, documentos, marcas
        limpiar_resultados()
        archivos = sorted(p for p in carpeta_resultados.iterdir() if p.is_file())
        graficas = sorted((p for p in archivos if p.suffix.lower() == ".png"), key=orden_grafica)
        documentos = [p for p in archivos if p.suffix.lower() in {".csv", ".txt"}]
        if csv_entrada and csv_entrada.is_file():
            documentos.insert(0, csv_entrada)
        resumen.value = f"{len(graficas)} gráficas · {len(documentos)} archivos de datos e informes"
        selector_grafica.options = [ft.DropdownOption(key=p.name, text=nombre_legible(p)) for p in graficas]
        if graficas:
            selector_grafica.value = graficas[0].name
        for archivo in graficas:
            caja = ft.Checkbox(label=nombre_legible(archivo), value=False, on_change=actualizar_marcadas)
            marcas[archivo.name] = caja
            lista_seleccion.controls.append(caja)
        actualizar_marcadas()
        selector_datos.options = [
            ft.DropdownOption(key=p.name, text=("CSV de entrada · " if p == csv_entrada else "") + nombre_legible(p))
            for p in documentos
        ]
        if documentos:
            selector_datos.value = documentos[0].name
        mostrar_documento()
        mostrar_grafica()

    async def procesar(e):
        nonlocal carpeta_resultados
        if not csv_entrada or not csv_entrada.is_file():
            aviso.value = "Selecciona un CSV válido."
            page.update()
            return
        generar.disabled = True
        guardar_boton.disabled = True
        carpeta_resultados = SALIDA
        aviso.value = "Procesando información topográfica..."
        limpiar_resultados()
        page.update()
        try:
            codigo = await asyncio.to_thread(
                ejecutar_perfiles, [str(csv_entrada), "-o", str(SALIDA)]
            )
            if codigo != 0:
                aviso.value = "El cálculo no terminó correctamente. Revisa la terminal."
                return
            aviso.value = "Cálculos terminados. Selecciona qué deseas consultar o exportar."
            cargar_resultados()
            guardar_boton.disabled = False
            mostrar_graficas()
        except Exception as exc:
            aviso.value = f"Error durante el cálculo: {exc}"
        finally:
            generar.disabled = False
            page.update()

    generar.on_click = procesar

    async def guardar_graficas(e):
        elegidas = [p for p in graficas if marcas[p.name].value and p.is_file()]
        if not elegidas:
            aviso_guardar.value = "Marca al menos una gráfica para exportar."
            page.update()
            return
        try:
            if tipo_grafica.value == "pdf":
                contenido = await asyncio.to_thread(exportar_pdf_graficas, elegidas)
                nombre = "perfiles_seleccionados.pdf"
            elif len(elegidas) == 1:
                contenido = elegidas[0].read_bytes()
                nombre = elegidas[0].name
            else:
                contenido = comprimir_png(elegidas)
                nombre = "graficas_seleccionadas.zip"
            extension = nombre.rsplit(".", 1)[-1]
            ruta = await ft.FilePicker().save_file(
                dialog_title="Guardar gráficas seleccionadas",
                file_name=nombre,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[extension],
                src_bytes=contenido,
            )
            aviso_guardar.value = f"Archivo guardado: {ruta}" if ruta else "Guardado cancelado."
        except Exception as exc:
            aviso_guardar.value = f"No se pudieron exportar las gráficas: {exc}"
        page.update()

    async def guardar_datos(e):
        ruta_origen = next((p for p in documentos if p.name == selector_datos.value), None)
        if not ruta_origen:
            aviso_guardar.value = "Selecciona primero un archivo de datos."
            page.update()
            return
        formato = tipo_datos.value or "xlsx"
        try:
            if formato == "xlsx":
                contenido = await asyncio.to_thread(generar_excel, ruta_origen)
            elif formato == "docx":
                contenido = await asyncio.to_thread(generar_word, ruta_origen)
            else:
                if ruta_origen.suffix.lower() == ".csv":
                    contenido = ruta_origen.read_bytes()
                else:
                    encabezados, filas = leer_tabla(ruta_origen)
                    salida = io.StringIO()
                    escritor = csv.writer(salida)
                    escritor.writerow(encabezados)
                    escritor.writerows(filas)
                    contenido = salida.getvalue().encode("utf-8-sig")
            nombre = f"{ruta_origen.stem}.{formato}"
            destino = await ft.FilePicker().save_file(
                dialog_title="Guardar datos o informe",
                file_name=nombre,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[formato],
                src_bytes=contenido,
            )
            aviso_guardar.value = f"Archivo guardado: {destino}" if destino else "Guardado cancelado."
        except ModuleNotFoundError as exc:
            aviso_guardar.value = f"Falta una dependencia: {exc}. Instala openpyxl y python-docx."
        except Exception as exc:
            aviso_guardar.value = f"No se pudo exportar: {exc}"
        page.update()

    def guardar_en_historial(e=None):
        if not csv_entrada or not graficas:
            aviso_historial.value = "Primero carga un CSV y ejecuta un cálculo."
            page.update()
            return
        try:
            proyecto_id, calculo_id = guardar_proyecto(
                nombre_proyecto.value or "",
                descripcion_proyecto.value or "",
                csv_entrada,
                carpeta_resultados,
            )
            aviso_historial.value = (
                f"Guardado en SQLite: proyecto #{proyecto_id}, cálculo #{calculo_id}."
            )
        except Exception as exc:
            aviso_historial.value = f"No se pudo guardar: {exc}"
        page.update()

    guardar_boton.on_click = guardar_en_historial

    def abrir_calculo_guardado(calculo_id: int):
        nonlocal csv_entrada, carpeta_resultados
        try:
            registro = obtener_calculo(calculo_id)
            if registro is None:
                raise ValueError("No existe el cálculo solicitado.")
            temporal = tempfile.TemporaryDirectory(prefix="perfil_vial_hist_")
            temporales_historial.append(temporal)
            csv_entrada, carpeta_resultados = extraer_calculo(
                registro, Path(temporal.name)
            )
            archivo_entrada.value = f"{csv_entrada.name} (historial)"
            nombre_proyecto.value = registro["nombre_proyecto"]
            descripcion_proyecto.value = registro["descripcion"]
            generar.disabled = False
            cargar_resultados()
            guardar_boton.disabled = False
            aviso.value = (
                f"Recuperado: {registro['nombre_proyecto']} · "
                f"cálculo #{registro['id']}. Resultados originales restaurados."
            )
            mostrar_vias()
        except Exception as exc:
            aviso_historial.value = f"No se pudo abrir el cálculo: {exc}"
            page.update()

    def borrar_proyecto(proyecto_id: int, confirmacion: ft.Checkbox):
        if not confirmacion.value:
            aviso_historial.value = "Marca 'Confirmar eliminación' antes de borrar."
        else:
            try:
                eliminado = eliminar_proyecto(proyecto_id)
                aviso_historial.value = (
                    "Proyecto y cálculos asociados eliminados de SQLite."
                    if eliminado else "El proyecto ya no existe."
                )
                refrescar_historial()
            except Exception as exc:
                aviso_historial.value = f"No se pudo eliminar: {exc}"
        page.update()

    def refrescar_historial(e=None):
        lista_historial.controls.clear()
        registros = listar_proyectos(buscar_proyecto.value or "")
        todos = listar_proyectos()
        if not registros:
            lista_historial.controls.append(ft.Text("No hay proyectos que coincidan."))
        for p in registros:
            calculos = listar_calculos(p["id"])
            confirmar = ft.Checkbox(label="Confirmar eliminación", value=False)
            botones_calculo = [
                ft.Button(
                    f"ABRIR CÁLCULO #{c['id']} · {c['creado_en']}",
                    on_click=lambda ev, cid=c["id"]: abrir_calculo_guardado(cid),
                )
                for c in calculos
            ]
            lista_historial.controls.append(
                tarjeta(ft.Column(controls=[
                    ft.Text(f"#{p['id']}  {p['nombre']}", weight=ft.FontWeight.BOLD, color=AZUL, size=17),
                    ft.Text(p["descripcion"] or "Sin descripción", color=GRIS),
                    ft.Text(f"Fecha: {p['creado_en']}  ·  Cálculos: {p['total_calculos']}", color=GRIS, size=12),
                    ft.Row(controls=botones_calculo, wrap=True),
                    ft.Row(controls=[confirmar, ft.Button(
                        "ELIMINAR PROYECTO",
                        on_click=lambda ev, pid=p["id"], conf=confirmar: borrar_proyecto(pid, conf),
                    )], wrap=True),
                ], spacing=7))
            )
        def crear_opciones():
            return [ft.DropdownOption(key=str(p["ultimo_calculo_id"]),
                    text=f"{p['nombre']} (#{p['ultimo_calculo_id']})")
                    for p in todos if p["ultimo_calculo_id"] is not None]
        comparacion_a.options = crear_opciones()
        comparacion_b.options = crear_opciones()
        page.update()

    def comparar_calculos(e=None):
        if not comparacion_a.value or not comparacion_b.value:
            comparacion_resultado.value = "Selecciona dos proyectos para comparar."
        else:
            try:
                r = resumen_comparacion(int(comparacion_a.value), int(comparacion_b.value))
                pa = "No disponible" if r["puntos_bajos_a"] is None else str(r["puntos_bajos_a"])
                pb = "No disponible" if r["puntos_bajos_b"] is None else str(r["puntos_bajos_b"])
                comparacion_resultado.value = (
                    f"{r['proyecto_a']}: {pa} puntos bajos, {r['graficas_a']} gráficas.\n"
                    f"{r['proyecto_b']}: {pb} puntos bajos, {r['graficas_b']} gráficas.\n"
                    "Comparación descriptiva; no sustituye la validación geométrica de ingeniería."
                )
            except Exception as exc:
                comparacion_resultado.value = f"No se pudo comparar: {exc}"
        page.update()

    def mostrar_historial(e=None):
        page.controls.clear()
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12, controls=[
            cabecera(),
            tarjeta(ft.Column(controls=[
                ft.Text("HISTORIAL DE PROYECTOS | SQLITE", size=22, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[buscar_proyecto, ft.Button("BUSCAR / ACTUALIZAR", on_click=refrescar_historial),
                                 ft.Button("VOLVER A DISEÑO VIAL", on_click=mostrar_vias)], wrap=True),
                aviso_historial,
            ], spacing=10)),
            lista_historial,
            tarjeta(ft.Column(controls=[
                ft.Text("COMPARAR DOS PROYECTOS", size=18, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Compara los últimos cálculos guardados de cada proyecto.", color=GRIS),
                ft.Row(controls=[comparacion_a, comparacion_b,
                                 ft.Button("COMPARAR", on_click=comparar_calculos)], wrap=True),
                comparacion_resultado,
            ], spacing=10)),
        ]))
        refrescar_historial()
        page.update()

    def cabecera():
        return tarjeta(ft.Row(controls=[
            ft.Column(controls=[
                ft.Text("PERFIL VIAL", size=28, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Análisis topográfico · Ingeniería Civil", color=GRIS),
            ], spacing=3),
            ft.Text("Proyecto 02 | Programación II", color=GRIS),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))

    def mostrar_graficas(e=None):
        panel.controls.clear()
        panel.controls.extend([
            tarjeta(ft.Column(controls=[
                ft.Text("01  |  VISUALIZADOR DE GRÁFICAS", size=21, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Elige una para previsualizarla. Marca una o varias para exportar.", color=GRIS),
                selector_grafica,
                titulo_vista,
                ft.Container(content=imagen, padding=12, bgcolor=FONDO, border_radius=10),
            ], spacing=12)),
            tarjeta(ft.Column(controls=[
                ft.Text("EXPORTAR GRÁFICAS", size=18, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[
                    ft.Button("MARCAR TODAS", on_click=marcar_todas),
                    ft.Button("LIMPIAR SELECCIÓN", on_click=limpiar_marcas),
                    contador_seleccion,
                ], wrap=True),
                lista_seleccion,
                ft.Row(controls=[tipo_grafica, ft.Button("GUARDAR SELECCIONADAS", on_click=guardar_graficas)], wrap=True),
                aviso_guardar,
            ], spacing=12)),
        ])
        page.update()

    def mostrar_datos(e=None):
        panel.controls.clear()
        panel.controls.extend([
            tarjeta(ft.Column(controls=[
                ft.Text("02  |  DATOS Y CARTERAS", size=21, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Selecciona un CSV o informe. Se presenta solo una vista previa ordenada.", color=GRIS),
                selector_datos,
                vista_datos,
            ], spacing=12)),
            tarjeta(ft.Column(controls=[
                ft.Text("EXPORTAR DATOS", size=18, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[tipo_datos, ft.Button("GUARDAR ARCHIVO", on_click=guardar_datos)], wrap=True),
                ft.Text("Excel, Word y CSV conservan los datos del archivo elegido. "
                        "El Word tabular no es aún la memoria de cálculo docxtpl.", color=GRIS, size=12),
                aviso_guardar,
            ], spacing=12)),
        ])
        page.update()

    def mostrar_vias(e=None):
        page.controls.clear()
        page.add(ft.Column(expand=True, spacing=12, controls=[
            cabecera(),
            tarjeta(ft.Column(controls=[
                ft.Text("DISEÑO VIAL", size=23, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[ft.Button("SELECCIONAR CSV", on_click=elegir_entrada),
                                 archivo_entrada, generar], wrap=True),
                aviso, resumen,
                ft.Row(controls=[nombre_proyecto, descripcion_proyecto, guardar_boton], wrap=True),
                aviso_historial,
                ft.Row(controls=[ft.Button("GRÁFICAS", on_click=mostrar_graficas),
                                 ft.Button("DATOS E INFORMES", on_click=mostrar_datos),
                                 ft.Button("HISTORIAL", on_click=mostrar_historial),
                                 ft.Button("INICIO", on_click=mostrar_inicio)], wrap=True),
            ], spacing=11)),
            panel,
        ]))
        if graficas:
            mostrar_graficas()
        else:
            panel.controls = [tarjeta(ft.Text("Carga un CSV y pulsa CALCULAR para ver resultados.", color=GRIS))]
        page.update()

    def mostrar_redes(e=None):
        page.controls.clear()
        page.add(cabecera(), tarjeta(ft.Column(controls=[
            ft.Text("REDES DE ALCANTARILLADO", size=23, color=AZUL, weight=ft.FontWeight.BOLD),
            ft.Text("Módulo pendiente: pozos, tuberías, interferencias y carteras de instalación."),
            ft.Button("VOLVER AL INICIO", on_click=mostrar_inicio),
        ])))
        page.update()

    def mostrar_inicio(e=None):
        page.controls.clear()
        page.add(cabecera(), tarjeta(ft.Column(controls=[
            ft.Text("Selecciona el módulo", size=23, color=AZUL, weight=ft.FontWeight.BOLD),
            ft.Row(controls=[
                ft.Button("DISEÑO VIAL", on_click=mostrar_vias),
                ft.Button("REDES DE ALCANTARILLADO", on_click=mostrar_redes),
                ft.Button("HISTORIAL", on_click=mostrar_historial),
            ], wrap=True),
        ], spacing=16)))
        page.update()

    mostrar_inicio()


if __name__ == "__main__":
    ft.run(main)
