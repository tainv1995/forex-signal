from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from app.core.enums import Timeframe


class MarketDataError(Exception):
    """Raised when a provider cannot reliably fulfill a market data request."""


@dataclass(frozen=True, slots=True)
class PriceTick:
    symbol: str
    price: float
    timestamp: datetime
    bid: float | None = None
    ask: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("PriceTick.timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Candle.timestamp must be timezone-aware")
        if self.high < max(self.open, self.close):
            raise ValueError(f"Candle high below open/close: {self}")
        if self.low > min(self.open, self.close):
            raise ValueError(f"Candle low above open/close: {self}")
        if self.high < self.low:
            raise ValueError(f"Candle high below low: {self}")


class MarketDataProvider(ABC):
    """Uniform interface for reading XAUUSD price data.

    Implementations swap freely (TradingView webhook, broker REST/stream, mock)
    without the analysis engine knowing which one is behind it.
    """

    @abstractmethod
    async def get_current_price(self, symbol: str) -> PriceTick: ...

    @abstractmethod
    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 200
    ) -> list[Candle]: ...

    @abstractmethod
    def subscribe_ticks(self, symbol: str) -> AsyncIterator[PriceTick]: ...

    async def aclose(self) -> None:
        """Release provider resources (HTTP clients, streams). No-op by default."""
        return
