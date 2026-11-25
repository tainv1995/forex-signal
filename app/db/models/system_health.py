from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class SystemHealthModel(Base):
    """One row per health check performed. Uptime % is derived from these, not
    assumed - if nothing has been recorded yet, uptime is genuinely unknown."""

    __tablename__ = "system_health"
    __table_args__ = (Index("ix_system_health_checked_at", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
