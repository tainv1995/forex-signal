import asyncio
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class TelegramError(Exception):
    """Raised when the Telegram Bot API cannot be reached or rejects a request."""


class TelegramClient:
    """Thin wrapper around the Telegram Bot API with retry/backoff and rate-limit
    handling (Section 47) - callers never see a raw httpx exception."""

    def __init__(
        self,
        bot_token: str,
        max_retries: int = 3,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not bot_token:
            raise TelegramError("TELEGRAM_BOT_TOKEN must be set to use the Telegram client")
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token}",
            timeout=timeout,
            transport=transport,
        )

    async def send_message(self, chat_id: str, text: str) -> int:
        """Returns the Telegram message_id on success."""
        data = await self._call("sendMessage", {"chat_id": chat_id, "text": text})
        return int(data["message_id"])

    async def get_updates(
        self, offset: int | None = None, timeout: int = 30
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = await self._client.get("/getUpdates", params=params, timeout=timeout + 10)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise TelegramError(f"getUpdates failed: {payload}")
        result: list[dict[str, Any]] = payload["result"]
        return result

    async def _call(self, method: str, json_body: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await self._client.post(f"/{method}", json=json_body)
            except httpx.TransportError as exc:
                last_error = exc
                await asyncio.sleep(_backoff_seconds(attempt))
                continue

            if response.status_code == 429:
                retry_after = response.json().get("parameters", {}).get("retry_after")
                await asyncio.sleep(
                    retry_after if retry_after is not None else _backoff_seconds(attempt)
                )
                continue

            if response.status_code >= 500:
                last_error = TelegramError(f"{method} returned {response.status_code}")
                await asyncio.sleep(_backoff_seconds(attempt))
                continue

            payload = response.json()
            if response.status_code >= 400 or not payload.get("ok"):
                raise TelegramError(f"{method} failed: {payload}")
            result: dict[str, Any] = payload["result"]
            return result

        raise TelegramError(f"{method} failed after {self._max_retries} attempts") from last_error

    async def aclose(self) -> None:
        await self._client.aclose()


def _backoff_seconds(attempt: int) -> float:
    return min(0.5 * (2.0**attempt), 8.0)
