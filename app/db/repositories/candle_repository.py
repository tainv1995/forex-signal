from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Timeframe
from app.db.models.candle import CandleModel
from app.market_data.base import Candle


class CandleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, candles: Sequence[Candle], source: str) -> None:
        if not candles:
            return
        rows = [
            {
                "symbol": candle.symbol,
                "timeframe": candle.timeframe.value,
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "source": source,
            }
            for candle in candles
        ]
        stmt = insert(CandleModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candles_symbol_timeframe_timestamp",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "source": stmt.excluded.source,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_recent(self, symbol: str, timeframe: Timeframe, limit: int = 200) -> list[Candle]:
        stmt = (
            select(CandleModel)
            .where(CandleModel.symbol == symbol, CandleModel.timeframe == timeframe.value)
            .order_by(CandleModel.timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [
            Candle(
                symbol=row.symbol,
                timeframe=Timeframe(row.timeframe),
                timestamp=row.timestamp,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in reversed(rows)
        ]
