from datetime import UTC, datetime
from itertools import pairwise

import pytest

from app.core.enums import Timeframe
from app.core.timeframes import TIMEFRAME_DURATIONS
from app.market_data.mock import MockProvider


@pytest.mark.asyncio
async def test_get_candles_returns_requested_length_and_valid_ohlc() -> None:
    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles("XAUUSD", Timeframe.M5, limit=50)

    assert len(candles) == 50
    for candle in candles:
        assert candle.high >= max(candle.open, candle.close)
        assert candle.low <= min(candle.open, candle.close)
        assert candle.high >= candle.low


@pytest.mark.asyncio
async def test_get_candles_timestamps_are_evenly_spaced_and_ascending() -> None:
    provider = MockProvider()
    candles = await provider.get_candles("XAUUSD", Timeframe.M1, limit=20)
    interval = TIMEFRAME_DURATIONS[Timeframe.M1]

    for previous, current in pairwise(candles):
        assert current.timestamp - previous.timestamp == interval


@pytest.mark.asyncio
async def test_get_candles_is_stable_across_repeated_calls() -> None:
    provider = MockProvider()
    first = await provider.get_candles("XAUUSD", Timeframe.M15, limit=10)
    second = await provider.get_candles("XAUUSD", Timeframe.M15, limit=10)

    assert [c.timestamp for c in first] == [c.timestamp for c in second]
    assert [c.close for c in first] == [c.close for c in second]


@pytest.mark.asyncio
async def test_get_current_price_returns_tick_with_bid_below_ask() -> None:
    provider = MockProvider()
    tick = await provider.get_current_price("XAUUSD")

    assert tick.symbol == "XAUUSD"
    assert tick.bid is not None
    assert tick.ask is not None
    assert tick.bid <= tick.ask
    assert tick.timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_subscribe_ticks_yields_live_ticks() -> None:
    provider = MockProvider()
    stream = provider.subscribe_ticks("XAUUSD")
    tick = await anext(stream)

    assert tick.symbol == "XAUUSD"
    assert (datetime.now(UTC) - tick.timestamp).total_seconds() < 5
