from datetime import UTC, datetime, timedelta

from app.core.enums import Direction, SignalStatus, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal
from app.engines.targets import TakeProfit
from app.tracking.signal_tracker import evaluate_active_signal, evaluate_waiting_entry

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _buy_signal(created_at: datetime = NOW) -> Signal:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        "GOLD-20260817-001",
        "XAUUSD",
        Direction.BUY,
        4391.0,
        4393.0,
        StopLoss(4384.0, "t"),
        tps,
        0.86,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        created_at,
    )


def _sell_signal(created_at: datetime = NOW) -> Signal:
    # entry 4405-4407, SL above at 4414, TPs falling below the zone: 4403/4401/4399/4397/4395
    tps = [TakeProfit(i, 4405.0 - i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        "GOLD-20260817-002",
        "XAUUSD",
        Direction.SELL,
        4405.0,
        4407.0,
        StopLoss(4414.0, "t"),
        tps,
        0.85,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        created_at,
    )


# --- evaluate_waiting_entry ---------------------------------------------------


def test_price_inside_entry_zone_activates() -> None:
    step = evaluate_waiting_entry(_buy_signal(), current_price=4392.0, now=NOW, atr_value=2.0)

    assert step is not None
    assert step.previous_status == SignalStatus.WAITING_ENTRY
    assert step.signal.status == SignalStatus.ACTIVE


def test_price_far_outside_zone_marks_missed_entry() -> None:
    step = evaluate_waiting_entry(
        _buy_signal(), current_price=4400.0, now=NOW, atr_value=2.0, max_chase_atr_mult=2.0
    )

    assert step is not None
    assert step.signal.status == SignalStatus.MISSED_ENTRY


def test_price_slightly_outside_zone_within_chase_distance_keeps_waiting() -> None:
    step = evaluate_waiting_entry(
        _buy_signal(), current_price=4394.0, now=NOW, atr_value=2.0, max_chase_atr_mult=2.0
    )

    assert step is None


def test_expires_after_time_budget_even_if_price_never_ran_away() -> None:
    created_at = NOW - timedelta(minutes=200)
    step = evaluate_waiting_entry(
        _buy_signal(created_at),
        current_price=4394.0,
        now=NOW,
        atr_value=2.0,
        max_chase_atr_mult=2.0,
        expiry_minutes=120,
    )

    assert step is not None
    assert step.signal.status == SignalStatus.EXPIRED


def test_no_action_for_a_signal_that_is_not_waiting_entry() -> None:
    signal = activate(_buy_signal(), NOW)

    step = evaluate_waiting_entry(signal, current_price=4392.0, now=NOW, atr_value=2.0)

    assert step is None


# --- evaluate_active_signal ----------------------------------------------------


def test_stop_loss_hit_returns_single_stopped_step() -> None:
    signal = activate(_buy_signal(), NOW)

    steps = evaluate_active_signal(signal, current_price=4383.0, now=NOW)

    assert len(steps) == 1
    assert steps[0].previous_status == SignalStatus.ACTIVE
    assert steps[0].signal.status == SignalStatus.STOPPED


def test_single_tp1_hit() -> None:
    signal = activate(_buy_signal(), NOW)

    steps = evaluate_active_signal(signal, current_price=4396.0, now=NOW)

    assert len(steps) == 1
    assert steps[0].signal.status == SignalStatus.TP1_HIT


def test_price_jump_clears_multiple_targets_in_one_pass() -> None:
    # entry ~4392, TP1=4395, TP2=4397, TP3=4399, TP4=4401, TP5=4403
    signal = activate(_buy_signal(), NOW)

    steps = evaluate_active_signal(signal, current_price=4400.0, now=NOW)

    assert [s.signal.status for s in steps] == [
        SignalStatus.TP1_HIT,
        SignalStatus.TP2_HIT,
        SignalStatus.TP3_HIT,
    ]
    # each step's previous_status chains from the one before it
    assert steps[0].previous_status == SignalStatus.ACTIVE
    assert steps[1].previous_status == SignalStatus.TP1_HIT
    assert steps[2].previous_status == SignalStatus.TP2_HIT


def test_price_jump_all_the_way_to_tp5_closes_the_signal() -> None:
    signal = activate(_buy_signal(), NOW)

    steps = evaluate_active_signal(signal, current_price=4410.0, now=NOW)

    assert len(steps) == 5
    assert steps[-1].signal.status == SignalStatus.TP5_HIT
    assert steps[-1].signal.is_terminal


def test_no_targets_reached_yields_no_steps() -> None:
    signal = activate(_buy_signal(), NOW)

    steps = evaluate_active_signal(signal, current_price=4392.5, now=NOW)

    assert steps == []


def test_terminal_signal_yields_no_steps() -> None:
    signal = activate(_buy_signal(), NOW)
    steps = evaluate_active_signal(signal, current_price=4410.0, now=NOW)
    terminal_signal = steps[-1].signal

    assert evaluate_active_signal(terminal_signal, current_price=4420.0, now=NOW) == []


def test_sell_signal_stop_loss_and_targets_work_symmetrically() -> None:
    signal = activate(_sell_signal(), NOW)

    sl_steps = evaluate_active_signal(signal, current_price=4415.0, now=NOW)
    assert sl_steps[0].signal.status == SignalStatus.STOPPED

    tp_steps = evaluate_active_signal(signal, current_price=4398.0, now=NOW)
    assert [s.signal.status for s in tp_steps] == [
        SignalStatus.TP1_HIT,
        SignalStatus.TP2_HIT,
        SignalStatus.TP3_HIT,
    ]
