from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import atr, candles_to_frame
from app.analysis.swings import (
    Swing,
    cluster_by_price,
    confirmed_swings,
    find_swings,
    swing_highs,
    swing_lows,
)
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

FVGKind = Literal["bullish", "bearish"]

SWEEP_ONLY_CONFIDENCE = 0.65
SWEEP_DISPLACEMENT_CONFIDENCE = 0.85
FVG_CONFLUENCE_BONUS = 0.05
OFF_DISCOUNT_PENALTY = 0.05
MAX_CONFIDENCE = 0.95
DISPLACEMENT_ATR_MULT = 1.5
SWEEP_LOOKBACK = 5
EQUAL_LEVEL_ATR_MULT = 0.15
MIN_TOUCHES_FOR_EQUAL = 2


@dataclass(frozen=True, slots=True)
class FairValueGap:
    kind: FVGKind
    low: float
    high: float
    middle_index: int


def find_fair_value_gaps(candles: Sequence[Candle]) -> list[FairValueGap]:
    """3-candle imbalance: candle1 and candle3 don't overlap, leaving a gap candle2
    never traded through - price often returns to "fill" it before continuing."""
    gaps: list[FairValueGap] = []
    for i in range(2, len(candles)):
        first, third = candles[i - 2], candles[i]
        if first.high < third.low:
            gaps.append(FairValueGap("bullish", first.high, third.low, i - 1))
        elif first.low > third.high:
            gaps.append(FairValueGap("bearish", third.high, first.low, i - 1))
    return gaps


def _equal_level_clusters(
    swings: Sequence[Swing], kind: Literal["high", "low"], tolerance: float
) -> list[list[Swing]]:
    same_kind = [s for s in swings if s.kind == kind]
    return [c for c in cluster_by_price(same_kind, tolerance) if len(c) >= MIN_TOUCHES_FOR_EQUAL]


def _detect_sweep(
    candles: Sequence[Candle], level: float, side: Literal["sell_side", "buy_side"], lookback: int
) -> Candle | None:
    """A sweep wicks past resting liquidity, then closes back on the other side of it
    (a stop hunt), rather than a clean breakout that keeps going."""
    for candle in candles[-lookback:]:
        if side == "sell_side" and candle.low < level and candle.close > level:
            return candle
        if side == "buy_side" and candle.high > level and candle.close < level:
            return candle
    return None


def _has_displacement(
    candles: Sequence[Candle], atr_value: float, direction: Literal["up", "down"], lookback: int
) -> bool:
    if atr_value <= 0:
        return False
    for candle in candles[-lookback:]:
        body = abs(candle.close - candle.open)
        if body < atr_value * DISPLACEMENT_ATR_MULT:
            continue
        if direction == "up" and candle.close > candle.open:
            return True
        if direction == "down" and candle.close < candle.open:
            return True
    return False


def analyze_liquidity_smc(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    left: int = 2,
    right: int = 2,
) -> AnalysisResult:
    min_len = left + right + 30
    if len(candles) < min_len:
        return neutral_result(
            StrategyName.LIQUIDITY_SMC, timeframe, "not enough candles for SMC analysis"
        )

    df = candles_to_frame(candles)
    atr_series = atr(df, period=14).dropna()
    if atr_series.empty:
        return neutral_result(StrategyName.LIQUIDITY_SMC, timeframe, "ATR unavailable")
    current_atr = float(atr_series.iloc[-1])

    swings = confirmed_swings(find_swings(candles, left=left, right=right))
    highs, lows = swing_highs(swings), swing_lows(swings)
    if not highs or not lows:
        return neutral_result(
            StrategyName.LIQUIDITY_SMC, timeframe, "not enough structure for SMC analysis"
        )

    tolerance = current_atr * EQUAL_LEVEL_ATR_MULT
    equal_lows = _equal_level_clusters(lows, "low", tolerance)
    equal_highs = _equal_level_clusters(highs, "high", tolerance)
    fvgs = find_fair_value_gaps(candles[-40:])

    range_high, range_low = highs[-1].price, lows[-1].price
    current_price = float(candles[-1].close)
    position_pct = (
        (current_price - range_low) / (range_high - range_low) if range_high > range_low else 0.5
    )
    in_discount = position_pct <= 0.5

    metadata: dict[str, object] = {
        "equal_low_zones": len(equal_lows),
        "equal_high_zones": len(equal_highs),
        "position_in_range_pct": round(position_pct, 3),
        "fvg_count": len(fvgs),
    }

    if equal_lows:
        most_recent_low_cluster = max(equal_lows, key=lambda cluster: max(s.index for s in cluster))
        sell_side_level = min(s.price for s in most_recent_low_cluster)
        sweep = _detect_sweep(candles, sell_side_level, "sell_side", SWEEP_LOOKBACK)
        if sweep:
            displaced = _has_displacement(candles, current_atr, "up", SWEEP_LOOKBACK)
            bullish_fvg_here = any(
                f.kind == "bullish" and f.low <= current_price <= f.high for f in fvgs
            )
            if displaced:
                confidence = SWEEP_DISPLACEMENT_CONFIDENCE
                confidence += FVG_CONFLUENCE_BONUS if bullish_fvg_here else 0.0
                confidence -= 0.0 if in_discount else OFF_DISCOUNT_PENALTY
                return AnalysisResult(
                    strategy=StrategyName.LIQUIDITY_SMC,
                    direction=Direction.BUY,
                    confidence=min(confidence, MAX_CONFIDENCE),
                    timeframe=timeframe,
                    reason=(
                        f"{timeframe.value} sell-side liquidity swept below {sell_side_level:.2f} "
                        "with bullish displacement"
                        + (", price sitting in a bullish FVG" if bullish_fvg_here else "")
                    ),
                    levels={"liquidity_level": sell_side_level},
                    metadata=metadata | {"event": "sweep_displacement"},
                )
            return AnalysisResult(
                strategy=StrategyName.LIQUIDITY_SMC,
                direction=Direction.BUY,
                confidence=SWEEP_ONLY_CONFIDENCE,
                timeframe=timeframe,
                reason=(
                    f"{timeframe.value} sell-side liquidity swept below {sell_side_level:.2f}, "
                    "awaiting displacement confirmation"
                ),
                levels={"liquidity_level": sell_side_level},
                metadata=metadata | {"event": "sweep_only"},
            )

    if equal_highs:
        most_recent_high_cluster = max(
            equal_highs, key=lambda cluster: max(s.index for s in cluster)
        )
        buy_side_level = max(s.price for s in most_recent_high_cluster)
        sweep = _detect_sweep(candles, buy_side_level, "buy_side", SWEEP_LOOKBACK)
        if sweep:
            displaced = _has_displacement(candles, current_atr, "down", SWEEP_LOOKBACK)
            bearish_fvg_here = any(
                f.kind == "bearish" and f.low <= current_price <= f.high for f in fvgs
            )
            if displaced:
                confidence = SWEEP_DISPLACEMENT_CONFIDENCE
                confidence += FVG_CONFLUENCE_BONUS if bearish_fvg_here else 0.0
                confidence -= 0.0 if not in_discount else OFF_DISCOUNT_PENALTY
                return AnalysisResult(
                    strategy=StrategyName.LIQUIDITY_SMC,
                    direction=Direction.SELL,
                    confidence=min(confidence, MAX_CONFIDENCE),
                    timeframe=timeframe,
                    reason=(
                        f"{timeframe.value} buy-side liquidity swept above {buy_side_level:.2f} "
                        "with bearish displacement"
                        + (", price sitting in a bearish FVG" if bearish_fvg_here else "")
                    ),
                    levels={"liquidity_level": buy_side_level},
                    metadata=metadata | {"event": "sweep_displacement"},
                )
            return AnalysisResult(
                strategy=StrategyName.LIQUIDITY_SMC,
                direction=Direction.SELL,
                confidence=SWEEP_ONLY_CONFIDENCE,
                timeframe=timeframe,
                reason=(
                    f"{timeframe.value} buy-side liquidity swept above {buy_side_level:.2f}, "
                    "awaiting displacement confirmation"
                ),
                levels={"liquidity_level": buy_side_level},
                metadata=metadata | {"event": "sweep_only"},
            )

    return neutral_result(
        StrategyName.LIQUIDITY_SMC,
        timeframe,
        f"{timeframe.value} no liquidity sweep detected at equal highs/lows",
        metadata=metadata,
    )
