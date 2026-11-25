from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from app.analysis.rsi_momentum import (
    MOMENTUM_ONLY_CONFIDENCE,
    _high_divergence,
    _low_divergence,
    analyze_rsi_momentum,
)
from app.analysis.swings import Swing, SwingKind
from app.core.enums import Direction, Timeframe
from tests.helpers import make_candles


def _swing(index: int, price: float, kind: SwingKind) -> Swing:
    return Swing(
        index=index,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        price=price,
        kind=kind,
        confirmed=True,
    )


def _rsi_series(values: dict[int, float]) -> pd.Series:
    series = pd.Series(np.nan, index=range(max(values) + 1))
    for position, value in values.items():
        series.iloc[position] = value
    return series


@pytest.mark.parametrize(
    ("prev_price", "last_price", "prev_rsi", "last_rsi", "expected"),
    [
        (100, 95, 25, 35, "regular_bullish"),  # price LL, RSI HL -> reversal up
        (100, 105, 35, 25, "hidden_bullish"),  # price HL, RSI LL -> continuation up
        (100, 100, 30, 30, None),  # no change, no divergence
    ],
)
def test_low_divergence_classification(
    prev_price: float, last_price: float, prev_rsi: float, last_rsi: float, expected: str | None
) -> None:
    lows = [_swing(10, prev_price, "low"), _swing(20, last_price, "low")]
    rsi_series = _rsi_series({10: prev_rsi, 20: last_rsi})

    result = _low_divergence(lows, rsi_series)

    assert (result[0] if result else None) == expected


@pytest.mark.parametrize(
    ("prev_price", "last_price", "prev_rsi", "last_rsi", "expected"),
    [
        (100, 105, 75, 65, "regular_bearish"),  # price HH, RSI LH -> reversal down
        (100, 95, 65, 75, "hidden_bearish"),  # price LH, RSI HH -> continuation down
        (100, 100, 70, 70, None),
    ],
)
def test_high_divergence_classification(
    prev_price: float, last_price: float, prev_rsi: float, last_rsi: float, expected: str | None
) -> None:
    highs = [_swing(10, prev_price, "high"), _swing(20, last_price, "high")]
    rsi_series = _rsi_series({10: prev_rsi, 20: last_rsi})

    result = _high_divergence(highs, rsi_series)

    assert (result[0] if result else None) == expected


def test_regular_bullish_divergence_end_to_end() -> None:
    leg1 = list(np.linspace(2650, 2600, 20))
    bounce = list(np.linspace(2600, 2630, 15))
    leg2 = list(np.linspace(2630, 2595, 30) + 1.5 * np.sin(np.linspace(0, 6 * np.pi, 30)))
    tail = list(np.linspace(2595, 2605, 8))
    candles = make_candles(leg1 + bounce + leg2 + tail, timeframe=Timeframe.M15)

    result = analyze_rsi_momentum(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["divergence"] == "regular_bullish"


def test_regular_bearish_divergence_end_to_end() -> None:
    leg1 = list(np.linspace(2550, 2600, 20))
    pull = list(np.linspace(2600, 2570, 15))
    leg2 = list(np.linspace(2570, 2605, 30) + 1.5 * np.sin(np.linspace(0, 6 * np.pi, 30)))
    tail = list(np.linspace(2605, 2595, 8))
    candles = make_candles(leg1 + pull + leg2 + tail, timeframe=Timeframe.M15)

    result = analyze_rsi_momentum(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["divergence"] == "regular_bearish"


def test_momentum_only_fallback_when_no_divergence_present() -> None:
    # A clean, steady rally with no prior swing to diverge against - RSI momentum
    # fallback should fire, but only at the capped, cautious confidence level (never
    # a naive "RSI is high -> SELL").
    closes = list(np.linspace(2600, 2650, 60))
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_rsi_momentum(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.confidence == MOMENTUM_ONLY_CONFIDENCE
    assert "divergence" not in result.metadata


def test_neutral_when_not_enough_candles() -> None:
    candles = make_candles([2600.0] * 10, timeframe=Timeframe.M15)

    result = analyze_rsi_momentum(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "not enough" in result.reason
