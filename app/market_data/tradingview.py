import json
from collections.abc import AsyncIterator
from datetime import datetime

from redis.asyncio import Redis

from app.core.enums import Timeframe
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceTick

TICK_KEY = "tv:tick:{symbol}"
TICK_CHANNEL = "tv:ticks:{symbol}"
CANDLES_KEY = "tv:candles:{symbol}:{timeframe}"
MAX_CACHED_CANDLES = 500


def tick_key(symbol: str) -> str:
    return TICK_KEY.format(symbol=symbol)


def tick_channel(symbol: str) -> str:
    return TICK_CHANNEL.format(symbol=symbol)


def candles_key(symbol: str, timeframe: Timeframe) -> str:
    return CANDLES_KEY.format(symbol=symbol, timeframe=timeframe.value)


def _tick_to_json(tick: PriceTick) -> str:
    return json.dumps(
        {
            "symbol": tick.symbol,
            "price": tick.price,
            "bid": tick.bid,
            "ask": tick.ask,
            "timestamp": tick.timestamp.isoformat(),
        }
    )


def _tick_from_json(raw: str) -> PriceTick:
    data = json.loads(raw)
    return PriceTick(
        symbol=data["symbol"],
        price=data["price"],
        bid=data.get("bid"),
        ask=data.get("ask"),
        timestamp=datetime.fromisoformat(data["timestamp"]),
    )


def _candle_to_json(candle: Candle) -> str:
    return json.dumps(
        {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe.value,
            "timestamp": candle.timestamp.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
    )


def _candle_from_json(raw: str) -> Candle:
    data = json.loads(raw)
    return Candle(
        symbol=data["symbol"],
        timeframe=Timeframe(data["timeframe"]),
        timestamp=datetime.fromisoformat(data["timestamp"]),
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data.get("volume"),
    )


class TradingViewProvider(MarketDataProvider):
    """Reads data pushed in by the TradingView Alert -> Webhook -> Backend flow.

    TradingView has no stable public API for pulling realtime candles without
    scraping or bypassing auth/CAPTCHA, which this project will not do. Instead,
    the user configures a TradingView alert (webhook action, "Once Per Bar Close")
    that POSTs to /webhook/tradingview; that endpoint (app/api/webhook.py) writes
    here via Redis, and this provider only ever reads what has actually arrived.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_current_price(self, symbol: str) -> PriceTick:
        raw = await self._redis.get(tick_key(symbol))
        if raw is None:
            raise MarketDataError(
                f"No TradingView tick received yet for {symbol}. "
                "Configure a TradingView webhook alert pointing at /webhook/tradingview."
            )
        return _tick_from_json(str(raw))

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 200
    ) -> list[Candle]:
        raw_list = await self._redis.lrange(candles_key(symbol, timeframe), 0, limit - 1)
        candles = [_candle_from_json(str(raw)) for raw in raw_list]
        return list(reversed(candles))

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[PriceTick]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(tick_channel(symbol))
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield _tick_from_json(str(message["data"]))
        finally:
            await pubsub.unsubscribe(tick_channel(symbol))
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    @staticmethod
    async def store_tick(redis: Redis, tick: PriceTick) -> None:
        await redis.set(tick_key(tick.symbol), _tick_to_json(tick), ex=3600)
        await redis.publish(tick_channel(tick.symbol), _tick_to_json(tick))

    @staticmethod
    async def store_candle(redis: Redis, candle: Candle) -> None:
        key = candles_key(candle.symbol, candle.timeframe)
        await redis.lpush(key, _candle_to_json(candle))
        await redis.ltrim(key, 0, MAX_CACHED_CANDLES - 1)
