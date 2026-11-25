import httpx
import pytest

from app.core.enums import Timeframe
from app.market_data.base import MarketDataError
from app.market_data.broker import OANDAProvider


def test_missing_credentials_raise_market_data_error() -> None:
    with pytest.raises(MarketDataError):
        OANDAProvider(api_key="", account_id="")


@pytest.mark.asyncio
async def test_get_current_price_parses_oanda_pricing_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/accounts/acc-1/pricing"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "prices": [
                    {
                        "time": "2026-08-17T13:50:00.123456789Z",
                        "bids": [{"price": "2660.50"}],
                        "asks": [{"price": "2660.80"}],
                    }
                ]
            },
        )

    provider = OANDAProvider(
        api_key="test-key",
        account_id="acc-1",
        transport=httpx.MockTransport(handler),
    )
    tick = await provider.get_current_price("XAUUSD")

    assert tick.bid == 2660.50
    assert tick.ask == 2660.80
    assert tick.price == pytest.approx(2660.65)
    assert tick.timestamp.microsecond == 123456


@pytest.mark.asyncio
async def test_get_current_price_raises_when_no_prices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"prices": []})

    provider = OANDAProvider(
        api_key="test-key", account_id="acc-1", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(MarketDataError):
        await provider.get_current_price("XAUUSD")


@pytest.mark.asyncio
async def test_get_candles_skips_incomplete_candle_and_maps_granularity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/instruments/XAU_USD/candles"
        assert request.url.params["granularity"] == "M15"
        return httpx.Response(
            200,
            json={
                "candles": [
                    {
                        "time": "2026-08-17T13:30:00.000000000Z",
                        "complete": True,
                        "volume": 500,
                        "mid": {"o": "2660.0", "h": "2662.0", "l": "2659.0", "c": "2661.5"},
                    },
                    {
                        "time": "2026-08-17T13:45:00.000000000Z",
                        "complete": False,
                        "volume": 10,
                        "mid": {"o": "2661.5", "h": "2661.6", "l": "2661.4", "c": "2661.5"},
                    },
                ]
            },
        )

    provider = OANDAProvider(
        api_key="test-key", account_id="acc-1", transport=httpx.MockTransport(handler)
    )
    candles = await provider.get_candles("XAUUSD", Timeframe.M15, limit=10)

    assert len(candles) == 1
    assert candles[0].close == 2661.5
    assert candles[0].symbol == "XAUUSD"
