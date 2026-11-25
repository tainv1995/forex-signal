from collections.abc import Sequence

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import atr, candles_to_frame
from app.analysis.swings import Swing, confirmed_swings, find_swings
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

RETRACEMENT_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)
EXTENSION_RATIOS = (1.272, 1.618)
GOLDEN_ZONE = (0.5, 0.618)
GOLDEN_ZONE_CONFIDENCE = 0.68


def _last_alternating_leg(swings: Sequence[Swing]) -> tuple[Swing, Swing] | None:
    """The most recent swing-low -> swing-high (or reverse) pair, i.e. one clean leg.

    Two consecutive swings of the *same* kind (e.g. two highs in a row because the
    low between them wasn't confirmed) don't define a leg, so we walk back until we
    find an actual alternation.
    """
    ordered = sorted(swings, key=lambda s: s.index)
    for i in range(len(ordered) - 1, 0, -1):
        if ordered[i].kind != ordered[i - 1].kind:
            return ordered[i - 1], ordered[i]
    return None


def analyze_fibonacci(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    left: int = 2,
    right: int = 2,
    min_move_atr_mult: float = 3.0,
    golden_zone_atr_mult: float = 0.5,
) -> AnalysisResult:
    min_len = left + right + 30
    if len(candles) < min_len:
        return neutral_result(StrategyName.FIBONACCI, timeframe, "not enough candles for Fibonacci")

    df = candles_to_frame(candles)
    atr_series = atr(df, period=14).dropna()
    if atr_series.empty:
        return neutral_result(StrategyName.FIBONACCI, timeframe, "ATR unavailable")
    current_atr = float(atr_series.iloc[-1])

    swings = confirmed_swings(find_swings(candles, left=left, right=right))
    leg = _last_alternating_leg(swings)
    if leg is None:
        return neutral_result(
            StrategyName.FIBONACCI, timeframe, "no clean swing leg to draw Fibonacci from"
        )

    start, end = leg
    move_size = abs(end.price - start.price)
    if current_atr <= 0 or move_size < current_atr * min_move_atr_mult:
        return neutral_result(
            StrategyName.FIBONACCI,
            timeframe,
            "swing leg too small relative to ATR, not a meaningful Fibonacci",
            metadata={"move_size": move_size, "atr": current_atr},
        )

    is_up_move = end.price > start.price
    sign = -1 if is_up_move else 1  # retracement moves back down from a high, or up from a low

    def retracement(ratio: float) -> float:
        return end.price + sign * move_size * ratio

    def extension(ratio: float) -> float:
        return end.price - sign * move_size * (ratio - 1.0)

    levels = {
        f"fib_{ratio:.3f}".rstrip("0").rstrip("."): retracement(ratio)
        for ratio in RETRACEMENT_RATIOS
    }
    levels |= {
        f"fib_ext_{ratio:.3f}".rstrip("0").rstrip("."): extension(ratio)
        for ratio in EXTENSION_RATIOS
    }

    golden_low_ratio, golden_high_ratio = GOLDEN_ZONE
    golden_a, golden_b = retracement(golden_low_ratio), retracement(golden_high_ratio)
    golden_low, golden_high = min(golden_a, golden_b), max(golden_a, golden_b)
    proximity = current_atr * golden_zone_atr_mult

    current_price = float(candles[-1].close)
    metadata = {
        "leg_start": start.price,
        "leg_end": end.price,
        "leg_start_index": start.index,
        "leg_end_index": end.index,
        "move_size": move_size,
        "golden_zone_low": golden_low,
        "golden_zone_high": golden_high,
    }

    if golden_low - proximity <= current_price <= golden_high + proximity:
        direction = Direction.BUY if is_up_move else Direction.SELL
        return AnalysisResult(
            strategy=StrategyName.FIBONACCI,
            direction=direction,
            confidence=GOLDEN_ZONE_CONFIDENCE,
            timeframe=timeframe,
            reason=(
                f"{timeframe.value} price retraced into Fib golden zone "
                f"{golden_low:.2f}-{golden_high:.2f} of the {'up' if is_up_move else 'down'} leg "
                f"{start.price:.2f}->{end.price:.2f}"
            ),
            levels=levels,
            metadata=metadata,
        )

    return neutral_result(
        StrategyName.FIBONACCI,
        timeframe,
        f"{timeframe.value} price has not reached the Fib golden zone "
        f"{golden_low:.2f}-{golden_high:.2f} yet",
        metadata=metadata | {"levels": levels},
    )
