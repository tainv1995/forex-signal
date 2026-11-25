from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_health import SystemHealthModel


class SystemHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, status: str, checked_at: datetime) -> None:
        self._session.add(SystemHealthModel(status=status, checked_at=checked_at))
        await self._session.commit()

    async def uptime_percentage(self, start: datetime, end: datetime) -> float | None:
        """Fraction of recorded checks in [start, end) that were healthy - None (not
        0%) if no checks were recorded, since that's "unknown", not "fully down"."""
        total_stmt = select(func.count()).where(
            SystemHealthModel.checked_at >= start, SystemHealthModel.checked_at < end
        )
        total = (await self._session.execute(total_stmt)).scalar_one()
        if total == 0:
            return None

        healthy_stmt = select(func.count()).where(
            SystemHealthModel.checked_at >= start,
            SystemHealthModel.checked_at < end,
            SystemHealthModel.status == "healthy",
        )
        healthy = (await self._session.execute(healthy_stmt)).scalar_one()
        return healthy / total
