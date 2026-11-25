import json
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import Direction, SignalStatus, SignalTier
from app.db.models.signal import (
    SignalEventModel,
    SignalModel,
    SignalSequenceModel,
    SignalTargetModel,
)
from app.engines.signal import Signal, TargetLevel, format_signal_id

# Non-terminal statuses: a symbol should never have two of these open at once
# (Section 51: "Không tạo hai Active Signal giống nhau").
OPEN_STATUSES = frozenset(
    {
        SignalStatus.DETECTED,
        SignalStatus.WAITING_ENTRY,
        SignalStatus.ACTIVE,
        SignalStatus.TP1_HIT,
        SignalStatus.TP2_HIT,
        SignalStatus.TP3_HIT,
        SignalStatus.TP4_HIT,
    }
)


def _to_domain(model: SignalModel) -> Signal:
    targets = tuple(
        TargetLevel(
            level=t.level, price=t.price, rr=t.rr, basis=t.basis, hit=t.hit, hit_at=t.hit_at
        )
        for t in sorted(model.targets, key=lambda t: t.level)
    )
    return Signal(
        id=model.id,
        symbol=model.symbol,
        direction=Direction(model.direction),
        status=SignalStatus(model.status),
        entry_low=model.entry_low,
        entry_high=model.entry_high,
        stop_loss=model.stop_loss,
        targets=targets,
        confidence=model.confidence,
        confluence_tier=SignalTier(model.confluence_tier),
        agreement=model.agreement,
        reasons=tuple(json.loads(model.reasons)),
        timeframe=model.timeframe,
        created_at=model.created_at,
        activated_at=model.activated_at,
        closed_at=model.closed_at,
        telegram_message_id=model.telegram_message_id,
        invalidation_reason=model.invalidation_reason,
    )


class SignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_signal_id(self, prefix: str, day: date) -> str:
        """Atomically hand out the next per-day sequence number so two concurrent
        workers can never mint the same signal ID."""
        stmt = (
            insert(SignalSequenceModel)
            .values(day=day, last_value=1)
            .on_conflict_do_update(
                index_elements=[SignalSequenceModel.day],
                set_={"last_value": SignalSequenceModel.last_value + 1},
            )
            .returning(SignalSequenceModel.last_value)
        )
        result = await self._session.execute(stmt)
        sequence = result.scalar_one()
        await self._session.commit()
        return format_signal_id(prefix, day, sequence)

    async def create(self, signal: Signal) -> None:
        model = SignalModel(
            id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction.value,
            status=signal.status.value,
            entry_low=signal.entry_low,
            entry_high=signal.entry_high,
            stop_loss=signal.stop_loss,
            confidence=signal.confidence,
            confluence_tier=signal.confluence_tier.value,
            agreement=signal.agreement,
            reasons=json.dumps(list(signal.reasons)),
            timeframe=signal.timeframe,
            created_at=signal.created_at,
            activated_at=signal.activated_at,
            closed_at=signal.closed_at,
            telegram_message_id=signal.telegram_message_id,
            invalidation_reason=signal.invalidation_reason,
            targets=[
                SignalTargetModel(
                    level=t.level, price=t.price, rr=t.rr, basis=t.basis, hit=t.hit, hit_at=t.hit_at
                )
                for t in signal.targets
            ],
        )
        self._session.add(model)
        if signal.events:
            # Flush the signal row first - SignalEventModel has no mapped relationship
            # to SignalModel, so autoflush ordering can't infer this FK dependency.
            await self._session.flush()
            event_type, event_at = signal.events[-1]
            self._session.add(
                SignalEventModel(signal_id=signal.id, event=event_type.value, timestamp=event_at)
            )
        await self._session.commit()

    async def get(self, signal_id: str) -> Signal | None:
        stmt = (
            select(SignalModel)
            .where(SignalModel.id == signal_id)
            .options(selectinload(SignalModel.targets))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_open_signals(self, symbol: str) -> list[Signal]:
        stmt = (
            select(SignalModel)
            .where(
                SignalModel.symbol == symbol,
                SignalModel.status.in_([s.value for s in OPEN_STATUSES]),
            )
            .options(selectinload(SignalModel.targets))
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars().all()]

    async def get_closed_between(self, symbol: str, start: datetime, end: datetime) -> list[Signal]:
        """Signals that reached a terminal status in [start, end) - the basis for a
        daily report covering that window."""
        stmt = (
            select(SignalModel)
            .where(
                SignalModel.symbol == symbol,
                SignalModel.closed_at >= start,
                SignalModel.closed_at < end,
            )
            .options(selectinload(SignalModel.targets))
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars().all()]

    async def get_created_since(self, symbol: str, since: datetime) -> list[Signal]:
        """Signals created at or after `since` - the basis for cooldown and
        max-signals-per-hour checks before minting a new one (Section 31)."""
        stmt = (
            select(SignalModel)
            .where(SignalModel.symbol == symbol, SignalModel.created_at >= since)
            .options(selectinload(SignalModel.targets))
        )
        result = await self._session.execute(stmt)
        return [_to_domain(m) for m in result.scalars().all()]

    async def apply_transition(self, previous_status: SignalStatus, signal: Signal) -> bool:
        """Persist a state transition with an optimistic conditional UPDATE keyed on
        the status the signal had *before* this transition. If another worker already
        moved it on, rowcount is 0 and we back off instead of double-processing the
        same TP/SL hit (Section 51)."""
        stmt = (
            update(SignalModel)
            .where(SignalModel.id == signal.id, SignalModel.status == previous_status.value)
            .values(
                status=signal.status.value,
                activated_at=signal.activated_at,
                closed_at=signal.closed_at,
                telegram_message_id=signal.telegram_message_id,
                invalidation_reason=signal.invalidation_reason,
            )
        )
        result = await self._session.execute(stmt)
        # UPDATE always returns a CursorResult at runtime, which has .rowcount - the
        # broader Result[Any] stub just doesn't expose it statically.
        if result.rowcount == 0:  # type: ignore[attr-defined]
            await self._session.rollback()
            return False

        for target in signal.targets:
            if not target.hit:
                continue
            await self._session.execute(
                update(SignalTargetModel)
                .where(
                    SignalTargetModel.signal_id == signal.id,
                    SignalTargetModel.level == target.level,
                    ~SignalTargetModel.hit,
                )
                .values(hit=True, hit_at=target.hit_at)
            )

        if signal.events:
            event_type, event_at = signal.events[-1]
            self._session.add(
                SignalEventModel(signal_id=signal.id, event=event_type.value, timestamp=event_at)
            )

        await self._session.commit()
        return True
