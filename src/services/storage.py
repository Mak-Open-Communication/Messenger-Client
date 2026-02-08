from flet.controls.services.shared_preferences import SharedPreferences

KEY_TOKEN = "ghosty_auth_token"
KEY_SERVER_HOST = "ghosty_server_host"
KEY_SERVER_PORT = "ghosty_server_port"
KEY_THEME_MODE = "ghosty_theme_mode"
KEY_DISPLAY_NAME = "ghosty_display_name"
KEY_USERNAME = "ghosty_username"
KEY_USER_ID = "ghosty_user_id"

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 4207


class StorageService:
    def __init__(self):
        self._prefs = SharedPreferences()

    async def get_token(self) -> str | None:
        return await self._prefs.get(KEY_TOKEN)

    async def set_token(self, token: str):
        await self._prefs.set(KEY_TOKEN, token)

    async def clear_token(self):
        await self._prefs.remove(KEY_TOKEN)

    async def get_server_address(self) -> tuple[str, int]:
        host = await self._prefs.get(KEY_SERVER_HOST)
        port = await self._prefs.get(KEY_SERVER_PORT)
        return (
            host or DEFAULT_SERVER_HOST,
            int(port) if port else DEFAULT_SERVER_PORT,
        )

    async def set_server_address(self, host: str, port: int):
        await self._prefs.set(KEY_SERVER_HOST, host)
        await self._prefs.set(KEY_SERVER_PORT, str(port))

    async def get_theme_mode(self) -> str:
        mode = await self._prefs.get(KEY_THEME_MODE)
        return mode or "light"

    async def set_theme_mode(self, mode: str):
        await self._prefs.set(KEY_THEME_MODE, mode)

    async def save_user_info(self, username: str, display_name: str, user_id: int):
        await self._prefs.set(KEY_USERNAME, username)
        await self._prefs.set(KEY_DISPLAY_NAME, display_name)
        await self._prefs.set(KEY_USER_ID, str(user_id))

    async def get_user_info(self) -> dict:
        return {
            "username": await self._prefs.get(KEY_USERNAME),
            "display_name": await self._prefs.get(KEY_DISPLAY_NAME),
            "user_id": await self._prefs.get(KEY_USER_ID),
        }

    async def clear_all(self):
        await self._prefs.clear()
