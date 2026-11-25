from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.db.repositories.telegram_message_repository import TelegramMessageRepository
from app.db.session import get_session_factory
from app.market_data.base import MarketDataProvider
from app.telegram.client import TelegramClient
from app.telegram.notifier import TelegramNotifier
from app.workers.analysis_worker import run_analysis_cycle
from app.workers.report_worker import run_daily_report_cycle
from app.workers.tracking_worker import run_tracking_cycle

logger = get_logger(__name__)


@dataclass(slots=True)
class WorkerRuntime:
    scheduler: AsyncIOScheduler
    client: TelegramClient

    async def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)
        await self.client.aclose()


def _notifier_for(
    client: TelegramClient, settings: Settings, session: AsyncSession
) -> TelegramNotifier:
    return TelegramNotifier(
        client,
        TelegramMessageRepository(session),
        settings.telegram_chat_id,
        settings.telegram_symbol_label,
        settings.telegram_show_metadata,
    )


def start_workers(settings: Settings, provider: MarketDataProvider) -> WorkerRuntime | None:
    """Wires the analysis/tracking/daily-report cycles into a running scheduler.

    Telegram is the bot's only output channel today (no dashboard yet), so if it
    isn't configured there is nothing useful to automate - this returns None rather
    than silently running a bot that can never tell anyone what it found."""
    if not (settings.telegram_bot_token and settings.telegram_enabled):
        logger.warning(
            "TELEGRAM_BOT_TOKEN not set (or TELEGRAM_ENABLED=false) - "
            "analysis/tracking/report workers will not start."
        )
        return None

    client = TelegramClient(settings.telegram_bot_token, max_retries=settings.telegram_max_retries)
    session_factory = get_session_factory()

    async def _analysis_job() -> None:
        async with session_factory() as session:
            notifier = _notifier_for(client, settings, session)
            try:
                await run_analysis_cycle(settings, provider, session, get_redis(), notifier)
            except Exception:
                logger.exception("analysis cycle failed")

    async def _tracking_job() -> None:
        async with session_factory() as session:
            notifier = _notifier_for(client, settings, session)
            try:
                await run_tracking_cycle(settings, provider, session, notifier)
            except Exception:
                logger.exception("tracking cycle failed")

    async def _report_job() -> None:
        async with session_factory() as session:
            notifier = _notifier_for(client, settings, session)
            try:
                await run_daily_report_cycle(settings, provider, session, notifier)
            except Exception:
                logger.exception("daily report cycle failed")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _analysis_job,
        "interval",
        seconds=settings.analysis_interval_seconds,
        id="analysis_cycle",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _tracking_job,
        "interval",
        seconds=settings.tracking_interval_seconds,
        id="tracking_cycle",
        max_instances=1,
        coalesce=True,
    )
    report_hour, report_minute = (int(part) for part in settings.report_time.split(":"))
    scheduler.add_job(
        _report_job,
        CronTrigger(hour=report_hour, minute=report_minute, timezone=settings.report_timezone),
        id="daily_report",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "workers started: analysis every %ss, tracking every %ss, report at %s %s",
        settings.analysis_interval_seconds,
        settings.tracking_interval_seconds,
        settings.report_time,
        settings.report_timezone,
    )
    return WorkerRuntime(scheduler=scheduler, client=client)
