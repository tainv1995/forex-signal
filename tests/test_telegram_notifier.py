from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, hit_target
from app.engines.targets import TakeProfit
from app.telegram.client import TelegramClient, TelegramError
from app.telegram.notifier import TelegramNotifier

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


class FakeMessageRepo:
    def __init__(self) -> None:
        self.reserved: dict[str, int] = {}
        self.sent: dict[int, int] = {}
        self.failed: dict[int, str] = {}
        self._next_id = 1

    async def try_reserve(
        self, idempotency_key: str, signal_id: str | None, event: str, chat_id: str, text: str
    ) -> int | None:
        if idempotency_key in self.reserved:
            return None
        row_id = self._next_id
        self._next_id += 1
        self.reserved[idempotency_key] = row_id
        return row_id

    async def mark_sent(self, row_id: int, telegram_message_id: int) -> None:
        self.sent[row_id] = telegram_message_id

    async def mark_failed(self, row_id: int, error: str) -> None:
        self.failed[row_id] = error


def _signal() -> Signal:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        "GOLD-20260817-001",
        "XAUUSD",
        Direction.BUY,
        4391.0,
        4393.0,
        StopLoss(4384.0, "t"),
        tps,
        0.86,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )


def _notifier(
    handler: Callable[[httpx.Request], httpx.Response], repo: FakeMessageRepo | None = None
) -> tuple[TelegramNotifier, FakeMessageRepo]:
    repo = repo or FakeMessageRepo()
    client = TelegramClient("test-token", transport=httpx.MockTransport(handler))
    notifier = TelegramNotifier(
        client, repo, chat_id="123", symbol_label="GOLD", show_metadata=True
    )
    return notifier, repo


@pytest.mark.asyncio
async def test_notify_new_signal_sends_and_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 100}})

    notifier, repo = _notifier(handler)

    message_id = await notifier.notify_new_signal(_signal())

    assert message_id == 100
    assert repo.sent == {1: 100}


@pytest.mark.asyncio
async def test_duplicate_notification_is_skipped_without_calling_telegram_again() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 100}})

    notifier, _repo = _notifier(handler)
    signal = _signal()

    first = await notifier.notify_new_signal(signal)
    second = await notifier.notify_new_signal(signal)

    assert first == 100
    assert second is None
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_tp5_hit_sends_full_tp_message_not_a_plain_tp_hit() -> None:
    sent_text = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent_text["text"] = request.content
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    notifier, repo = _notifier(handler)
    signal = activate(_signal(), NOW)
    for level in range(1, 6):
        signal = hit_target(signal, level, NOW)

    await notifier.notify_tp_hit(signal, level=5)

    assert "GOLD-20260817-001:TP5_HIT" in repo.reserved
    assert b"FULL TP" in sent_text["text"]


@pytest.mark.asyncio
async def test_failed_send_marks_repository_and_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "blocked"})

    notifier, repo = _notifier(handler)

    with pytest.raises(TelegramError):
        await notifier.notify_stop_loss(_signal())

    assert repo.failed == {1: "sendMessage failed: {'ok': False, 'description': 'blocked'}"}
    assert repo.sent == {}


@pytest.mark.asyncio
async def test_notify_cancelled_includes_reason_lines() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    notifier, _ = _notifier(handler)

    await notifier.notify_cancelled(_signal(), ["Market Structure Invalidated"])

    assert b"Market Structure Invalidated" in captured["body"]
    assert b"CANCELLED" in captured["body"]
