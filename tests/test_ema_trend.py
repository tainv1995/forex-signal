import numpy as np

from app.analysis.ema_trend import (
    CROSSOVER_ONLY_CONFIDENCE,
    MAX_STACK_CONFIDENCE,
    analyze_ema_trend,
)
from app.core.enums import Direction, Timeframe
from tests.helpers import make_candles

N = 260


def _trending_closes(slope: float, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    trend = np.linspace(0, slope, N)
    noise = rng.normal(0, 0.4, N)
    return list(2600 + trend + noise)


def test_buy_on_clean_bullish_ema_stack() -> None:
    candles = make_candles(_trending_closes(60), timeframe=Timeframe.M15)

    result = analyze_ema_trend(candles, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.metadata["bullish_stack"] is True
    assert (
        result.levels["ema20"]
        > result.levels["ema50"]
        > result.levels["ema100"]
        > result.levels["ema200"]
    )
    assert result.confidence <= MAX_STACK_CONFIDENCE


def test_sell_on_clean_bearish_ema_stack() -> None:
    candles = make_candles(_trending_closes(-60), timeframe=Timeframe.M15)

    result = analyze_ema_trend(candles, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert result.metadata["bearish_stack"] is True
    assert (
        result.levels["ema20"]
        < result.levels["ema50"]
        < result.levels["ema100"]
        < result.levels["ema200"]
    )


def test_sideways_market_never_reaches_full_stack_confidence() -> None:
    # Bounded oscillation (not a random walk, which can drift into a false stack by
    # chance) - a genuinely range-bound market should never claim a clean EMA stack.
    rng = np.random.default_rng(3)
    i = np.arange(N)
    closes = list(2600 + 8 * np.sin(2 * np.pi * i / 40) + rng.normal(0, 0.3, N))
    candles = make_candles(closes, timeframe=Timeframe.M15)

    result = analyze_ema_trend(candles, Timeframe.M15)

    assert result.metadata["bullish_stack"] is False
    assert result.metadata["bearish_stack"] is False
    assert result.confidence <= CROSSOVER_ONLY_CONFIDENCE


def test_neutral_when_not_enough_candles_for_ema200() -> None:
    candles = make_candles(_trending_closes(10)[:100], timeframe=Timeframe.M15)

    result = analyze_ema_trend(candles, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
