import numpy as np

from app.analysis.fibonacci import analyze_fibonacci
from app.core.enums import Direction, Timeframe
from tests.helpers import make_candles


def test_buy_when_price_retraces_into_golden_zone_of_an_up_leg() -> None:
    rng = np.random.default_rng(4)
    warmup = list(2500 + rng.normal(0, 0.3, 30))
    up_leg = list(np.linspace(2500, 2600, 25))
    retrace = list(np.linspace(2600, 2544, 10))  # lands inside the 50-61.8% zone
    candles = make_candles(warmup + up_leg + retrace, timeframe=Timeframe.M15)

    result = analyze_fibonacci(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.confidence == 0.68
    assert (
        result.metadata["golden_zone_low"] < candles[-1].close < result.metadata["golden_zone_high"]
    )


def test_sell_when_price_bounces_into_golden_zone_of_a_down_leg() -> None:
    rng = np.random.default_rng(4)
    warmup = list(2600 + rng.normal(0, 0.3, 30))
    down_leg = list(np.linspace(2600, 2500, 25))
    bounce = list(np.linspace(2500, 2556, 10))  # lands inside the 50-61.8% zone
    candles = make_candles(warmup + down_leg + bounce, timeframe=Timeframe.M15)

    result = analyze_fibonacci(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.confidence == 0.68


def test_neutral_when_no_swing_leg_is_large_enough() -> None:
    rng = np.random.default_rng(4)
    closes = list(2600 + rng.normal(0, 0.5, 70))
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_fibonacci(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "too small" in result.reason


def test_neutral_when_price_has_not_reached_golden_zone_yet() -> None:
    rng = np.random.default_rng(4)
    warmup = list(2500 + rng.normal(0, 0.3, 30))
    up_leg = list(np.linspace(2500, 2600, 25))
    shallow_retrace = list(np.linspace(2600, 2590, 10))  # only a shallow pullback
    candles = make_candles(warmup + up_leg + shallow_retrace, timeframe=Timeframe.M15)

    result = analyze_fibonacci(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "golden zone" in result.reason
    assert "levels" in result.metadata


def test_neutral_when_not_enough_candles() -> None:
    candles = make_candles([2600.0] * 10, timeframe=Timeframe.M15)

    result = analyze_fibonacci(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
