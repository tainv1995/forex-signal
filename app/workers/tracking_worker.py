from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.indicators import latest_atr
from app.core.config import Settings
from app.core.enums import Timeframe
from app.core.logging import get_logger
from app.db.repositories.signal_repository import SignalRepository
from app.market_data.base import MarketDataError, MarketDataProvider
from app.telegram.notifier import TelegramNotifier
from app.tracking.event_processor import process_symbol_tick

logger = get_logger(__name__)


async def run_tracking_cycle(
    settings: Settings,
    provider: MarketDataProvider,
    session: AsyncSession,
    notifier: TelegramNotifier,
) -> None:
    """One tracking tick for `settings.symbol` - no-ops immediately if nothing is
    open, so this can run far more often than the analysis cycle without wasting
    market data calls."""
    signal_repo = SignalRepository(session)
    if not await signal_repo.get_open_signals(settings.symbol):
        return

    try:
        primary_timeframe = Timeframe(settings.primary_timeframe)
        tick = await provider.get_current_price(settings.symbol)
        candles = await provider.get_candles(settings.symbol, primary_timeframe, limit=100)
    except (MarketDataError, ValueError):
        logger.warning("market data unavailable, skipping tracking cycle for %s", settings.symbol)
        return

    atr_value = latest_atr(candles)
    if atr_value is None or atr_value <= 0:
        return

    await process_symbol_tick(
        settings.symbol,
        tick.price,
        datetime.now(UTC),
        atr_value,
        signal_repo,
        notifier,
        max_chase_atr_mult=settings.entry_max_chase_atr_mult,
        expiry_minutes=settings.entry_expiry_minutes,
    )
