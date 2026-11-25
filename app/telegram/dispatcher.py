from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.bias import gather_bias_and_confidence
from app.core.config import Settings
from app.db.repositories.signal_repository import SignalRepository
from app.market_data.base import MarketDataError, MarketDataProvider
from app.telegram.commands import (
    ADMIN_COMMANDS,
    StatusSnapshot,
    format_active_signal,
    format_pause,
    format_price,
    format_report_not_ready,
    format_resume,
    format_status,
    format_unauthorized,
    format_unknown_command,
    is_admin,
    parse_command,
)

PAUSE_KEY = "bot:signal_generation_paused"


async def is_paused(redis: Redis) -> bool:
    value = await redis.get(PAUSE_KEY)
    return value == "1"


async def set_paused(redis: Redis, paused: bool) -> None:
    await redis.set(PAUSE_KEY, "1" if paused else "0")


async def gather_status_snapshot(
    settings: Settings, provider: MarketDataProvider, redis: Redis, session: AsyncSession
) -> StatusSnapshot:
    try:
        tick = await provider.get_current_price(settings.symbol)
        last_price: float | None = tick.price
        market_data_ok = True
    except MarketDataError:
        last_price, market_data_ok = None, False

    bias, buy_confidence, sell_confidence = await gather_bias_and_confidence(
        provider, settings.symbol
    )

    open_signals = await SignalRepository(session).get_open_signals(settings.symbol)
    paused = await is_paused(redis)

    return StatusSnapshot(
        symbol=settings.symbol,
        running=not paused,
        last_price=last_price,
        bias_by_timeframe=bias,
        buy_confidence=buy_confidence,
        sell_confidence=sell_confidence,
        active_signal_id=open_signals[0].id if open_signals else None,
        market_data_ok=market_data_ok,
        telegram_ok=True,
        database_ok=True,
    )


async def handle_command(
    text: str,
    user_id: int,
    settings: Settings,
    provider: MarketDataProvider,
    redis: Redis,
    session: AsyncSession,
) -> str:
    command = parse_command(text)
    if not command:
        return ""
    if command not in ADMIN_COMMANDS:
        return format_unknown_command(command)
    if not is_admin(user_id, settings.telegram_admin_ids):
        return format_unauthorized()

    if command == "/status":
        return format_status(await gather_status_snapshot(settings, provider, redis, session))
    if command == "/price":
        try:
            tick = await provider.get_current_price(settings.symbol)
        except MarketDataError as exc:
            return f"Không lấy được giá: {exc}"
        return format_price(settings.symbol, tick.price)
    if command == "/signal":
        open_signals = await SignalRepository(session).get_open_signals(settings.symbol)
        return format_active_signal(open_signals[0] if open_signals else None)
    if command == "/analysis":
        bias, _, _ = await gather_bias_and_confidence(provider, settings.symbol)
        return "\n".join(f"{tf}: {label}" for tf, label in bias.items())
    if command == "/report":
        return format_report_not_ready()
    if command == "/pause":
        await set_paused(redis, True)
        return format_pause()
    if command == "/resume":
        await set_paused(redis, False)
        return format_resume()
    return format_unknown_command(command)
