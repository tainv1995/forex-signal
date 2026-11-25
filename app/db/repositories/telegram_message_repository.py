from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.telegram_message import TelegramMessageModel


class TelegramMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_reserve(
        self, idempotency_key: str, signal_id: str | None, event: str, chat_id: str, text: str
    ) -> int | None:
        """Atomically claims `idempotency_key` for a PENDING send. Returns the new
        row id if this call won the claim, or None if it was already claimed - by
        this worker on a prior attempt or a concurrent one (Section 47/51: never
        send the same signal event to Telegram twice)."""
        stmt = (
            insert(TelegramMessageModel)
            .values(
                idempotency_key=idempotency_key,
                signal_id=signal_id,
                event=event,
                chat_id=chat_id,
                text=text,
                status="PENDING",
            )
            .on_conflict_do_nothing(index_elements=[TelegramMessageModel.idempotency_key])
            .returning(TelegramMessageModel.id)
        )
        result = await self._session.execute(stmt)
        row_id = result.scalar_one_or_none()
        await self._session.commit()
        return row_id

    async def mark_sent(self, row_id: int, telegram_message_id: int) -> None:
        await self._session.execute(
            update(TelegramMessageModel)
            .where(TelegramMessageModel.id == row_id)
            .values(status="SENT", telegram_message_id=telegram_message_id)
        )
        await self._session.commit()

    async def mark_failed(self, row_id: int, error: str) -> None:
        await self._session.execute(
            update(TelegramMessageModel)
            .where(TelegramMessageModel.id == row_id)
            .values(status="FAILED", error=error)
        )
        await self._session.commit()
