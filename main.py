import flet as ft

from src.app import Application


async def main(page: ft.Page):
    try:
        app = Application(page)
        await app.start()
    except Exception as e:
        page.controls.clear()
        page.controls.append(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Startup Error", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.ERROR),
                        ft.Text(str(e), size=14, selectable=True),
                    ],
                    spacing=12,
                ),
                padding=ft.padding.all(20),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        )
        page.update()


ft.run(main)
