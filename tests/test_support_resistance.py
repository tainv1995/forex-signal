from app.analysis.support_resistance import analyze_support_resistance
from app.core.enums import Direction, Timeframe
from tests.helpers import candles_from_ohlc


def _bar(o: float, c: float, wick: float = 0.3) -> tuple[float, float, float, float]:
    return (o, max(o, c) + wick, min(o, c) - wick, c)


def _touch_high(level: float, base: float) -> list[tuple[float, float, float, float]]:
    """5 bars: approach up, a peak bar whose upper wick reaches exactly `level`, reject down."""
    peak_open, peak_close = base + 8, base + 6
    return [
        _bar(base, base + 4),
        _bar(base + 4, base + 8),
        _bar(peak_open, peak_close, wick=level - max(peak_open, peak_close)),
        _bar(peak_close, base + 3),
        _bar(base + 3, base),
    ]


def _touch_low(level: float, base: float) -> list[tuple[float, float, float, float]]:
    """Mirror of _touch_high: approach down, a trough bar reaching `level`, reject up."""
    trough_open, trough_close = base - 8, base - 6
    return [
        _bar(base, base - 4),
        _bar(base - 4, base - 8),
        _bar(trough_open, trough_close, wick=min(trough_open, trough_close) - level),
        _bar(trough_close, base - 3),
        _bar(base - 3, base),
    ]


_WARMUP = [
    _bar(100, 100.5),
    _bar(100.5, 99.8),
    _bar(99.8, 100.2),
    _bar(100.2, 99.9),
    _bar(99.9, 100),
]


def test_sell_when_price_returns_to_a_repeated_resistance_zone() -> None:
    rows = [
        *_WARMUP,
        *_touch_high(120.0, 100),
        *_touch_high(120.3, 100.5),
        *_touch_high(119.8, 99.5),
        _bar(98, 102),
        _bar(102, 107),
        _bar(107, 112),
        _bar(112, 116),
        _bar(116, 119.2, wick=0.2),  # approaches the zone again without breaking it
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_support_resistance(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.SELL
    assert result.levels["resistance"] == 120.05
    assert result.metadata["zone_count"] >= 1


def test_buy_when_price_returns_to_a_repeated_support_zone() -> None:
    rows = [
        *_WARMUP,
        *_touch_low(80.0, 100),
        *_touch_low(79.7, 99.5),
        *_touch_low(80.2, 100.5),
        _bar(102, 98),
        _bar(98, 93),
        _bar(93, 88),
        _bar(88, 84),
        _bar(84, 80.8, wick=0.2),
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_support_resistance(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.BUY
    assert result.levels["support"] == 79.95


def test_neutral_when_price_sits_between_zones() -> None:
    rows = [
        *_WARMUP,
        *_touch_low(80.0, 100),
        *_touch_low(79.7, 99.5),
        *_touch_low(80.2, 100.5),
        _bar(102, 98),
        _bar(98, 95),
        _bar(95, 96),
        _bar(96, 97),
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_support_resistance(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_not_enough_candles() -> None:
    rows = _WARMUP
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_support_resistance(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
