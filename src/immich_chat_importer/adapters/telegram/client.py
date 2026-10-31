import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .errors import TelegramError


class TelegramClient:
    """The small Bot API surface used by this adapter, including local-server paths."""

    def __init__(
        self, token: str, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.token = token
        self.username = ""
        self._http = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/bot{token}/",
            timeout=httpx.Timeout(60, connect=30),
            transport=transport,
        )

    async def __aenter__(self) -> "TelegramClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call(self, method: str, **data: Any) -> Any:
        try:
            response = await self._http.post(method, json=data)
        except httpx.RequestError:
            # Request URLs contain the bot token; never include them in exceptions/logs.
            raise TelegramError(0, "Telegram network request failed") from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(response.status_code, "Invalid Telegram response") from None
        if not response.is_success or not body.get("ok"):
            raise TelegramError(
                body.get("error_code", response.status_code),
                body.get("description", "Telegram request failed"),
                (body.get("parameters") or {}).get("retry_after"),
            )
        return body["result"]

    async def get_file(self, file_id: str) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(
            file_path=(await self.call("getFile", file_id=file_id)).get("file_path")
        )

    async def send_message(self, chat_id: int, text: str, message_id: int) -> None:
        await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_parameters={"message_id": message_id},
        )

    async def updates(self) -> AsyncIterator[dict[str, Any]]:
        user = await self.call("getMe")
        self.username = user.get("username", "")
        offset = 0
        failures = 0
        while True:
            try:
                updates = await self.call(
                    "getUpdates", offset=offset, timeout=30, allowed_updates=["message"]
                )
                failures = 0
            except TelegramError as exc:
                if exc.code not in (0, 429) and exc.code < 500:
                    raise
                failures += 1
                await asyncio.sleep(exc.retry_after or min(2 ** min(failures, 3), 5))
                continue
            for update in updates:
                offset = update["update_id"] + 1
                yield update
