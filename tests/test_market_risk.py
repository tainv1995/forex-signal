import pytest

from app.core.enums import MarketRiskState
from app.market_data.base import Candle
from app.market_data.risk import VolatilityMarketRiskProvider
from tests.helpers import candles_from_ohlc


def _normal_rows(n: int, base: float = 100.0) -> list[tuple[float, float, float, float]]:
    rows = []
    price = base
    for i in range(n):
        o = price
        c = price + (0.3 if i % 2 == 0 else -0.3)
        h = max(o, c) + 0.2
        low = min(o, c) - 0.2
        rows.append((o, h, low, c))
        price = c
    return rows


@pytest.mark.asyncio
async def test_normal_volatility_reports_normal() -> None:
    rows = _normal_rows(60)

    async def get_candles(symbol: str) -> list[Candle]:
        return candles_from_ohlc(rows)

    provider = VolatilityMarketRiskProvider(get_candles)

    assert await provider.get_risk_state("XAUUSD") is MarketRiskState.NORMAL


@pytest.mark.asyncio
async def test_volatility_spike_reports_abnormal() -> None:
    rows = _normal_rows(59)
    last_open = rows[-1][3]
    rows.append((last_open, last_open + 20, last_open - 20, last_open + 15))  # huge spike bar

    async def get_candles(symbol: str) -> list[Candle]:
        return candles_from_ohlc(rows)

    provider = VolatilityMarketRiskProvider(get_candles)

    assert await provider.get_risk_state("XAUUSD") is MarketRiskState.ABNORMAL_VOLATILITY


@pytest.mark.asyncio
async def test_weekend_flat_tail_reports_abnormal_low_volatility() -> None:
    # Real incident (2026-10-18): a weekend market close makes the data provider
    # fill recent bars with a near-flat repeated price instead of a true gap. ATR(14)
    # off just the recent window reads near-zero even though the market actually
    # trades with real range - must flag it as abnormal rather than let entry/risk
    # size itself off a stale, artificially tiny ATR.
    rows = _normal_rows(220)
    flat_price = rows[-1][3]
    rows += [(flat_price, flat_price + 0.01, flat_price - 0.01, flat_price) for _ in range(20)]

    async def get_candles(symbol: str) -> list[Candle]:
        return candles_from_ohlc(rows)

    provider = VolatilityMarketRiskProvider(get_candles)

    assert await provider.get_risk_state("XAUUSD") is MarketRiskState.ABNORMAL_VOLATILITY


@pytest.mark.asyncio
async def test_not_enough_candles_reports_normal_not_a_guess() -> None:
    rows = _normal_rows(10)

    async def get_candles(symbol: str) -> list[Candle]:
        return candles_from_ohlc(rows)

    provider = VolatilityMarketRiskProvider(get_candles)

    assert await provider.get_risk_state("XAUUSD") is MarketRiskState.NORMAL
