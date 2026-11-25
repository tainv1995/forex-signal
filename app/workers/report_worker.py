from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.repositories.signal_repository import SignalRepository
from app.db.repositories.system_health_repository import SystemHealthRepository
from app.market_data.base import MarketDataProvider
from app.reports.daily import build_daily_report, format_daily_report
from app.telegram.notifier import TelegramNotifier

logger = get_logger(__name__)


async def run_daily_report_cycle(
    settings: Settings,
    provider: MarketDataProvider,
    session: AsyncSession,
    notifier: TelegramNotifier,
) -> str:
    """Builds and sends the report for "today" in REPORT_TIMEZONE - meant to be
    scheduled at REPORT_TIME (Section 38). Returns the report text either way, so
    callers/tests can inspect it even with Telegram disabled."""
    tz = ZoneInfo(settings.report_timezone)
    report_date = datetime.now(tz).date()

    data = await build_daily_report(
        settings,
        provider,
        SignalRepository(session),
        SystemHealthRepository(session),
        report_date,
    )
    text = format_daily_report(data)

    if settings.telegram_enabled:
        await notifier.notify_daily_report(report_date, text)
    else:
        logger.info("Telegram disabled, daily report not sent:\n%s", text)

    return text
