from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    account_id: int
    username: str
    display_name: str
    last_online_at: Optional[str] = None
    in_online: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Account":
        return cls(
            account_id=d.get("account_id", 0),
            username=d.get("username", ""),
            display_name=d.get("display_name", ""),
            last_online_at=d.get("last_online_at"),
            in_online=d.get("in_online", False),
            created_at=d.get("created_at"),
        )


@dataclass
class AuthToken:
    token_id: int
    user_id: int
    token: str
    agent: Optional[str] = None
    is_current: bool = False
    is_online: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "AuthToken":
        return cls(
            token_id=d.get("token_id", 0),
            user_id=d.get("user_id", 0),
            token=d.get("token", ""),
            agent=d.get("agent"),
            is_current=d.get("is_current", False),
            is_online=d.get("is_online", False),
            created_at=d.get("created_at"),
        )


@dataclass
class Chat:
    chat_id: int
    chat_name: str
    owner: Optional[Account] = None
    members: list = field(default_factory=list)
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Chat":
        owner = Account.from_dict(d["owner"]) if d.get("owner") else None
        members = [Account.from_dict(m) for m in d.get("members", [])]
        return cls(
            chat_id=d.get("chat_id", 0),
            chat_name=d.get("chat_name", ""),
            owner=owner,
            members=members,
            created_at=d.get("created_at"),
        )


@dataclass
class MessageTag:
    tag_id: int
    message_id: int
    for_user: Optional[Account] = None
    type: str = ""
    tag: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "MessageTag":
        for_user = Account.from_dict(d["for_user"]) if d.get("for_user") else None
        return cls(
            tag_id=d.get("tag_id", 0),
            message_id=d.get("message_id", 0),
            for_user=for_user,
            type=d.get("type", ""),
            tag=d.get("tag", ""),
        )


@dataclass
class Message:
    message_id: int
    chat_id: int
    sender_user: Optional[Account] = None
    is_read: bool = False
    tags: list = field(default_factory=list)
    contents: list = field(default_factory=list)
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        sender = Account.from_dict(d["sender_user"]) if d.get("sender_user") else None
        tags = [MessageTag.from_dict(t) for t in d.get("tags", []) if isinstance(t, dict)]
        return cls(
            message_id=d.get("message_id", 0),
            chat_id=d.get("chat_id", 0),
            sender_user=sender,
            is_read=d.get("is_read", False),
            tags=tags,
            contents=d.get("contents", []),
            created_at=d.get("created_at"),
        )

    @property
    def text(self) -> str:
        parts = []
        for chunk in self.contents:
            if isinstance(chunk, dict):
                if "text" in chunk:
                    parts.append(chunk["text"])
                elif chunk.get("type") == "text":
                    parts.append(chunk.get("content", ""))
            elif isinstance(chunk, str):
                parts.append(chunk)
        return "".join(parts)


@dataclass
class Result:
    success: bool
    errors: list
    data: object = None

    @classmethod
    def from_raw(cls, raw) -> "Result":
        if isinstance(raw, dict) and "success" in raw:
            return cls(
                success=raw.get("success", False),
                errors=raw.get("errors", []),
                data=raw.get("data"),
            )
        return cls(success=True, errors=[], data=raw)

    @property
    def error_message(self) -> str:
        if not self.errors:
            return ""
        first = self.errors[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            return str(first[1])
        return str(first)
