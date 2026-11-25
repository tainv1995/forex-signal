"""End-to-end verification of Phase 8 (invalidate/cancel/reversal) against real
Postgres: three signals, three outcomes - KEEP (healthy structure, no DB/Telegram
change), CLOSE (own confidence collapsed but no strong opposite - no Telegram notice,
by request 2026-09-03: signals are reference-only, a "cancelled" broadcast for a soft
decay reads as a directive rather than information), REVERSE (own confidence
collapsed AND the opposite side is strong and confident - DOES send a "cancelled"
notice, since the market has genuinely flipped and a new opposite signal follows).

Usage:
    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_signal_reversal.py
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
from app.engines.confluence import ConfluenceResult
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal
from app.engines.targets import TakeProfit
from app.telegram.client import TelegramClient
from app.telegram.notifier import TelegramNotifier
from app.tracking.event_processor import process_signal_health_check


def _confluence(direction: Direction, buy_score: float, sell_score: float) -> ConfluenceResult:
    confidence = buy_score if direction is Direction.BUY else sell_score
    tier = SignalTier.STRONG if direction is not Direction.NEUTRAL else SignalTier.NO_TRADE
    return ConfluenceResult(direction, tier, confidence, 8, 10, buy_score, sell_score)


async def main() -> None:
    session_factory = get_session_factory()
    now = datetime.now(UTC)
    sent_texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_texts.append(request.content.decode())
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent_texts)}})

    client = TelegramClient("fake-token", transport=httpx.MockTransport(handler))

    async with session_factory() as session:
        signal_repo = SignalRepository(session)
        notifier = TelegramNotifier(
            client, TelegramMessageRepository(session), "123", "GOLD", show_metadata=True
        )

        async def _new_active_signal(tag: str) -> Signal:
            symbol = f"RVS{uuid.uuid4().hex[:6]}"
            signal_id = await signal_repo.next_signal_id(f"RVS{tag}", date.today())  # noqa: DTZ011
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
                ["r"],
                "M15",
                now,
            )
            signal = activate(signal, now)
            await signal_repo.create(signal)
            return signal

        # Case 1: structure still healthy -> KEEP, no DB/Telegram change.
        signal_keep = await _new_active_signal("K")
        healthy = _confluence(Direction.BUY, buy_score=0.80, sell_score=0.20)
        decision = await process_signal_health_check(
            signal_keep, healthy, now, signal_repo, notifier
        )
        reloaded = await signal_repo.get(signal_keep.id)
        assert decision.action == "KEEP"
        assert reloaded is not None and reloaded.status is SignalStatus.ACTIVE
        assert len(sent_texts) == 0
        print(f"case 1 (KEEP) ok: status={reloaded.status.value}, messages sent={len(sent_texts)}")

        # Case 2: own confidence collapsed, no strong opposite -> CLOSE (INVALIDATED),
        # no Telegram notice.
        signal_close = await _new_active_signal("C")
        weak = _confluence(Direction.NEUTRAL, buy_score=0.40, sell_score=0.50)
        decision = await process_signal_health_check(signal_close, weak, now, signal_repo, notifier)
        reloaded = await signal_repo.get(signal_close.id)
        assert decision.action == "CLOSE"
        assert reloaded is not None and reloaded.status is SignalStatus.INVALIDATED
        assert len(sent_texts) == 0
        print(f"case 2 (CLOSE) ok: status={reloaded.status.value}, messages sent={len(sent_texts)}")

        # Duplicate health check on the now-terminal signal must be a no-op.
        decision = await process_signal_health_check(signal_close, weak, now, signal_repo, notifier)
        assert len(sent_texts) == 0
        print(f"case 2 duplicate check ok (idempotent): messages sent={len(sent_texts)}")

        # Case 3: own confidence collapsed AND opposite side is strong -> REVERSE,
        # DOES send a "cancelled" notice for the old signal.
        signal_reverse = await _new_active_signal("R")
        strong_opposite = _confluence(Direction.SELL, buy_score=0.42, sell_score=0.88)
        decision = await process_signal_health_check(
            signal_reverse, strong_opposite, now, signal_repo, notifier
        )
        reloaded = await signal_repo.get(signal_reverse.id)
        assert decision.action == "REVERSE"
        assert reloaded is not None and reloaded.status is SignalStatus.REVERSED
        assert len(sent_texts) == 1 and "CANCELLED" in sent_texts[0]
        print(
            f"case 3 (REVERSE) ok: status={reloaded.status.value}, messages sent={len(sent_texts)}"
        )

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
