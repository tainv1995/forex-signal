from app.analysis.price_action import (
    ISOLATED_CONFIDENCE,
    NEAR_ZONE_CONFIDENCE,
    analyze_price_action,
)
from app.core.enums import Direction, Timeframe
from tests.helpers import candles_from_ohlc


def _bar(o: float, c: float, wick: float = 0.3) -> tuple[float, float, float, float]:
    return (o, max(o, c) + wick, min(o, c) - wick, c)


def _touch_low(level: float, base: float) -> list[tuple[float, float, float, float]]:
    trough_open, trough_close = base - 8, base - 6
    return [
        _bar(base, base - 4),
        _bar(base - 4, base - 8),
        _bar(trough_open, trough_close, wick=min(trough_open, trough_close) - level),
        _bar(trough_close, base - 3),
        _bar(base - 3, base),
    ]


_WARMUP = [_bar(100 + (i % 2) * 0.2, 100 - (i % 2) * 0.2) for i in range(15)]


def test_bullish_engulfing_at_a_swing_low_is_a_strong_signal() -> None:
    rows = [
        *_WARMUP,
        *_touch_low(80.0, 100),
        _bar(102, 106),
        _bar(106, 110),
        _bar(110, 100),
        (81, 81.2, 79.8, 80.3),  # bearish
        (80.2, 82.5, 80.0, 82.0),  # engulfs it, closes right back at the swing low zone
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_price_action(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["pattern"] == "bullish_engulfing"
    assert result.metadata["near_swing_zone"] is True
    assert result.confidence == NEAR_ZONE_CONFIDENCE


def test_bullish_engulfing_far_from_any_swing_zone_is_a_weak_signal() -> None:
    rows = [
        *_WARMUP,
        *_touch_low(80.0, 100),
        _bar(102, 106),
        _bar(106, 130),
        _bar(130, 150),
        (151, 151.2, 149.8, 150.3),  # bearish, far above the only known swing zone
        (150.2, 152.5, 150.0, 152.0),  # engulfs it, but in open air
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_price_action(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["near_swing_zone"] is False
    assert result.confidence == ISOLATED_CONFIDENCE


def test_bearish_engulfing_is_detected() -> None:
    rows = [
        *_WARMUP,
        *_touch_low(80.0, 100),
        _bar(102, 106),
        _bar(106, 110),
        (105, 107.3, 104.8, 107),  # bullish
        (107.5, 107.8, 104.3, 104.5),  # engulfs it, closes down
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_price_action(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["pattern"] == "bearish_engulfing"


def test_neutral_when_last_candle_has_no_significant_pattern() -> None:
    rows = [*_WARMUP, *_touch_low(80.0, 100), _bar(102, 103), _bar(103, 103.5), _bar(103.5, 103.6)]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_price_action(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_not_enough_candles() -> None:
    candles = candles_from_ohlc(_WARMUP[:10], timeframe=Timeframe.M15)

    result = analyze_price_action(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
