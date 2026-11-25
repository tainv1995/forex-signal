import json
from collections.abc import AsyncIterator

import httpx

from app.core.enums import Timeframe
from app.core.logging import get_logger
from app.core.time import parse_iso8601
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceTick

logger = get_logger(__name__)

_OANDA_GRANULARITY: dict[Timeframe, str] = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
}


class OANDAProvider(MarketDataProvider):
    """Official OANDA v20 REST/stream API - a legitimate swap-in for TradingView.

    Requires a free OANDA practice (demo) account: https://www.oanda.com/demo-account/
    No scraping, no cookie/session bypass - just an authenticated REST API call.
    """

    def __init__(
        self,
        api_key: str,
        account_id: str,
        environment: str = "practice",
        instrument: str = "XAU_USD",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key or not account_id:
            raise MarketDataError(
                "OANDA_API_KEY and OANDA_ACCOUNT_ID must be set to use the broker provider"
            )
        self._instrument = instrument
        self._account_id = account_id
        rest_host = (
            "api-fxpractice.oanda.com" if environment == "practice" else "api-fxtrade.oanda.com"
        )
        self._stream_host = (
            "stream-fxpractice.oanda.com"
            if environment == "practice"
            else "stream-fxtrade.oanda.com"
        )
        self._client = httpx.AsyncClient(
            base_url=f"https://{rest_host}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )

    async def get_current_price(self, symbol: str) -> PriceTick:
        try:
            response = await self._client.get(
                f"/v3/accounts/{self._account_id}/pricing",
                params={"instruments": self._instrument},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError(f"OANDA request failed for {self._instrument}: {exc}") from exc
        prices = response.json().get("prices") or []
        if not prices:
            raise MarketDataError(f"OANDA returned no pricing for {self._instrument}")
        quote = prices[0]
        bid = float(quote["bids"][0]["price"])
        ask = float(quote["asks"][0]["price"])
        return PriceTick(
            symbol=symbol,
            price=round((bid + ask) / 2, 5),
            bid=bid,
            ask=ask,
            timestamp=parse_iso8601(quote["time"]),
        )

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 200
    ) -> list[Candle]:
        granularity = _OANDA_GRANULARITY[timeframe]
        try:
            response = await self._client.get(
                f"/v3/instruments/{self._instrument}/candles",
                params={"granularity": granularity, "count": min(limit, 5000), "price": "M"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataError(f"OANDA request failed for {self._instrument}: {exc}") from exc
        candles: list[Candle] = []
        for raw in response.json().get("candles", []):
            if not raw.get("complete", False):
                continue  # never expose the still-forming candle (Section 42: no look-ahead)
            mid = raw["mid"]
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=parse_iso8601(raw["time"]),
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=float(raw.get("volume", 0)),
                )
            )
        return candles

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[PriceTick]:
        url = f"https://{self._stream_host}/v3/accounts/{self._account_id}/pricing/stream"
        async with (
            httpx.AsyncClient(headers=self._client.headers, timeout=None) as stream_client,
            stream_client.stream("GET", url, params={"instruments": self._instrument}) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                payload = json.loads(line)
                if payload.get("type") != "PRICE":
                    continue
                bid = float(payload["bids"][0]["price"])
                ask = float(payload["asks"][0]["price"])
                yield PriceTick(
                    symbol=symbol,
                    price=round((bid + ask) / 2, 5),
                    bid=bid,
                    ask=ask,
                    timestamp=parse_iso8601(payload["time"]),
                )

    async def aclose(self) -> None:
        await self._client.aclose()
