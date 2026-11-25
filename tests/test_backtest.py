from itertools import pairwise

import pytest

from app.backtest.engine import run_backtest
from app.core.enums import SignalStatus, Timeframe
from app.market_data.mock import MockProvider


@pytest.mark.asyncio
async def test_backtest_runs_end_to_end_on_mock_data_without_lookahead_errors() -> None:
    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles("XAUUSD", Timeframe.M15, limit=400)

    result = await run_backtest(candles, Timeframe.M15, "XAUUSD", min_lookback=250)

    assert result.stats.total_signals >= 0
    # Every produced signal must be a real, internally consistent Signal object.
    for signal in result.signals:
        assert signal.status in SignalStatus
        assert len(signal.targets) == 5
        # SL is always exactly -1R by construction; any TP hit is a positive R.
        for target in signal.targets:
            if target.hit:
                assert target.rr > 0

    # Signals must appear in chronological order and never before the warm-up window.
    created_ats = [s.created_at for s in result.signals]
    assert created_ats == sorted(created_ats)
    if created_ats:
        assert created_ats[0] >= candles[250].timestamp

    assert result.max_consecutive_losses >= 0
    assert result.signals_per_day >= 0


@pytest.mark.asyncio
async def test_backtest_returns_empty_result_when_not_enough_candles() -> None:
    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles("XAUUSD", Timeframe.M15, limit=50)

    result = await run_backtest(candles, Timeframe.M15, "XAUUSD", min_lookback=250)

    assert result.stats.total_signals == 0
    assert result.signals == []


@pytest.mark.asyncio
async def test_backtest_never_holds_two_open_signals_at_once() -> None:
    # Reconstructed by checking no signal's created_at falls strictly between another
    # open signal's own created_at and closed_at - a simple non-overlap sanity check.
    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles("XAUUSD", Timeframe.M15, limit=500)

    result = await run_backtest(candles, Timeframe.M15, "XAUUSD", min_lookback=250)

    closed_signals = [s for s in result.signals if s.closed_at is not None]
    for earlier, later in pairwise(closed_signals):
        assert earlier.closed_at is not None
        assert later.created_at >= earlier.closed_at
