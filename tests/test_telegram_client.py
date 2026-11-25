import httpx
import pytest

from app.telegram.client import TelegramClient, TelegramError


def test_empty_token_raises_immediately() -> None:
    with pytest.raises(TelegramError):
        TelegramClient(bot_token="")


@pytest.mark.asyncio
async def test_send_message_returns_message_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bottest-token/sendMessage"
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    client = TelegramClient("test-token", transport=httpx.MockTransport(handler))
    message_id = await client.send_message("123", "hello")

    assert message_id == 42


@pytest.mark.asyncio
async def test_send_message_retries_on_server_error_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500, json={"ok": False})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    client = TelegramClient("test-token", max_retries=5, transport=httpx.MockTransport(handler))
    message_id = await client.send_message("123", "hello")

    assert message_id == 7
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_send_message_respects_retry_after_on_429() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 0}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    client = TelegramClient("test-token", transport=httpx.MockTransport(handler))
    message_id = await client.send_message("123", "hello")

    assert message_id == 9
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_send_message_raises_after_exhausting_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False})

    client = TelegramClient("test-token", max_retries=2, transport=httpx.MockTransport(handler))

    with pytest.raises(TelegramError):
        await client.send_message("123", "hello")


@pytest.mark.asyncio
async def test_send_message_raises_immediately_on_bad_request() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    client = TelegramClient("test-token", max_retries=5, transport=httpx.MockTransport(handler))

    with pytest.raises(TelegramError, match="chat not found"):
        await client.send_message("123", "hello")
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_get_updates_returns_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/bottest-token/getUpdates"
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

    client = TelegramClient("test-token", transport=httpx.MockTransport(handler))
    updates = await client.get_updates(offset=5)

    assert updates == [{"update_id": 1}]
