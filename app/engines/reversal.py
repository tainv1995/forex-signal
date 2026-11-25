from dataclasses import dataclass
from typing import Literal

from app.core.enums import Direction
from app.engines.confluence import ConfluenceResult
from app.engines.signal import Signal

DEFAULT_INVALIDATION_FLOOR = 0.55
DEFAULT_REVERSAL_THRESHOLD = 0.82

ReversalAction = Literal["KEEP", "CLOSE", "REVERSE"]


@dataclass(frozen=True, slots=True)
class ReversalDecision:
    action: ReversalAction
    reason_lines: list[str]


def _own_and_opposite_scores(signal: Signal, confluence: ConfluenceResult) -> tuple[float, float]:
    if signal.direction is Direction.BUY:
        return confluence.buy_score, confluence.sell_score
    return confluence.sell_score, confluence.buy_score


def evaluate_signal_health(
    signal: Signal,
    confluence: ConfluenceResult,
    invalidation_floor: float = DEFAULT_INVALIDATION_FLOOR,
    reversal_threshold: float = DEFAULT_REVERSAL_THRESHOLD,
) -> ReversalDecision:
    """Re-checks a live signal against a freshly recomputed confluence.

    Never flips a signal on a single weak wobble (Section 29: "không đảo chiều chỉ vì
    1 cây M1 đỏ, RSI giảm, MACD cross nhỏ"). Two independent bars must clear before
    anything happens:
      1. the signal's OWN direction confidence has to have genuinely fallen
         (`invalidation_floor`) - that alone only justifies closing it (CLOSE);
      2. reversing outright additionally requires the confluence engine's own
         tie-breaking to have flipped to the opposite side *and* that opposite side
         to clear a high, separate `reversal_threshold` (Section 16/29's stronger bar).
    """
    own_score, opposite_score = _own_and_opposite_scores(signal, confluence)
    opposite_direction = Direction.SELL if signal.direction is Direction.BUY else Direction.BUY

    if own_score >= invalidation_floor:
        return ReversalDecision("KEEP", [])

    structure_flipped = confluence.is_tradeable and confluence.direction is opposite_direction

    if structure_flipped and opposite_score >= reversal_threshold:
        bias = "Bullish" if opposite_direction is Direction.BUY else "Bearish"
        return ReversalDecision(
            "REVERSE",
            [
                "Market Structure Invalidated",
                f"Strong {bias} Reversal Confirmed",
            ],
        )

    return ReversalDecision(
        "CLOSE",
        [
            "Market Structure Invalidated",
            f"{signal.direction.value} confidence dropped to {own_score:.0%}",
        ],
    )
