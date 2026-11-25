import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.repositories.system_health_repository import SystemHealthRepository
from app.db.session import get_engine, get_session_factory
from app.market_data.factory import get_market_data_provider

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

# /health can be polled far more often than market data actually needs to be
# re-fetched (Docker's own container healthcheck alone hits this every 30s) - on
# a metered provider like Twelve Data, calling get_current_price() on every single
# hit burns through a whole day's free-tier credit budget on liveness checks alone,
# starving real analysis. This only needs to prove "can we still reach the
# provider", so a short cache is enough; it never affects the actual trading data
# path (analysis/tracking workers always call the provider directly).
_MARKET_DATA_CACHE_TTL_SECONDS = 600.0
_market_data_cache: tuple[float, str, float | None] | None = None


async def _check_market_data() -> tuple[str, float | None]:
    global _market_data_cache
    now = asyncio.get_running_loop().time()
    if _market_data_cache is not None:
        cached_at, status, price = _market_data_cache
        if now - cached_at < _MARKET_DATA_CACHE_TTL_SECONDS:
            return status, price

    settings = get_settings()
    try:
        provider = get_market_data_provider()
        tick = await asyncio.wait_for(provider.get_current_price(settings.symbol), timeout=5.0)
        result: tuple[str, float | None] = ("connected", tick.price)
    except Exception:  # noqa: BLE001 - health check must report status, never raise
        result = ("disconnected", None)

    _market_data_cache = (now, *result)
    return result


async def _check_database() -> str:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "connected"
    except Exception:  # noqa: BLE001 - health check must report status, never raise
        return "disconnected"


async def _check_redis() -> str:
    try:
        redis = get_redis()
        await redis.ping()
        return "connected"
    except Exception:  # noqa: BLE001 - health check must report status, never raise
        return "disconnected"


async def _record_heartbeat(status: str) -> None:
    """Best-effort: /health is the only thing polled regularly today, so recording
    a heartbeat here is what makes the daily report's "Bot Uptime" real data instead
    of a made-up number. If the DB itself is down, there's nothing to record into,
    so this must never raise and break the health check it's piggybacking on."""
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await SystemHealthRepository(session).record(status, datetime.now(UTC))
    except Exception:  # see docstring: must never break the health check itself
        logger.debug("failed to record health heartbeat", exc_info=True)


@router.get("/health")
async def health() -> dict[str, object]:
    settings = get_settings()
    database_status = await _check_database()
    redis_status = await _check_redis()
    market_data_status, last_price = await _check_market_data()
    overall = (
        "healthy"
        if database_status == "connected"
        and redis_status == "connected"
        and market_data_status == "connected"
        else "degraded"
    )
    await _record_heartbeat(overall)

    return {
        "status": overall,
        "symbol": settings.symbol,
        "environment": settings.app_env,
        "paperMode": settings.paper_mode,
        "marketDataProvider": settings.market_data_provider.value,
        "database": database_status,
        "redis": redis_status,
        "marketData": market_data_status,
        "lastPrice": last_price,
    }


@router.get("/health/database")
async def health_database() -> dict[str, object]:
    return {"status": await _check_database()}


@router.get("/health/redis")
async def health_redis() -> dict[str, object]:
    return {"status": await _check_redis()}


@router.get("/health/data")
async def health_data() -> dict[str, object]:
    status, last_price = await _check_market_data()
    return {"status": status, "lastPrice": last_price}
