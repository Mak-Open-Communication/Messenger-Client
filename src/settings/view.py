import flet as ft
from typing import Callable, Awaitable


class SettingsView:
    def __init__(
        self,
        page: ft.Page,
        on_theme_toggle: Callable,
        on_display_name_save: Callable[[str], Awaitable],
        on_logout: Callable[..., Awaitable],
        on_back: Callable,
        on_revoke_token: Callable[[str], Awaitable] = None,
    ):
        self.page = page
        self.on_theme_toggle = on_theme_toggle
        self.on_display_name_save = on_display_name_save
        self.on_logout = on_logout
        self.on_back = on_back
        self.on_revoke_token = on_revoke_token

        self.display_name_field = ft.TextField(label="Display name", width=300)
        self.server_field = ft.TextField(label="Server address", width=300, read_only=True)
        self.theme_switch = ft.Switch(
            label="Dark mode",
            value=page.theme_mode == ft.ThemeMode.DARK,
            on_change=self._theme_changed,
        )
        self._sessions_column = ft.Column(spacing=4)
        self._sessions_loading = ft.ProgressRing(visible=False, width=20, height=20)

    def build(self, is_narrow: bool = False) -> ft.Column:
        back_btn = ft.IconButton(ft.Icons.ARROW_BACK, on_click=self.on_back, tooltip="Back")

        header = ft.Container(
            content=ft.Row(
                controls=[
                    back_btn,
                    ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD, expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.SURFACE,
        )

        content = ft.Column(
            controls=[
                ft.Text("Appearance", size=16, weight=ft.FontWeight.BOLD),
                self.theme_switch,
                ft.Divider(),
                ft.Text("Profile", size=16, weight=ft.FontWeight.BOLD),
                self.display_name_field,
                ft.ElevatedButton("Save", on_click=self._save_name, width=120),
                ft.Divider(),
                ft.Text("Server", size=16, weight=ft.FontWeight.BOLD),
                self.server_field,
                ft.Divider(),
                ft.Text("Active Sessions", size=16, weight=ft.FontWeight.BOLD),
                self._sessions_loading,
                self._sessions_column,
                ft.Divider(),
                ft.Container(height=8),
                ft.ElevatedButton(
                    "Logout",
                    icon=ft.Icons.LOGOUT,
                    on_click=self._logout_click,
                    color=ft.Colors.ERROR,
                    width=200,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Column(
            controls=[
                header,
                ft.Divider(height=1),
                ft.Container(content=content, padding=ft.padding.all(20), expand=True),
            ],
            expand=True,
            spacing=0,
        )

    def set_user_info(self, display_name: str, server_addr: str):
        self.display_name_field.value = display_name
        self.server_field.value = server_addr

    def set_sessions(self, tokens: list):
        self._sessions_column.controls.clear()
        self._sessions_loading.visible = False
        for t in tokens:
            if isinstance(t, dict):
                agent = t.get("agent", "unknown") or "unknown"
                token_str = t.get("token", "")
                is_current = t.get("is_current", False)
                is_online = t.get("is_online", False)
            else:
                agent = getattr(t, "agent", "unknown") or "unknown"
                token_str = getattr(t, "token", "")
                is_current = getattr(t, "is_current", False)
                is_online = getattr(t, "is_online", False)

            label = agent
            if is_current:
                label += " (current)"
            if is_online:
                label += " - online"

            row_controls = [
                ft.Icon(ft.Icons.DEVICES, size=20),
                ft.Text(label, size=14, expand=True),
            ]
            if not is_current and self.on_revoke_token:
                def _make_revoke_handler(tk):
                    async def revoke_click(e):
                        await self._revoke_token(tk)
                    return revoke_click

                revoke_click = _make_revoke_handler(token_str)

                row_controls.append(
                    ft.IconButton(
                        ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        tooltip="Revoke session",
                        on_click=revoke_click,
                    )
                )

            self._sessions_column.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=row_controls,
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                )
            )

    async def _theme_changed(self, e):
        await self.on_theme_toggle(e.control.value)

    async def _save_name(self, e):
        name = self.display_name_field.value.strip()
        if name:
            await self.on_display_name_save(name)

    async def _revoke_token(self, token_str: str):
        if self.on_revoke_token:
            await self.on_revoke_token(token_str)

    async def _logout_click(self, e):
        await self.on_logout()
