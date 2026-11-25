from collections.abc import Sequence
from typing import Literal

import pandas as pd

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import candles_to_frame
from app.analysis.indicators import rsi as rsi_indicator
from app.analysis.swings import Swing, confirmed_swings, find_swings, swing_highs, swing_lows
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

DivergenceKind = Literal["regular_bullish", "hidden_bullish", "regular_bearish", "hidden_bearish"]

REGULAR_DIVERGENCE_BASE = 0.70
REGULAR_DIVERGENCE_MAX = 0.80
HIDDEN_DIVERGENCE_BASE = 0.60
HIDDEN_DIVERGENCE_MAX = 0.68
MOMENTUM_ONLY_CONFIDENCE = 0.50
MOMENTUM_NEUTRAL_BAND = 5.0


def _low_divergence(
    lows: Sequence[Swing], rsi_series: pd.Series
) -> tuple[DivergenceKind, Swing, Swing] | None:
    if len(lows) < 2:
        return None
    prev, last = lows[-2], lows[-1]
    prev_rsi, last_rsi = float(rsi_series.iloc[prev.index]), float(rsi_series.iloc[last.index])
    if last.price < prev.price and last_rsi > prev_rsi:
        return "regular_bullish", prev, last
    if last.price > prev.price and last_rsi < prev_rsi:
        return "hidden_bullish", prev, last
    return None


def _high_divergence(
    highs: Sequence[Swing], rsi_series: pd.Series
) -> tuple[DivergenceKind, Swing, Swing] | None:
    if len(highs) < 2:
        return None
    prev, last = highs[-2], highs[-1]
    prev_rsi, last_rsi = float(rsi_series.iloc[prev.index]), float(rsi_series.iloc[last.index])
    if last.price > prev.price and last_rsi < prev_rsi:
        return "regular_bearish", prev, last
    if last.price < prev.price and last_rsi > prev_rsi:
        return "hidden_bearish", prev, last
    return None


def analyze_rsi_momentum(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    period: int = 14,
    overbought: float = 70.0,
    oversold: float = 30.0,
    swing_left: int = 2,
    swing_right: int = 2,
) -> AnalysisResult:
    min_len = period + swing_left + swing_right + 20
    if len(candles) < min_len:
        return neutral_result(StrategyName.RSI_MOMENTUM, timeframe, "not enough candles for RSI")

    close = candles_to_frame(candles)["close"]
    rsi_series = rsi_indicator(close, period)
    if rsi_series.dropna().empty:
        return neutral_result(StrategyName.RSI_MOMENTUM, timeframe, "RSI not yet warmed up")

    current_rsi = float(rsi_series.iloc[-1])
    is_overbought = current_rsi >= overbought
    is_oversold = current_rsi <= oversold

    swings = confirmed_swings(find_swings(candles, left=swing_left, right=swing_right))
    lows, highs = swing_lows(swings), swing_highs(swings)

    low_div = _low_divergence(lows, rsi_series)
    high_div = _high_divergence(highs, rsi_series)

    metadata: dict[str, object] = {
        "rsi": current_rsi,
        "overbought": is_overbought,
        "oversold": is_oversold,
    }

    # Regular divergence (reversal signal) takes priority over hidden (continuation).
    if low_div and low_div[0] == "regular_bullish":
        confidence = REGULAR_DIVERGENCE_BASE + (0.08 if is_oversold else 0.0)
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.BUY,
            confidence=min(confidence, REGULAR_DIVERGENCE_MAX),
            timeframe=timeframe,
            reason=f"{timeframe.value} regular bullish RSI divergence: price lower low, RSI higher low"
            + (" (oversold)" if is_oversold else ""),
            metadata=metadata | {"divergence": "regular_bullish"},
        )

    if high_div and high_div[0] == "regular_bearish":
        confidence = REGULAR_DIVERGENCE_BASE + (0.08 if is_overbought else 0.0)
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.SELL,
            confidence=min(confidence, REGULAR_DIVERGENCE_MAX),
            timeframe=timeframe,
            reason=f"{timeframe.value} regular bearish RSI divergence: price higher high, RSI lower high"
            + (" (overbought)" if is_overbought else ""),
            metadata=metadata | {"divergence": "regular_bearish"},
        )

    if low_div and low_div[0] == "hidden_bullish":
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.BUY,
            confidence=HIDDEN_DIVERGENCE_BASE,
            timeframe=timeframe,
            reason=f"{timeframe.value} hidden bullish RSI divergence: price higher low, RSI lower low "
            "(trend continuation)",
            metadata=metadata | {"divergence": "hidden_bullish"},
        )

    if high_div and high_div[0] == "hidden_bearish":
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.SELL,
            confidence=HIDDEN_DIVERGENCE_BASE,
            timeframe=timeframe,
            reason=f"{timeframe.value} hidden bearish RSI divergence: price lower high, RSI higher high "
            "(trend continuation)",
            metadata=metadata | {"divergence": "hidden_bearish"},
        )

    # No divergence: fall back to plain momentum, never a naive "RSI>70 => SELL".
    if current_rsi > 50 + MOMENTUM_NEUTRAL_BAND:
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.BUY,
            confidence=MOMENTUM_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} RSI momentum above 50 ({current_rsi:.1f}), no divergence",
            metadata=metadata,
        )
    if current_rsi < 50 - MOMENTUM_NEUTRAL_BAND:
        return AnalysisResult(
            strategy=StrategyName.RSI_MOMENTUM,
            direction=Direction.SELL,
            confidence=MOMENTUM_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} RSI momentum below 50 ({current_rsi:.1f}), no divergence",
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.RSI_MOMENTUM,
        timeframe,
        f"{timeframe.value} RSI near 50 ({current_rsi:.1f}), no momentum or divergence",
        metadata=metadata,
    )
