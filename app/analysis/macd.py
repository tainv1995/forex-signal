from collections.abc import Sequence

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import candles_to_frame
from app.analysis.indicators import macd as macd_indicator
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

# MACD is a confirmation tool, never an independent trigger (Section 9).
CROSSOVER_BASE_CONFIDENCE = 0.60
MOMENTUM_ONLY_CONFIDENCE = 0.52
MAX_CONFIDENCE = 0.75
CROSSOVER_LOOKBACK = 6
HISTOGRAM_LOOKBACK = 5


def analyze_macd(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> AnalysisResult:
    min_len = slow + signal + CROSSOVER_LOOKBACK + 1
    if len(candles) < min_len:
        return neutral_result(StrategyName.MACD, timeframe, "not enough candles for MACD")

    close = candles_to_frame(candles)["close"]
    macd_line, signal_line, histogram = macd_indicator(close, fast, slow, signal)
    if histogram.dropna().empty:
        return neutral_result(StrategyName.MACD, timeframe, "MACD not yet warmed up")

    diff = (macd_line - signal_line).iloc[-CROSSOVER_LOOKBACK:]
    crossed_bullish = bool(diff.iloc[0] < 0 and diff.iloc[-1] > 0)
    crossed_bearish = bool(diff.iloc[0] > 0 and diff.iloc[-1] < 0)

    hist_recent = histogram.dropna().iloc[-HISTOGRAM_LOOKBACK:]
    histogram_rising = bool(hist_recent.iloc[-1] > hist_recent.iloc[0])

    macd_value = float(macd_line.iloc[-1])
    above_zero = macd_value > 0
    below_zero = macd_value < 0

    metadata = {
        "macd": macd_value,
        "signal": float(signal_line.iloc[-1]),
        "histogram": float(histogram.iloc[-1]),
        "histogram_rising": histogram_rising,
        "above_zero_line": above_zero,
    }

    if crossed_bullish:
        confidence = (
            CROSSOVER_BASE_CONFIDENCE
            + (0.08 if above_zero else 0)
            + (0.05 if histogram_rising else 0)
        )
        return AnalysisResult(
            strategy=StrategyName.MACD,
            direction=Direction.BUY,
            confidence=min(confidence, MAX_CONFIDENCE),
            timeframe=timeframe,
            reason=f"{timeframe.value} MACD bullish crossover"
            + (" above zero line" if above_zero else " below zero line"),
            metadata=metadata,
        )

    if crossed_bearish:
        confidence = (
            CROSSOVER_BASE_CONFIDENCE
            + (0.08 if below_zero else 0)
            + (0.05 if not histogram_rising else 0)
        )
        return AnalysisResult(
            strategy=StrategyName.MACD,
            direction=Direction.SELL,
            confidence=min(confidence, MAX_CONFIDENCE),
            timeframe=timeframe,
            reason=f"{timeframe.value} MACD bearish crossover"
            + (" below zero line" if below_zero else " above zero line"),
            metadata=metadata,
        )

    if above_zero and histogram_rising:
        return AnalysisResult(
            strategy=StrategyName.MACD,
            direction=Direction.BUY,
            confidence=MOMENTUM_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} MACD above zero line, histogram building (momentum)",
            metadata=metadata,
        )

    if below_zero and not histogram_rising:
        return AnalysisResult(
            strategy=StrategyName.MACD,
            direction=Direction.SELL,
            confidence=MOMENTUM_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} MACD below zero line, histogram fading (momentum)",
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.MACD,
        timeframe,
        f"{timeframe.value} MACD has no clear signal",
        metadata=metadata,
    )
