from app.analysis.market_structure import analyze_market_structure
from app.core.enums import Direction, Timeframe
from app.market_data.base import MarketDataError, MarketDataProvider

DEFAULT_BIAS_TIMEFRAMES = (Timeframe.H4, Timeframe.H1, Timeframe.M15)
MTF_TIMEFRAMES = (Timeframe.H4, Timeframe.H1, Timeframe.M30, Timeframe.M15, Timeframe.M5)
BIAS_LABELS = {Direction.BUY: "BULLISH", Direction.SELL: "BEARISH", Direction.NEUTRAL: "NEUTRAL"}


async def gather_timeframe_directions(
    provider: MarketDataProvider,
    symbol: str,
    timeframes: tuple[Timeframe, ...],
) -> dict[Timeframe, tuple[Direction, float]]:
    """market_structure's (direction, confidence) per timeframe - the raw input
    analyze_multi_timeframe() needs. A timeframe whose candles can't be fetched is
    simply omitted (not faked as NEUTRAL), same "don't invent data" rule as
    everywhere else."""
    directions: dict[Timeframe, tuple[Direction, float]] = {}
    for timeframe in timeframes:
        try:
            candles = await provider.get_candles(symbol, timeframe, limit=300)
        except MarketDataError:
            continue
        result = analyze_market_structure(candles, timeframe)
        directions[timeframe] = (result.direction, result.confidence)
    return directions


async def gather_bias_and_confidence(
    provider: MarketDataProvider,
    symbol: str,
    timeframes: tuple[Timeframe, ...] = DEFAULT_BIAS_TIMEFRAMES,
) -> tuple[dict[str, str], float, float]:
    """Per-timeframe market_structure bias (BULLISH/BEARISH/NEUTRAL) plus the best
    BUY/SELL confidence seen across those timeframes - shared by the /status and
    /analysis Telegram commands and the daily report's "Market Bias" section."""
    directions = await gather_timeframe_directions(provider, symbol, timeframes)

    bias: dict[str, str] = {}
    buy_confidence = 0.0
    sell_confidence = 0.0
    for timeframe in timeframes:
        if timeframe not in directions:
            bias[timeframe.value] = "N/A"
            continue
        direction, confidence = directions[timeframe]
        bias[timeframe.value] = BIAS_LABELS[direction]
        if direction is Direction.BUY:
            buy_confidence = max(buy_confidence, confidence)
        elif direction is Direction.SELL:
            sell_confidence = max(sell_confidence, confidence)
    return bias, buy_confidence, sell_confidence
