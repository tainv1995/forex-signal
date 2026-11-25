"""One-off verification of SignalRepository against a real Postgres instance.

Not a pytest suite on purpose (same convention as the Phase 2 webhook/candle checks):
this needs a live DATABASE_URL, so it's run manually via:

    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_signal_repository.py
"""

import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.enums import Direction, SignalStatus, SignalTier
from app.db.repositories.signal_repository import SignalRepository
from app.db.session import get_session_factory
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, hit_target
from app.engines.targets import TakeProfit


async def main() -> None:
    session_factory = get_session_factory()
    today = date.today()  # noqa: DTZ011 - local calendar day is fine for a signal ID
    now = datetime.now(UTC)

    async with session_factory() as session:
        repo = SignalRepository(session)

        id_a = await repo.next_signal_id("VERIFY", today)
        id_b = await repo.next_signal_id("VERIFY", today)
        assert id_a != id_b, "sequence must not repeat"
        print(f"sequence ok: {id_a} -> {id_b}")

        take_profits = [
            TakeProfit(level=i, price=2650.0 + i * 2, rr=float(i), basis="test")
            for i in range(1, 6)
        ]
        signal = build_signal(
            signal_id=id_a,
            symbol="XAUUSD_VERIFY",
            direction=Direction.BUY,
            entry_low=2645.0,
            entry_high=2647.0,
            stop_loss=StopLoss(price=2640.0, basis="test"),
            take_profits=take_profits,
            confidence=0.8,
            confluence_tier=SignalTier.VALID,
            agreement=6,
            reasons=["[market_structure] test"],
            timeframe="M15",
            created_at=now,
        )
        await repo.create(signal)
        print(f"created {signal.id} status={signal.status.value}")

        open_signals = await repo.get_open_signals("XAUUSD_VERIFY")
        assert any(s.id == signal.id for s in open_signals)
        print(f"open signals for symbol: {[s.id for s in open_signals]}")

        activated = activate(signal, now)
        ok = await repo.apply_transition(SignalStatus.WAITING_ENTRY, activated)
        assert ok
        reloaded = await repo.get(signal.id)
        assert reloaded is not None
        assert reloaded.status is SignalStatus.ACTIVE
        print(f"activated ok, reloaded status={reloaded.status.value}")

    # Simulate two workers racing to record the same TP1 hit concurrently - each on
    # its own session/connection, the way two real worker processes would be. A
    # single AsyncSession isn't safe for concurrent use, so this must NOT reuse the
    # session above (Section 51: only one of these two updates may ever win).
    tp1_a = hit_target(reloaded, level=1, at=now)
    tp1_b = hit_target(reloaded, level=1, at=now)

    async def _apply(signal_variant: Signal) -> bool:
        async with session_factory() as worker_session:
            return await SignalRepository(worker_session).apply_transition(
                SignalStatus.ACTIVE, signal_variant
            )

    result_a, result_b = await asyncio.gather(_apply(tp1_a), _apply(tp1_b))
    assert {result_a, result_b} == {True, False}, "exactly one of the two racing updates should win"
    print(f"race check ok: worker A={result_a} worker B={result_b} (exactly one True)")

    async with session_factory() as session:
        final = await SignalRepository(session).get(signal.id)
        assert final is not None
        assert final.status is SignalStatus.TP1_HIT
        assert final.targets[0].hit is True
        print(f"final status={final.status.value}, TP1 hit={final.targets[0].hit}")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
