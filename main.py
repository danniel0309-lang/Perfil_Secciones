import flet as ft


def main(page: ft.Page):

    # Configuracion de la ventana
    page.title = "PERFIL VIAL - Ingenieria Civil"

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
                        on_click=lambda e: mostrar_modulo("vias"),
                    ),
                    ft.Button(
                        "REDES DE ALCANTARILLADO",
                        on_click=lambda e: mostrar_modulo("redes"),
                    ),
                ],
                spacing=20,
            )
        )

        page.update()

    # Pantallas de los modulos
    def mostrar_modulo(modulo):
        page.controls.clear()

        if modulo == "vias":
            titulo = "MODULO DE DISENO VIAL"
            descripcion = "Perfiles, secciones y cantidades de obra."
        else:
            titulo = "MODULO DE ALCANTARILLADO"
            descripcion = "Pozos, tuberias e interferencias."

        page.add(
            ft.Column(
                controls=[
                    ft.Text(
                        titulo,
                        size=25,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(descripcion),
                    ft.Divider(),
                    ft.Button(
                        "VOLVER AL INICIO",
                        on_click=lambda e: mostrar_inicio(),
                    ),
                ],
                spacing=20,
            )
        )

        page.update()

    # Abrir la pantalla principal
    mostrar_inicio()


if __name__ == "__main__":
    ft.run(main)

