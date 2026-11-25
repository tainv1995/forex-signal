from enum import StrEnum


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


class Direction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class SignalStatus(StrEnum):
    DETECTED = "DETECTED"
    WAITING_ENTRY = "WAITING_ENTRY"
    ACTIVE = "ACTIVE"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    TP4_HIT = "TP4_HIT"
    TP5_HIT = "TP5_HIT"
    STOPPED = "STOPPED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"
    REVERSED = "REVERSED"
    EXPIRED = "EXPIRED"
    MISSED_ENTRY = "MISSED_ENTRY"


class SignalEventType(StrEnum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    ENTRY_TOUCHED = "ENTRY_TOUCHED"
    TP1_HIT = "TP1_HIT"
    TP2_HIT = "TP2_HIT"
    TP3_HIT = "TP3_HIT"
    TP4_HIT = "TP4_HIT"
    TP5_HIT = "TP5_HIT"
    SL_HIT = "SL_HIT"
    SIGNAL_INVALIDATED = "SIGNAL_INVALIDATED"
    SIGNAL_CANCELLED = "SIGNAL_CANCELLED"
    SIGNAL_REVERSED = "SIGNAL_REVERSED"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"


class MarketSession(StrEnum):
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    OFF_HOURS = "OFF_HOURS"


class MarketRiskState(StrEnum):
    NORMAL = "NORMAL"
    HIGH_IMPACT_NEWS_SOON = "HIGH_IMPACT_NEWS_SOON"
    HIGH_IMPACT_NEWS_ACTIVE = "HIGH_IMPACT_NEWS_ACTIVE"
    ABNORMAL_VOLATILITY = "ABNORMAL_VOLATILITY"


class MarketDataProviderType(StrEnum):
    TRADINGVIEW = "tradingview"
    BROKER = "broker"
    TWELVEDATA = "twelvedata"
    MOCK = "mock"


class StrategyName(StrEnum):
    MARKET_STRUCTURE = "market_structure"
    SUPPORT_RESISTANCE = "support_resistance"
    EMA_TREND = "ema_trend"
    RSI_MOMENTUM = "rsi_momentum"
    MACD = "macd"
    VOLATILITY = "volatility"
    FIBONACCI = "fibonacci"
    PRICE_ACTION = "price_action"
    LIQUIDITY_SMC = "liquidity_smc"
    MULTI_TIMEFRAME = "multi_timeframe"


class SignalTier(StrEnum):
    NO_TRADE = "NO_TRADE"
    WATCH = "WATCH"
    VALID = "VALID"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"
