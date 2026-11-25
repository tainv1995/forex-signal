from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.webhook import router as webhook_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis
from app.db.session import dispose_engine
from app.market_data.factory import dispose_market_data_provider, get_market_data_provider
from app.workers.scheduler import start_workers

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)
    logger.info("Starting gold-signal-bot (env=%s, symbol=%s)", settings.app_env, settings.symbol)

    worker_runtime = start_workers(settings, get_market_data_provider())

    yield

    logger.info("Shutting down gold-signal-bot")
    if worker_runtime is not None:
        await worker_runtime.shutdown()
    await dispose_market_data_provider()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(title="Gold Signal Bot", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(market_router)
    app.include_router(webhook_router)
    return app


app = create_app()
