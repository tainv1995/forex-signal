from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class SignalModel(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_symbol_status", "symbol", "status"),
        Index("ix_signals_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_low: Mapped[float] = mapped_column(Float, nullable=False)
    entry_high: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confluence_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    agreement: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    timeframe: Mapped[str] = mapped_column(String(4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    targets: Mapped[list["SignalTargetModel"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan", order_by="SignalTargetModel.level"
    )


class SignalTargetModel(Base):
    __tablename__ = "signal_targets"
    __table_args__ = (Index("ix_signal_targets_signal_id", "signal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    rr: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False)
    hit: Mapped[bool] = mapped_column(nullable=False, default=False)
    hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    signal: Mapped[SignalModel] = relationship(back_populates="targets")


class SignalEventModel(Base):
    __tablename__ = "signal_events"
    __table_args__ = (Index("ix_signal_events_signal_id", "signal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SignalSequenceModel(Base):
    """One row per calendar day; `last_value` is incremented atomically to hand out
    the next GOLD-YYYYMMDD-NNN sequence number without collisions across workers."""

    __tablename__ = "signal_sequences"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
