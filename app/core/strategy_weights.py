from app.core.enums import StrategyName

# Section 17: market structure / liquidity / multi-timeframe carry the most weight;
# RSI/MACD are confirmation-only and never dominate the confluence score.
DEFAULT_STRATEGY_WEIGHTS: dict[StrategyName, float] = {
    StrategyName.MARKET_STRUCTURE: 1.30,
    StrategyName.SUPPORT_RESISTANCE: 1.15,
    StrategyName.EMA_TREND: 0.80,
    StrategyName.RSI_MOMENTUM: 0.70,
    StrategyName.MACD: 0.65,
    StrategyName.VOLATILITY: 0.70,
    StrategyName.FIBONACCI: 0.85,
    StrategyName.PRICE_ACTION: 1.00,
    StrategyName.LIQUIDITY_SMC: 1.30,
    StrategyName.MULTI_TIMEFRAME: 1.35,
}
