import flet as ft


async def main(page: ft.Page):
    page.title = "Messenger"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 30
    if page.web or page.platform in (ft.PagePlatform.LINUX, ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS):
        page.window.width = 450
        page.window.height = 600

    # --- state ---
    tasks_column = ft.Column(spacing=8)

    async def add_task(e):
        text = new_task_field.value.strip()
        if not text:
            return
        task_row = _build_task_row(text)
        tasks_column.controls.append(task_row)
        new_task_field.value = ""
        await new_task_field.focus()
        page.update()

    def _build_task_row(text: str) -> ft.Row:
        cb = ft.Checkbox(label=text, on_change=lambda e: page.update())
        row = ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_size=18,
            tooltip="Удалить",
            on_click=lambda e, r=row: _delete_task_row(r),
        )
        row.controls = [cb, delete_btn]
        return row

    def _delete_task_row(row: ft.Row):
        tasks_column.controls.remove(row)
        page.update()

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
            theme_btn.icon = ft.Icons.LIGHT_MODE
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_btn.icon = ft.Icons.DARK_MODE
        page.update()

    # --- UI ---
    theme_btn = ft.IconButton(
        icon=ft.Icons.DARK_MODE,
        tooltip="Сменить тему",
        on_click=toggle_theme,
    )

    header = ft.Row(
        [
            ft.Text("To-Do", size=28, weight=ft.FontWeight.BOLD),
            theme_btn,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    new_task_field = ft.TextField(
        hint_text="Новая задача...",
        expand=True,
        on_submit=add_task,
    )

    input_row = ft.Row(
        [
            new_task_field,
            ft.IconButton(
                icon=ft.Icons.ADD_CIRCLE,
                icon_size=32,
                tooltip="Добавить",
                on_click=add_task,
            ),
        ],
    )

    page.add(header, input_row, ft.Divider(), tasks_column)


ft.run(main)
