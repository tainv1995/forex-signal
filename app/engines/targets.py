from collections.abc import Sequence
from dataclasses import dataclass

from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName
from app.engines.risk import StopLoss, reward_to_risk

# TP1..TP5 expressed as R-multiples (risk = |entry - SL|) when no structural level is
# available nearby - conservative near-term target through a stretch target. Shape
# only - see rr_ladder_for() for why the actual values used in production are scaled
# by MIN_RR rather than this fixed tuple.
DEFAULT_RR_LADDER: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0)
# A structural level "fills" a rung only if it's within [80%, 130%] of that rung's
# R-multiple - a LOWER-bound-only check let a level far beyond a rung (e.g. 3.08R)
# get greedily claimed by the *first* rung it technically cleared (TP1 @ 1.0R),
# leaving every later rung with no candidates and forcing them into raw R-multiple
# projections that then got bunched up right after TP1 by the monotonic-order fix
# below - real incident: GOLD-20260903-001 (TP1 @ 3.08R, TP2-5 crammed within ~3
# points of it instead of spreading out to their own 1.5R/2.0R/3.0R/4.0R).
STRUCTURAL_MATCH_LOWER_TOLERANCE = 0.8
STRUCTURAL_MATCH_UPPER_TOLERANCE = 1.3
FIB_EXTENSION_KEYS = ("fib_ext_1.272", "fib_ext_1.618")
MIN_TICK = 0.01


def rr_ladder_for(min_rr: float) -> tuple[float, ...]:
    """Real incident (2026-09-08): with the fixed DEFAULT_RR_LADDER, TP1's rung
    (1.0R) combined with STRUCTURAL_MATCH_UPPER_TOLERANCE (1.3) meant TP1 could
    never legally reach above 1.3R - so with MIN_RR at its default 1.5, every single
    signal was silently rejected by meets_minimum_rr() at the final gate for 5 days
    straight (zero signals, not "the market was quiet"). Scaling the ladder by
    min_rr keeps TP1 at exactly min_rr (passes with equality) no matter what MIN_RR
    is configured to, instead of a fixed rung that can silently fall below it."""
    return tuple(min_rr * m for m in DEFAULT_RR_LADDER)


@dataclass(frozen=True, slots=True)
class TakeProfit:
    level: int
    price: float
    rr: float
    basis: str


def _structural_candidates(direction: Direction, results: Sequence[AnalysisResult]) -> list[float]:
    raw: list[float] = []
    for result in results:
        if result.strategy is StrategyName.SUPPORT_RESISTANCE:
            key = "resistance" if direction is Direction.BUY else "support"
            level = result.levels.get(key)
            if level is not None:
                raw.append(level)
        elif result.strategy is StrategyName.FIBONACCI:
            for key in FIB_EXTENSION_KEYS:
                level = result.levels.get(key)
                if level is not None:
                    raw.append(level)
        elif result.strategy is StrategyName.LIQUIDITY_SMC:
            level = result.levels.get("liquidity_level")
            if level is not None:
                raw.append(level)
    return raw


def _enforce_monotonic(prices: list[float], direction: Direction) -> list[float]:
    fixed = list(prices)
    for i in range(1, len(fixed)):
        if direction is Direction.BUY and fixed[i] <= fixed[i - 1]:
            fixed[i] = fixed[i - 1] + max(abs(fixed[i - 1]) * 0.0005, MIN_TICK)
        elif direction is Direction.SELL and fixed[i] >= fixed[i - 1]:
            fixed[i] = fixed[i - 1] - max(abs(fixed[i - 1]) * 0.0005, MIN_TICK)
    return fixed


def calculate_take_profits(
    direction: Direction,
    entry_reference: float,
    stop_loss: StopLoss,
    results: Sequence[AnalysisResult],
    rr_ladder: Sequence[float] = DEFAULT_RR_LADDER,
) -> list[TakeProfit] | None:
    """TP1 < TP2 < ... < TP5 for BUY (reverse for SELL), each preferring a genuine
    structural level (S/R, Fib extension, liquidity) over a raw ATR/R-multiple
    projection when one sits close enough to that rung (Section 20)."""
    if direction is Direction.NEUTRAL:
        return None

    risk = abs(entry_reference - stop_loss.price)
    if risk <= 0:
        return None

    raw_candidates = _structural_candidates(direction, results)
    if direction is Direction.BUY:
        candidates = sorted({c for c in raw_candidates if c > entry_reference})
    else:
        candidates = sorted({c for c in raw_candidates if c < entry_reference}, reverse=True)

    used: set[float] = set()
    chosen: list[tuple[float, str]] = []
    for index, ratio in enumerate(rr_ladder):
        projected = (
            entry_reference + ratio * risk
            if direction is Direction.BUY
            else entry_reference - ratio * risk
        )
        match: float | None = None
        for candidate in candidates:
            if candidate in used:
                continue
            reached_ratio = abs(candidate - entry_reference) / risk
            # TP1 (index 0) is the rung meets_minimum_rr() actually gates on - a
            # "structural" TP1 below the rung's own ratio (e.g. rr_ladder_for(min_rr)'s
            # exact min_rr) would pass the [80%, 130%] band meant for TP2..TP5 while
            # still failing the RR gate outright. Its lower bound is the ratio itself,
            # never 80% of it.
            lower = ratio if index == 0 else ratio * STRUCTURAL_MATCH_LOWER_TOLERANCE
            upper = ratio * STRUCTURAL_MATCH_UPPER_TOLERANCE
            if lower <= reached_ratio <= upper:
                match = candidate
                break
        if match is not None:
            used.add(match)
            chosen.append((match, "structural"))
        else:
            chosen.append((projected, "rr_projection"))

    prices = _enforce_monotonic([price for price, _ in chosen], direction)

    return [
        TakeProfit(
            level=i + 1,
            price=price,
            rr=reward_to_risk(entry_reference, stop_loss, price),
            basis=chosen[i][1],
        )
        for i, price in enumerate(prices)
    ]
