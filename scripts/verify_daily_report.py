"""End-to-end verification of Phase 9's daily report against real Postgres: create a
few closed signals "today", record a couple of health heartbeats, build the report
via build_daily_report() (real DB query + real bias from MockProvider), and send it
through the real notifier (Telegram mocked, same reasoning as
verify_signal_tracking.py) - including the idempotency check (same day never sent
twice).

Usage:
    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_daily_report.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.core.enums import Direction, SignalTier
from app.db.repositories.signal_repository import SignalRepository
from app.db.repositories.system_health_repository import SystemHealthRepository
from app.db.repositories.telegram_message_repository import TelegramMessageRepository
from app.db.session import get_session_factory
from app.engines.risk import StopLoss
from app.engines.signal import activate, build_signal, hit_target, stop_out
from app.engines.targets import TakeProfit
from app.market_data.mock import MockProvider
from app.reports.daily import build_daily_report, format_daily_report
from app.telegram.client import TelegramClient
from app.telegram.notifier import TelegramNotifier


async def main() -> None:
    settings = get_settings()
    session_factory = get_session_factory()
    tz = ZoneInfo(settings.report_timezone)
    report_date = datetime.now(tz).date()
    now = datetime.now(UTC)
    symbol = f"RPT{uuid.uuid4().hex[:6]}"
    sent_texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_texts.append(request.content.decode())
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent_texts)}})

    client = TelegramClient("fake-token", transport=httpx.MockTransport(handler))
    provider = MockProvider(base_price=settings.mock_base_price)

    async with session_factory() as session:
        signal_repo = SignalRepository(session)
        notifier = TelegramNotifier(
            client, TelegramMessageRepository(session), "123", "GOLD", show_metadata=True
        )

        def tps(direction: Direction) -> list[TakeProfit]:
            sign = 1 if direction is Direction.BUY else -1
            return [TakeProfit(i, 4391.0 + sign * i * 2, float(i), "t") for i in range(1, 6)]

        win = activate(
            build_signal(
                await signal_repo.next_signal_id("RPT", report_date),
                symbol,
                Direction.BUY,
                4389.0,
                4391.0,
                StopLoss(4384.0, "t"),
                tps(Direction.BUY),
                0.9,
                SignalTier.STRONG,
                9,
                ["r"],
                "M15",
                now,
            ),
            now,
        )
        for level in range(1, 6):
            win = hit_target(win, level, now)
        loss = stop_out(
            activate(
                build_signal(
                    await signal_repo.next_signal_id("RPT", report_date),
                    symbol,
                    Direction.SELL,
                    4391.0,
                    4393.0,
                    StopLoss(4398.0, "t"),
                    tps(Direction.SELL),
                    0.8,
                    SignalTier.VALID,
                    7,
                    ["r"],
                    "M15",
                    now,
                ),
                now,
            ),
            now,
        )
        await signal_repo.create(win)
        await signal_repo.create(loss)
        print(f"created 2 closed signals for symbol={symbol}")

        health_repo = SystemHealthRepository(session)
        await health_repo.record("healthy", now)
        await health_repo.record("healthy", now)
        print("recorded 2 healthy heartbeats")

        # Scope this run's report to just our test signals without mutating the
        # shared (lru_cache'd) Settings singleton.
        scoped_settings = settings.model_copy(update={"symbol": symbol})
        data = await build_daily_report(
            scoped_settings, provider, signal_repo, health_repo, report_date
        )
        assert data.stats.total_signals == 2
        assert data.stats.win_count == 1
        assert data.stats.sl_count == 1
        assert data.uptime_percentage == 1.0
        print(
            f"report built ok: total={data.stats.total_signals}, uptime={data.uptime_percentage:.0%}"
        )

        text = format_daily_report(data)
        print("\n--- report text ---")
        print(text)
        print("--- end report text ---\n")

        message_id = await notifier.notify_daily_report(report_date, text)
        assert message_id is not None
        assert len(sent_texts) == 1
        print(f"sent ok, message_id={message_id}")

        # Same-day report must not be re-sent (idempotency).
        again = await notifier.notify_daily_report(report_date, text)
        assert again is None
        assert len(sent_texts) == 1
        print("duplicate same-day send correctly skipped (idempotent)")

        await signal_repo.get(win.id)  # sanity: round-trips fine

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
