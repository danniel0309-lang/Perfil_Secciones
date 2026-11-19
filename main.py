"""Perfil Vial V10.7 | cotas extremas BV-EJE-BV y sumideros antes de rasante.

Conserva el motor topográfico original, Flet 1.0.4 y las exportaciones.
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
from app.modelo import muestrear_eje, guardar_muestreo_csv, guardar_muestreo_png
from perfil_vial.parsing import read_survey
from app.memoria import crear_memoria
from app.rasante import (
    calcular_rasante, guardar_rasante_csv, guardar_rasante_png, guardar_resumen_txt,
)
from app.transversal import (
    ParametrosVia, calcular_via_bv, guardar_cartera_vial_bv, guardar_control_drenaje, guardar_perfil_tres_cotas_png, guardar_perfiles_originales_con_diseno, guardar_via_csv, guardar_cantidades_csv,
    guardar_via_png, guardar_via_resumen, guardar_balance_png,
)
from app.sumideros import Sumidero, evaluar_sumideros, guardar_sumideros_csv
from app.alcantarillado import (
    Pozo, Tramo, Interferencia, ParametrosZanja, calcular_red,
    guardar_red_tramos, guardar_red_cartera, guardar_red_cantidades,
    guardar_interferencias, guardar_red_png, guardar_red_resumen,
    guardar_red_perfil_general,
)
from app.formularios import (
    crear_tramos_desde_pozos, crear_sumideros_desde_filas, crear_interferencias_desde_filas,
)
from app.db import (
    inicializar_db, guardar_proyecto, listar_proyectos, listar_calculos,
    obtener_calculo, eliminar_proyecto, extraer_calculo, resumen_comparacion,
)


VERSION_INTERFAZ = "10.7"  # Indicador visible: comprueba que se instaló la actualización.

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "salida"
RED_SALIDA = SALIDA / "redes"

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
    "perfil_ideal": "Perfil ideal original (auxiliar, no es la cartera de 3 cotas)",
    "secciones_minimos": "Mínimos de secciones transversales",
    "informe_puntos_bajos": "Informe de puntos bajos",
    "rasante_proyecto": "Rasante EJE auxiliar (solo longitudinal)",
    "perfil_tres_cotas_via": "Comparación BV–EJE–BV: perfiles originales y proyecto",
    "perfil_longitudinal_izquierdo_comparativo": "Costado izquierdo: perfiles originales + BV de diseño",
    "perfil_longitudinal_derecho_comparativo": "Costado derecho: perfiles originales + BV de diseño",
    "cartera_ideal_tres_cotas": "CARTERA BV-EJE-BV · preliminar o completa según datos",
    "rasante_resumen": "Resumen del prediseño de rasante",
    "transversal_proyecto": "Sección transversal de proyecto (ejemplo central)",
    "balance_areas_via": "Áreas transversales de corte y relleno",
    "cantidades_via": "Cantidades de obra vial (estimadas)",
    "volumenes_movimiento_tierras": "Cartera de áreas y volúmenes entre secciones",
    "resumen_via": "Alcance de cantidades viales",
    "cartera_vial_antes_despues": "Cartera de cotas originales y propuestas BV-EJE-BV",
    "control_drenaje_vial": "Control de pendientes y posibles puntos de empozamiento",
    "sumideros_proyecto": "Sumideros y comparación de rejillas",
    "entrada_tramos_red": "Datos de tramos introducidos",
    "red_tramos": "Resumen geométrico de redes entre pozos",
    "red_perfil_longitudinal": "Perfil longitudinal completo de alcantarillado",
    "red_cartera_instalacion": "Cartera de instalación por tubo",
    "red_cantidades": "Cantidades geométricas de alcantarillado",
    "red_interferencias": "Interferencias y holguras verticales",
    "red_resumen": "Advertencias y alcance del cálculo de redes",
}


def etiquetas_abscisas_graficas(csv_origen: str | Path | None) -> dict[str, str]:
    """Etiqueta cada sección con la abscisa REAL leída del CSV.

    Las láminas originales `secciones_pNN.png` contienen seis secciones por
    hoja (configuración CLI usada por esta interfaz); se etiquetan por rango.
    No se deducen abscisas a partir de números de archivo si falta el CSV.
    Funciona también con el CSV recuperado desde el historial SQLite.
    """
    if not csv_origen or not Path(csv_origen).is_file():
        return {}
    try:
        secciones = read_survey(csv_origen).sections
    except (ValueError, OSError, KeyError):
        return {}  # Sin CSV vial válido no inventar abscisas.
    labels = [s.label for s in secciones]
    if not labels:
        return {}
    resultado = {
        f"transversal_diseno_{i:03d}.png": f"Sección diseñada · {label}"
        for i, label in enumerate(labels, 1)
    }
    resultado["transversal_proyecto.png"] = f"Sección diseñada central · {labels[len(labels)//2]}"
    if len(labels) <= 6:
        rango = labels[0] if len(labels) == 1 else f"{labels[0]} a {labels[-1]}"
        resultado["secciones.png"] = f"Secciones originales · {rango}"
    for inicio in range(0, len(labels), 6):
        pagina = inicio // 6 + 1
        subset = labels[inicio:inicio+6]
        rango = subset[0] if len(subset) == 1 else f"{subset[0]} a {subset[-1]}"
        resultado[f"secciones_p{pagina:02d}.png"] = f"Secciones originales · {rango}"
    return resultado


def nombre_legible(archivo: Path, etiquetas_abscisas: dict[str, str] | None = None) -> str:
    if etiquetas_abscisas and archivo.name in etiquetas_abscisas:
        return etiquetas_abscisas[archivo.name]
    if archivo.stem.startswith("transversal_diseno_"):
        # Fallback cuando no existe el CSV de origen.
        return f"Sección diseñada · índice {archivo.stem.rsplit('_', 1)[-1]} (sin abscisa verificable)"
    if archivo.stem.startswith("secciones_p"):
        return f"Secciones originales · hoja {archivo.stem.rsplit('p', 1)[-1]} (sin abscisas verificables)"
    return NOMBRES.get(archivo.stem, archivo.stem.replace("_", " ").capitalize())


def orden_grafica(archivo: Path):
    nombre = archivo.stem
    if nombre == "red_perfil_longitudinal":
        return (-4, nombre)
    if nombre.startswith("red_perfil_tramo"):
        return (-3, nombre)
    if nombre.startswith("transversal_diseno"):
        return (3, nombre)
    if nombre == "perfil_tres_cotas_via":
        return (-2, nombre)
    if nombre.endswith("_comparativo"):
        return (-1.5, nombre)
    if nombre == "rasante_proyecto":
        return (-1, nombre)
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
    page.title = f"Perfil Vial V{VERSION_INTERFAZ} | Ingeniería Civil - Vías y Alcantarillado"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = FONDO
    page.padding = 20

    csv_entrada = None
    carpeta_resultados = SALIDA
    temporales_historial = []  # Mantiene las carpetas de historial mientras la ventana siga abierta.
    graficas = []
    documentos = []
    marcas = {}
    etiquetas_graficas = {}
    modulo_actual = "vias"  # Para regresar correctamente desde gráficas y datos.

    aviso = ft.Text("Selecciona un CSV para comenzar.", color=GRIS)
    archivo_entrada = ft.Text("Ningún archivo seleccionado", color=GRIS)
    resumen = ft.Text("", color=GRIS)
    generar = ft.Button("CALCULAR PERFILES Y SECCIONES", disabled=True)
    selector_grafica = ft.Dropdown(label="Gráfica para visualizar", width=440, options=[])
    # Visor ampliable con zoom y paneo; todas las gráficas comparten el mismo visor.
    imagen = ft.Image(src="", width=1060, height=620, fit=ft.BoxFit.CONTAIN)
    visor_grafica = ft.InteractiveViewer(
        content=imagen,
        min_scale=0.35,
        max_scale=8.0,
        boundary_margin=ft.Margin.all(200),
        height=650,
        constrained=True,
        visible=False,
    )

    async def acercar_grafica(e):
        if visor_grafica.visible:
            await visor_grafica.zoom(1.35)

    async def alejar_grafica(e):
        if visor_grafica.visible:
            await visor_grafica.zoom(1 / 1.35)

    async def restablecer_grafica(e):
        if visor_grafica.visible:
            await visor_grafica.reset()

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
    boton_rasante = ft.Button("CALCULAR RASANTE", disabled=True)
    estado_rasante = ft.Text(
        "Ingresa semianchos, bombeo y sumideros ANTES de calcular. "
        "Se conservarán las primeras y últimas cotas medidas de BV IZQ, EJE y BV DER.", color=GRIS,
    )
    # DISEÑO VIAL: todos los valores son editables y NO equivalen a un estándar.
    ancho_izq = ft.TextField(label="Ancho EJE → BV izquierda (m) · obligatorio", value="", width=315)
    ancho_der = ft.TextField(label="Ancho EJE → BV derecha (m) · obligatorio", value="", width=315)
    pendiente_min_long = ft.TextField(label="Pendiente longitudinal de revisión BV (%) · no bloquea cálculo; 0 = alerta solo si horizontal", value="0", width=500)
    pendiente_trans = ft.TextField(label="Pendiente transversal (%)", value="2", width=210)
    orientacion_trans = ft.Dropdown(label="Sentido transversal", value="dos_aguas", width=245,
        options=[ft.DropdownOption(key="dos_aguas", text="Dos aguas (eje alto)"),
                 ft.DropdownOption(key="derecha", text="Una agua hacia DERECHA"),
                 ft.DropdownOption(key="izquierda", text="Una agua hacia IZQUIERDA")])
    e_asfalto = ft.TextField(label="Asfalto (m)", value="0.08", width=150)
    e_base = ft.TextField(label="Base granular (m)", value="0.80", width=165)
    e_subbase = ft.TextField(label="Subbase (m)", value="0", width=155)
    e_rajon = ft.TextField(label="Rajón (m)", value="0", width=145)
    e_incremento = ft.TextField(label="Factor de compactación (%) · incremento de material suelto", value="0", width=300)
    # SUMIDEROS: cada registro se introduce en celdas independientes.
    filas_sumideros = []
    lista_sumideros = ft.Column(controls=[], spacing=7)
    cantidad_sumideros = ft.TextField(label="Número de sumideros", value="0", width=175)
    aviso_transversal = ft.Text(
        "La cubicación requiere rasante calculada y secciones con ancho suficiente.", color=GRIS)
    boton_transversal = ft.Button("CALCULAR SECCIONES, CANTIDADES Y SUMIDEROS", disabled=True)

    # REDES: número explícito de pozos. Cada pozo intermedio conserva entrada y salida diferentes.
    cantidad_pozos = ft.TextField(label="Número de pozos", value="2", width=160)
    campos_pozos = []
    lista_pozos = ft.Column(controls=[], spacing=10)
    campos_tramos = []
    lista_tramos = ft.Column(controls=[], spacing=10)
    red_aviso = ft.Text("Introduce el LOMO exterior de conexión en cada pozo y el DIÁMETRO EXTERIOR (pulg) de cada tramo; la batea se calculará automáticamente.", color=GRIS)
    red_sobreancho = ft.TextField(label="Sobreancho total sobre diámetro (m)", value="0.60", width=300)
    red_cama = ft.TextField(label="Cama de triturado (m)", value="0.10", width=190)
    red_largo = ft.TextField(label="Longitud efectiva tubo (m)", value="5.85", width=210)
    red_base = ft.TextField(label="Base granular (m)", value="0.80", width=190)
    red_asfalto = ft.TextField(label="Asfalto (m)", value="0.08", width=170)
    red_subbase = ft.TextField(label="Subbase (m)", value="0", width=170)
    red_rajon = ft.TextField(label="Rajón (m)", value="0", width=165)
    red_incremento = ft.TextField(label="Incremento suministro (%)", value="0", width=240)
    # INTERFERENCIAS: una fila por red que intercepte el tramo.
    filas_cruces = []
    lista_cruces = ft.Column(controls=[], spacing=7)
    cantidad_cruces = ft.TextField(label="Número de interferencias", value="0", width=190)

    def paso_automatico(csv_path):
        # Las abscisas se leen del CSV; no se solicitan estaciones nuevas.
        import numpy as np
        sec = read_survey(csv_path).sections
        ds = np.diff([x.station for x in sec])
        if len(ds) == 0 or np.min(ds) <= 0:
            raise ValueError("El CSV necesita dos abscisas diferentes y crecientes.")
        return float(np.min(ds))

    def limpiar_celdas(e=None):
        # Limpia entradas, conservando la estructura de formularios y listas.
        controles = [nombre_proyecto, descripcion_proyecto,
                     ancho_izq, ancho_der, pendiente_min_long, pendiente_trans, e_asfalto, e_base,
                     e_subbase, e_rajon, e_incremento, cantidad_sumideros,
                     cantidad_pozos, cantidad_cruces, red_sobreancho, red_cama,
                     red_largo, red_base, red_asfalto, red_subbase, red_rajon, red_incremento]
        for lista in (filas_sumideros, campos_pozos, campos_tramos, filas_cruces):
            for fila in lista:
                controles.extend(c for c in fila.values() if isinstance(c, ft.TextField))
        for control in controles:
            control.value = ""
        for control in [orientacion_trans]:
            control.value = None
        for lista in (filas_sumideros, campos_tramos, filas_cruces):
            for fila in lista:
                for control in fila.values():
                    if isinstance(control, ft.Dropdown):
                        control.value = None
        # No se pierden archivos previamente calculados; solo se vacían recuadros.
        page.update()

    def numero(campo, nombre=None):
        try:
            valor = float((campo.value or "").strip().replace(",", "."))
        except (ValueError, AttributeError):
            raise ValueError(f"Indica un número para {nombre or campo.label}.")
        if not __import__("math").isfinite(valor):
            raise ValueError(f"El número para {nombre or campo.label} debe ser finito.")
        return valor

    def campo(label, ancho=185, valor=""):
        return ft.TextField(label=label, width=ancho, value=valor)

    def _cantidad(control, etiqueta, minimo, maximo):
        try:
            n = int((control.value or "").strip())
        except ValueError:
            raise ValueError(f"{etiqueta}: escribe un número entero.") from None
        if not minimo <= n <= maximo:
            raise ValueError(f"{etiqueta}: indica entre {minimo} y {maximo}.")
        return n

    def nuevo_sumidero():
        i = len(filas_sumideros) + 1
        datos = dict(
            nombre=campo("Nombre", 155),
            abscisa=campo("Abscisa (m)", 145),
            costado=ft.Dropdown(label="Costado", width=132, value="IZQ",
                options=[ft.DropdownOption(key="IZQ", text="IZQ"),
                         ft.DropdownOption(key="DER", text="DER")]),
            rejilla=campo("Cota rejilla = rasante existente (m)", 290),
        )
        vista = tarjeta(ft.Column(controls=[
            ft.Text(f"SUMIDERO #{i}", weight=ft.FontWeight.BOLD, color=AZUL),
            ft.Row(controls=list(datos.values()), wrap=True),
        ], spacing=6))
        datos["vista"] = vista
        filas_sumideros.append(datos)
        lista_sumideros.controls.append(vista)

    def quitar_sumidero(e=None):
        if filas_sumideros:
            filas_sumideros.pop()
            lista_sumideros.controls.pop()
            cantidad_sumideros.value = str(len(filas_sumideros))
            page.update()

    def ajustar_sumideros(e=None):
        try:
            n = _cantidad(cantidad_sumideros, "Sumideros", 0, 100)
            while len(filas_sumideros) > n:
                filas_sumideros.pop(); lista_sumideros.controls.pop()
            while len(filas_sumideros) < n:
                nuevo_sumidero()
            page.update()
        except ValueError as exc:
            aviso_transversal.value = str(exc)
            page.update()

    def agregar_sumidero(e=None):
        if len(filas_sumideros) >= 100:
            aviso_transversal.value = "Máximo 100 sumideros."
        else:
            nuevo_sumidero(); cantidad_sumideros.value = str(len(filas_sumideros))
        page.update()

    def _ficha_pozo(i, n, anterior=None):
        # Un pozo intermedio dispone de ENTRADA y SALIDA independientes.
        datos = dict(
            nombre=anterior["nombre"] if anterior else campo("Nombre pozo", 155),
            abscisa=anterior["abscisa"] if anterior else campo("Abscisa (m)", 155),
            rasante=anterior["rasante"] if anterior else campo("Cota rasante (m)", 190),
        )
        if i > 0:
            datos["lomo_entrada"] = (anterior.get("lomo_entrada") if anterior else None) or campo("LOMO entrada ext. (m)", 210)
        if i < n-1:
            datos["lomo_salida"] = (anterior.get("lomo_salida") if anterior else None) or campo("LOMO salida ext. (m)", 210)
        datos["vista"] = tarjeta(ft.Column(controls=[
            ft.Text(f"POZO #{i+1} " + ("· SALIDA" if i == 0 else "· ENTRADA" if i == n-1 else "· ENTRADA Y SALIDA"),
                    size=16, weight=ft.FontWeight.BOLD, color=AZUL),
            ft.Row(controls=[valor for clave, valor in datos.items() if clave != "vista"], wrap=True),
        ], spacing=7))
        return datos

    def _ficha_tramo(i, anterior=None):
        datos = dict(
            red=anterior["red"] if anterior else ft.Dropdown(label="Tipo de red", value="PLUVIAL", width=190,
                options=[ft.DropdownOption(key="PLUVIAL", text="Pluvial"),
                         ft.DropdownOption(key="RESIDUAL", text="Residual")]),
            material=anterior["material"] if anterior else ft.Dropdown(label="Material", value="PVC", width=185,
                options=[ft.DropdownOption(key="PVC", text="PVC (blanco)"),
                         ft.DropdownOption(key="CONCRETO", text="Concreto (gris)")]),
        )
        datos["diametro_exterior_pulg"] = (anterior.get("diametro_exterior_pulg") if anterior else None) or campo("Diámetro EXTERIOR tubo (pulg)", 240)
        datos["vista"] = tarjeta(ft.Row(controls=[
            ft.Text(f"TRAMO #{i+1} | Pozo {i+1} → Pozo {i+2}",
                    weight=ft.FontWeight.BOLD, color=AZUL),
            datos["red"], datos["material"], datos["diametro_exterior_pulg"]], wrap=True))
        return datos

    def ajustar_pozos(e=None):
        try:
            n = _cantidad(cantidad_pozos, "Pozos", 2, 201)
            anteriores = list(campos_pozos)
            tramos_anteriores = list(campos_tramos)
            campos_pozos.clear(); campos_tramos.clear()
            lista_pozos.controls.clear(); lista_tramos.controls.clear()
            for i in range(n):
                datos = _ficha_pozo(i, n, anteriores[i] if i < len(anteriores) else None)
                campos_pozos.append(datos)
                lista_pozos.controls.append(datos["vista"])
            for i in range(n-1):
                datos = _ficha_tramo(i, tramos_anteriores[i] if i < len(tramos_anteriores) else None)
                campos_tramos.append(datos)
                lista_tramos.controls.append(datos["vista"])
            red_aviso.value = f"Formulario: {n} pozos y {n-1} tramos consecutivos. Ingresa lomos exteriores y un diámetro exterior por tramo."
            page.update()
        except ValueError as exc:
            red_aviso.value = str(exc)
            page.update()

    def _nuevo_cruce():
        i = len(filas_cruces) + 1
        datos = dict(
            tramo=campo("N.º de tramo", 140),
            abscisa=campo("Abscisa cruce (m)", 175),
            servicio=ft.Dropdown(label="Servicio", width=190, value="AGUA POTABLE", options=[
                ft.DropdownOption(key="AGUA POTABLE", text="Agua potable"),
                ft.DropdownOption(key="GAS", text="Gas"),
                ft.DropdownOption(key="TELEFONIA", text="Telefonía"),
                ft.DropdownOption(key="ELECTRICA", text="Eléctrica"),
                ft.DropdownOption(key="OTRO", text="Otro")]),
            otro=campo("Si es otra red: nombre", 195),
            superior=campo("Cota lomo de red cruzada (m)", 215),
            diametro=campo("Diámetro EXTERIOR (pulg)", 210),
        )
        datos["vista"] = tarjeta(ft.Column(controls=[
            ft.Text(f"INTERFERENCIA #{i}", color=AZUL, weight=ft.FontWeight.BOLD),
            ft.Row(controls=list(datos.values()), wrap=True),
        ], spacing=6))
        filas_cruces.append(datos)
        lista_cruces.controls.append(datos["vista"])

    def ajustar_cruces(e=None):
        try:
            n = _cantidad(cantidad_cruces, "Interferencias", 0, 100)
            while len(filas_cruces) > n:
                filas_cruces.pop(); lista_cruces.controls.pop()
            while len(filas_cruces) < n:
                _nuevo_cruce()
            page.update()
        except ValueError as exc:
            red_aviso.value = str(exc); page.update()

    def agregar_cruce(e=None):
        if len(filas_cruces) < 100:
            _nuevo_cruce(); cantidad_cruces.value = str(len(filas_cruces))
        else:
            red_aviso.value = "Máximo 100 interferencias."
        page.update()

    def quitar_cruce(e=None):
        if filas_cruces:
            filas_cruces.pop(); lista_cruces.controls.pop()
            cantidad_cruces.value = str(len(filas_cruces))
            page.update()

    ajustar_pozos()  # Dos pozos iniciales; no asigna cotas ficticias.

    def limpiar_resultados():
        nonlocal graficas, documentos, marcas, etiquetas_graficas
        etiquetas_graficas = {}
        graficas = []
        documentos = []
        marcas = {}
        lista_seleccion.controls.clear()
        selector_grafica.options = []
        selector_grafica.value = None
        visor_grafica.visible = False
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
            boton_rasante.disabled = True
            boton_transversal.disabled = True
            estado_rasante.value = "Se conservan los tres pares de cotas BV IZQ, EJE, BV DER de inicio y fin."
            archivo_entrada.value = csv_entrada.name
            aviso.value = "Archivo cargado. Puedes iniciar el cálculo."
            generar.disabled = False
            limpiar_resultados()
        except Exception as exc:
            aviso.value = f"No se pudo seleccionar el archivo: {exc}"
        page.update()

    def mostrar_grafica(e=None):
        if not selector_grafica.value:
            visor_grafica.visible = False
            page.update()
            return
        ruta = next((p for p in graficas if p.name == selector_grafica.value), None)
        if ruta and ruta.is_file():
            try:
                imagen.src = ruta.read_bytes()
                visor_grafica.visible = True
                titulo_vista.value = nombre_legible(ruta, etiquetas_graficas)
            except OSError as exc:
                visor_grafica.visible = False
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
        nonlocal graficas, documentos, marcas, etiquetas_graficas
        limpiar_resultados()
        etiquetas_graficas = etiquetas_abscisas_graficas(csv_entrada)
        archivos = sorted(p for p in carpeta_resultados.iterdir() if p.is_file())
        graficas = sorted((p for p in archivos if p.suffix.lower() == ".png"), key=orden_grafica)
        documentos = [p for p in archivos if p.suffix.lower() in {".csv", ".txt"}]
        if csv_entrada and csv_entrada.is_file():
            documentos.insert(0, csv_entrada)
        resumen.value = f"{len(graficas)} gráficas · {len(documentos)} archivos de datos e informes"
        selector_grafica.options = [ft.DropdownOption(key=p.name, text=nombre_legible(p, etiquetas_graficas)) for p in graficas]
        if graficas:
            selector_grafica.value = graficas[0].name
        for archivo in graficas:
            caja = ft.Checkbox(label=nombre_legible(archivo, etiquetas_graficas), value=False, on_change=actualizar_marcadas)
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
        boton_rasante.disabled = True
        boton_transversal.disabled = True
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
            # Un nuevo CSV no debe mostrar productos de diseño de un CSV anterior.
            for viejo in SALIDA.glob('transversal_diseno_*.png'): viejo.unlink()
            for anterior in ('transversal_proyecto.png','balance_areas_via.png',
                             'volumenes_movimiento_tierras.csv','cantidades_via.csv',
                             'resumen_via.txt','sumideros_proyecto.csv','sumideros_ubicacion.png',
                             'cartera_vial_antes_despues.csv','cartera_ideal_tres_cotas.csv',
                             'control_drenaje_vial.csv','perfil_tres_cotas_via.png',
                             'perfil_longitudinal_izquierdo_comparativo.png',
                             'perfil_longitudinal_derecho_comparativo.png'):
                (SALIDA/anterior).unlink(missing_ok=True)
            for nombre in ("rasante_proyecto.csv", "rasante_proyecto.png", "rasante_resumen.txt"):
                (SALIDA / nombre).unlink(missing_ok=True)
            # Modelo independiente: SciPy interpola cotas EJE entre mediciones.
            # Un error de interpolación no debe borrar los resultados originales.
            try:
                paso = paso_automatico(csv_entrada)
                r = await asyncio.to_thread(muestrear_eje, csv_entrada, paso)
                await asyncio.to_thread(guardar_muestreo_csv, r, SALIDA / "cotas_eje_interpoladas.csv")
                await asyncio.to_thread(guardar_muestreo_png, r, SALIDA / "cotas_eje_interpoladas.png")
                aviso.value = "Cálculos terminados. SciPy generó cotas EJE estimadas entre estaciones."
            except (ValueError, TypeError) as exc:
                # No reutilizar silenciosamente las interpolaciones de otro CSV.
                for anterior in (SALIDA / "cotas_eje_interpoladas.csv", SALIDA / "cotas_eje_interpoladas.png"):
                    anterior.unlink(missing_ok=True)
                aviso.value = f"Perfiles originales generados; SciPy no pudo interpolar: {exc}"
            cargar_resultados()
            guardar_boton.disabled = False
            boton_rasante.disabled = False
            boton_transversal.disabled = True
            mostrar_graficas()
        except Exception as exc:
            aviso.value = f"Error durante el cálculo: {exc}"
        finally:
            generar.disabled = False
            page.update()

    generar.on_click = procesar

    def _parametros_via_del_formulario():
        """No inventar anchos. Ambos se solicitan explícitamente al usuario."""
        return ParametrosVia(
            numero(ancho_izq), numero(ancho_der), numero(pendiente_trans),
            orientacion_trans.value or 'dos_aguas',
            numero(e_asfalto), numero(e_base), numero(e_subbase),
            numero(e_rajon), numero(e_incremento),
        )

    def _sumideros_del_formulario():
        return crear_sumideros_desde_filas([
            {clave: control.value for clave, control in fila.items() if clave != 'vista'}
            for fila in filas_sumideros
        ])

    def _eliminar_productos_de_via_anteriores():
        for viejo in SALIDA.glob('transversal_diseno_*.png'):
            viejo.unlink(missing_ok=True)
        for viejo in ('sumideros_proyecto.csv','sumideros_ubicacion.png',
                      'transversal_proyecto.png','balance_areas_via.png',
                      'volumenes_movimiento_tierras.csv','cantidades_via.csv',
                      'resumen_via.txt','cartera_vial_antes_despues.csv',
                      'cartera_ideal_tres_cotas.csv','control_drenaje_vial.csv',
                      'perfil_tres_cotas_via.png',
                      'perfil_longitudinal_izquierdo_comparativo.png',
                      'perfil_longitudinal_derecho_comparativo.png'):
            (SALIDA/viejo).unlink(missing_ok=True)

    def _guardar_obra_completa(ras, parametros, sumideros, pendiente_minima):
        """Misma salida completa tanto para CALCULAR RASANTE como para SECCIONES."""
        via=calcular_via_bv(csv_entrada, ras, parametros, sumideros, pendiente_minima)
        datos=evaluar_sumideros(via, sumideros)
        _eliminar_productos_de_via_anteriores()
        guardar_cartera_vial_bv(via, csv_entrada, SALIDA/'volumenes_movimiento_tierras.csv')
        guardar_cartera_vial_bv(via, csv_entrada, SALIDA/'cartera_vial_antes_despues.csv')
        guardar_cartera_vial_bv(via, csv_entrada, SALIDA/'cartera_ideal_tres_cotas.csv')
        guardar_perfil_tres_cotas_png(via, SALIDA/'perfil_tres_cotas_via.png')
        guardar_perfiles_originales_con_diseno(via, csv_entrada, SALIDA)
        guardar_control_drenaje(via, datos, SALIDA/'control_drenaje_vial.csv')
        guardar_cantidades_csv(via,SALIDA/'cantidades_via.csv')
        guardar_via_resumen(via,SALIDA/'resumen_via.txt')
        guardar_via_png(via,SALIDA/'transversal_proyecto.png')
        guardar_balance_png(via,SALIDA/'balance_areas_via.png')
        for i in range(len(via.secciones)):
            guardar_via_png(via,SALIDA/f'transversal_diseno_{i+1:03d}.png',i)
        if datos:
            guardar_sumideros_csv(datos,SALIDA/'sumideros_proyecto.csv')
        return via,len(datos)

    async def disenar_rasante(e):
        if csv_entrada is None or not csv_entrada.is_file() or not graficas:
            estado_rasante.value = "Primero selecciona el CSV y genera los perfiles originales."
            page.update()
            return
        try:
            # Sin datos de la sección no se inventan cotas BV ni se prepara
            # una cartera parcial de una sola línea.
            parametros_via = _parametros_via_del_formulario()
            criterio = numero(pendiente_min_long)
            sumideros_via = _sumideros_del_formulario()
        except (ValueError, TypeError) as exc:
            estado_rasante.value = f"Completa los datos de la vía y sumideros antes de diseñar: {exc}"
            page.update()
            return
        boton_rasante.disabled = True
        estado_rasante.value = "Calculando BV izquierda, EJE y BV derecha con sumideros y extremos fijos..."
        page.update()
        try:
            def calcular_y_guardar():
                ras = calcular_rasante(csv_entrada, paso_automatico(csv_entrada), 'constante')
                # Primero se valida que TODO el diseño sea calculable.
                via, n = _guardar_obra_completa(ras, parametros_via, sumideros_via, criterio)
                guardar_rasante_csv(ras, SALIDA / 'rasante_proyecto.csv')
                guardar_rasante_png(ras, SALIDA / 'rasante_proyecto.png')
                guardar_resumen_txt(ras, SALIDA / 'rasante_resumen.txt')
                return via, n

            via, n = await asyncio.to_thread(calcular_y_guardar)
            boton_transversal.disabled = False
            cargar_resultados()
            selector_datos.value = 'cartera_ideal_tres_cotas.csv'
            selector_grafica.value = 'perfil_tres_cotas_via.png'
            mostrar_documento()
            mostrar_grafica()
            alertas = via.lineas_drenaje.advertencias
            estado_rasante.value = (
                f"Diseño completo BV IZQ–EJE–BV DER en {len(via.secciones)} abscisas; "
                f"sumideros incorporados: {n}. Cartera y secciones generadas. "
                + (f"ATENCIÓN: {len(alertas)} advertencia(s) de drenaje; consulta CONTROL DRENAJE. "
                   if alertas else "Sin alertas geométricas. ")
                + "No constituye validación hidráulica. Abre GRÁFICAS / DATOS E INFORMES."
            )
        except (ValueError, TypeError, RuntimeError, OSError) as exc:
            estado_rasante.value = f"No se pudo completar la rasante de tres cotas: {exc}."
        finally:
            boton_rasante.disabled = False
            page.update()

    boton_rasante.on_click = disenar_rasante

    async def disenar_seccion_y_cantidades(e):
        if not csv_entrada or not csv_entrada.is_file() or carpeta_resultados != SALIDA:
            aviso_transversal.value = "Primero calcula la rasante de un CSV topográfico en DISEÑO VIAL."
            page.update(); return
        if not (SALIDA / 'rasante_proyecto.csv').is_file():
            aviso_transversal.value = "Primero presiona CALCULAR RASANTE."
            page.update(); return
        boton_transversal.disabled=True
        aviso_transversal.value='Calculando áreas entre secciones y cantidades geométricas...'
        page.update()
        try:
            # Las dimensiones no se deducen del CSV: el usuario las introduce.
            p=_parametros_via_del_formulario()
            sumideros=_sumideros_del_formulario()
            paso=paso_automatico(csv_entrada)
            criterio=numero(pendiente_min_long)

            def producir():
                ras=calcular_rasante(csv_entrada,paso,'constante')
                return _guardar_obra_completa(ras,p,sumideros,criterio)
            via,n=await asyncio.to_thread(producir)
            cargar_resultados()
            selector_datos.value = 'cartera_ideal_tres_cotas.csv'
            selector_grafica.value = 'perfil_tres_cotas_via.png'
            mostrar_graficas()
            alertas = via.lineas_drenaje.advertencias
            aviso_transversal.value=(
                f"Secciones: {len(via.secciones)} | corte geométrico: {via.resumen['excavacion_m3']:.3f} m³ | "
                f"relleno geométrico: {via.resumen['relleno_geometrico_m3']:.3f} m³ | "
                f"sumideros: {n}. CARTERA_IDEAL_TRES_COTAS generada. "
                + (f"ATENCIÓN: {len(alertas)} advertencia(s) por pendientes/cotas de drenaje; "
                   "consulta CONTROL_DRENAJE_VIAL antes de usar el diseño. " if alertas else '')
                + "Salida y capacidad hidráulica NO verificadas. Prediseño sin taludes."
            )
        except Exception as exc:
            aviso_transversal.value=f'No se calcularon las cantidades: {exc}'
        finally:
            boton_transversal.disabled=False
            page.update()

    boton_transversal.on_click=disenar_seccion_y_cantidades

    async def procesar_redes(e):
        nonlocal csv_entrada, carpeta_resultados
        red_aviso.value='Calculando tramos y cartera de instalación...'
        page.update()
        try:
            parametros=ParametrosZanja(
                numero(red_sobreancho),numero(red_cama),numero(red_largo),
                numero(red_base),numero(red_asfalto),numero(red_subbase),numero(red_incremento),numero(red_rajon))
            tramos = crear_tramos_desde_pozos(
                [{clave: control.value for clave, control in pozo.items() if clave != 'vista'}
                 for pozo in campos_pozos],
                [{clave: control.value for clave, control in tramo.items() if clave != 'vista'}
                 for tramo in campos_tramos],
            )
            cruces = crear_interferencias_desde_filas([
                {clave: control.value for clave, control in fila.items() if clave != 'vista'}
                for fila in filas_cruces
            ])

            def producir():
                r=calcular_red(tramos,parametros,cruces)
                RED_SALIDA.mkdir(parents=True,exist_ok=True)
                # Solo eliminamos los perfiles previos de esta carpeta de redes.
                for vieja in RED_SALIDA.glob('red_perfil_tramo_*.png'): vieja.unlink()
                guardar_red_tramos(r,RED_SALIDA/'red_tramos.csv')
                guardar_red_cartera(r,RED_SALIDA/'red_cartera_instalacion.csv')
                guardar_red_cantidades(r,RED_SALIDA/'red_cantidades.csv')
                guardar_interferencias(r,RED_SALIDA/'red_interferencias.csv')
                guardar_red_resumen(r,RED_SALIDA/'red_resumen.txt')
                guardar_red_perfil_general(r, RED_SALIDA/'red_perfil_longitudinal.png')
                for k in range(len(r.tramos)):
                    guardar_red_png(r,RED_SALIDA/f'red_perfil_tramo_{k+1:03d}.png',k)
                # Fuente del historial: datos del usuario, no cotas de campo inventadas.
                with (RED_SALIDA/'entrada_tramos_red.csv').open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.writer(f)
                    w.writerow(['Pozo_salida','Pozo_entrada','Abscisa_salida_m','Abscisa_entrada_m',
                                'Rasante_salida_m','Rasante_entrada_m','Lomo_salida_exterior_m',
                                'Batea_salida_exterior_m','Lomo_entrada_exterior_m',
                                'Batea_entrada_exterior_m','Material','Tipo_red'])
                    for t in tramos:
                        a,b=t.inicio,t.fin
                        w.writerow([a.nombre,b.nombre,a.abscisa_m,b.abscisa_m,a.cota_rasante_m,
                                    b.cota_rasante_m,a.cota_lomo_exterior_m,a.cota_batea_exterior_m,
                                    b.cota_lomo_exterior_m,b.cota_batea_exterior_m,t.material,t.red])
                return r
            r=await asyncio.to_thread(producir)
            carpeta_resultados=RED_SALIDA
            csv_entrada=RED_SALIDA/'entrada_tramos_red.csv'
            archivo_entrada.value='Datos de tramos de alcantarillado'
            guardar_boton.disabled=False
            cargar_resultados(); mostrar_graficas()
            red_aviso.value=(f"{len(r.tramos)} tramos | "
                f"{r.cantidades['longitud_m']:.2f} m | "
                f"{r.cantidades['numero_tubos_por_tramos']} tubos/cortes estimados | "
                f"advertencias: {len(r.advertencias)}. Lee RED_RESUMEN antes de usar cantidades.")
        except Exception as exc:
            red_aviso.value=f'No se generó la red: {exc}'
        page.update()

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

    async def guardar_memoria(e):
        """Genera la memoria reglada con docxtpl, no un simple Word tabular."""
        if not csv_entrada or not Path(csv_entrada).is_file():
            aviso_guardar.value = "Selecciona o recupera primero un proyecto con CSV válido."
            page.update()
            return
        try:
            aviso_guardar.value = "Generando memoria de cálculo..."
            page.update()
            if (carpeta_resultados / 'red_cantidades.csv').is_file():
                from app.memoria_obra import crear_memoria_obra
                contenido = await asyncio.to_thread(
                    crear_memoria_obra, carpeta_resultados, nombre_proyecto.value or 'Redes de alcantarillado', 'red')
                archivo_word = 'memoria_redes_alcantarillado.docx'
            elif (carpeta_resultados / 'cantidades_via.csv').is_file():
                from app.memoria_obra import crear_memoria_obra
                contenido = await asyncio.to_thread(
                    crear_memoria_obra, carpeta_resultados, nombre_proyecto.value or 'Diseño vial', 'via')
                archivo_word = 'memoria_diseno_vial.docx'
            else:
                paso = paso_automatico(csv_entrada)
                contenido = await asyncio.to_thread(
                    crear_memoria, csv_entrada, nombre_proyecto.value or "Perfil Vial", paso
                )
                archivo_word = 'memoria_interpolacion_eje.docx'
            destino = await ft.FilePicker().save_file(
                dialog_title="Guardar memoria de cálculo Word",
                file_name=archivo_word,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["docx"],
                src_bytes=contenido,
            )
            aviso_guardar.value = f"Memoria guardada: {destino}" if destino else "Guardado cancelado."
        except Exception as exc:
            aviso_guardar.value = f"No se pudo generar la memoria: {exc}"
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
            boton_rasante.disabled = not (carpeta_resultados / 'rasante_proyecto.csv').exists()
            boton_transversal.disabled = not (carpeta_resultados / 'rasante_proyecto.csv').exists()
            aviso.value = (
                f"Recuperado: {registro['nombre_proyecto']} · "
                f"cálculo #{registro['id']}. Resultados originales restaurados."
            )
            if csv_entrada.name == 'entrada_tramos_red.csv':
                red_aviso.value = ('Resultados de alcantarillado recuperados desde SQLite. '
                                   'Selecciona GRÁFICAS o DATOS para consultarlos.')
                mostrar_redes()
            else:
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
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS, spacing=12, controls=[
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
            ft.Text(f"Proyecto 02 | Programación II · V{VERSION_INTERFAZ}", color=VERDE, weight=ft.FontWeight.BOLD),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))

    def volver_modulo(e=None):
        if modulo_actual == "redes":
            mostrar_redes()
        else:
            mostrar_vias()

    def mostrar_graficas(e=None):
        # Pantalla REAL de resultados. En V7 se cambiaba un panel al final de la
        # página y parecía que el botón no hacía nada al quedarse fuera de vista.
        page.controls.clear()
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS, spacing=12, controls=[
            cabecera(),
            ft.Row(controls=[ft.Button("← VOLVER AL MÓDULO", on_click=volver_modulo),
                             ft.Button("DATOS E INFORMES", on_click=mostrar_datos)], wrap=True),
            tarjeta(ft.Column(controls=[
                ft.Text("01  |  VISUALIZADOR DE GRÁFICAS", size=21,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Elige una para visualizarla. Marca varias si deseas exportarlas.", color=GRIS),
                resumen, selector_grafica, titulo_vista,
                ft.Row(controls=[
                    ft.Button("＋ AMPLIAR", on_click=acercar_grafica),
                    ft.Button("－ ALEJAR", on_click=alejar_grafica),
                    ft.Button("RESTABLECER", on_click=restablecer_grafica),
                    ft.Text("Arrastra para mover la imagen ampliada; también puedes usar el gesto de zoom.",
                            color=GRIS, size=12),
                ], wrap=True),
                ft.Row(controls=[
                    ft.Container(content=visor_grafica, bgcolor=FONDO,
                                 padding=8, border_radius=10, expand=True, height=675),
                ]),
            ], spacing=12)),
            tarjeta(ft.Column(controls=[
                ft.Text("EXPORTAR GRÁFICAS", size=18, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[ft.Button("MARCAR TODAS", on_click=marcar_todas),
                                 ft.Button("LIMPIAR SELECCIÓN", on_click=limpiar_marcas),
                                 contador_seleccion], wrap=True),
                lista_seleccion,
                ft.Row(controls=[tipo_grafica,
                                 ft.Button("GUARDAR SELECCIONADAS", on_click=guardar_graficas)], wrap=True),
                aviso_guardar,
            ], spacing=12)),
        ]))
        if graficas:
            mostrar_grafica()
        else:
            titulo_vista.value = "Aún no hay gráficas. Regresa y ejecuta el cálculo."
            visor_grafica.visible = False
        page.update()

    def mostrar_datos(e=None):
        page.controls.clear()
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS, spacing=12, controls=[
            cabecera(),
            ft.Row(controls=[ft.Button("← VOLVER AL MÓDULO", on_click=volver_modulo),
                             ft.Button("GRÁFICAS", on_click=mostrar_graficas)], wrap=True),
            tarjeta(ft.Column(controls=[
                ft.Text("02  |  DATOS Y CARTERAS", size=21,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Selecciona un CSV o informe para ver su contenido.", color=GRIS),
                resumen, selector_datos, vista_datos,
            ], spacing=12)),
            tarjeta(ft.Column(controls=[
                ft.Text("EXPORTAR DATOS", size=18, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[tipo_datos, ft.Button("GUARDAR ARCHIVO", on_click=guardar_datos)], wrap=True),
                ft.Button("GENERAR MEMORIA DE CÁLCULO (DOCXTPL)", on_click=guardar_memoria),
                ft.Text("Exporta Excel, Word y CSV desde la cartera seleccionada. "
                        "La memoria técnica contiene resultados y una gráfica.", color=GRIS, size=12),
                aviso_guardar,
            ], spacing=12)),
        ]))
        mostrar_documento()
        page.update()

    def mostrar_vias(e=None):
        nonlocal modulo_actual
        modulo_actual = "vias"
        page.controls.clear()
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS, spacing=12, controls=[
            cabecera(),
            tarjeta(ft.Column(controls=[
                ft.Text("DISEÑO VIAL", size=23, weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[ft.Button("SELECCIONAR CSV", on_click=elegir_entrada),
                                 archivo_entrada, generar,
                                 ft.Button("LIMPIAR TODAS LAS CELDAS", on_click=limpiar_celdas)], wrap=True),
                aviso, resumen,
                ft.Row(controls=[nombre_proyecto, descripcion_proyecto, guardar_boton], wrap=True),
                aviso_historial,
                ft.Row(controls=[ft.Button("HISTORIAL", on_click=mostrar_historial),
                                 ft.Button("INICIO", on_click=mostrar_inicio)], wrap=True),
            ], spacing=11)),
            tarjeta(ft.Column(controls=[
                ft.Text("RASANTE LONGITUDINAL | BV IZQUIERDA · EJE · BV DERECHA", size=18,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Las TRES líneas conservan sus propias cotas medidas en la primera "
                        "y última abscisa. En cada tramo se aplica interpolación lineal, "
                        "incluyendo los sumideros como puntos de control. No hay opción de suavizado.",
                        color=GRIS),
                ft.Row(controls=[ancho_izq, ancho_der], wrap=True),
                ft.Row(controls=[pendiente_trans, orientacion_trans, pendiente_min_long],wrap=True),
                ft.Divider(),
                ft.Text("SUMIDEROS | INTRODUCIR ANTES DEL PREDISEÑO", size=17,
                        weight=ft.FontWeight.BOLD,color=AZUL),
                ft.Text("Cada sumidero recibe nombre, abscisa, costado y cota de rejilla. "
                        "Se utiliza esa cota en el BV indicado. Si no hay sumideros, escribe 0; "
                        "el programa revisará posibles zonas sin salida de agua.",color=GRIS,size=12),
                ft.Row(controls=[cantidad_sumideros,
                    ft.Button("GENERAR FILAS", on_click=ajustar_sumideros),
                    ft.Button("+ SUMIDERO", on_click=agregar_sumidero),
                    ft.Button("QUITAR ÚLTIMO", on_click=quitar_sumidero)],wrap=True),
                lista_sumideros,
                boton_rasante,
                estado_rasante,
            ], spacing=10)),
            tarjeta(ft.Column(controls=[
                ft.Text("SECCIONES TRANSVERSALES | CANTIDADES Y MATERIALES",size=18,
                        weight=ft.FontWeight.BOLD,color=AZUL),
                ft.Text("Se generan secciones comparativas de las cotas EXISTENTES y de "
                        "PROYECTO para todas las abscisas. Las cantidades emplean los semianchos "
                        "introducidos arriba y las capas configuradas aquí. Las pendientes "
                        "y la salida hidráulica requieren verificación adicional.",color=GRIS,size=12),
                ft.Row(controls=[e_asfalto,e_base,e_subbase,e_rajon,e_incremento],wrap=True),
                ft.Row(controls=[boton_transversal],wrap=True),
                aviso_transversal,
                ft.Row(controls=[ft.Button("GRÁFICAS",on_click=mostrar_graficas),
                                 ft.Button("DATOS E INFORMES",on_click=mostrar_datos)],wrap=True),
            ],spacing=10)),
        ]))
        page.update()

    def mostrar_redes(e=None):
        nonlocal modulo_actual
        modulo_actual = "redes"
        page.controls.clear()
        page.add(ft.Column(expand=True, scroll=ft.ScrollMode.ALWAYS, spacing=12, controls=[
            cabecera(),
            tarjeta(ft.Column(controls=[
                ft.Text("REDES DE ALCANTARILLADO | PERFIL ENTRE POZOS", size=23,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Define el número de pozos. El programa crea un tramo entre cada par "
                        "consecutivo. En cada pozo intermedio, el LOMO de entrada y salida tiene cota independiente; el diámetro se introduce una vez por tramo.",
                        color=GRIS),
                ft.Row(controls=[cantidad_pozos,
                    ft.Button("GENERAR / ACTUALIZAR POZOS", on_click=ajustar_pozos),
                    ft.Button("LIMPIAR TODAS LAS CELDAS", on_click=limpiar_celdas),
                    ft.Button("GRÁFICAS", on_click=mostrar_graficas),
                    ft.Button("DATOS E INFORMES", on_click=mostrar_datos),
                    ft.Button("HISTORIAL", on_click=mostrar_historial),
                    ft.Button("INICIO", on_click=mostrar_inicio)], wrap=True),
                red_aviso,
            ], spacing=10)),
            ft.Text("01 | DATOS DE LOS POZOS", size=18,
                    weight=ft.FontWeight.BOLD, color=AZUL),
            lista_pozos,
            ft.Text("02 | DIÁMETRO EXTERIOR, MATERIAL Y TIPO DE RED POR TRAMO", size=18,
                    weight=ft.FontWeight.BOLD, color=AZUL),
            lista_tramos,
            tarjeta(ft.Column(controls=[
                ft.Text("03 | INTERFERENCIAS EXISTENTES", size=18,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Text("Cada cruce se representa como un círculo de sección transversal "
                        "(perpendicular al colector). Registra abscisa, lomo exterior y "
                        "diámetro EXTERIOR en pulgadas; verificar el cruce real en planta.",
                        color=GRIS, size=12),
                ft.Row(controls=[cantidad_cruces,
                    ft.Button("GENERAR FILAS", on_click=ajustar_cruces),
                    ft.Button("+ INTERFERENCIA", on_click=agregar_cruce),
                    ft.Button("QUITAR ÚLTIMA", on_click=quitar_cruce)], wrap=True),
                lista_cruces,
            ], spacing=9)),
            tarjeta(ft.Column(controls=[
                ft.Text("04 | ZANJA Y CAPAS | PARÁMETROS EDITABLES", size=18,
                        weight=ft.FontWeight.BOLD, color=AZUL),
                ft.Row(controls=[red_sobreancho, red_cama, red_largo, red_base,
                                 red_asfalto, red_subbase, red_rajon, red_incremento], wrap=True),
                ft.Text("Los espesores indicados son valores de proyecto, NO límites normativos.",
                        color=GRIS, size=12),
                ft.Button("CALCULAR RED, PERFIL LONGITUDINAL Y CARTERA", on_click=procesar_redes),
                ft.Row(controls=[nombre_proyecto, descripcion_proyecto, guardar_boton], wrap=True),
                aviso_historial,
                ft.Row(controls=[ft.Button("VER GRÁFICAS", on_click=mostrar_graficas),
                                 ft.Button("VER DATOS E INFORMES", on_click=mostrar_datos)], wrap=True),
            ], spacing=10)),
        ]))
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
