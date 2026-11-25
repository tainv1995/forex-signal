from app.core.config import Settings, get_settings
from app.core.enums import MarketDataProviderType
from app.core.redis import get_redis
from app.market_data.base import MarketDataProvider
from app.market_data.broker import OANDAProvider
from app.market_data.mock import MockProvider
from app.market_data.tradingview import TradingViewProvider
from app.market_data.twelvedata import TwelveDataProvider

_provider: MarketDataProvider | None = None


def _build_provider(settings: Settings) -> MarketDataProvider:
    match settings.market_data_provider:
        case MarketDataProviderType.MOCK:
            return MockProvider(base_price=settings.mock_base_price)
        case MarketDataProviderType.TRADINGVIEW:
            return TradingViewProvider(redis=get_redis())
        case MarketDataProviderType.BROKER:
            return OANDAProvider(
                api_key=settings.oanda_api_key,
                account_id=settings.oanda_account_id,
                environment=settings.oanda_environment,
                instrument=settings.oanda_instrument,
            )
        case MarketDataProviderType.TWELVEDATA:
            return TwelveDataProvider(
                api_key=settings.twelvedata_api_key,
                symbol=settings.twelvedata_symbol,
            )


def get_market_data_provider() -> MarketDataProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider(get_settings())
    return _provider


async def dispose_market_data_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.aclose()
    _provider = None
