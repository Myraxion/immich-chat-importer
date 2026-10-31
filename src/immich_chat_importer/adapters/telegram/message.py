from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from .client import TelegramClient


class TelegramData(SimpleNamespace):
    """Attribute view over only the received JSON; no global Bot API model graph."""

    def __getattr__(self, name: str) -> Any:
        return None

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)


def _decode(value: Any, key: str = "") -> Any:
    if key in ("date", "forward_date") and isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, dict):
        return TelegramData(
            **{("from_user" if k == "from" else k): _decode(v, k) for k, v in value.items()}
        )
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


class Message(TelegramData):
    @classmethod
    def from_payload(cls, data: dict[str, Any], bot: TelegramClient | None = None) -> "Message":
        return cls(**vars(_decode(data)), _bot=bot)

    async def reply(self, text: str) -> None:
        if self._bot is None:
            raise RuntimeError("Message is not bound to a Telegram client")
        await self._bot.send_message(self.chat.id, text, self.message_id)
