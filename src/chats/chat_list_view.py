import flet as ft
from typing import Callable, Awaitable, Optional

from src.common.models import Chat


class ChatListView:
    def __init__(
        self,
        page: ft.Page,
        on_chat_selected: Callable[[Chat], Awaitable],
        on_settings_click: Callable,
        on_new_chat: Callable[..., Awaitable],
    ):
        self.page = page
        self.on_chat_selected = on_chat_selected
        self.on_settings_click = on_settings_click
        self.on_new_chat = on_new_chat

        self.chats: list[Chat] = []
        self.selected_chat_id: Optional[int] = None

        self._list_view = ft.ListView(expand=True, spacing=0, padding=ft.padding.symmetric(vertical=4))
        self._loading = ft.ProgressRing(width=30, height=30)
        self._loading_container: Optional[ft.Container] = None
        self._empty_text = ft.Text(
            "No chats yet", size=14, color=ft.Colors.ON_SURFACE_VARIANT,
            text_align=ft.TextAlign.CENTER,
        )
        self._empty_container: Optional[ft.Container] = None
        self._root: Optional[ft.Column] = None

    def build(self) -> ft.Column:
        if self._root is not None:
            return self._root

        async def fab_click(e):
            await self.on_new_chat()

        appbar = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("GHosty", size=20, weight=ft.FontWeight.BOLD, expand=True),
                    ft.IconButton(ft.Icons.SETTINGS, on_click=self.on_settings_click, tooltip="Settings"),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            bgcolor=ft.Colors.SURFACE,
        )

        self._loading_container = ft.Container(
            content=self._loading, alignment=ft.Alignment.CENTER, visible=False,
        )
        self._empty_container = ft.Container(
            content=self._empty_text, alignment=ft.Alignment.CENTER, visible=False,
        )

        body = ft.Stack(
            controls=[
                self._list_view,
                self._loading_container,
                self._empty_container,
            ],
            expand=True,
        )

        fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=fab_click,
            tooltip="New chat",
            mini=True,
        )

        self._root = ft.Column(
            controls=[
                appbar,
                ft.Divider(height=1),
                ft.Container(content=body, expand=True),
                ft.Container(
                    content=fab,
                    alignment=ft.Alignment.BOTTOM_RIGHT,
                    padding=ft.padding.only(right=16, bottom=16),
                ),
            ],
            expand=True,
            spacing=0,
        )
        return self._root

    def set_loading(self, loading: bool):
        if self._loading_container:
            self._loading_container.visible = loading
        if self._empty_container:
            self._empty_container.visible = False

    def update_chats(self, chats: list[Chat]):
        self.chats = chats
        self._list_view.controls.clear()
        if not chats:
            if self._empty_container:
                self._empty_container.visible = True
        else:
            if self._empty_container:
                self._empty_container.visible = False
            for chat in chats:
                self._list_view.controls.append(self._build_chat_tile(chat))

    def _build_chat_tile(self, chat: Chat) -> ft.Control:
        is_selected = chat.chat_id == self.selected_chat_id
        member_count = len(chat.members)
        initial = chat.chat_name[0].upper() if chat.chat_name else "?"

        async def on_click(e):
            await self._chat_clicked(chat)

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.CircleAvatar(
                        content=ft.Text(initial, size=16, weight=ft.FontWeight.BOLD),
                        bgcolor=ft.Colors.PRIMARY_CONTAINER,
                        radius=22,
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(chat.chat_name, weight=ft.FontWeight.W_500, size=15),
                            ft.Text(
                                f"{member_count} member{'s' if member_count != 1 else ''}",
                                size=12, color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=16, vertical=10),
            bgcolor=ft.Colors.SECONDARY_CONTAINER if is_selected else None,
            border_radius=ft.border_radius.all(8),
            margin=ft.margin.symmetric(horizontal=4, vertical=1),
            on_click=on_click,
            ink=True,
        )

    async def _chat_clicked(self, chat: Chat):
        self.selected_chat_id = chat.chat_id
        self.update_chats(self.chats)
        self.page.update()
        await self.on_chat_selected(chat)
