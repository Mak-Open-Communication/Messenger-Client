import flet as ft
from typing import Callable, Awaitable


class AuthView:
    def __init__(self, page: ft.Page, on_login_success: Callable[..., Awaitable]):
        self.page = page
        self.on_login_success = on_login_success
        self._is_register = False

        self.server_field = ft.TextField(
            label="Server address",
            hint_text="host:port",
            value="127.0.0.1:4207",
        )
        self.username_field = ft.TextField(label="Username", autofocus=True)
        self.password_field = ft.TextField(
            label="Password", password=True, can_reveal_password=True,
        )
        self.display_name_field = ft.TextField(label="Display name", visible=False)

        self.error_text = ft.Text("", color=ft.Colors.RED, visible=False, size=13)
        self.submit_btn = ft.ElevatedButton("Log in", on_click=self._on_submit, width=200)
        self.toggle_link = ft.TextButton(
            "Don't have an account? Register", on_click=self._toggle_mode,
        )
        self.progress = ft.ProgressRing(visible=False, width=20, height=20)

    def build(self) -> ft.Container:
        form = ft.Column(
            controls=[
                ft.Text("GHosty", size=32, weight=ft.FontWeight.BOLD),
                ft.Text("Messenger", size=16, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(height=20),
                self.server_field,
                self.username_field,
                self.password_field,
                self.display_name_field,
                self.error_text,
                ft.Container(height=10),
                ft.Row(
                    [self.submit_btn, self.progress],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [self.toggle_link],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            width=350,
        )
        return ft.Container(
            content=form,
            alignment=ft.Alignment.CENTER,
            expand=True,
            padding=ft.padding.all(20),
        )

    def _toggle_mode(self, e):
        self._is_register = not self._is_register
        self.display_name_field.visible = self._is_register
        self.submit_btn.text = "Register" if self._is_register else "Log in"
        self.toggle_link.text = (
            "Already have an account? Log in" if self._is_register
            else "Don't have an account? Register"
        )
        self.error_text.visible = False
        self.page.update()

    async def _on_submit(self, e):
        username = self.username_field.value.strip()
        password = self.password_field.value.strip()
        if not username or not password:
            self._show_error("Username and password are required")
            return
        if self._is_register:
            display_name = self.display_name_field.value.strip()
            if not display_name:
                self._show_error("Display name is required")
                return

        host, port = self._parse_server(self.server_field.value.strip())
        if not host:
            self._show_error("Invalid server address. Use host:port format.")
            return

        self.submit_btn.disabled = True
        self.progress.visible = True
        self.error_text.visible = False
        self.page.update()

        try:
            await self.on_login_success(
                host=host,
                port=port,
                username=username,
                password=password,
                display_name=self.display_name_field.value.strip() if self._is_register else None,
                is_register=self._is_register,
            )
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.submit_btn.disabled = False
            self.progress.visible = False
            self.page.update()

    def _parse_server(self, text: str) -> tuple:
        try:
            if ":" in text:
                parts = text.rsplit(":", 1)
                return parts[0], int(parts[1])
            return text, 4207
        except (ValueError, IndexError):
            return None, None

    def _show_error(self, msg: str):
        self.error_text.value = msg
        self.error_text.visible = True
        self.page.update()

    def set_server_address(self, host: str, port: int):
        self.server_field.value = f"{host}:{port}"
