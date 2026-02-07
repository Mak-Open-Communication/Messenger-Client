import flet as ft


class Application:
    def __init__(self, page: ft.Page):
        self.page = page

        self.tasks_column = ft.Column(spacing=8)

    async def start(self):
        self.page.title = "GHosty"
        self.page.theme_mode = ft.ThemeMode.LIGHT

        self.page.padding = 30

        if self.page.web or self.page.platform in (
            ft.PagePlatform.LINUX,
            ft.PagePlatform.WINDOWS,
            ft.PagePlatform.MACOS,
        ):
            self.page.window.width = 450
            self.page.window.height = 600

        self.theme_btn = ft.IconButton(
            icon=ft.Icons.DARK_MODE,
            tooltip="Сменить тему",
            on_click=self._toggle_theme,
        )

        header = ft.Row(
            [
                ft.Text("To-Do", size=28, weight=ft.FontWeight.BOLD),
                self.theme_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.new_task_field = ft.TextField(
            hint_text="Новая задача...",
            expand=True,
            on_submit=self._add_task,
        )

        input_row = ft.Row(
            [
                self.new_task_field,
                ft.IconButton(
                    icon=ft.Icons.ADD_CIRCLE,
                    icon_size=32,
                    tooltip="Добавить",
                    on_click=self._add_task,
                ),
            ],
        )

        self.page.add(header, input_row, ft.Divider(), self.tasks_column)

    async def _add_task(self, e):
        text = self.new_task_field.value.strip()
        if not text:
            return

        task_row = self._build_task_row(text)

        self.tasks_column.controls.append(task_row)
        self.new_task_field.value = ""

        await self.new_task_field.focus()

        self.page.update()

    def _build_task_row(self, text: str) -> ft.Row:
        cb = ft.Checkbox(label=text, on_change=lambda e: self.page.update())
        row = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=18,
            tooltip="Удалить",
            on_click=lambda e, r=row: self._delete_task_row(r),
        )
        row.controls = [cb, delete_btn]

        return row

    def _delete_task_row(self, row: ft.Row):
        self.tasks_column.controls.remove(row)

        self.page.update()

    def _toggle_theme(self, e):
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.page.theme_mode = ft.ThemeMode.DARK
            self.theme_btn.icon = ft.Icons.LIGHT_MODE

        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.theme_btn.icon = ft.Icons.DARK_MODE

        self.page.update()
