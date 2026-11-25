from collections.abc import Sequence
from typing import Literal

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.swings import Swing, confirmed_swings, find_swings, swing_highs, swing_lows
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

Trend = Literal["bullish", "bearish", "sideway"]
SwingLabel = Literal["HH", "HL", "LH", "LL"]

MIN_SWINGS_REQUIRED = 2


def _label_last(swings: Sequence[Swing]) -> tuple[SwingLabel | None, Swing | None]:
    if len(swings) < MIN_SWINGS_REQUIRED:
        return None, swings[-1] if swings else None
    prev, curr = swings[-2], swings[-1]
    if curr.kind == "high":
        label: SwingLabel = "HH" if curr.price > prev.price else "LH"
    else:
        label = "HL" if curr.price > prev.price else "LL"
    return label, curr


def _trend_from_labels(high_label: SwingLabel | None, low_label: SwingLabel | None) -> Trend:
    if high_label == "HH" and low_label == "HL":
        return "bullish"
    if high_label == "LH" and low_label == "LL":
        return "bearish"
    return "sideway"


def analyze_market_structure(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    left: int = 2,
    right: int = 2,
) -> AnalysisResult:
    """HH/HL/LH/LL classification + rule-based BOS/CHoCH detection.

    A "break" only counts against a *confirmed* swing extreme (Section 42: no
    look-ahead) - a random small wiggle never qualifies since find_swings already
    filters those out with the left/right fractal window.
    """
    if len(candles) < (left + right + 4):
        return neutral_result(
            StrategyName.MARKET_STRUCTURE, timeframe, "not enough candles for structure analysis"
        )

    swings = confirmed_swings(find_swings(candles, left=left, right=right))
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    if len(highs) < MIN_SWINGS_REQUIRED or len(lows) < MIN_SWINGS_REQUIRED:
        return neutral_result(
            StrategyName.MARKET_STRUCTURE,
            timeframe,
            "insufficient confirmed swing structure to classify trend",
            metadata={"swing_high_count": len(highs), "swing_low_count": len(lows)},
        )

    high_label, last_high = _label_last(highs)
    low_label, last_low = _label_last(lows)
    trend = _trend_from_labels(high_label, low_label)
    assert last_high is not None
    assert last_low is not None

    current_close = candles[-1].close
    breaks_above_high = current_close > last_high.price
    breaks_below_low = current_close < last_low.price

    metadata = {
        "trend": trend,
        "high_label": high_label,
        "low_label": low_label,
        "last_swing_high": last_high.price,
        "last_swing_low": last_low.price,
    }
    levels = {"swing_high": last_high.price, "swing_low": last_low.price}

    if trend == "bullish":
        if breaks_below_low:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.SELL,
                confidence=0.80,
                timeframe=timeframe,
                reason=f"{timeframe.value} bearish CHoCH: price broke below prior HL "
                f"({last_low.price}), bullish structure invalidated",
                levels=levels,
                metadata=metadata | {"event": "CHoCH"},
            )
        if breaks_above_high:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.BUY,
                confidence=0.78,
                timeframe=timeframe,
                reason=f"{timeframe.value} bullish BOS: price broke above prior HH "
                f"({last_high.price}), uptrend continuation",
                levels=levels,
                metadata=metadata | {"event": "BOS"},
            )
    elif trend == "bearish":
        if breaks_above_high:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.BUY,
                confidence=0.80,
                timeframe=timeframe,
                reason=f"{timeframe.value} bullish CHoCH: price broke above prior LH "
                f"({last_high.price}), bearish structure invalidated",
                levels=levels,
                metadata=metadata | {"event": "CHoCH"},
            )
        if breaks_below_low:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.SELL,
                confidence=0.78,
                timeframe=timeframe,
                reason=f"{timeframe.value} bearish BOS: price broke below prior LL "
                f"({last_low.price}), downtrend continuation",
                levels=levels,
                metadata=metadata | {"event": "BOS"},
            )
    else:
        if breaks_above_high:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.BUY,
                confidence=0.62,
                timeframe=timeframe,
                reason=f"{timeframe.value} sideway range broken to the upside "
                f"({last_high.price}), potential reversal",
                levels=levels,
                metadata=metadata | {"event": "range_breakout"},
            )
        if breaks_below_low:
            return AnalysisResult(
                strategy=StrategyName.MARKET_STRUCTURE,
                direction=Direction.SELL,
                confidence=0.62,
                timeframe=timeframe,
                reason=f"{timeframe.value} sideway range broken to the downside "
                f"({last_low.price}), potential reversal",
                levels=levels,
                metadata=metadata | {"event": "range_breakout"},
            )

    return neutral_result(
        StrategyName.MARKET_STRUCTURE,
        timeframe,
        f"{timeframe.value} structure is {trend} with no fresh break of structure",
        metadata=metadata,
    )
