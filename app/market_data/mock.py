import asyncio
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.core.enums import Timeframe
from app.core.timeframes import TIMEFRAME_DURATIONS, floor_to_interval
from app.market_data.base import Candle, MarketDataProvider, PriceTick


class MockProvider(MarketDataProvider):
    """Deterministic-per-symbol random-walk data generator.

    Not a stub: produces internally consistent OHLC candles (high/low bracket
    open/close) and a live-feeling tick stream, so downstream analysis and
    tracking code can be developed and tested without any external dependency.
    """

    def __init__(self, base_price: float = 2650.0) -> None:
        self._base_price = base_price
        self._candles: dict[tuple[str, Timeframe], list[Candle]] = {}
        self._rngs: dict[str, random.Random] = {}
        self._lock = asyncio.Lock()

    def _rng(self, symbol: str) -> random.Random:
        if symbol not in self._rngs:
            self._rngs[symbol] = random.Random(f"mock-seed:{symbol}")
        return self._rngs[symbol]

    def _generate_candle(
        self,
        symbol: str,
        timeframe: Timeframe,
        timestamp: datetime,
        open_price: float,
        rng: random.Random,
    ) -> Candle:
        volatility = max(open_price * 0.0009, 0.01)
        close = max(0.01, open_price + rng.gauss(0, volatility))
        wick_up = abs(rng.gauss(0, volatility * 0.6))
        wick_down = abs(rng.gauss(0, volatility * 0.6))
        high = max(open_price, close) + wick_up
        low = max(0.01, min(open_price, close) - wick_down)
        volume = round(abs(rng.gauss(500.0, 150.0)), 2)
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=volume,
        )

    def _ensure_candles(self, symbol: str, timeframe: Timeframe, limit: int) -> list[Candle]:
        key = (symbol, timeframe)
        interval = TIMEFRAME_DURATIONS[timeframe]
        latest_open = floor_to_interval(datetime.now(UTC), interval)
        series = self._candles.setdefault(key, [])
        rng = self._rng(symbol)

        if not series:
            start = latest_open - interval * (limit - 1)
            price = self._base_price
            ts = start
            while ts <= latest_open:
                candle = self._generate_candle(symbol, timeframe, ts, price, rng)
                series.append(candle)
                price = candle.close
                ts += interval
        else:
            price = series[-1].close
            ts = series[-1].timestamp + interval
            while ts <= latest_open:
                candle = self._generate_candle(symbol, timeframe, ts, price, rng)
                series.append(candle)
                price = candle.close
                ts += interval

        if len(series) > limit:
            del series[: len(series) - limit]
        return list(series[-limit:])

    async def get_current_price(self, symbol: str) -> PriceTick:
        async with self._lock:
            candles = self._ensure_candles(symbol, Timeframe.M1, limit=1)
        last_close = candles[-1].close
        rng = self._rng(symbol)
        jitter = rng.gauss(0, max(last_close * 0.00015, 0.005))
        mid = round(last_close + jitter, 2)
        spread = max(round(last_close * 0.00005, 2), 0.02)
        return PriceTick(
            symbol=symbol,
            price=mid,
            bid=round(mid - spread / 2, 2),
            ask=round(mid + spread / 2, 2),
            timestamp=datetime.now(UTC),
        )

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 200
    ) -> list[Candle]:
        async with self._lock:
            return self._ensure_candles(symbol, timeframe, limit)

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[PriceTick]:
        while True:
            yield await self.get_current_price(symbol)
            await asyncio.sleep(1.0)
