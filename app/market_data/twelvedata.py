import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx

from app.core.enums import Timeframe
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceTick

_INTERVAL: dict[Timeframe, str] = {
    Timeframe.M1: "1min",
    Timeframe.M5: "5min",
    Timeframe.M15: "15min",
    Timeframe.M30: "30min",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1day",
}

_DURATION: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}


def _parse_datetime(raw: str) -> datetime:
    fmt = "%Y-%m-%d %H:%M:%S" if len(raw) > 10 else "%Y-%m-%d"
    return datetime.strptime(raw, fmt).replace(tzinfo=UTC)


class TwelveDataProvider(MarketDataProvider):
    """https://twelvedata.com REST API - a free-tier *market data* API (email
    signup only, no trading/broker account) that covers XAU/USD spot gold with
    real OHLC candles across timeframes. Authenticated REST calls only, same
    "no scraping" rule as every other provider in this module.
    """

    def __init__(
        self,
        api_key: str,
        symbol: str = "XAU/USD",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise MarketDataError("TWELVEDATA_API_KEY must be set to use the twelvedata provider")
        self._symbol = symbol
        self._client = httpx.AsyncClient(
            base_url="https://api.twelvedata.com",
            params={"apikey": api_key},
            timeout=10.0,
            transport=transport,
        )

    async def get_current_price(self, symbol: str) -> PriceTick:
        try:
            response = await self._client.get("/price", params={"symbol": self._symbol})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Twelve Data request failed for {self._symbol}: {exc}") from exc
        payload = response.json()
        if "price" not in payload:
            raise MarketDataError(f"Twelve Data error for {self._symbol}: {payload}")
        # /price has no timestamp field - it's defined as "the latest available
        # price", so the fetch time is an honest timestamp for it (not a guess).
        return PriceTick(symbol=symbol, price=float(payload["price"]), timestamp=datetime.now(UTC))

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 200
    ) -> list[Candle]:
        try:
            response = await self._client.get(
                "/time_series",
                params={
                    "symbol": self._symbol,
                    "interval": _INTERVAL[timeframe],
                    "outputsize": min(limit + 1, 5000),
                    "order": "asc",
                    "timezone": "UTC",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Twelve Data request failed for {self._symbol}: {exc}") from exc
        payload = response.json()
        values = payload.get("values")
        if values is None:
            raise MarketDataError(f"Twelve Data error for {self._symbol}: {payload}")

        candles = [
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=_parse_datetime(raw["datetime"]),
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                volume=float(raw["volume"]) if raw.get("volume") is not None else None,
            )
            for raw in values
        ]

        # Twelve Data does not flag whether the newest bar is still forming, so -
        # same discipline as the OANDA provider's `complete` filter (Section 42: no
        # look-ahead bias) - drop any bar whose period hasn't fully elapsed yet.
        now = datetime.now(UTC)
        duration = _DURATION[timeframe]
        closed = [c for c in candles if c.timestamp + duration <= now]
        return closed[-limit:]

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[PriceTick]:
        # Free tier has no push/streaming endpoint - poll the same REST call the
        # rest of the app uses, same pattern as MockProvider.subscribe_ticks.
        while True:
            yield await self.get_current_price(symbol)
            await asyncio.sleep(5.0)

    async def aclose(self) -> None:
        await self._client.aclose()
