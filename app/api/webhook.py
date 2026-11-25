from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import AliasChoices, BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.time import parse_iso8601
from app.core.timeframes import TRADINGVIEW_INTERVAL_MAP
from app.db.repositories.candle_repository import CandleRepository
from app.db.session import get_db
from app.market_data.base import Candle, PriceTick
from app.market_data.tradingview import TradingViewProvider

router = APIRouter(prefix="/webhook", tags=["webhook"])
logger = get_logger(__name__)


class TradingViewAlertPayload(BaseModel):
    """Matches a TradingView alert message set to "Once Per Bar Close":

    {"symbol": "{{ticker}}", "interval": "{{interval}}", "time": "{{timenow}}",
     "open": {{open}}, "high": {{high}}, "low": {{low}}, "close": {{close}},
     "volume": {{volume}}}
    """

    symbol: str = Field(validation_alias=AliasChoices("symbol", "ticker"))
    interval: str = Field(validation_alias=AliasChoices("interval", "timeframe"))
    time: str = Field(validation_alias=AliasChoices("time", "timenow"))
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


def _verify_secret(token: str | None, header_secret: str | None, settings: Settings) -> None:
    if not settings.tradingview_webhook_secret:
        raise HTTPException(503, "TRADINGVIEW_WEBHOOK_SECRET is not configured")
    if (token or header_secret) != settings.tradingview_webhook_secret:
        raise HTTPException(401, "invalid or missing webhook token")


def _normalize_symbol(raw: str, configured: str) -> str | None:
    candidate = raw.split(":")[-1].upper()
    return configured if candidate == configured.upper() else None


@router.post("/tradingview")
async def tradingview_webhook(
    payload: TradingViewAlertPayload,
    token: str | None = None,
    x_webhook_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict[str, object]:
    settings = get_settings()
    _verify_secret(token, x_webhook_secret, settings)

    timeframe = TRADINGVIEW_INTERVAL_MAP.get(payload.interval)
    if timeframe is None:
        raise HTTPException(400, f"unsupported interval: {payload.interval}")

    symbol = _normalize_symbol(payload.symbol, settings.symbol)
    if symbol is None:
        raise HTTPException(400, f"unexpected symbol: {payload.symbol}")

    timestamp = parse_iso8601(payload.time)
    candle = Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=payload.open,
        high=payload.high,
        low=payload.low,
        close=payload.close,
        volume=payload.volume,
    )

    await TradingViewProvider.store_candle(redis, candle)
    await TradingViewProvider.store_tick(
        redis, PriceTick(symbol=symbol, price=candle.close, timestamp=timestamp)
    )
    await CandleRepository(db).upsert_many([candle], source="tradingview")

    logger.info("TradingView webhook stored %s %s %s", symbol, timeframe.value, timestamp)
    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe.value,
        "timestamp": timestamp.isoformat(),
    }
