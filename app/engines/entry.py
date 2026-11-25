from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName

ZONE_WIDTH_ATR_MULT = 0.15
MAX_CHASE_ATR_MULT = 2.0

# Which AnalysisResult.levels key to pull an entry candidate from, per method, and
# what to call it in the report. Order doesn't matter - all candidates are pooled and
# the nearest reachable one wins.
_BUY_LEVEL_SOURCES: tuple[tuple[StrategyName, str, str], ...] = (
    (StrategyName.SUPPORT_RESISTANCE, "support", "support_zone"),
    (StrategyName.EMA_TREND, "ema20", "ema_pullback"),
    (StrategyName.VOLATILITY, "bollinger_lower", "bollinger_band"),
    (StrategyName.LIQUIDITY_SMC, "liquidity_level", "liquidity_sweep"),
)
_SELL_LEVEL_SOURCES: tuple[tuple[StrategyName, str, str], ...] = (
    (StrategyName.SUPPORT_RESISTANCE, "resistance", "support_zone"),
    (StrategyName.EMA_TREND, "ema20", "ema_pullback"),
    (StrategyName.VOLATILITY, "bollinger_upper", "bollinger_band"),
    (StrategyName.LIQUIDITY_SMC, "liquidity_level", "liquidity_sweep"),
)


@dataclass(frozen=True, slots=True)
class EntryZone:
    low: float
    high: float
    basis: str
    reachable: bool

    @property
    def mid(self) -> float:
        return (self.low + self.high) / 2


def _golden_zone_candidate(results: Sequence[AnalysisResult]) -> tuple[float, str] | None:
    for result in results:
        if result.strategy is not StrategyName.FIBONACCI:
            continue
        low, high = result.levels.get("fib_0.5"), result.levels.get("fib_0.618")
        if low is not None and high is not None:
            return (low + high) / 2, "fib_golden_zone"
    return None


def find_entry_zone(
    direction: Direction,
    current_price: float,
    results: Sequence[AnalysisResult],
    atr_value: float,
    zone_width_atr_mult: float = ZONE_WIDTH_ATR_MULT,
    max_chase_atr_mult: float = MAX_CHASE_ATR_MULT,
) -> EntryZone | None:
    """Never signal an entry at the already-run current price (Section 18) - find the
    nearest pullback level (S/R, Fib golden zone, EMA, Bollinger, liquidity level) and
    build a zone around it instead."""
    if direction is Direction.NEUTRAL or atr_value <= 0:
        return None

    by_strategy = {r.strategy: r for r in results}
    sources = _BUY_LEVEL_SOURCES if direction is Direction.BUY else _SELL_LEVEL_SOURCES

    candidates: list[tuple[float, str]] = []
    for strategy, key, basis in sources:
        result = by_strategy.get(strategy)
        if result is None:
            continue
        level = result.levels.get(key)
        if level is not None:
            candidates.append((level, basis))

    golden = _golden_zone_candidate(results)
    if golden is not None:
        candidates.append(golden)

    if not candidates:
        return None

    if direction is Direction.BUY:
        on_side = [c for c in candidates if c[0] <= current_price]
        level, basis = (
            max(on_side, key=lambda c: c[0]) if on_side else min(candidates, key=lambda c: c[0])
        )
    else:
        on_side = [c for c in candidates if c[0] >= current_price]
        level, basis = (
            min(on_side, key=lambda c: c[0]) if on_side else max(candidates, key=lambda c: c[0])
        )

    zone_width = atr_value * zone_width_atr_mult
    distance = abs(current_price - level)
    reachable = distance <= atr_value * max_chase_atr_mult

    return EntryZone(
        low=level - zone_width, high=level + zone_width, basis=basis, reachable=reachable
    )
