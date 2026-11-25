from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName

SL_BUFFER_ATR_MULT = 0.25
# If the nearest genuine invalidation point sits this close to entry (or closer),
# the resulting risk is too thin to be a meaningful stop - real noise would clip it
# almost immediately regardless of what the R:R math says. Reject rather than widen
# the stop artificially (Section 19: never invent an arbitrary distance).
MIN_SL_ATR_MULT = 0.5


@dataclass(frozen=True, slots=True)
class StopLoss:
    price: float
    basis: str


def _invalidation_candidates(
    direction: Direction, results: Sequence[AnalysisResult]
) -> list[tuple[float, str]]:
    candidates: list[tuple[float, str]] = []
    for result in results:
        if result.strategy is StrategyName.MARKET_STRUCTURE:
            key = "swing_low" if direction is Direction.BUY else "swing_high"
            level = result.levels.get(key)
            if level is not None:
                candidates.append((level, "market_structure_swing"))
        elif result.strategy is StrategyName.LIQUIDITY_SMC:
            level = result.levels.get("liquidity_level")
            if level is not None:
                candidates.append((level, "liquidity_level"))
        elif result.strategy is StrategyName.SUPPORT_RESISTANCE:
            key = "support" if direction is Direction.BUY else "resistance"
            level = result.levels.get(key)
            if level is not None:
                candidates.append((level, "support_resistance_zone"))
    return candidates


def calculate_stop_loss(
    direction: Direction,
    entry_reference: float,
    results: Sequence[AnalysisResult],
    atr_value: float,
    buffer_atr_mult: float = SL_BUFFER_ATR_MULT,
) -> StopLoss | None:
    """SL sits beyond the nearest genuine invalidation point (Section 19), never
    picked just to make the R:R look good. If structure gives nothing usable, we
    return None rather than inventing an arbitrary distance."""
    if direction is Direction.NEUTRAL or atr_value <= 0:
        return None

    candidates = _invalidation_candidates(direction, results)
    if not candidates:
        return None

    buffer = atr_value * buffer_atr_mult
    if direction is Direction.BUY:
        below = [c for c in candidates if c[0] < entry_reference]
        level, basis = (
            max(below, key=lambda c: c[0]) if below else min(candidates, key=lambda c: c[0])
        )
        price = level - buffer
    else:
        above = [c for c in candidates if c[0] > entry_reference]
        level, basis = (
            min(above, key=lambda c: c[0]) if above else max(candidates, key=lambda c: c[0])
        )
        price = level + buffer

    # Real incident (GOLD-20260909-001): when no candidate sits on the correct side
    # of entry, the fallback above picks the "least bad" of what's left - which can
    # still land on the WRONG side of entry (a "stop loss" that's actually in the
    # profit direction) if the buffer isn't enough to cross back over. A stop on the
    # wrong side is never usable, no matter its distance - reject outright rather
    # than let MIN_SL_ATR_MULT's distance-only check wave it through.
    wrong_side = (direction is Direction.BUY and price >= entry_reference) or (
        direction is Direction.SELL and price <= entry_reference
    )
    if wrong_side:
        return None

    if abs(entry_reference - price) < atr_value * MIN_SL_ATR_MULT:
        return None

    return StopLoss(price=price, basis=basis)


def risk_distance(entry_reference: float, stop_loss: StopLoss) -> float:
    return abs(entry_reference - stop_loss.price)


def reward_to_risk(entry_reference: float, stop_loss: StopLoss, target_price: float) -> float:
    risk = risk_distance(entry_reference, stop_loss)
    if risk <= 0:
        return 0.0
    return abs(target_price - entry_reference) / risk


def meets_minimum_rr(rr: float, min_rr: float = 1.5) -> bool:
    return rr >= min_rr
