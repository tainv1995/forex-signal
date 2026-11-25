from collections.abc import Sequence

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import candles_to_frame, ema
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

# EMA alone is a confirmation tool (Section 7: "Không BUY chỉ vì EMA crossover"),
# so its own confidence never rises to the level of a structure/liquidity-based signal.
MAX_STACK_CONFIDENCE = 0.75
CROSSOVER_ONLY_CONFIDENCE = 0.55
CROSSOVER_LOOKBACK = 6
SLOPE_LOOKBACK = 10


def analyze_ema_trend(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    fast: int = 20,
    mid: int = 50,
    slow: int = 100,
    trend: int = 200,
) -> AnalysisResult:
    if len(candles) < trend + SLOPE_LOOKBACK + 1:
        return neutral_result(
            StrategyName.EMA_TREND, timeframe, "not enough candles for EMA200 to be meaningful"
        )

    close = candles_to_frame(candles)["close"]
    ema_fast = ema(close, fast)
    ema_mid = ema(close, mid)
    ema_slow = ema(close, slow)
    ema_trend = ema(close, trend)

    if ema_trend.dropna().empty:
        return neutral_result(StrategyName.EMA_TREND, timeframe, "EMA200 not yet warmed up")

    price = float(close.iloc[-1])
    e_fast, e_mid, e_slow, e_trend = (
        float(ema_fast.iloc[-1]),
        float(ema_mid.iloc[-1]),
        float(ema_slow.iloc[-1]),
        float(ema_trend.iloc[-1]),
    )

    bullish_stack = price > e_fast > e_mid > e_slow > e_trend
    bearish_stack = price < e_fast < e_mid < e_slow < e_trend
    mid_slope = float(ema_mid.iloc[-1] - ema_mid.iloc[-1 - SLOPE_LOOKBACK])

    diff = (ema_fast - ema_mid).iloc[-CROSSOVER_LOOKBACK:]
    crossed_bullish = diff.iloc[0] < 0 and diff.iloc[-1] > 0
    crossed_bearish = diff.iloc[0] > 0 and diff.iloc[-1] < 0

    metadata = {
        "ema20": e_fast,
        "ema50": e_mid,
        "ema100": e_slow,
        "ema200": e_trend,
        "ema50_slope": mid_slope,
        "bullish_stack": bullish_stack,
        "bearish_stack": bearish_stack,
    }
    levels = {"ema20": e_fast, "ema50": e_mid, "ema100": e_slow, "ema200": e_trend}

    if bullish_stack:
        confidence = 0.68 + (0.05 if mid_slope > 0 else 0.0) + (0.02 if crossed_bullish else 0.0)
        return AnalysisResult(
            strategy=StrategyName.EMA_TREND,
            direction=Direction.BUY,
            confidence=min(confidence, MAX_STACK_CONFIDENCE),
            timeframe=timeframe,
            reason=f"{timeframe.value} bullish EMA stack: price > EMA20 > EMA50 > EMA100 > EMA200",
            levels=levels,
            metadata=metadata,
        )

    if bearish_stack:
        confidence = 0.68 + (0.05 if mid_slope < 0 else 0.0) + (0.02 if crossed_bearish else 0.0)
        return AnalysisResult(
            strategy=StrategyName.EMA_TREND,
            direction=Direction.SELL,
            confidence=min(confidence, MAX_STACK_CONFIDENCE),
            timeframe=timeframe,
            reason=f"{timeframe.value} bearish EMA stack: price < EMA20 < EMA50 < EMA100 < EMA200",
            levels=levels,
            metadata=metadata,
        )

    if crossed_bullish:
        return AnalysisResult(
            strategy=StrategyName.EMA_TREND,
            direction=Direction.BUY,
            confidence=CROSSOVER_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} EMA20 crossed above EMA50, stack not fully aligned yet",
            levels=levels,
            metadata=metadata,
        )

    if crossed_bearish:
        return AnalysisResult(
            strategy=StrategyName.EMA_TREND,
            direction=Direction.SELL,
            confidence=CROSSOVER_ONLY_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} EMA20 crossed below EMA50, stack not fully aligned yet",
            levels=levels,
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.EMA_TREND,
        timeframe,
        f"{timeframe.value} EMAs are mixed/tangled, no clear trend",
        metadata=metadata,
    )
