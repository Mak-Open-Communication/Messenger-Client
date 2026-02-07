import flet as ft

from src.app import Application


async def main(page: ft.Page):

    app = Application(page)

    await app.start()


ft.run(main)
