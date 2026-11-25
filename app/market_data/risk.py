from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence

from app.analysis.indicators import atr as atr_indicator
from app.analysis.indicators import candles_to_frame
from app.analysis.indicators import true_range as true_range_indicator
from app.core.enums import MarketRiskState
from app.market_data.base import Candle

ABNORMAL_VOLATILITY_LOOKBACK = 50
ABNORMAL_VOLATILITY_MULT = 3.0

# Real incident (2026-10-18): a weekend market close makes TwelveDataProvider fill
# recent bars with a near-flat repeated price (every candle's open bit-for-bit
# identical) instead of a true gap - the ATR(14) that entry/risk/targets rely on
# then reads near-zero, which would make SL/entry unrealistically tight right as the
# market reopens. This isn't a "spike" the check above catches (current bar vs
# recent average - both are flat here); it's the whole recent window being
# abnormally quiet relative to how the market actually trades. Comparing a short
# ATR against a much longer one catches it regardless of the cause (weekend,
# holiday, a feed outage serving stale data).
LOW_VOLATILITY_SHORT_PERIOD = 14
LOW_VOLATILITY_LONG_PERIOD = 200
LOW_VOLATILITY_RATIO = 0.15

# A plain callable rather than a MarketDataProvider dependency, so this module
# doesn't need to know any specific provider's full method signature - just
# "give me recent candles for this symbol".
GetRecentCandles = Callable[[str], Awaitable[Sequence[Candle]]]


class MarketRiskProvider(ABC):
    """Section 34: NORMAL / HIGH_IMPACT_NEWS_SOON / HIGH_IMPACT_NEWS_ACTIVE /
    ABNORMAL_VOLATILITY. No economic calendar is wired in yet (that's explicitly
    future work per the spec), so no implementation here can honestly report the
    NEWS states - only VolatilityMarketRiskProvider's ABNORMAL_VOLATILITY check is
    real today."""

    @abstractmethod
    async def get_risk_state(self, symbol: str) -> MarketRiskState: ...


class VolatilityMarketRiskProvider(MarketRiskProvider):
    """Flags ABNORMAL_VOLATILITY when the most recent bar's true range is a large
    multiple of the recent average (Section 34: "ATR tăng đột biến / M1 range quá
    lớn"). Never claims a news-related state - that would require calendar data
    this project doesn't have."""

    def __init__(
        self,
        get_recent_candles: GetRecentCandles,
        lookback: int = ABNORMAL_VOLATILITY_LOOKBACK,
        spike_mult: float = ABNORMAL_VOLATILITY_MULT,
    ) -> None:
        self._get_recent_candles = get_recent_candles
        self._lookback = lookback
        self._spike_mult = spike_mult

    async def get_risk_state(self, symbol: str) -> MarketRiskState:
        candles = await self._get_recent_candles(symbol)

        if len(candles) >= self._lookback + 1:
            true_range = true_range_indicator(candles_to_frame(candles)).dropna()
            if len(true_range) >= self._lookback + 1:
                recent = true_range.iloc[-self._lookback : -1]
                current = true_range.iloc[-1]
                average = float(recent.mean())
                if average > 0 and current > average * self._spike_mult:
                    return MarketRiskState.ABNORMAL_VOLATILITY

        if len(candles) >= LOW_VOLATILITY_LONG_PERIOD + 1:
            frame = candles_to_frame(candles)
            true_range = true_range_indicator(frame).dropna()
            long_atr = atr_indicator(frame, period=LOW_VOLATILITY_LONG_PERIOD).dropna()
            if len(true_range) >= LOW_VOLATILITY_SHORT_PERIOD and not long_atr.empty:
                # A plain mean of the last N bars (not Wilder's EMA, which still
                # carries real-market weight from before the quiet window even at
                # period=14) so a short, truly flat tail is reflected immediately
                # instead of being smoothed away.
                short_value = float(true_range.iloc[-LOW_VOLATILITY_SHORT_PERIOD:].mean())
                long_value = float(long_atr.iloc[-1])
                if long_value > 0 and short_value < long_value * LOW_VOLATILITY_RATIO:
                    return MarketRiskState.ABNORMAL_VOLATILITY

        return MarketRiskState.NORMAL
