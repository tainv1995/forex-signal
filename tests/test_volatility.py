import numpy as np

from app.analysis.volatility import analyze_volatility
from app.core.enums import Direction, Timeframe
from tests.helpers import make_candles


def test_squeeze_detected_when_volatility_coils_before_any_breakout() -> None:
    # Volatility trends down to a tight coil (a real squeeze looks like this, not
    # uniformly-random noise, which would rank near the 50th percentile every time).
    rng = np.random.default_rng(1)
    wide = list(2600 + rng.normal(0, 1.5, 40))
    decay = np.linspace(1.5, 0.05, 55)
    tight = [2600 + rng.normal(0, s) for s in decay]
    candles = make_candles(wide + tight, timeframe=Timeframe.M15)

    result = analyze_volatility(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert result.metadata["squeeze"] is True
    assert result.metadata["bandwidth_percentile"] <= 20.0


def test_mean_reversion_sell_when_price_rejected_above_upper_band() -> None:
    rng = np.random.default_rng(1)
    normal = list(2600 + rng.normal(0, 1.0, 90))
    poke_then_reject = [normal[-1] + 5, normal[-1] + 0.5]
    candles = make_candles(normal + poke_then_reject, timeframe=Timeframe.M15)

    result = analyze_volatility(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert "mean-reversion" in result.reason
    assert result.levels["atr"] > 0


def test_atr_spike_breakout_above_band_outside_a_squeeze() -> None:
    rng = np.random.default_rng(1)
    quiet = list(2600 + rng.normal(0, 0.05, 90))
    spike = [quiet[-1] + 3.0]
    candles = make_candles(quiet + spike, timeframe=Timeframe.M15)

    result = analyze_volatility(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert "ATR spike" in result.reason


def test_neutral_in_normal_volatility_price_inside_bands() -> None:
    rng = np.random.default_rng(1)
    closes = list(2600 + rng.normal(0, 1.0, 90)) + [2600.0, 2600.0]
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_volatility(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert result.metadata["squeeze"] is False


def test_neutral_when_not_enough_candles() -> None:
    candles = make_candles([2600.0] * 30, timeframe=Timeframe.M15)

    result = analyze_volatility(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
