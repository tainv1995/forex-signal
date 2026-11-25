import numpy as np

from app.analysis.macd import analyze_macd
from app.core.enums import Direction, Timeframe
from tests.helpers import make_candles


def test_buy_after_v_shaped_reversal_with_rising_histogram() -> None:
    rng = np.random.default_rng(5)
    decline = np.linspace(0, -15, 50)
    rally = np.linspace(-15, 5, 20)
    closes = list(2600 + np.concatenate([decline, rally]) + rng.normal(0, 0.15, 70))[:60]
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_macd(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["above_zero_line"] is True
    assert result.metadata["histogram_rising"] is True


def test_sell_after_inverted_v_reversal_with_falling_histogram() -> None:
    rng = np.random.default_rng(5)
    rally = np.linspace(0, 15, 50)
    decline = np.linspace(15, -5, 20)
    closes = list(2600 + np.concatenate([rally, decline]) + rng.normal(0, 0.15, 70))[:60]
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_macd(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["above_zero_line"] is False
    assert result.metadata["histogram_rising"] is False


def test_neutral_in_choppy_sideways_market() -> None:
    rng = np.random.default_rng(2)
    i = np.arange(100)
    closes = list(2600 + 5 * np.sin(2 * np.pi * i / 20) + rng.normal(0, 0.1, 100))
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_macd(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_not_enough_candles() -> None:
    candles = make_candles([2600.0] * 20, timeframe=Timeframe.M15)

    result = analyze_macd(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
