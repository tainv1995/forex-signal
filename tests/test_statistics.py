from datetime import UTC, datetime

from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, cancel, hit_target, stop_out
from app.engines.targets import TakeProfit
from app.reports.statistics import compute_statistics, outcome_of, realized_r

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _signal(
    signal_id: str, direction: Direction = Direction.BUY, confidence: float = 0.8
) -> Signal:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        signal_id,
        "XAUUSD",
        direction,
        4391.0,
        4393.0,
        StopLoss(4384.0, "t"),
        tps,
        confidence,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )


def _win_signal(levels_hit: int) -> Signal:
    signal = activate(_signal("GOLD-1"), NOW)
    for level in range(1, levels_hit + 1):
        signal = hit_target(signal, level, NOW)
    return signal


def _sl_signal() -> Signal:
    return stop_out(activate(_signal("GOLD-2"), NOW), NOW)


def _cancelled_signal() -> Signal:
    return cancel(_signal("GOLD-3"), NOW, reason="test")


def _stopped_after_partial_win() -> Signal:
    signal = activate(_signal("GOLD-4"), NOW)
    signal = hit_target(signal, 1, NOW)
    return stop_out(signal, NOW)


def test_outcome_and_realized_r_for_full_win() -> None:
    signal = _win_signal(5)

    assert outcome_of(signal) == "WIN"
    assert realized_r(signal) == 5.0


def test_outcome_and_realized_r_for_stop_loss() -> None:
    signal = _sl_signal()

    assert outcome_of(signal) == "SL"
    assert realized_r(signal) == -1.0


def test_outcome_and_realized_r_for_cancelled() -> None:
    signal = _cancelled_signal()

    assert outcome_of(signal) == "CANCELLED"
    assert realized_r(signal) is None


def test_partial_win_then_stopped_still_counts_as_win() -> None:
    # TP1 banked before the rest got stopped out - a real (partial) win, not a loss.
    signal = _stopped_after_partial_win()

    assert outcome_of(signal) == "WIN"
    assert realized_r(signal) == 1.0


def test_compute_statistics_aggregates_correctly() -> None:
    signals = [
        _win_signal(5),
        _sl_signal(),
        _cancelled_signal(),
        _stopped_after_partial_win(),
    ]

    stats = compute_statistics(signals)

    assert stats.total_signals == 4
    assert stats.win_count == 2  # full win + partial win
    assert stats.sl_count == 1
    assert stats.cancelled_count == 1
    assert stats.win_rate == 2 / 3  # win / (win + sl), cancelled excluded
    assert stats.tp_hit_counts[1] == 2  # both winners hit TP1
    assert stats.tp_hit_counts[5] == 1  # only the full winner reached TP5
    assert stats.average_rr is not None
    assert stats.best_signal is not None
    assert stats.best_signal.id == "GOLD-1"  # the 5R full winner


def test_compute_statistics_on_empty_list_does_not_crash() -> None:
    stats = compute_statistics([])

    assert stats.total_signals == 0
    assert stats.win_rate is None
    assert stats.average_confidence is None
    assert stats.average_rr is None
    assert stats.best_signal is None


def test_win_rate_is_none_when_no_decided_trades() -> None:
    stats = compute_statistics([_cancelled_signal()])

    assert stats.win_rate is None
