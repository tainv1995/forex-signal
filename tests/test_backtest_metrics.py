from datetime import UTC, datetime, timedelta

from app.backtest.metrics import max_consecutive_losses, summarize_backtest
from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, cancel, hit_target, stop_out
from app.engines.targets import TakeProfit

BASE = datetime(2026, 8, 1, tzinfo=UTC)


def _signal(signal_id: str, created_at: datetime) -> Signal:
    tps = [TakeProfit(i, 4391.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        signal_id,
        "XAUUSD",
        Direction.BUY,
        4389.0,
        4391.0,
        StopLoss(4384.0, "t"),
        tps,
        0.8,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        created_at,
    )


def _win(signal_id: str, created_at: datetime, levels: int = 1) -> Signal:
    signal = activate(_signal(signal_id, created_at), created_at)
    for level in range(1, levels + 1):
        signal = hit_target(signal, level, created_at)
    return signal


def _loss(signal_id: str, created_at: datetime) -> Signal:
    return stop_out(activate(_signal(signal_id, created_at), created_at), created_at)


def test_max_consecutive_losses_counts_the_longest_streak() -> None:
    signals = [
        _win("S1", BASE),
        _loss("S2", BASE + timedelta(hours=1)),
        _loss("S3", BASE + timedelta(hours=2)),
        _loss("S4", BASE + timedelta(hours=3)),
        _win("S5", BASE + timedelta(hours=4)),
        _loss("S6", BASE + timedelta(hours=5)),
    ]

    assert max_consecutive_losses(signals) == 3


def test_max_consecutive_losses_is_zero_with_no_losses() -> None:
    signals = [_win("S1", BASE), _win("S2", BASE + timedelta(hours=1))]

    assert max_consecutive_losses(signals) == 0


def test_cancelled_signal_does_not_break_a_loss_streak() -> None:
    signals = [
        _loss("S1", BASE),
        cancel(_signal("S2", BASE + timedelta(hours=1)), BASE + timedelta(hours=1), "test"),
        _loss("S3", BASE + timedelta(hours=2)),
    ]

    # A cancelled signal (no trade taken) doesn't reset the streak either way.
    assert max_consecutive_losses(signals) == 2


def test_summarize_backtest_computes_rates_and_expectancy() -> None:
    signals = [
        _win("S1", BASE, levels=5),  # +5R
        _win("S2", BASE + timedelta(hours=1), levels=1),  # +1R
        _loss("S3", BASE + timedelta(hours=2)),  # -1R
        cancel(_signal("S4", BASE + timedelta(hours=3)), BASE + timedelta(hours=3), "test"),
    ]

    result = summarize_backtest(signals, days_covered=2.0)

    assert result.stats.total_signals == 4
    assert result.sl_rate == 1 / 4
    assert result.tp_hit_rates[1] == 2 / 4
    assert result.tp_hit_rates[5] == 1 / 4
    # win_rate = 2/3, avg_win_r = (5+1)/2 = 3.0, loss_rate = 1/3
    # expectancy = 2/3*3.0 - 1/3*1.0
    assert result.expectancy is not None
    assert round(result.expectancy, 4) == round(2 / 3 * 3.0 - 1 / 3 * 1.0, 4)
    assert result.signals_per_day == 2.0
    assert result.max_consecutive_losses == 1


def test_summarize_backtest_on_empty_signals() -> None:
    result = summarize_backtest([], days_covered=5.0)

    assert result.stats.total_signals == 0
    assert result.sl_rate is None
    assert result.expectancy is None
    assert result.signals_per_day == 0.0
