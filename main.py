import asyncio
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import flet as ft

from perfil_vial.cli import run as ejecutar_perfiles


# Carpeta principal del proyecto
CARPETA_PROYECTO = Path(__file__).resolve().parent


def main(page: ft.Page):

    page.title = "PERFIL VIAL - Ingenieria Civil"

    # Variables de la interfaz
    archivo_csv = None

    texto_archivo = ft.Text("Ningun archivo seleccionado")
    texto_estado = ft.Text("")
    texto_resultados = ft.Text("")

    boton_generar = ft.Button(
        "GENERAR PERFILES Y SECCIONES",
        disabled=True,
    )

    # Seleccionar archivo CSV
    async def seleccionar_csv(e):
        nonlocal archivo_csv

        try:
            archivos = await ft.FilePicker().pick_files(
                dialog_title="Seleccionar archivo topografico",
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv"],
            )

            if not archivos:
                return

            if not archivos[0].path:
                texto_estado.value = (
                    "No se pudo obtener la ruta del archivo."
                )
                page.update()
                return

            archivo_csv = Path(archivos[0].path)

            texto_archivo.value = (
                f"Archivo seleccionado: {archivo_csv.name}"
            )

            texto_estado.value = "CSV seleccionado correctamente."
            texto_resultados.value = ""
            boton_generar.disabled = False

        except Exception as error:
            texto_estado.value = f"Error al seleccionar: {error}"

        page.update()

    # Ejecutar los calculos originales
    async def generar_perfiles(e):

        if archivo_csv is None or not archivo_csv.is_file():
            texto_estado.value = "Selecciona un archivo CSV valido."
            page.update()
            return

        carpeta_salida = CARPETA_PROYECTO / "salida"

        boton_generar.disabled = True
        texto_estado.value = "Procesando informacion topografica..."
        texto_resultados.value = ""
        page.update()

        try:
            resultado = await asyncio.to_thread(
                ejecutar_perfiles,
                [
                    str(archivo_csv),
                    "-o",
                    str(carpeta_salida),
                ],
            )

            if resultado == 0:
                archivos = sorted(carpeta_salida.iterdir())

                texto_estado.value = (
                    "Calculos realizados correctamente."
                )

                texto_resultados.value = (
                    f"Carpeta: {carpeta_salida}\n"
                    f"Archivos encontrados: {len(archivos)}"
                )

            else:
                texto_estado.value = (
                    "No fue posible completar el calculo. "
                    "Revisa los mensajes de la terminal."
                )

        except Exception as error:
            texto_estado.value = f"Error: {error}"

        finally:
            boton_generar.disabled = False
            page.update()

    boton_generar.on_click = generar_perfiles

    # Pantalla principal
    def mostrar_inicio():

        page.controls.clear()

        page.add(
            ft.Column(
                controls=[
                    ft.Text(
                        "PERFIL VIAL",
                        size=32,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Aplicacion de Ingenieria Civil",
                        size=18,
                    ),
                    ft.Divider(),
                    ft.Button(
                        "DISENO VIAL",
                        on_click=lambda e: mostrar_vias(),
                    ),
                    ft.Button(
                        "REDES DE ALCANTARILLADO",
                        on_click=lambda e: mostrar_redes(),
                    ),
                ],
                spacing=20,
            )
        )

        page.update()

    # Modulo de diseno vial
    def mostrar_vias():

        page.controls.clear()

        page.add(
            ft.Column(
                controls=[
                    ft.Text(
                        "MODULO DE DISENO VIAL",
                        size=26,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Generacion de perfiles y secciones transversales"
                    ),
                    ft.Divider(),

                    ft.Button(
                        "SELECCIONAR ARCHIVO CSV",
                        on_click=seleccionar_csv,
                    ),

                    texto_archivo,

                    boton_generar,

                    texto_estado,

                    texto_resultados,

                    ft.Divider(),

                    ft.Button(
                        "VOLVER AL INICIO",
                        on_click=lambda e: mostrar_inicio(),
                    ),
                ],
                spacing=15,
            )
        )

        page.update()

    # Modulo de alcantarillado
    def mostrar_redes():

        page.controls.clear()

        page.add(
            ft.Column(
                controls=[
                    ft.Text(
                        "MODULO DE ALCANTARILLADO",
                        size=26,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Pozos, tuberias e interferencias."
                    ),
                    ft.Text(
                        "Modulo en desarrollo."
                    ),
                    ft.Button(
                        "VOLVER AL INICIO",
                        on_click=lambda e: mostrar_inicio(),
                    ),
                ],
                spacing=20,
            )
        )

        page.update()

    mostrar_inicio()


if __name__ == "__main__":
    ft.run(main)


