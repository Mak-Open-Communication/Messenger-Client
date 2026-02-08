import hashlib
import logging
from typing import Optional

import flet as ft

from src.htcp.aio_client import AsyncClient
from src.common.models import Result

logger = logging.getLogger("ghosty.api")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def detect_agent(page: ft.Page) -> str:
    if page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS):
        return "ghosty-mobile"
    return "ghosty-desktop"


class ApiService:
    def __init__(self):
        self._client: Optional[AsyncClient] = None
        self._token: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.connected

    async def connect(self, host: str, port: int):
        if self._client and self._client.connected:
            await self._client.disconnect()
        self._client = AsyncClient(server_host=host, server_port=port)
        await self._client.connect()

    async def disconnect(self):
        if self._client and self._client.connected:
            await self._client.disconnect()
        self._client = None

    def set_token(self, token: str):
        self._token = token

    def clear_token(self):
        self._token = None

    async def _call(self, transaction: str, **kwargs) -> Result:
        if not self.connected:
            return Result(success=False, errors=[("connection", "Not connected to server")], data=None)
        try:
            raw = await self._client.call(transaction=transaction, **kwargs)
            return Result.from_raw(raw)
        except Exception as e:
            logger.error(f"API call '{transaction}' failed: {e}")
            return Result(success=False, errors=[("exception", str(e))], data=None)

    async def _auth_call(self, transaction: str, **kwargs) -> Result:
        if not self._token:
            return Result(success=False, errors=[("auth", "No token")], data=None)
        return await self._call(transaction, token=self._token, **kwargs)

    # --- Auth ---

    async def login(self, username: str, password: str, agent: str) -> Result:
        pwd_hash = hash_password(password)
        result = await self._call("login", username=username, password_hash=pwd_hash, agent=agent)
        if result.success and result.data:
            self._extract_token(result.data)
        return result

    async def register(self, username: str, visible_name: str, password: str, agent: str) -> Result:
        pwd_hash = hash_password(password)
        result = await self._call(
            "register", username=username, visible_name=visible_name,
            password_hash=pwd_hash, agent=agent,
        )
        if result.success and result.data:
            self._extract_token(result.data)
        return result

    def _extract_token(self, data):
        if isinstance(data, dict):
            token_data = data.get("token")
            if isinstance(token_data, dict):
                self._token = token_data.get("token", "")

    async def logout_token(self, target_token: str = None) -> Result:
        t = target_token or self._token
        return await self._auth_call("logout", target_token=t)

    async def verify_token(self) -> Result:
        return await self._auth_call("verify_token", target_token=self._token)

    # --- Users ---

    async def get_user(self, target_user_id: int) -> Result:
        return await self._auth_call("get_user", target_user_id=target_user_id)

    async def search_users(self, query: str, limit: int = 20) -> Result:
        return await self._auth_call("search_users", query=query, limit=limit)

    async def update_profile(self, display_name: str) -> Result:
        return await self._auth_call("update_profile", display_name=display_name)

    async def get_my_tokens(self) -> Result:
        return await self._auth_call("get_my_tokens", current_token=self._token)

    # --- Chats ---

    async def get_my_chats(self) -> Result:
        return await self._auth_call("get_my_chats")

    async def create_chat(self, chat_name: str, members: list[str]) -> Result:
        return await self._auth_call("create_chat", chat_name=chat_name, members=members)

    async def get_chat_info(self, chat_id: int) -> Result:
        return await self._auth_call("get_chat_info", chat_id=chat_id)

    async def rename_chat(self, chat_id: int, new_name: str) -> Result:
        return await self._auth_call("rename_chat", chat_id=chat_id, new_name=new_name)

    async def add_member(self, chat_id: int, username: str) -> Result:
        return await self._auth_call("add_member", chat_id=chat_id, username=username)

    async def remove_member(self, chat_id: int, target_user_id: int) -> Result:
        return await self._auth_call("remove_member", chat_id=chat_id, target_user_id=target_user_id)

    async def leave_chat(self, chat_id: int) -> Result:
        return await self._auth_call("leave_chat", chat_id=chat_id)

    async def delete_chat(self, chat_id: int) -> Result:
        return await self._auth_call("delete_chat", chat_id=chat_id)

    # --- Messages ---

    async def get_messages(self, chat_id: int, limit: int = 50, before_id: int = None) -> Result:
        kwargs = {"chat_id": chat_id, "limit": limit}
        if before_id is not None:
            kwargs["before_id"] = before_id
        return await self._auth_call("get_messages", **kwargs)

    async def send_message(self, chat_id: int, text: str) -> Result:
        contents = [{"type": "text", "resource_name": "db", "content": text}]
        return await self._auth_call("send_message", chat_id=chat_id, contents=contents)

    async def delete_message(self, message_id: int) -> Result:
        return await self._auth_call("delete_message", message_id=message_id)

    async def edit_message(self, message_id: int, new_text: str) -> Result:
        new_contents = [{"type": "text", "resource_name": "db", "content": new_text}]
        return await self._auth_call("edit_message", message_id=message_id, new_contents=new_contents)
