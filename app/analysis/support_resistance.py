from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import atr, candles_to_frame
from app.analysis.swings import Swing, cluster_by_price, confirmed_swings, find_swings
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

MIN_TOUCHES_FOR_ZONE = 2


@dataclass(frozen=True, slots=True)
class Zone:
    low: float
    high: float
    touches: int
    strength: float
    most_recent_index: int

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


def _round_number_bonus(price: float, step: float = 50.0, max_bonus: float = 0.08) -> float:
    nearest = round(price / step) * step
    distance = abs(price - nearest)
    return max(0.0, 1 - distance / (step / 5)) * max_bonus


def _build_zones(swings: Sequence[Swing], tolerance: float, total_candles: int) -> list[Zone]:
    zones: list[Zone] = []
    for cluster in cluster_by_price(swings, tolerance):
        if len(cluster) < MIN_TOUCHES_FOR_ZONE:
            continue
        low = min(s.price for s in cluster)
        high = max(s.price for s in cluster)
        most_recent_index = max(s.index for s in cluster)
        recency = most_recent_index / max(total_candles - 1, 1)
        touch_score = min(len(cluster) / 5, 1.0)
        strength = min(
            1.0, 0.4 * touch_score + 0.35 * recency + _round_number_bonus((low + high) / 2)
        )
        zones.append(
            Zone(
                low=low,
                high=high,
                touches=len(cluster),
                strength=strength,
                most_recent_index=most_recent_index,
            )
        )
    return zones


def analyze_support_resistance(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    left: int = 2,
    right: int = 2,
    cluster_atr_mult: float = 0.6,
    proximity_atr_mult: float = 0.35,
) -> AnalysisResult:
    min_len = left + right + 20
    if len(candles) < min_len:
        return neutral_result(
            StrategyName.SUPPORT_RESISTANCE, timeframe, "not enough candles to map S/R zones"
        )

    df = candles_to_frame(candles)
    atr_series = atr(df, period=14).dropna()
    if atr_series.empty:
        return neutral_result(
            StrategyName.SUPPORT_RESISTANCE, timeframe, "ATR unavailable, cannot size S/R zones"
        )
    current_atr = float(atr_series.iloc[-1])
    if current_atr <= 0:
        return neutral_result(
            StrategyName.SUPPORT_RESISTANCE, timeframe, "zero volatility, cannot map S/R zones"
        )

    swings = confirmed_swings(find_swings(candles, left=left, right=right))
    zones = _build_zones(
        swings, tolerance=current_atr * cluster_atr_mult, total_candles=len(candles)
    )
    if not zones:
        return neutral_result(
            StrategyName.SUPPORT_RESISTANCE,
            timeframe,
            "no repeated-touch zone found (no naive single-swing S/R)",
        )

    current_price = candles[-1].close
    proximity = current_atr * proximity_atr_mult

    below = [z for z in zones if z.high <= current_price]
    above = [z for z in zones if z.low >= current_price]
    nearest_support = max(below, key=lambda z: z.high) if below else None
    nearest_resistance = min(above, key=lambda z: z.low) if above else None

    levels: dict[str, float] = {}
    if nearest_support:
        levels["support"] = nearest_support.mid
    if nearest_resistance:
        levels["resistance"] = nearest_resistance.mid

    metadata = {
        "zone_count": len(zones),
        "atr": current_atr,
        "nearest_support_strength": nearest_support.strength if nearest_support else None,
        "nearest_resistance_strength": nearest_resistance.strength if nearest_resistance else None,
    }

    if nearest_support and current_price - nearest_support.high <= proximity:
        confidence = round(0.55 + 0.35 * nearest_support.strength, 2)
        return AnalysisResult(
            strategy=StrategyName.SUPPORT_RESISTANCE,
            direction=Direction.BUY,
            confidence=min(confidence, 0.9),
            timeframe=timeframe,
            reason=(
                f"{timeframe.value} price reacting at support zone "
                f"{nearest_support.low:.2f}-{nearest_support.high:.2f} "
                f"({nearest_support.touches} touches)"
            ),
            levels=levels,
            metadata=metadata,
        )

    if nearest_resistance and nearest_resistance.low - current_price <= proximity:
        confidence = round(0.55 + 0.35 * nearest_resistance.strength, 2)
        return AnalysisResult(
            strategy=StrategyName.SUPPORT_RESISTANCE,
            direction=Direction.SELL,
            confidence=min(confidence, 0.9),
            timeframe=timeframe,
            reason=(
                f"{timeframe.value} price reacting at resistance zone "
                f"{nearest_resistance.low:.2f}-{nearest_resistance.high:.2f} "
                f"({nearest_resistance.touches} touches)"
            ),
            levels=levels,
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.SUPPORT_RESISTANCE,
        timeframe,
        f"{timeframe.value} price is between zones, no immediate S/R reaction",
        metadata=metadata,
    )
