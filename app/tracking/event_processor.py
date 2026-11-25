from datetime import datetime

from app.core.enums import SignalStatus
from app.core.logging import get_logger
from app.db.repositories.signal_repository import SignalRepository
from app.engines.confluence import ConfluenceResult
from app.engines.reversal import (
    DEFAULT_INVALIDATION_FLOOR,
    DEFAULT_REVERSAL_THRESHOLD,
    ReversalDecision,
    evaluate_signal_health,
)
from app.engines.signal import Signal, cancel, invalidate, reverse
from app.telegram.notifier import TelegramNotifier
from app.tracking.signal_tracker import (
    DEFAULT_EXPIRY_MINUTES,
    DEFAULT_MAX_CHASE_ATR_MULT,
    evaluate_active_signal,
    evaluate_waiting_entry,
)

logger = get_logger(__name__)


async def process_symbol_tick(
    symbol: str,
    current_price: float,
    now: datetime,
    atr_value: float,
    signal_repo: SignalRepository,
    notifier: TelegramNotifier,
    max_chase_atr_mult: float = DEFAULT_MAX_CHASE_ATR_MULT,
    expiry_minutes: int = DEFAULT_EXPIRY_MINUTES,
) -> None:
    """One tick of tracking for every open signal on `symbol`. Persists each
    transition with an optimistic conditional update and only sends a Telegram
    message for the transitions this call actually won (Section 51) - if another
    worker already applied it, apply_transition returns False and we move on
    without re-notifying."""
    open_signals = await signal_repo.get_open_signals(symbol)

    for signal in open_signals:
        if signal.status is SignalStatus.WAITING_ENTRY:
            step = evaluate_waiting_entry(
                signal, current_price, now, atr_value, max_chase_atr_mult, expiry_minutes
            )
            if step is None:
                continue
            applied = await signal_repo.apply_transition(step.previous_status, step.signal)
            if not applied:
                logger.info(
                    "skipped stale transition for %s (already applied elsewhere)", signal.id
                )
                continue
            if step.signal.status is SignalStatus.ACTIVE:
                await notifier.notify_entry_activated(step.signal, current_price)
            continue

        for step in evaluate_active_signal(signal, current_price, now):
            applied = await signal_repo.apply_transition(step.previous_status, step.signal)
            if not applied:
                logger.info(
                    "stopped processing %s mid-sequence: state diverged from another worker",
                    signal.id,
                )
                break
            if step.signal.status is SignalStatus.STOPPED:
                await notifier.notify_stop_loss(step.signal)
            elif step.tp_level is not None:
                await notifier.notify_tp_hit(step.signal, step.tp_level)


async def process_signal_health_check(
    signal: Signal,
    confluence: ConfluenceResult,
    now: datetime,
    signal_repo: SignalRepository,
    notifier: TelegramNotifier,
    invalidation_floor: float = DEFAULT_INVALIDATION_FLOOR,
    reversal_threshold: float = DEFAULT_REVERSAL_THRESHOLD,
) -> ReversalDecision:
    """Re-checks one open signal against a freshly recomputed confluence (Section 28).

    A plain CLOSE (confidence quietly decayed, no strong opposite) sends no Telegram
    notice (by request, 2026-09-03): signals are reference-only, readers manage their
    own positions their own way, and broadcasting "cancelled" for a soft decay reads
    as a directive rather than information. REVERSE is different - the market has
    genuinely flipped to a strong, confident opposite call, which is worth announcing
    explicitly alongside the new opposite-direction signal that follows (by request),
    so REVERSE still sends the "cancelled" notice for the old signal. The status
    transition (and signal_events/stats record) always happens normally either way -
    only the CLOSE-case group notification is suppressed. TP/SL hit notices are
    unaffected (see process_symbol_tick).

    On REVERSE, this only closes the old signal - it does not create the new
    opposite-direction signal itself. The caller already has `confluence` (now
    dominated by the opposite side) and should run it through the normal
    entry/risk/targets -> build_signal pipeline exactly like any other fresh signal
    (Section 29: "Sau đó nếu SELL đủ điều kiện thì phát tín hiệu SELL mới") - a
    reversal isn't a special code path, it's a close followed by an ordinary create.
    """
    decision = evaluate_signal_health(signal, confluence, invalidation_floor, reversal_threshold)
    if decision.action == "KEEP":
        return decision

    reason = "; ".join(decision.reason_lines)
    previous_status = signal.status
    if signal.status is SignalStatus.WAITING_ENTRY:
        updated = cancel(signal, now, reason)
    elif decision.action == "REVERSE":
        updated = reverse(signal, now, reason)
    else:
        updated = invalidate(signal, now, reason)

    applied = await signal_repo.apply_transition(previous_status, updated)
    if not applied:
        logger.info("skipped stale health-check transition for %s", signal.id)
    elif decision.action == "REVERSE":
        await notifier.notify_cancelled(updated, decision.reason_lines)

    return decision
