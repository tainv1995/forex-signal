from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.base import AnalysisResult
from app.analysis.ema_trend import analyze_ema_trend
from app.analysis.fibonacci import analyze_fibonacci
from app.analysis.indicators import latest_atr
from app.analysis.liquidity_smc import analyze_liquidity_smc
from app.analysis.macd import analyze_macd
from app.analysis.market_structure import analyze_market_structure
from app.analysis.price_action import analyze_price_action
from app.analysis.support_resistance import analyze_support_resistance
from app.analysis.volatility import analyze_volatility
from app.core.config import Settings
from app.core.enums import MarketRiskState, Timeframe
from app.core.logging import get_logger
from app.db.repositories.signal_repository import SignalRepository
from app.engines.confluence import ConfluenceResult, compute_confluence
from app.engines.entry import find_entry_zone
from app.engines.risk import calculate_stop_loss, meets_minimum_rr
from app.engines.signal import Signal, build_signal, set_telegram_message_id
from app.engines.targets import calculate_take_profits, rr_ladder_for
from app.market_data.base import Candle, MarketDataError, MarketDataProvider
from app.market_data.risk import VolatilityMarketRiskProvider
from app.telegram.dispatcher import is_paused
from app.telegram.notifier import TelegramNotifier
from app.tracking.event_processor import process_signal_health_check

logger = get_logger(__name__)

# Direction/confluence voters: Market Structure, Support/Resistance, Liquidity/SMC,
# Price Action - the "does the market actually show a real setup" question.
SINGLE_TIMEFRAME_METHODS = (
    analyze_market_structure,
    analyze_support_resistance,
    analyze_liquidity_smc,
    analyze_price_action,
)

# EMA Trend, MACD, Volatility and Fibonacci don't get a confluence vote - they're
# purely passive: computed only to supply entry/risk/targets with real price levels
# (EMA20 pullback, Bollinger bands, Fib extensions) and the ATR value itself. They
# never block or veto a signal; dropping them from confluence shouldn't also starve
# those engines of real levels to work with.
STRUCTURAL_ONLY_METHODS = (
    analyze_ema_trend,
    analyze_macd,
    analyze_volatility,
    analyze_fibonacci,
)


async def _run_full_analysis(
    provider: MarketDataProvider, symbol: str, primary_timeframe: Timeframe
) -> tuple[list[AnalysisResult], list[AnalysisResult], float | None]:
    """The 4 active production methods feed confluence; a further 4 (EMA Trend,
    MACD, Volatility, Fibonacci) are computed only to supply entry/risk/targets with
    real structural levels - see STRUCTURAL_ONLY_METHODS. The same functions run for
    the analysis worker, backtest, and dispatcher /status command - there is no
    separate "live" scoring path."""
    candles = await provider.get_candles(symbol, primary_timeframe, limit=300)
    results = [method(candles, primary_timeframe) for method in SINGLE_TIMEFRAME_METHODS]
    structural_extra = [method(candles, primary_timeframe) for method in STRUCTURAL_ONLY_METHODS]
    return results, structural_extra, latest_atr(candles)


async def _try_create_signal(
    settings: Settings,
    signal_repo: SignalRepository,
    notifier: TelegramNotifier,
    confluence: ConfluenceResult,
    level_sources: list[AnalysisResult],
    atr_value: float | None,
    current_price: float,
    now: datetime,
    primary_timeframe: Timeframe,
) -> Signal | None:
    """Entry/Risk/Targets -> build_signal -> persist -> notify, given a confluence
    read that's already been judged tradeable-or-not by the caller. Shared by the
    normal fresh-setup path and the REVERSE path (Section 29: closing the old signal
    and opening the new opposite one is the same ordinary pipeline, not a special
    code path)."""
    if not confluence.is_tradeable or atr_value is None or atr_value <= 0:
        return None

    entry = find_entry_zone(
        confluence.direction,
        current_price,
        level_sources,
        atr_value,
        max_chase_atr_mult=settings.entry_max_chase_atr_mult,
    )
    if entry is None or not entry.reachable:
        return None

    stop_loss = calculate_stop_loss(confluence.direction, entry.mid, level_sources, atr_value)
    if stop_loss is None:
        return None

    targets = calculate_take_profits(
        confluence.direction,
        entry.mid,
        stop_loss,
        level_sources,
        rr_ladder=rr_ladder_for(settings.min_rr),
    )
    if targets is None or not meets_minimum_rr(targets[0].rr, settings.min_rr):
        return None

    signal_id = await signal_repo.next_signal_id(settings.signal_id_prefix, now.date())
    signal = build_signal(
        signal_id=signal_id,
        symbol=settings.symbol,
        direction=confluence.direction,
        entry_low=entry.low,
        entry_high=entry.high,
        stop_loss=stop_loss,
        take_profits=targets,
        confidence=confluence.confidence,
        confluence_tier=confluence.tier,
        agreement=confluence.agreement,
        reasons=confluence.reasons,
        timeframe=primary_timeframe.value,
        created_at=now,
    )
    await signal_repo.create(signal)
    if settings.telegram_enabled:
        message_id = await notifier.notify_new_signal(signal)
        if message_id is not None:
            updated = set_telegram_message_id(signal, message_id)
            await signal_repo.apply_transition(signal.status, updated)

    logger.info(
        "created signal %s %s (%s)", signal.id, signal.direction.value, signal.confluence_tier.value
    )
    return signal


async def run_analysis_cycle(
    settings: Settings,
    provider: MarketDataProvider,
    session: AsyncSession,
    redis: Redis,
    notifier: TelegramNotifier,
) -> Signal | None:
    """One analysis cycle for `settings.symbol`: re-checks any open signal for
    invalidation/reversal, and - only if nothing is open, generation isn't paused,
    and cooldown/rate-limit allow it - looks for a fresh setup. Returns the signal
    it created, if any (mostly useful for tests/scripts)."""
    signal_repo = SignalRepository(session)
    now = datetime.now(UTC)

    if not settings.signal_generation_enabled:
        return None
    if await is_paused(redis):
        return None

    try:
        primary_timeframe = Timeframe(settings.primary_timeframe)
    except ValueError:
        logger.error("invalid PRIMARY_TIMEFRAME setting: %s", settings.primary_timeframe)
        return None

    open_signals = await signal_repo.get_open_signals(settings.symbol)
    if open_signals:
        # A confluence check needs the SAME analysis pass used to trade - re-run it
        # fresh and let the reversal engine decide (Section 28/29).
        try:
            results, structural_extra, atr_value = await _run_full_analysis(
                provider, settings.symbol, primary_timeframe
            )
        except MarketDataError:
            logger.warning(
                "market data unavailable, skipping health check for open signals on %s",
                settings.symbol,
            )
            return None
        confluence = compute_confluence(
            results,
            weights=settings.strategy_weights,
            min_agreement=settings.min_method_agreement,
            strong_agreement=settings.strong_method_agreement,
        )
        reversed_any = False
        for signal in open_signals:
            decision = await process_signal_health_check(
                signal,
                confluence,
                now,
                signal_repo,
                notifier,
                invalidation_floor=settings.invalidation_confidence_floor,
                reversal_threshold=settings.reversal_signal_confidence,
            )
            reversed_any = reversed_any or decision.action == "REVERSE"

        if not reversed_any:
            return None  # never open a second position while one is already live

        # By request (2026-09-03): a REVERSE close is immediately followed by the
        # ordinary fresh-signal pipeline in the same cycle, using the SAME confluence
        # read that triggered the reversal - not a several-minutes-later afterthought.
        try:
            current_price = (await provider.get_current_price(settings.symbol)).price
        except MarketDataError:
            logger.warning(
                "market data unavailable, skipping post-reversal signal for %s", settings.symbol
            )
            return None
        return await _try_create_signal(
            settings,
            signal_repo,
            notifier,
            confluence,
            results + structural_extra,
            atr_value,
            current_price,
            now,
            primary_timeframe,
        )

    cooldown_since = now - timedelta(minutes=settings.signal_cooldown_minutes)
    recent = await signal_repo.get_created_since(settings.symbol, cooldown_since)
    if recent:
        logger.debug("cooldown active for %s, skipping analysis cycle", settings.symbol)
        return None

    hour_ago = now - timedelta(hours=1)
    last_hour = await signal_repo.get_created_since(settings.symbol, hour_ago)
    if len(last_hour) >= settings.max_signals_per_hour:
        logger.debug("max signals/hour reached for %s, skipping", settings.symbol)
        return None

    async def _recent_candles(symbol: str) -> list[Candle]:
        # 250 (not 100): VolatilityMarketRiskProvider's low-volatility check needs a
        # long-period ATR (200) to compare the short-term one against - same request,
        # just a larger outputsize, no extra API credit cost.
        return await provider.get_candles(symbol, primary_timeframe, limit=250)

    risk_provider = VolatilityMarketRiskProvider(_recent_candles)
    try:
        risk_state = await risk_provider.get_risk_state(settings.symbol)
    except MarketDataError:
        logger.warning("market data unavailable, skipping analysis cycle for %s", settings.symbol)
        return None
    if risk_state is not MarketRiskState.NORMAL:
        # Section 34: pause new signals during abnormal volatility rather than
        # trying to trade through it.
        logger.info(
            "market risk state=%s for %s, pausing new signals", risk_state.value, settings.symbol
        )
        return None

    try:
        results, structural_extra, atr_value = await _run_full_analysis(
            provider, settings.symbol, primary_timeframe
        )
        current_price = (await provider.get_current_price(settings.symbol)).price
    except MarketDataError:
        logger.warning("market data unavailable, skipping analysis cycle for %s", settings.symbol)
        return None

    confluence = compute_confluence(
        results,
        weights=settings.strategy_weights,
        min_agreement=settings.min_method_agreement,
        strong_agreement=settings.strong_method_agreement,
    )
    # Entry/risk/targets get the confluence-voting methods plus the structural-only
    # ones (EMA Trend, MACD, Volatility, Fibonacci) so they can prefer a real price
    # level over a raw ATR/R-multiple projection - those 4 methods just don't get a
    # confluence vote.
    return await _try_create_signal(
        settings,
        signal_repo,
        notifier,
        confluence,
        results + structural_extra,
        atr_value,
        current_price,
        now,
        primary_timeframe,
    )
