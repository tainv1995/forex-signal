from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.core.enums import Direction, SignalStatus
from app.engines.signal import Signal

Outcome = Literal["WIN", "SL", "CANCELLED"]

CANCEL_LIKE_STATUSES = frozenset(
    {
        SignalStatus.CANCELLED,
        SignalStatus.INVALIDATED,
        SignalStatus.REVERSED,
        SignalStatus.EXPIRED,
        SignalStatus.MISSED_ENTRY,
    }
)


def realized_r(signal: Signal) -> float | None:
    """R actually achieved, or None if the signal never became a decided trade (no
    fill, or invalidated/reversed before any TP or SL - we don't fabricate a result
    for a trade that was never actually filled or never resolved)."""
    hit_targets = [t for t in signal.targets if t.hit]
    if hit_targets:
        return max(hit_targets, key=lambda t: t.level).rr
    if signal.status is SignalStatus.STOPPED:
        return -1.0
    return None


def outcome_of(signal: Signal) -> Outcome:
    if any(t.hit for t in signal.targets):
        return "WIN"
    if signal.status is SignalStatus.STOPPED:
        return "SL"
    return "CANCELLED"


@dataclass(frozen=True, slots=True)
class SignalStatistics:
    total_signals: int
    buy_count: int
    sell_count: int
    win_count: int
    sl_count: int
    cancelled_count: int
    win_rate: float | None
    tp_hit_counts: dict[int, int] = field(default_factory=dict)
    average_confidence: float | None = None
    average_rr: float | None = None
    best_signal: Signal | None = None


def compute_statistics(signals: Sequence[Signal]) -> SignalStatistics:
    total = len(signals)
    buy_count = sum(1 for s in signals if s.direction is Direction.BUY)
    sell_count = sum(1 for s in signals if s.direction is Direction.SELL)

    outcomes = Counter(outcome_of(s) for s in signals)
    win_count = outcomes["WIN"]
    sl_count = outcomes["SL"]
    cancelled_count = outcomes["CANCELLED"]

    decided = win_count + sl_count
    win_rate = win_count / decided if decided > 0 else None

    tp_hit_counts = {
        level: sum(1 for s in signals if any(t.level == level and t.hit for t in s.targets))
        for level in range(1, 6)
    }

    average_confidence = sum(s.confidence for s in signals) / total if total > 0 else None

    realized = [r for s in signals for r in [realized_r(s)] if r is not None]
    average_rr = sum(realized) / len(realized) if realized else None

    best_signal = None
    best_r = float("-inf")
    for signal in signals:
        r = realized_r(signal)
        if r is not None and r > best_r:
            best_r = r
            best_signal = signal

    return SignalStatistics(
        total_signals=total,
        buy_count=buy_count,
        sell_count=sell_count,
        win_count=win_count,
        sl_count=sl_count,
        cancelled_count=cancelled_count,
        win_rate=win_rate,
        tp_hit_counts=tp_hit_counts,
        average_confidence=average_confidence,
        average_rr=average_rr,
        best_signal=best_signal,
    )
