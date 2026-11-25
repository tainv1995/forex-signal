import math
from collections.abc import Sequence
from datetime import UTC, datetime

from app.core.enums import Timeframe
from app.core.timeframes import TIMEFRAME_DURATIONS
from app.market_data.base import Candle

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def make_candles(
    closes: Sequence[float],
    timeframe: Timeframe = Timeframe.M15,
    start: datetime = BASE_TIME,
    wick: float = 0.5,
    symbol: str = "XAUUSD",
) -> list[Candle]:
    """Build a simple OHLC series from a list of close prices.

    Each candle opens at the previous close and adds a fixed wick above/below, plus a
    tiny bounded (non-monotonic, ~zero-mean) per-index jitter. Without the jitter, a
    candle whose close is a local turning point and the next candle (which opens
    exactly there) would compute the exact same high/low and hide any swing at that
    point behind a false tie - real OHLC data essentially never has that coincidence.
    Good enough when a test mostly cares about the close series (indicators, swings);
    it is NOT precise enough when a test needs an exact wick value - use
    candles_from_ohlc for those instead.
    """
    interval = TIMEFRAME_DURATIONS[timeframe]
    candles: list[Candle] = []
    open_price = closes[0]
    for i, close in enumerate(closes):
        jitter_high = 1e-3 * math.sin(i * 2.399)
        jitter_low = 1e-3 * math.sin(i * 1.732 + 1)
        high = max(open_price, close) + wick + jitter_high
        low = min(open_price, close) - wick - jitter_low
        candles.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + interval * i,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=100.0,
            )
        )
        open_price = close
    return candles


def candles_from_ohlc(
    rows: Sequence[tuple[float, float, float, float]],
    timeframe: Timeframe = Timeframe.M15,
    start: datetime = BASE_TIME,
    symbol: str = "XAUUSD",
    volume: float = 100.0,
) -> list[Candle]:
    """Build candles from explicit (open, high, low, close) tuples.

    Use this whenever a test depends on the exact shape of a bar or the exact
    ordering of highs/lows between bars (swings, price action patterns, FVGs,
    liquidity sweeps) - make_candles' derived wicks are not precise enough there.
    """
    interval = TIMEFRAME_DURATIONS[timeframe]
    return [
        Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=start + interval * i,
            open=o,
            high=h,
            low=low,
            close=c,
            volume=volume,
        )
        for i, (o, h, low, c) in enumerate(rows)
    ]
