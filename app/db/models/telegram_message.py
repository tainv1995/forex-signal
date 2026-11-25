from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class TelegramMessageModel(Base):
    """One row per Telegram message actually sent. `idempotency_key` is unique so a
    given (signal, event) pair can only ever be sent once, even if two workers race
    to send it (Section 47: never send the same TP/SL notification twice)."""

    __tablename__ = "telegram_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    signal_id: Mapped[str | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(30), nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
