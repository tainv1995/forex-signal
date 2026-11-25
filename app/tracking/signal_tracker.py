from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.enums import Direction, SignalStatus
from app.engines.signal import Signal, activate, expire, hit_target, mark_missed_entry, stop_out

DEFAULT_MAX_CHASE_ATR_MULT = 2.0
DEFAULT_EXPIRY_MINUTES = 120


@dataclass(frozen=True, slots=True)
class TrackingStep:
    """One state transition the tracker wants applied, in order. The tracker never
    applies these itself - the caller persists each one (via
    SignalRepository.apply_transition, keyed on the *previous* status) and only
    notifies Telegram for the ones that actually won the race (Section 51).

    `tp_level` is set when this step is a TP hit, so the caller doesn't have to
    parse it back out of the status string."""

    previous_status: SignalStatus
    signal: Signal
    tp_level: int | None = None


def distance_from_entry_zone(signal: Signal, current_price: float) -> float:
    if current_price < signal.entry_low:
        return signal.entry_low - current_price
    if current_price > signal.entry_high:
        return current_price - signal.entry_high
    return 0.0


def evaluate_waiting_entry(
    signal: Signal,
    current_price: float,
    now: datetime,
    atr_value: float,
    max_chase_atr_mult: float = DEFAULT_MAX_CHASE_ATR_MULT,
    expiry_minutes: int = DEFAULT_EXPIRY_MINUTES,
) -> TrackingStep | None:
    """A WAITING_ENTRY signal can: touch its zone (-> ACTIVE), run away without ever
    touching it (-> MISSED_ENTRY), or simply time out (-> EXPIRED, Section 32)."""
    if signal.status is not SignalStatus.WAITING_ENTRY:
        return None

    if signal.entry_low <= current_price <= signal.entry_high:
        return TrackingStep(signal.status, activate(signal, now))

    if atr_value > 0:
        distance = distance_from_entry_zone(signal, current_price)
        if distance > atr_value * max_chase_atr_mult:
            return TrackingStep(signal.status, mark_missed_entry(signal, now))

    if now - signal.created_at > timedelta(minutes=expiry_minutes):
        return TrackingStep(signal.status, expire(signal, now))

    return None


def evaluate_active_signal(
    signal: Signal, current_price: float, now: datetime
) -> list[TrackingStep]:
    """A live signal can be stopped out, or clear one or more TP levels. A single
    fast price jump can clear several targets at once (Section 25: 4394 -> 4400
    jumping straight through TP1/TP2/TP3) - every level it actually reached must be
    recorded, in order, not just the furthest one."""
    if signal.next_target is None:
        return []

    hit_sl = (signal.direction is Direction.BUY and current_price <= signal.stop_loss) or (
        signal.direction is Direction.SELL and current_price >= signal.stop_loss
    )
    if hit_sl:
        return [TrackingStep(signal.status, stop_out(signal, now))]

    steps: list[TrackingStep] = []
    current = signal
    while current.next_target is not None:
        target = current.next_target
        reached = (
            current_price >= target.price
            if current.direction is Direction.BUY
            else current_price <= target.price
        )
        if not reached:
            break
        previous_status = current.status
        current = hit_target(current, target.level, now)
        steps.append(TrackingStep(previous_status, current, tp_level=target.level))

    return steps
