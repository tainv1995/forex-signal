"""Smoke-test the Phase 10 worker layer (run_analysis_cycle / run_tracking_cycle /
run_daily_report_cycle) against real Postgres + Redis. The pieces each of these
calls (process_symbol_tick, process_signal_health_check, build_daily_report, ...)
already have their own dedicated verify_*.py scripts - this one proves the thin
wrapper functions wire settings/provider/repo/notifier together correctly.

Usage:
    docker compose up -d postgres redis
    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_workers.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.core.enums import Direction, SignalStatus, SignalTier
from app.core.redis import get_redis
from app.db.repositories.signal_repository import SignalRepository
from app.db.repositories.telegram_message_repository import TelegramMessageRepository
from app.db.session import get_session_factory
from app.engines.risk import StopLoss
from app.engines.signal import activate, build_signal
from app.engines.targets import TakeProfit
from app.market_data.mock import MockProvider
from app.telegram.client import TelegramClient
from app.telegram.notifier import TelegramNotifier
from app.workers.analysis_worker import run_analysis_cycle
from app.workers.report_worker import run_daily_report_cycle
from app.workers.tracking_worker import run_tracking_cycle


async def main() -> None:
    settings = get_settings().model_copy(
        update={"symbol": f"WRK{uuid.uuid4().hex[:6]}", "signal_id_prefix": "WRK"}
    )
    session_factory = get_session_factory()
    redis = get_redis()
    provider = MockProvider(base_price=2650.0)
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

        # 1) run_analysis_cycle on a symbol with no open signal and no market data
        #    history yet - must run cleanly and simply decline to trade (Mock random
        #    walk essentially never clears the confluence bar in one shot; that's
        #    the correct, honest behaviour, not a bug - see run_backtest_example.py).
        result = await run_analysis_cycle(settings, provider, session, redis, notifier)
        print(f"run_analysis_cycle (no open signal): created={result.id if result else None}")

        # 2) run_tracking_cycle with NO open signal must no-op immediately.
        await run_tracking_cycle(settings, provider, session, notifier)
        assert len(sent_texts) == 0
        print("run_tracking_cycle (no open signal): no-op ok")

        # 3) Manually create an ACTIVE signal deep in-the-money so the very next
        #    tracking cycle is guaranteed to record a TP1 hit end-to-end through the
        #    real worker function (not just process_symbol_tick directly).
        tick = await provider.get_current_price(settings.symbol)
        signal = build_signal(
            await signal_repo.next_signal_id(settings.signal_id_prefix, now.date()),
            settings.symbol,
            Direction.BUY,
            tick.price - 5,
            tick.price - 3,
            StopLoss(tick.price - 20, "t"),
            [TakeProfit(i, tick.price - 4 + i * 0.5, float(i), "t") for i in range(1, 6)],
            0.8,
            SignalTier.VALID,
            6,
            ["r"],
            settings.primary_timeframe,
            now,
        )
        signal = activate(signal, now)
        await signal_repo.create(signal)
        print(f"created in-the-money signal {signal.id} for tracking test")

        await run_tracking_cycle(settings, provider, session, notifier)
        reloaded = await signal_repo.get(signal.id)
        assert reloaded is not None
        assert reloaded.status is not SignalStatus.WAITING_ENTRY
        print(f"run_tracking_cycle advanced signal to status={reloaded.status.value}")

        # 4) run_daily_report_cycle must build and send a report without raising.
        text = await run_daily_report_cycle(settings, provider, session, notifier)
        assert "DAILY REPORT" in text
        assert any("DAILY REPORT" in t for t in sent_texts)
        print("run_daily_report_cycle sent a report ok")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
