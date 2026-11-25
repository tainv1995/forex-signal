from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.enums import Timeframe
from app.market_data.base import MarketDataError
from app.market_data.factory import get_market_data_provider
from app.market_data.quality import validate_candles

router = APIRouter(prefix="/market", tags=["market-data"])


@router.get("/price")
async def get_price() -> dict[str, object]:
    settings = get_settings()
    provider = get_market_data_provider()
    try:
        tick = await provider.get_current_price(settings.symbol)
    except MarketDataError as exc:
        raise HTTPException(503, str(exc)) from exc

    return {
        "symbol": tick.symbol,
        "price": tick.price,
        "bid": tick.bid,
        "ask": tick.ask,
        "timestamp": tick.timestamp.isoformat(),
        "provider": settings.market_data_provider.value,
    }


@router.get("/candles")
async def get_candles(timeframe: Timeframe = Timeframe.M15, limit: int = 20) -> dict[str, object]:
    settings = get_settings()
    provider = get_market_data_provider()
    try:
        candles = await provider.get_candles(settings.symbol, timeframe, limit=limit)
    except MarketDataError as exc:
        raise HTTPException(503, str(exc)) from exc

    issues = validate_candles(candles)
    return {
        "symbol": settings.symbol,
        "timeframe": timeframe.value,
        "count": len(candles),
        "provider": settings.market_data_provider.value,
        "candles": [asdict(candle) for candle in candles],
        "qualityIssues": [issue.kind for issue in issues],
    }
