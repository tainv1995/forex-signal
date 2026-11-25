from collections.abc import Sequence

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import atr, bollinger_bands, candles_to_frame
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

SQUEEZE_BREAKOUT_CONFIDENCE = 0.60
MEAN_REVERSION_CONFIDENCE = 0.55
LATE_BREAKOUT_CONFIDENCE = 0.50


def analyze_volatility(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    atr_period: int = 14,
    bb_period: int = 20,
    bb_std: float = 2.0,
    squeeze_lookback: int = 50,
    squeeze_percentile: float = 20.0,
) -> AnalysisResult:
    min_len = max(atr_period, bb_period) + squeeze_lookback + 5
    if len(candles) < min_len:
        return neutral_result(
            StrategyName.VOLATILITY, timeframe, "not enough candles for ATR/Bollinger"
        )

    df = candles_to_frame(candles)
    atr_series = atr(df, atr_period).dropna()
    upper, middle, lower = bollinger_bands(df["close"], bb_period, bb_std)
    if atr_series.empty or middle.dropna().empty:
        return neutral_result(StrategyName.VOLATILITY, timeframe, "ATR/Bollinger not yet warmed up")

    bandwidth = ((upper - lower) / middle).dropna()
    if len(bandwidth) < squeeze_lookback:
        return neutral_result(
            StrategyName.VOLATILITY, timeframe, "not enough history to rank bandwidth"
        )

    recent_bandwidth = bandwidth.iloc[-squeeze_lookback:]
    current_bandwidth = float(recent_bandwidth.iloc[-1])
    percentile_rank = float((recent_bandwidth < current_bandwidth).mean() * 100)
    is_squeeze = percentile_rank <= squeeze_percentile

    current_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])
    current_upper, current_lower = float(upper.iloc[-1]), float(lower.iloc[-1])
    prev_upper, prev_lower = float(upper.iloc[-2]), float(lower.iloc[-2])
    current_atr = float(atr_series.iloc[-1])

    metadata = {
        "atr": current_atr,
        "bandwidth_percentile": percentile_rank,
        "squeeze": is_squeeze,
        "upper_band": current_upper,
        "middle_band": float(middle.iloc[-1]),
        "lower_band": current_lower,
    }
    levels = {
        "atr": current_atr,
        "bollinger_upper": current_upper,
        "bollinger_lower": current_lower,
    }

    breaks_above = current_close > current_upper
    breaks_below = current_close < current_lower
    rejected_from_above = prev_close > prev_upper and current_close <= current_upper
    rejected_from_below = prev_close < prev_lower and current_close >= current_lower

    if is_squeeze:
        if breaks_above:
            return AnalysisResult(
                strategy=StrategyName.VOLATILITY,
                direction=Direction.BUY,
                confidence=SQUEEZE_BREAKOUT_CONFIDENCE,
                timeframe=timeframe,
                reason=f"{timeframe.value} Bollinger squeeze breaking out upside (volatility expansion)",
                levels=levels,
                metadata=metadata,
            )
        if breaks_below:
            return AnalysisResult(
                strategy=StrategyName.VOLATILITY,
                direction=Direction.SELL,
                confidence=SQUEEZE_BREAKOUT_CONFIDENCE,
                timeframe=timeframe,
                reason=f"{timeframe.value} Bollinger squeeze breaking out downside (volatility expansion)",
                levels=levels,
                metadata=metadata,
            )
        return neutral_result(
            StrategyName.VOLATILITY,
            timeframe,
            f"{timeframe.value} Bollinger squeeze (volatility compression), awaiting breakout",
            metadata=metadata,
        )

    if rejected_from_above:
        return AnalysisResult(
            strategy=StrategyName.VOLATILITY,
            direction=Direction.SELL,
            confidence=MEAN_REVERSION_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} price rejected above upper Bollinger band, mean-reversion setup",
            levels=levels,
            metadata=metadata,
        )
    if rejected_from_below:
        return AnalysisResult(
            strategy=StrategyName.VOLATILITY,
            direction=Direction.BUY,
            confidence=MEAN_REVERSION_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} price rejected below lower Bollinger band, mean-reversion setup",
            levels=levels,
            metadata=metadata,
        )
    if breaks_above:
        return AnalysisResult(
            strategy=StrategyName.VOLATILITY,
            direction=Direction.BUY,
            confidence=LATE_BREAKOUT_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} ATR spike, price extended above upper band",
            levels=levels,
            metadata=metadata,
        )
    if breaks_below:
        return AnalysisResult(
            strategy=StrategyName.VOLATILITY,
            direction=Direction.SELL,
            confidence=LATE_BREAKOUT_CONFIDENCE,
            timeframe=timeframe,
            reason=f"{timeframe.value} ATR spike, price extended below lower band",
            levels=levels,
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.VOLATILITY,
        timeframe,
        f"{timeframe.value} normal volatility, price inside bands",
        metadata=metadata,
    )
