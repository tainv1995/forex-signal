from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.enums import Timeframe
from app.market_data.base import MarketDataError
from app.market_data.twelvedata import TwelveDataProvider


def test_missing_api_key_raises_market_data_error() -> None:
    with pytest.raises(MarketDataError):
        TwelveDataProvider(api_key="")


@pytest.mark.asyncio
async def test_get_current_price_parses_price_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/price"
        assert request.url.params["symbol"] == "XAU/USD"
        assert request.url.params["apikey"] == "test-key"
        return httpx.Response(200, json={"price": "2660.50"})

    provider = TwelveDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))
    tick = await provider.get_current_price("XAUUSD")

    assert tick.price == 2660.50
    assert tick.symbol == "XAUUSD"


@pytest.mark.asyncio
async def test_get_current_price_raises_on_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "message": "invalid apikey"})

    provider = TwelveDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))

    with pytest.raises(MarketDataError):
        await provider.get_current_price("XAUUSD")


@pytest.mark.asyncio
async def test_get_candles_drops_still_forming_bar_and_maps_interval() -> None:
    closed_bar_time = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    forming_bar_time = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/time_series"
        assert request.url.params["interval"] == "15min"
        assert request.url.params["symbol"] == "XAU/USD"
        return httpx.Response(
            200,
            json={
                "values": [
                    {
                        "datetime": closed_bar_time,
                        "open": "2660.0",
                        "high": "2662.0",
                        "low": "2659.0",
                        "close": "2661.5",
                        "volume": "500",
                    },
                    {
                        "datetime": forming_bar_time,
                        "open": "2661.5",
                        "high": "2661.9",
                        "low": "2661.4",
                        "close": "2661.8",
                        "volume": "10",
                    },
                ]
            },
        )

    provider = TwelveDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))
    candles = await provider.get_candles("XAUUSD", Timeframe.M15, limit=10)

    assert len(candles) == 1
    assert candles[0].close == 2661.5
    assert candles[0].symbol == "XAUUSD"


@pytest.mark.asyncio
async def test_get_candles_raises_on_error_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "message": "invalid apikey"})

    provider = TwelveDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))

    with pytest.raises(MarketDataError):
        await provider.get_candles("XAUUSD", Timeframe.M15)


@pytest.mark.asyncio
async def test_subscribe_ticks_yields_from_current_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"price": "2660.50"})

    provider = TwelveDataProvider(api_key="test-key", transport=httpx.MockTransport(handler))
    stream = provider.subscribe_ticks("XAUUSD")
    tick = await stream.__anext__()

    assert tick.price == 2660.50
