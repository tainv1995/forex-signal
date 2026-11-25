from datetime import UTC, date, datetime

import pytest

from app.core.enums import Direction, SignalEventType, SignalStatus, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import (
    InvalidTransitionError,
    Signal,
    activate,
    build_signal,
    cancel,
    expire,
    format_signal_id,
    hit_target,
    invalidate,
    mark_missed_entry,
    reverse,
    set_telegram_message_id,
    stop_out,
)
from app.engines.targets import TakeProfit

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _take_profits() -> list[TakeProfit]:
    return [
        TakeProfit(level=i, price=4390.0 + i * 2, rr=float(i), basis="test") for i in range(1, 6)
    ]


def _new_signal() -> Signal:
    return build_signal(
        signal_id="GOLD-20260817-001",
        symbol="XAUUSD",
        direction=Direction.BUY,
        entry_low=4391.0,
        entry_high=4393.0,
        stop_loss=StopLoss(price=4384.0, basis="test"),
        take_profits=_take_profits(),
        confidence=0.86,
        confluence_tier=SignalTier.STRONG,
        agreement=8,
        reasons=["[market_structure] bullish BOS"],
        timeframe="M15",
        created_at=NOW,
    )


def test_format_signal_id() -> None:
    assert format_signal_id("GOLD", date(2026, 8, 17), 1) == "GOLD-20260817-001"
    assert format_signal_id("GOLD", date(2026, 8, 17), 42) == "GOLD-20260817-042"


def test_build_signal_starts_waiting_entry_with_created_event() -> None:
    signal = _new_signal()

    assert signal.status == SignalStatus.WAITING_ENTRY
    assert signal.stop_loss == 4384.0
    assert len(signal.targets) == 5
    assert signal.events[-1] == (SignalEventType.SIGNAL_CREATED, NOW)
    assert signal.next_target is None  # not ACTIVE yet


def test_build_signal_rejects_neutral_direction() -> None:
    with pytest.raises(ValueError, match="NEUTRAL"):
        build_signal(
            "GOLD-20260817-001",
            "XAUUSD",
            Direction.NEUTRAL,
            4391.0,
            4393.0,
            StopLoss(4384.0, "test"),
            _take_profits(),
            0.8,
            SignalTier.VALID,
            6,
            [],
            "M15",
            NOW,
        )


def test_build_signal_requires_exactly_five_take_profits() -> None:
    with pytest.raises(ValueError, match="5"):
        build_signal(
            "GOLD-20260817-001",
            "XAUUSD",
            Direction.BUY,
            4391.0,
            4393.0,
            StopLoss(4384.0, "test"),
            _take_profits()[:3],
            0.8,
            SignalTier.VALID,
            6,
            [],
            "M15",
            NOW,
        )


def test_activate_moves_waiting_entry_to_active() -> None:
    signal = _new_signal()
    at = NOW.replace(minute=5)

    activated = activate(signal, at)

    assert activated.status == SignalStatus.ACTIVE
    assert activated.activated_at == at
    assert activated.next_target is not None
    assert activated.next_target.level == 1
    assert activated.events[-1] == (SignalEventType.ENTRY_TOUCHED, at)


def test_activate_twice_raises() -> None:
    signal = activate(_new_signal(), NOW)

    with pytest.raises(InvalidTransitionError):
        activate(signal, NOW)


def test_targets_must_be_hit_in_sequence() -> None:
    signal = activate(_new_signal(), NOW)

    with pytest.raises(InvalidTransitionError, match="expected TP1"):
        hit_target(signal, level=2, at=NOW)


def test_full_tp_sequence_reaches_terminal_tp5() -> None:
    signal = activate(_new_signal(), NOW)

    for level in range(1, 6):
        signal = hit_target(signal, level=level, at=NOW)
        assert signal.status == SignalStatus(f"TP{level}_HIT")
        hit = next(t for t in signal.targets if t.level == level)
        assert hit.hit is True
        assert hit.hit_at == NOW

    assert signal.is_terminal
    assert signal.closed_at == NOW
    assert signal.next_target is None


def test_cannot_hit_target_after_terminal() -> None:
    signal = activate(_new_signal(), NOW)
    for level in range(1, 6):
        signal = hit_target(signal, level=level, at=NOW)

    with pytest.raises(InvalidTransitionError):
        hit_target(signal, level=5, at=NOW)


def test_stop_out_from_active() -> None:
    signal = activate(_new_signal(), NOW)

    stopped = stop_out(signal, NOW)

    assert stopped.status == SignalStatus.STOPPED
    assert stopped.is_terminal
    assert stopped.closed_at == NOW
    assert stopped.events[-1] == (SignalEventType.SL_HIT, NOW)


def test_stop_out_after_partial_tp_hits() -> None:
    signal = activate(_new_signal(), NOW)
    signal = hit_target(signal, level=1, at=NOW)
    signal = hit_target(signal, level=2, at=NOW)

    stopped = stop_out(signal, NOW)

    assert stopped.status == SignalStatus.STOPPED
    assert stopped.targets[0].hit is True  # TP1/TP2 gains are not erased


def test_stop_out_before_activation_raises() -> None:
    with pytest.raises(InvalidTransitionError):
        stop_out(_new_signal(), NOW)


def test_cancel_before_entry_touched() -> None:
    signal = _new_signal()

    cancelled = cancel(signal, NOW, reason="structure invalidated")

    assert cancelled.status == SignalStatus.CANCELLED
    assert cancelled.invalidation_reason == "structure invalidated"


def test_cancel_after_activation_raises() -> None:
    signal = activate(_new_signal(), NOW)

    with pytest.raises(InvalidTransitionError):
        cancel(signal, NOW, reason="too late")


def test_invalidate_works_while_active() -> None:
    signal = activate(_new_signal(), NOW)

    invalidated = invalidate(signal, NOW, reason="bearish CHoCH")

    assert invalidated.status == SignalStatus.INVALIDATED
    assert invalidated.is_terminal


def test_invalidate_after_terminal_raises() -> None:
    signal = stop_out(activate(_new_signal(), NOW), NOW)

    with pytest.raises(InvalidTransitionError):
        invalidate(signal, NOW, reason="too late")


def test_reverse_works_while_active() -> None:
    signal = activate(_new_signal(), NOW)

    reversed_signal = reverse(signal, NOW, reason="strong opposite confluence")

    assert reversed_signal.status == SignalStatus.REVERSED
    assert reversed_signal.is_terminal


def test_expire_only_from_waiting_entry() -> None:
    signal = _new_signal()

    expired = expire(signal, NOW)

    assert expired.status == SignalStatus.EXPIRED
    with pytest.raises(InvalidTransitionError):
        expire(activate(_new_signal(), NOW), NOW)


def test_mark_missed_entry_only_from_waiting_entry() -> None:
    signal = _new_signal()

    missed = mark_missed_entry(signal, NOW)

    assert missed.status == SignalStatus.MISSED_ENTRY
    with pytest.raises(InvalidTransitionError):
        mark_missed_entry(activate(_new_signal(), NOW), NOW)


def test_set_telegram_message_id() -> None:
    signal = set_telegram_message_id(_new_signal(), 12345)

    assert signal.telegram_message_id == 12345
