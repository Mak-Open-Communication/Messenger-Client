import asyncio
import logging
from typing import Optional

import flet as ft

from src.services.api import ApiService, detect_agent
from src.services.storage import StorageService
from src.common.models import Account, Chat, Message, Result
from src.auth.view import AuthView
from src.chats.chat_list_view import ChatListView
from src.chats.chat_view import ChatView
from src.settings.view import SettingsView

logger = logging.getLogger("ghosty.app")

BREAKPOINT_WIDTH = 768
RECONNECT_INTERVAL = 5


class Application:
    def __init__(self, page: ft.Page):
        self.page = page
        self.api = ApiService()
        self.storage = StorageService()

        self._current_user_id: int = 0
        self._current_username: str = ""
        self._current_display_name: str = ""
        self._current_chat: Optional[Chat] = None
        self._is_wide: bool = True
        self._screen: str = "auth"
        self._connection_task: Optional[asyncio.Task] = None

        self._auth_view: Optional[AuthView] = None
        self._chat_list_view: Optional[ChatListView] = None
        self._chat_view: Optional[ChatView] = None
        self._settings_view: Optional[SettingsView] = None

    async def start(self):
        self.page.title = "GHosty"
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        self.page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        self.page.padding = 0
        self.page.spacing = 0

        theme_mode = await self.storage.get_theme_mode()
        self.page.theme_mode = ft.ThemeMode.DARK if theme_mode == "dark" else ft.ThemeMode.LIGHT

        if self.page.platform in (
            ft.PagePlatform.LINUX, ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS,
        ):
            self.page.window.width = 900
            self.page.window.height = 650
            self.page.window.min_width = 380
            self.page.window.min_height = 500

        self.page.on_resize = self._on_resize
        self._is_wide = (self.page.width or 900) >= BREAKPOINT_WIDTH

        token = await self.storage.get_token()
        if token:
            host, port = await self.storage.get_server_address()
            try:
                await self.api.connect(host, port)
                self.api.set_token(token)
                verify = await self.api.verify_token()
                if verify.success and verify.data:
                    user_info = await self.storage.get_user_info()
                    self._current_user_id = int(user_info.get("user_id") or 0)
                    self._current_username = user_info.get("username") or ""
                    self._current_display_name = user_info.get("display_name") or ""
                    await self._show_main_screen()
                    return
            except Exception as e:
                logger.warning(f"Session restore failed: {e}")
            await self.storage.clear_token()
            self.api.clear_token()

        await self._show_auth_screen()

    # --- Screen transitions ---

    async def _show_auth_screen(self):
        self._stop_connection()
        self._screen = "auth"
        self._auth_view = AuthView(self.page, on_login_success=self._handle_auth)
        host, port = await self.storage.get_server_address()
        self._auth_view.set_server_address(host, port)
        self._render()

    async def _show_main_screen(self):
        self._screen = "main"
        self._current_chat = None
        self._chat_list_view = ChatListView(
            page=self.page,
            on_chat_selected=self._on_chat_selected,
            on_settings_click=self._settings_click,
            on_new_chat=self._on_new_chat,
        )
        self._chat_view = ChatView(
            page=self.page,
            on_send_message=self._on_send_message,
            on_back=lambda e: self._on_chat_back(),
            on_chat_menu_action=self._on_chat_menu_action,
            on_message_action=self._on_message_action,
            current_user_id=self._current_user_id,
        )
        self._render()
        await self._load_chats()
        self._start_connection()

    async def _show_settings(self):
        self._screen = "settings"
        self._settings_view = SettingsView(
            page=self.page,
            on_theme_toggle=self._on_theme_toggle,
            on_display_name_save=self._on_display_name_save,
            on_logout=self._on_logout,
            on_back=self._settings_back_click,
            on_revoke_token=self._on_revoke_token,
        )
        host, port = await self.storage.get_server_address()
        self._settings_view.set_user_info(self._current_display_name, f"{host}:{port}")
        self._render()

        result = await self.api.get_my_tokens()
        if result.success and result.data:
            if isinstance(result.data, list):
                self._settings_view.set_sessions(result.data)
                self.page.update()

    async def _back_from_settings(self):
        await self._show_main_screen()

    def _show_error(self, message: str):
        dialog = ft.AlertDialog(
            title=ft.Text("Error"),
            content=ft.Text(str(message)),
            actions=[ft.TextButton("OK", on_click=lambda e: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    async def _settings_click(self, e):
        await self._show_settings()

    async def _settings_back_click(self, e):
        await self._back_from_settings()

    # --- Connection loop + Subscription ---

    def _start_connection(self):
        self._stop_connection()
        self._connection_task = asyncio.create_task(self._connection_loop())

    def _stop_connection(self):
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
        self._connection_task = None

    async def _connection_loop(self):
        try:
            while True:
                if not self.api.connected:
                    logger.info("Connection lost, attempting reconnect...")
                    ok = await self.api.reconnect()
                    if not ok:
                        await asyncio.sleep(RECONNECT_INTERVAL)
                        continue
                    logger.info("Reconnected successfully")
                    await self._on_reconnected()

                try:
                    await self._run_subscription()
                except Exception as e:
                    logger.warning(f"Subscription ended: {e}")
                    await asyncio.sleep(RECONNECT_INTERVAL)

        except asyncio.CancelledError:
            pass

    async def _run_subscription(self):
        token = self.api.get_token()
        if not token:
            await asyncio.sleep(RECONNECT_INTERVAL)
            return

        sub_client = await self.api.create_subscription_client()
        if not sub_client:
            await asyncio.sleep(RECONNECT_INTERVAL)
            return

        try:
            async with sub_client.subscribe(event_type="subscribe", token=token) as sub:
                async for event in sub:
                    try:
                        await self._handle_event(event)
                    except Exception as e:
                        logger.error(f"Event handler error: {e}", exc_info=True)
        finally:
            try:
                await sub_client.disconnect()
            except Exception:
                pass

    async def _handle_event(self, event):
        if not isinstance(event, dict):
            return
        event_type = event.get("type", "")
        data = event.get("data", {})
        if not isinstance(data, dict):
            data = {}

        if event_type == "new_message":
            await self._on_new_message_event(data)
        elif event_type == "message_edited" or event_type == "message_deleted":
            await self._on_message_changed_event(data)
        elif event_type == "user_online":
            await self._on_user_status_event(data, True)
        elif event_type == "user_offline":
            await self._on_user_status_event(data, False)
        elif event_type in ("chat_created", "member_added", "member_removed"):
            await self._on_chat_list_changed()

    async def _on_new_message_event(self, data: dict):
        chat_id = data.get("chat_id")
        sender_id = data.get("sender_user_id")

        if self._current_chat and self._current_chat.chat_id == chat_id:
            if sender_id != self._current_user_id:
                await self._reload_current_messages()

        if self._screen == "main":
            await self._load_chats()

    async def _on_message_changed_event(self, data: dict):
        chat_id = data.get("chat_id")
        if self._current_chat and self._current_chat.chat_id == chat_id:
            await self._reload_current_messages()

    async def _on_user_status_event(self, data: dict, is_online: bool):
        user_id = data.get("user_id")
        if self._current_chat:
            for member in self._current_chat.members:
                if member.account_id == user_id:
                    member.in_online = is_online
                    self._update_peer_status()
                    self.page.update()
                    break

    async def _on_chat_list_changed(self):
        if self._screen == "main":
            await self._load_chats()

    async def _reload_current_messages(self):
        if not self._current_chat or not self._chat_view:
            return
        result = await self.api.get_messages(self._current_chat.chat_id, limit=50)
        if result.success and result.data:
            msgs = [Message.from_dict(m) if isinstance(m, dict) else m for m in result.data]
            msgs.sort(key=lambda m: m.message_id)
            self._chat_view.set_messages(msgs)
            self.page.update()

    async def _on_reconnected(self):
        if self._screen == "main":
            await self._load_chats()
            if self._current_chat:
                result = await self.api.get_chat_info(self._current_chat.chat_id)
                if result.success and result.data:
                    self._current_chat = Chat.from_dict(result.data) if isinstance(result.data, dict) else result.data
                    self._update_peer_status()
                await self._reload_current_messages()

    # --- Peer status ---

    def _update_peer_status(self):
        if not self._current_chat or not self._chat_view:
            return
        others = [m for m in self._current_chat.members if m.account_id != self._current_user_id]
        if len(others) == 1:
            peer = others[0]
            self._chat_view.set_peer_status(peer.display_name, peer.in_online)
        else:
            self._chat_view.set_peer_status(None, False)
            self._chat_view._header_title.value = self._current_chat.chat_name

    # --- Render ---

    def _render(self):
        self.page.controls.clear()
        self.page.appbar = None
        self.page.floating_action_button = None

        if self._screen == "auth":
            self.page.controls.append(self._auth_view.build())

        elif self._screen == "main":
            chat_list_root = self._chat_list_view.build()
            chat_view_root = self._chat_view.build(is_narrow=not self._is_wide)

            if self._is_wide:
                sidebar = ft.Container(
                    content=chat_list_root,
                    width=320,
                    border=ft.border.only(right=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
                )
                chat_area = ft.Container(
                    content=chat_view_root,
                    expand=True,
                )
                self.page.controls.append(
                    ft.Row(
                        controls=[sidebar, chat_area],
                        expand=True,
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    )
                )
            else:
                has_chat = self._current_chat is not None
                chat_list_root.visible = not has_chat
                chat_view_root.visible = has_chat
                self.page.controls.append(chat_list_root)
                self.page.controls.append(chat_view_root)

        elif self._screen == "settings":
            self.page.controls.append(
                self._settings_view.build(is_narrow=not self._is_wide)
            )

        self.page.update()

    def _update_chat_selection(self):
        is_narrow = not self._is_wide
        self._chat_view.build(is_narrow=is_narrow)
        if is_narrow:
            has_chat = self._current_chat is not None
            self._chat_list_view.build().visible = not has_chat
            self._chat_view._root.visible = has_chat
        self.page.update()

    def _on_resize(self, e):
        was_wide = self._is_wide
        self._is_wide = e.width >= BREAKPOINT_WIDTH
        if was_wide != self._is_wide and self._screen in ("main", "settings"):
            self._render()

    # --- Auth ---

    async def _handle_auth(self, host: str, port: int, username: str,
                           password: str, display_name: str, is_register: bool):
        await self.api.connect(host, port)
        agent = detect_agent(self.page)

        if is_register:
            result = await self.api.register(username, display_name, password, agent)
        else:
            result = await self.api.login(username, password, agent)

        if not result.success:
            raise Exception(result.error_message or "Authentication failed")

        data = result.data
        token_str = ""
        account_id = 0
        account_username = username
        account_display_name = display_name or username

        if isinstance(data, dict):
            token_dict = data.get("token", {})
            account_dict = data.get("account", {})

            if isinstance(token_dict, dict):
                token_str = token_dict.get("token", "")
            if isinstance(account_dict, dict):
                account_id = account_dict.get("account_id", 0)
                account_username = account_dict.get("username", username)
                account_display_name = account_dict.get("display_name", display_name or username)

        self._current_user_id = account_id
        self._current_username = account_username
        self._current_display_name = account_display_name

        await self.storage.set_token(token_str)
        await self.storage.set_server_address(host, port)
        await self.storage.save_user_info(account_username, account_display_name, account_id)

        await self._show_main_screen()

    # --- Chat list ---

    async def _load_chats(self):
        if not self._chat_list_view:
            return
        self._chat_list_view.set_loading(True)
        self.page.update()

        result = await self.api.get_my_chats()

        self._chat_list_view.set_loading(False)
        if result.success and result.data:
            chats = [Chat.from_dict(c) if isinstance(c, dict) else c for c in result.data]
            self._chat_list_view.update_chats(chats)
        self.page.update()

    async def _on_chat_selected(self, chat: Chat):
        try:
            self._current_chat = chat
            self._chat_view.set_chat(chat)
            self._update_peer_status()
            self._update_chat_selection()

            result = await self.api.get_messages(chat.chat_id, limit=50)
            if result.success and result.data:
                msgs = [Message.from_dict(m) if isinstance(m, dict) else m for m in result.data]
                msgs.sort(key=lambda m: m.message_id)
                self._chat_view.set_messages(msgs)

            result = await self.api.get_chat_info(chat.chat_id)
            if result.success and result.data:
                self._current_chat = Chat.from_dict(result.data) if isinstance(result.data, dict) else result.data
                self._update_peer_status()

            self.page.update()
        except Exception as e:
            logger.error(f"Chat selection failed: {e}", exc_info=True)
            self._show_error(f"Failed to open chat: {e}")

    async def _on_new_chat(self):
        name_field = ft.TextField(label="Chat name", autofocus=True)
        members_field = ft.TextField(label="Members (usernames, comma-separated)")
        error_text = ft.Text("", color=ft.Colors.RED, visible=False, size=13)

        async def create(e):
            chat_name = name_field.value.strip()
            if not chat_name:
                error_text.value = "Chat name is required"
                error_text.visible = True
                self.page.update()
                return

            members_text = members_field.value.strip()
            members = [m.strip() for m in members_text.split(",") if m.strip()]
            if self._current_username and self._current_username not in members:
                members.append(self._current_username)

            result = await self.api.create_chat(chat_name, members)
            self.page.pop_dialog()
            if result.success:
                await self._load_chats()
            else:
                self._show_error(result.error_message or "Failed to create chat")
            self.page.update()

        dialog = ft.AlertDialog(
            title=ft.Text("New Chat"),
            content=ft.Column(
                [name_field, members_field, error_text],
                tight=True, spacing=12,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("Create", on_click=create),
            ],
        )
        self.page.show_dialog(dialog)

    def _on_chat_back(self):
        self._current_chat = None
        if self._chat_view:
            self._chat_view.set_chat(None)
        self._update_chat_selection()

    # --- Messages ---

    async def _on_send_message(self, chat_id: int, text: str):
        result = await self.api.send_message(chat_id, text)
        if result.success and result.data:
            msg = Message.from_dict(result.data) if isinstance(result.data, dict) else result.data
            self._chat_view.append_message(msg)
        elif not result.success:
            self._show_error(result.error_message or "Failed to send message")
        self.page.update()

    # --- Message context menu ---

    async def _on_message_action(self, message: Message):
        is_mine = message.sender_user and message.sender_user.account_id == self._current_user_id

        buttons = []

        if is_mine:
            async def edit_click(e):
                self.page.pop_dialog()
                await self._show_edit_message_dialog(message)

            buttons.append(
                ft.TextButton(
                    content=ft.Row(
                        [ft.Icon(ft.Icons.EDIT, size=20), ft.Text("Edit")],
                        spacing=12,
                    ),
                    on_click=edit_click,
                )
            )

        async def delete_click(e):
            self.page.pop_dialog()
            await self._show_delete_message_dialog(message)

        buttons.append(
            ft.TextButton(
                content=ft.Row(
                    [ft.Icon(ft.Icons.DELETE, size=20, color=ft.Colors.ERROR), ft.Text("Delete", color=ft.Colors.ERROR)],
                    spacing=12,
                ),
                on_click=delete_click,
            )
        )

        dialog = ft.AlertDialog(
            content=ft.Column(buttons, tight=True, spacing=0),
        )
        self.page.show_dialog(dialog)

    async def _show_edit_message_dialog(self, message: Message):
        text_field = ft.TextField(
            label="Edit message",
            value=message.text or "",
            autofocus=True,
            multiline=True,
            min_lines=1,
            max_lines=5,
        )

        async def do_edit(e):
            new_text = text_field.value.strip()
            if new_text and new_text != (message.text or ""):
                result = await self.api.edit_message(message.message_id, new_text)
                self.page.pop_dialog()
                if result.success:
                    await self._reload_current_messages()
                else:
                    self._show_error(result.error_message or "Failed to edit message")
            else:
                self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("Edit Message"),
            content=text_field,
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("Save", on_click=do_edit),
            ],
        )
        self.page.show_dialog(dialog)

    async def _show_delete_message_dialog(self, message: Message):
        preview = (message.text or "")[:50]
        if len(message.text or "") > 50:
            preview += "..."

        async def do_delete(e):
            result = await self.api.delete_message(message.message_id)
            self.page.pop_dialog()
            if result.success:
                await self._reload_current_messages()
            else:
                self._show_error(result.error_message or "Failed to delete message")

        dialog = ft.AlertDialog(
            title=ft.Text("Delete Message"),
            content=ft.Text(f'Delete "{preview}"?'),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("Delete", on_click=do_delete, color=ft.Colors.ERROR),
            ],
        )
        self.page.show_dialog(dialog)

    # --- Chat menu ---

    async def _on_chat_menu_action(self, action: str, chat: Chat):
        if action == "rename":
            name_field = ft.TextField(label="New name", value=chat.chat_name, autofocus=True)

            async def do_rename(e):
                new_name = name_field.value.strip()
                if new_name:
                    result = await self.api.rename_chat(chat.chat_id, new_name)
                    self.page.pop_dialog()
                    if result.success:
                        await self._load_chats()
                        chat.chat_name = new_name
                        self._chat_view._header_title.value = new_name
                    else:
                        self._show_error(result.error_message or "Failed to rename chat")
                    self.page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("Rename Chat"),
                content=name_field,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.ElevatedButton("Rename", on_click=do_rename),
                ],
            )
            self.page.show_dialog(dialog)

        elif action == "add_member":
            user_field = ft.TextField(label="Username", autofocus=True)

            async def do_add(e):
                username = user_field.value.strip()
                if username:
                    result = await self.api.add_member(chat.chat_id, username)
                    self.page.pop_dialog()
                    if result.success:
                        await self._load_chats()
                    else:
                        self._show_error(result.error_message or "Failed to add member")
                    self.page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("Add Member"),
                content=user_field,
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.ElevatedButton("Add", on_click=do_add),
                ],
            )
            self.page.show_dialog(dialog)

        elif action == "leave":
            async def do_leave(e):
                result = await self.api.leave_chat(chat.chat_id)
                self.page.pop_dialog()
                if result.success:
                    self._current_chat = None
                    if self._chat_view:
                        self._chat_view.set_chat(None)
                    await self._load_chats()
                    self._render()
                else:
                    self._show_error(result.error_message or "Failed to leave chat")

            dialog = ft.AlertDialog(
                title=ft.Text("Leave Chat"),
                content=ft.Text(f"Leave \"{chat.chat_name}\"?"),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.ElevatedButton("Leave", on_click=do_leave),
                ],
            )
            self.page.show_dialog(dialog)

        elif action == "delete":
            async def do_delete(e):
                result = await self.api.delete_chat(chat.chat_id)
                self.page.pop_dialog()
                if result.success:
                    self._current_chat = None
                    if self._chat_view:
                        self._chat_view.set_chat(None)
                    await self._load_chats()
                    self._render()
                else:
                    self._show_error(result.error_message or "Failed to delete chat")

            dialog = ft.AlertDialog(
                title=ft.Text("Delete Chat"),
                content=ft.Text(f"Delete \"{chat.chat_name}\"? This cannot be undone."),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: self.page.pop_dialog()),
                    ft.ElevatedButton("Delete", on_click=do_delete, color=ft.Colors.ERROR),
                ],
            )
            self.page.show_dialog(dialog)

    # --- Settings ---

    async def _on_theme_toggle(self, is_dark: bool):
        self.page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        self.page.update()
        await self.storage.set_theme_mode("dark" if is_dark else "light")

    async def _on_display_name_save(self, name: str):
        result = await self.api.update_profile(name)
        if result.success:
            self._current_display_name = name
            await self.storage.save_user_info(self._current_username, name, self._current_user_id)
        else:
            self._show_error(result.error_message or "Failed to update profile")

    async def _on_revoke_token(self, token_str: str):
        result = await self.api.logout_token(target_token=token_str)
        if result.success and self._settings_view:
            tokens_result = await self.api.get_my_tokens()
            if tokens_result.success and isinstance(tokens_result.data, list):
                self._settings_view.set_sessions(tokens_result.data)
                self.page.update()
        elif not result.success:
            self._show_error(result.error_message or "Failed to revoke session")

    async def _on_logout(self):
        self._stop_connection()
        await self.api.logout_token()
        await self.storage.clear_all()
        self.api.clear_token()
        await self.api.disconnect()
        self._current_chat = None
        self._current_user_id = 0
        self._current_username = ""
        self._current_display_name = ""
        await self._show_auth_screen()
