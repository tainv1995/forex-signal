"""End-to-end verification of the Phase 7 tracking pipeline against real Postgres:
create a signal, feed it a sequence of price ticks (including one big jump that
should clear three TP levels at once, per Section 25), and confirm the persisted
state and notification count are exactly right - including that duplicate ticks
never re-fire a notification.

Telegram itself is mocked here (no real send) purely to avoid spamming the chat
with dozens of test messages; the notifier/idempotency code path it exercises is
identical to a real send - see scripts/send_test_telegram_message.py for that.

Usage:
    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_signal_tracking.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.enums import Direction, SignalStatus, SignalTier
from app.db.repositories.signal_repository import SignalRepository
from app.db.repositories.telegram_message_repository import TelegramMessageRepository
from app.db.session import get_session_factory
from app.engines.risk import StopLoss
from app.engines.signal import build_signal
from app.engines.targets import TakeProfit
from app.telegram.client import TelegramClient
from app.telegram.notifier import TelegramNotifier
from app.tracking.event_processor import process_symbol_tick


async def main() -> None:
    session_factory = get_session_factory()
    symbol = f"TRK{uuid.uuid4().hex[:6]}"  # signals.symbol is VARCHAR(20)
    now = datetime.now(UTC)
    sent_texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_texts.append(request.content.decode())
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent_texts)}})

    client = TelegramClient("fake-token", transport=httpx.MockTransport(handler))

    async with session_factory() as session:
        signal_repo = SignalRepository(session)
        message_repo = TelegramMessageRepository(session)
        notifier = TelegramNotifier(client, message_repo, "123", "GOLD", show_metadata=True)

        signal_id = await signal_repo.next_signal_id("TRACK", date.today())  # noqa: DTZ011
        tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
        signal = build_signal(
            signal_id,
            symbol,
            Direction.BUY,
            4391.0,
            4393.0,
            StopLoss(4384.0, "t"),
            tps,
            0.86,
            SignalTier.STRONG,
            8,
            ["test"],
            "M15",
            now,
        )
        await signal_repo.create(signal)
        print(f"created {signal.id} status={signal.status.value}")

        # Tick 1: price enters the entry zone -> ACTIVE.
        await process_symbol_tick(
            symbol, 4392.0, now, atr_value=2.0, signal_repo=signal_repo, notifier=notifier
        )
        reloaded = await signal_repo.get(signal.id)
        assert reloaded is not None and reloaded.status is SignalStatus.ACTIVE
        assert len(sent_texts) == 1 and "ACTIVATED" in sent_texts[0]
        print(f"tick 1 ok: status={reloaded.status.value}, {len(sent_texts)} message(s) sent")

        # Tick 2: identical price again - must NOT re-fire the activation message.
        await process_symbol_tick(
            symbol, 4392.0, now, atr_value=2.0, signal_repo=signal_repo, notifier=notifier
        )
        assert len(sent_texts) == 1
        print(f"tick 2 ok (duplicate, idempotent): {len(sent_texts)} message(s) sent")

        # Tick 3: a single jump clears TP1, TP2 and TP3 at once (Section 25).
        await process_symbol_tick(
            symbol, 4400.0, now, atr_value=2.0, signal_repo=signal_repo, notifier=notifier
        )
        reloaded = await signal_repo.get(signal.id)
        assert reloaded is not None and reloaded.status is SignalStatus.TP3_HIT
        assert [t.hit for t in reloaded.targets] == [True, True, True, False, False]
        assert len(sent_texts) == 4  # activation + TP1 + TP2 + TP3
        print(f"tick 3 ok: status={reloaded.status.value}, {len(sent_texts)} message(s) sent")

        # Tick 4: same price again - must not re-fire any of the TP messages.
        await process_symbol_tick(
            symbol, 4400.0, now, atr_value=2.0, signal_repo=signal_repo, notifier=notifier
        )
        assert len(sent_texts) == 4
        print(f"tick 4 ok (duplicate, idempotent): {len(sent_texts)} message(s) sent")

        # Tick 5: price runs to TP5 -> terminal, FULL TP message instead of "TP5 HIT".
        await process_symbol_tick(
            symbol, 4410.0, now, atr_value=2.0, signal_repo=signal_repo, notifier=notifier
        )
        reloaded = await signal_repo.get(signal.id)
        assert reloaded is not None and reloaded.status is SignalStatus.TP5_HIT
        assert reloaded.is_terminal
        assert len(sent_texts) == 6  # + TP4 + FULL TP
        assert "FULL TP" in sent_texts[-1]
        print(f"tick 5 ok: status={reloaded.status.value}, {len(sent_texts)} message(s) sent")

        # Cleanup this run's rows so repeated runs stay clean.
        open_signals = await signal_repo.get_open_signals(symbol)
        assert open_signals == []  # terminal signal is no longer "open"

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
