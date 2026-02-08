import flet as ft

from src.common.models import Message


class MessageBubble(ft.Container):
    def __init__(self, message: Message, is_mine: bool, on_context_menu=None):
        self._message = message
        self._on_context_menu = on_context_menu

        sender_name = message.sender_user.display_name if message.sender_user else "Unknown"
        text_content = message.text or "(empty)"

        time_str = ""
        if message.created_at:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(str(message.created_at))
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        bubble_color = ft.Colors.PRIMARY_CONTAINER if is_mine else ft.Colors.SURFACE_CONTAINER

        controls = []
        if not is_mine:
            controls.append(
                ft.Text(sender_name, size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)
            )
        controls.append(ft.Text(text_content, size=14))
        if time_str:
            controls.append(
                ft.Text(time_str, size=10, color=ft.Colors.ON_SURFACE_VARIANT)
            )

        content_col = ft.Column(controls=controls, spacing=2, tight=True)

        content = ft.GestureDetector(
            content=content_col,
            on_secondary_tap_down=self._on_right_click,
            on_long_press_start=self._on_long_press,
        ) if on_context_menu else content_col

        super().__init__(
            content=content,
            bgcolor=bubble_color,
            border_radius=ft.border_radius.all(12),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            margin=ft.margin.only(
                left=60 if is_mine else 8,
                right=8 if is_mine else 60,
                top=2, bottom=2,
            ),
        )

    async def _on_right_click(self, e):
        if self._on_context_menu:
            await self._on_context_menu(self._message)

    async def _on_long_press(self, e):
        if self._on_context_menu:
            await self._on_context_menu(self._message)


class MessageInput(ft.Container):
    def __init__(self, on_send):
        self._on_send_callback = on_send

        self.text_field = ft.TextField(
            hint_text="Message...",
            expand=True,
            multiline=False,
            min_lines=1,
            max_lines=3,
            on_submit=self._on_submit,
            border_radius=ft.border_radius.all(24),
        )
        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND,
            on_click=self._on_submit,
            tooltip="Send",
            icon_color=ft.Colors.PRIMARY,
        )

        super().__init__(
            content=ft.Row(
                controls=[self.text_field, self.send_btn],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
        )

    async def _on_submit(self, e):
        text = self.text_field.value.strip()
        if not text:
            return
        self.text_field.value = ""
        await self.text_field.focus()
        await self._on_send_callback(text)
