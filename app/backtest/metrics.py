from collections.abc import Sequence
from dataclasses import dataclass

from app.engines.signal import Signal
from app.reports.statistics import SignalStatistics, compute_statistics, outcome_of


@dataclass(frozen=True, slots=True)
class BacktestResult:
    stats: SignalStatistics
    sl_rate: float | None
    tp_hit_rates: dict[int, float]
    expectancy: float | None
    max_consecutive_losses: int
    signals_per_day: float
    signals: list[Signal]


def max_consecutive_losses(signals: Sequence[Signal]) -> int:
    """Longest streak of SL outcomes in chronological order. A cancelled/expired
    signal (no trade actually taken) neither extends nor breaks a streak."""
    streak = 0
    worst = 0
    for signal in sorted(signals, key=lambda s: s.created_at):
        outcome = outcome_of(signal)
        if outcome == "SL":
            streak += 1
            worst = max(worst, streak)
        elif outcome == "WIN":
            streak = 0
    return worst


def summarize_backtest(signals: Sequence[Signal], days_covered: float) -> BacktestResult:
    stats = compute_statistics(signals)
    total = stats.total_signals

    sl_rate = stats.sl_count / total if total > 0 else None
    tp_hit_rates = {
        level: count / total if total > 0 else 0.0 for level, count in stats.tp_hit_counts.items()
    }

    # Expectancy = win_rate * avg_win_R - loss_rate * avg_loss_R (avg_loss_R is
    # always 1R by construction - SL is always exactly -1R).
    expectancy = None
    if stats.win_rate is not None:
        win_rs = [
            r
            for s in signals
            if outcome_of(s) == "WIN"
            for r in [max(t.rr for t in s.targets if t.hit)]
        ]
        avg_win_r = sum(win_rs) / len(win_rs) if win_rs else 0.0
        loss_rate = 1 - stats.win_rate
        expectancy = stats.win_rate * avg_win_r - loss_rate * 1.0

    signals_per_day = total / days_covered if days_covered > 0 else 0.0

    return BacktestResult(
        stats=stats,
        sl_rate=sl_rate,
        tp_hit_rates=tp_hit_rates,
        expectancy=expectancy,
        max_consecutive_losses=max_consecutive_losses(signals),
        signals_per_day=signals_per_day,
        signals=list(signals),
    )
