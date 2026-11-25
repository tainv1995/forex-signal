from app.analysis.liquidity_smc import (
    SWEEP_ONLY_CONFIDENCE,
    analyze_liquidity_smc,
    find_fair_value_gaps,
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


def _touch_high(level: float, base: float) -> list[tuple[float, float, float, float]]:
    peak_open, peak_close = base + 8, base + 6
    return [
        _bar(base, base + 4),
        _bar(base + 4, base + 8),
        _bar(peak_open, peak_close, wick=level - max(peak_open, peak_close)),
        _bar(peak_close, base + 3),
        _bar(base + 3, base),
    ]


def test_find_fair_value_gaps_detects_bullish_and_bearish_imbalance() -> None:
    bullish_rows = [_bar(100, 101), _bar(103, 106), _bar(107, 110)]
    bearish_rows = [_bar(110, 109), _bar(106, 103), _bar(102, 99)]
    bullish = find_fair_value_gaps(candles_from_ohlc(bullish_rows))
    bearish = find_fair_value_gaps(candles_from_ohlc(bearish_rows))

    assert bullish[0].kind == "bullish"
    assert bearish[0].kind == "bearish"


def test_buy_on_sell_side_liquidity_sweep_with_bullish_displacement() -> None:
    warmup = [_bar(150 + (i % 2) * 0.2, 150 - (i % 2) * 0.2) for i in range(15)]
    rows = [
        *warmup,
        *_touch_low(100.0, 120),  # equal low #1
        _bar(112, 118),
        _bar(118, 122),
        *_touch_low(100.3, 122),  # equal low #2, near #1
        _bar(114, 118),
        _bar(118, 121),
        _bar(121, 119),
        (119, 119.5, 98.0, 101.0),  # sweep: wicks below 100.0, closes back above
        (101.2, 112.0, 101.0, 111.5),  # bullish displacement
        _bar(111.5, 112),
        _bar(112, 112.5),
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_liquidity_smc(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["event"] == "sweep_displacement"
    assert result.levels["liquidity_level"] == 100.0


def test_sell_on_buy_side_liquidity_sweep_with_bearish_displacement() -> None:
    warmup = [_bar(50 + (i % 2) * 0.2, 50 - (i % 2) * 0.2) for i in range(15)]
    rows = [
        *warmup,
        *_touch_high(120.0, 100),
        _bar(108, 102),
        _bar(102, 98),
        *_touch_high(119.7, 98),
        _bar(106, 102),
        _bar(102, 99),
        _bar(99, 101),
        (101, 122.0, 100.5, 119.0),  # sweep: wicks above 120.0, closes back below
        (118.8, 119.0, 108.0, 108.5),  # bearish displacement
        _bar(108.5, 108),
        _bar(108, 107.5),
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_liquidity_smc(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["event"] == "sweep_displacement"
    assert result.levels["liquidity_level"] == 120.0


def test_sweep_without_displacement_is_a_weaker_watch_signal() -> None:
    warmup = [_bar(50 + (i % 2) * 0.2, 50 - (i % 2) * 0.2) for i in range(16)]
    rows = [
        *warmup,
        *_touch_high(120.0, 100),
        _bar(108, 102),
        _bar(102, 98),
        *_touch_high(119.7, 98),
        _bar(106, 102),
        _bar(102, 99),
        _bar(99, 101),
        (101, 122.0, 100.5, 119.0),  # sweep, but no strong follow-through
        _bar(119, 118.5),
        _bar(118.5, 118),
    ]
    candles = candles_from_ohlc(rows, timeframe=Timeframe.M15)

    result = analyze_liquidity_smc(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["event"] == "sweep_only"
    assert result.confidence == SWEEP_ONLY_CONFIDENCE


def test_neutral_when_no_equal_levels_swept() -> None:
    warmup = [_bar(100 + (i % 2) * 0.2, 100 - (i % 2) * 0.2) for i in range(40)]
    candles = candles_from_ohlc(warmup, timeframe=Timeframe.M15)

    result = analyze_liquidity_smc(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_not_enough_candles() -> None:
    candles = candles_from_ohlc([_bar(100, 100.5)] * 10, timeframe=Timeframe.M15)

    result = analyze_liquidity_smc(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
