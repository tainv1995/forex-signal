from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from app.core.enums import Direction, SignalEventType, SignalStatus, SignalTier
from app.engines.risk import StopLoss
from app.engines.targets import TakeProfit

# Statuses a signal can never leave once reached.
TERMINAL_STATUSES = frozenset(
    {
        SignalStatus.TP5_HIT,
        SignalStatus.STOPPED,
        SignalStatus.CANCELLED,
        SignalStatus.INVALIDATED,
        SignalStatus.REVERSED,
        SignalStatus.EXPIRED,
        SignalStatus.MISSED_ENTRY,
    }
)

# Which TP level a signal currently sitting in `status` is waiting for next.
_NEXT_TARGET_LEVEL: dict[SignalStatus, int] = {
    SignalStatus.ACTIVE: 1,
    SignalStatus.TP1_HIT: 2,
    SignalStatus.TP2_HIT: 3,
    SignalStatus.TP3_HIT: 4,
    SignalStatus.TP4_HIT: 5,
}
_TP_STATUS_FOR_LEVEL: dict[int, SignalStatus] = {
    1: SignalStatus.TP1_HIT,
    2: SignalStatus.TP2_HIT,
    3: SignalStatus.TP3_HIT,
    4: SignalStatus.TP4_HIT,
    5: SignalStatus.TP5_HIT,
}


class InvalidTransitionError(Exception):
    """Raised when a transition is attempted from a status that doesn't allow it."""


def format_signal_id(prefix: str, day: date, sequence: int) -> str:
    """e.g. GOLD-20260817-001. `sequence` must come from an atomic per-day counter
    (app/db/repositories/signal_repository.py) - never guessed client-side, or two
    concurrent signals could collide on the same ID."""
    return f"{prefix}-{day:%Y%m%d}-{sequence:03d}"


@dataclass(frozen=True, slots=True)
class TargetLevel:
    level: int
    price: float
    rr: float
    basis: str
    hit: bool = False
    hit_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Signal:
    id: str
    symbol: str
    direction: Direction
    status: SignalStatus
    entry_low: float
    entry_high: float
    stop_loss: float
    targets: tuple[TargetLevel, ...]
    confidence: float
    confluence_tier: SignalTier
    agreement: int
    reasons: tuple[str, ...]
    timeframe: str
    created_at: datetime
    activated_at: datetime | None = None
    closed_at: datetime | None = None
    telegram_message_id: int | None = None
    invalidation_reason: str | None = None
    events: tuple[tuple[SignalEventType, datetime], ...] = field(default_factory=tuple)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def next_target(self) -> TargetLevel | None:
        level = _NEXT_TARGET_LEVEL.get(self.status)
        if level is None:
            return None
        return next((t for t in self.targets if t.level == level), None)


def build_signal(
    signal_id: str,
    symbol: str,
    direction: Direction,
    entry_low: float,
    entry_high: float,
    stop_loss: StopLoss,
    take_profits: Sequence[TakeProfit],
    confidence: float,
    confluence_tier: SignalTier,
    agreement: int,
    reasons: Sequence[str],
    timeframe: str,
    created_at: datetime,
) -> Signal:
    """A freshly detected signal always starts DETECTED -> WAITING_ENTRY: it's real,
    but nothing has touched the entry zone yet (Section 22)."""
    if direction is Direction.NEUTRAL:
        raise ValueError("cannot build a signal with NEUTRAL direction")
    if len(take_profits) != 5:
        raise ValueError(f"expected exactly 5 take profits, got {len(take_profits)}")

    targets = tuple(
        TargetLevel(level=tp.level, price=tp.price, rr=tp.rr, basis=tp.basis) for tp in take_profits
    )
    return Signal(
        id=signal_id,
        symbol=symbol,
        direction=direction,
        status=SignalStatus.WAITING_ENTRY,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss.price,
        targets=targets,
        confidence=confidence,
        confluence_tier=confluence_tier,
        agreement=agreement,
        reasons=tuple(reasons),
        timeframe=timeframe,
        created_at=created_at,
        events=((SignalEventType.SIGNAL_CREATED, created_at),),
    )


def _with_event(signal: Signal, event: SignalEventType, at: datetime) -> Signal:
    return replace(signal, events=(*signal.events, (event, at)))


def activate(signal: Signal, at: datetime) -> Signal:
    """Price touched the entry zone: WAITING_ENTRY -> ACTIVE."""
    if signal.status is not SignalStatus.WAITING_ENTRY:
        raise InvalidTransitionError(f"cannot activate signal {signal.id} from {signal.status}")
    updated = replace(signal, status=SignalStatus.ACTIVE, activated_at=at)
    return _with_event(updated, SignalEventType.ENTRY_TOUCHED, at)


def hit_target(signal: Signal, level: int, at: datetime) -> Signal:
    """Advance to TPn_HIT. Levels must be hit in order - Section 25 requires each
    level a fast price jump clears to be recorded (the tracker calls this once per
    level it detects), but never out of sequence and never twice."""
    expected = _NEXT_TARGET_LEVEL.get(signal.status)
    if expected is None:
        raise InvalidTransitionError(
            f"signal {signal.id} cannot take a TP hit from {signal.status}"
        )
    if level != expected:
        raise InvalidTransitionError(f"signal {signal.id} expected TP{expected}, got TP{level}")

    new_targets = tuple(
        replace(t, hit=True, hit_at=at) if t.level == level else t for t in signal.targets
    )
    new_status = _TP_STATUS_FOR_LEVEL[level]
    closed_at = at if level == 5 else None
    updated = replace(signal, targets=new_targets, status=new_status, closed_at=closed_at)
    event = SignalEventType(f"TP{level}_HIT")
    return _with_event(updated, event, at)


def stop_out(signal: Signal, at: datetime) -> Signal:
    """SL hit: only valid once a signal is live (ACTIVE or has already banked some TPs)."""
    if signal.status not in _NEXT_TARGET_LEVEL:
        raise InvalidTransitionError(f"cannot stop out signal {signal.id} from {signal.status}")
    updated = replace(signal, status=SignalStatus.STOPPED, closed_at=at)
    return _with_event(updated, SignalEventType.SL_HIT, at)


def cancel(signal: Signal, at: datetime, reason: str) -> Signal:
    """Structure invalidated before entry was ever touched."""
    if signal.status not in (SignalStatus.DETECTED, SignalStatus.WAITING_ENTRY):
        raise InvalidTransitionError(f"cannot cancel signal {signal.id} from {signal.status}")
    updated = replace(
        signal, status=SignalStatus.CANCELLED, closed_at=at, invalidation_reason=reason
    )
    return _with_event(updated, SignalEventType.SIGNAL_CANCELLED, at)


def invalidate(signal: Signal, at: datetime, reason: str) -> Signal:
    """Structure invalidated while the signal was live (Section 28)."""
    if signal.is_terminal:
        raise InvalidTransitionError(f"signal {signal.id} is already terminal ({signal.status})")
    updated = replace(
        signal, status=SignalStatus.INVALIDATED, closed_at=at, invalidation_reason=reason
    )
    return _with_event(updated, SignalEventType.SIGNAL_INVALIDATED, at)


def reverse(signal: Signal, at: datetime, reason: str) -> Signal:
    """Opposite-direction confluence became strong enough to flip the call (Section 29)."""
    if signal.is_terminal:
        raise InvalidTransitionError(f"signal {signal.id} is already terminal ({signal.status})")
    updated = replace(
        signal, status=SignalStatus.REVERSED, closed_at=at, invalidation_reason=reason
    )
    return _with_event(updated, SignalEventType.SIGNAL_REVERSED, at)


def expire(signal: Signal, at: datetime) -> Signal:
    """Entry zone was never reached within the signal's time budget (Section 32)."""
    if signal.status is not SignalStatus.WAITING_ENTRY:
        raise InvalidTransitionError(f"cannot expire signal {signal.id} from {signal.status}")
    updated = replace(signal, status=SignalStatus.EXPIRED, closed_at=at)
    return _with_event(updated, SignalEventType.SIGNAL_EXPIRED, at)


def mark_missed_entry(signal: Signal, at: datetime) -> Signal:
    """Price ran away from the entry zone without ever tagging it (Section 18)."""
    if signal.status is not SignalStatus.WAITING_ENTRY:
        raise InvalidTransitionError(
            f"cannot mark signal {signal.id} as missed entry from {signal.status}"
        )
    return replace(signal, status=SignalStatus.MISSED_ENTRY, closed_at=at)


def set_telegram_message_id(signal: Signal, message_id: int) -> Signal:
    return replace(signal, telegram_message_id=message_id)
