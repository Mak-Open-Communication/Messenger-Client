import flet as ft
from typing import Callable, Awaitable, Optional

from src.common.models import Chat, Message
from src.messages.components import MessageBubble, MessageInput


class ChatView:
    def __init__(
        self,
        page: ft.Page,
        on_send_message: Callable[[int, str], Awaitable],
        on_back: Callable,
        on_chat_menu_action: Callable[[str, Chat], Awaitable],
        current_user_id: int = 0,
    ):
        self.page = page
        self.on_send_message = on_send_message
        self.on_back = on_back
        self.on_chat_menu_action = on_chat_menu_action
        self.current_user_id = current_user_id

        self._current_chat: Optional[Chat] = None
        self._messages: list[Message] = []

        self._message_list = ft.ListView(
            expand=True, spacing=4, auto_scroll=True,
            padding=ft.padding.symmetric(horizontal=4, vertical=8),
        )
        self._message_input = MessageInput(on_send=self._handle_send)
        self._header_title = ft.Text("", weight=ft.FontWeight.W_500, size=16)

        self._placeholder = ft.Container(
            content=ft.Text(
                "Select a chat", size=18,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

        async def rename_click(e):
            await self._menu_action("rename")

        async def add_member_click(e):
            await self._menu_action("add_member")

        async def leave_click(e):
            await self._menu_action("leave")

        async def delete_click(e):
            await self._menu_action("delete")

        self._back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=self.on_back,
            tooltip="Back",
            visible=False,
        )

        menu_btn = ft.PopupMenuButton(
            items=[
                ft.PopupMenuItem(content=ft.Text("Rename"), on_click=rename_click),
                ft.PopupMenuItem(content=ft.Text("Add member"), on_click=add_member_click),
                ft.PopupMenuItem(content=ft.Text("Leave chat"), on_click=leave_click),
                ft.PopupMenuItem(content=ft.Text("Delete chat"), on_click=delete_click),
            ],
        )

        header = ft.Container(
            content=ft.Row(
                controls=[
                    self._back_btn,
                    ft.Container(content=self._header_title, expand=True),
                    menu_btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            bgcolor=ft.Colors.SURFACE,
        )

        self._chat_column = ft.Column(
            controls=[
                header,
                ft.Divider(height=1),
                self._message_list,
                ft.Divider(height=1),
                self._message_input,
            ],
            expand=True,
            spacing=0,
            visible=False,
        )

        self._root = ft.Column(
            controls=[self._placeholder, self._chat_column],
            expand=True,
            spacing=0,
        )

    def build(self, is_narrow: bool = False) -> ft.Column:
        if self._current_chat is None:
            self._chat_column.visible = False
            self._placeholder.visible = True
        else:
            self._chat_column.visible = True
            self._placeholder.visible = False
            self._back_btn.visible = is_narrow
        return self._root

    def set_chat(self, chat: Optional[Chat]):
        self._current_chat = chat
        if chat:
            self._header_title.value = chat.chat_name
        self._messages.clear()
        self._message_list.controls.clear()

    def set_messages(self, messages: list[Message]):
        self._messages = messages
        self._rebuild_message_list()

    def append_message(self, message: Message):
        self._messages.append(message)
        is_mine = message.sender_user and message.sender_user.account_id == self.current_user_id
        self._message_list.controls.append(MessageBubble(message, is_mine))

    def _rebuild_message_list(self):
        self._message_list.controls.clear()
        for msg in self._messages:
            is_mine = msg.sender_user and msg.sender_user.account_id == self.current_user_id
            self._message_list.controls.append(MessageBubble(msg, is_mine))

    async def _handle_send(self, text: str):
        if self._current_chat:
            await self.on_send_message(self._current_chat.chat_id, text)

    async def _menu_action(self, action: str):
        if self._current_chat:
            await self.on_chat_menu_action(action, self._current_chat)
