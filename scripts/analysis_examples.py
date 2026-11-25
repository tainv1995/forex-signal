"""Run all 10 analysis methods against MockProvider candles and print the output.

Usage:
    python scripts/analysis_examples.py [SYMBOL] [TIMEFRAME]

This is the "Example Output" deliverable for Phase 3 - it exercises every method
end-to-end against a realistic (if synthetic) OHLC series, the same way the future
analysis worker will, without requiring a live market data connection.
"""

import asyncio
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis.ema_trend import analyze_ema_trend
from app.analysis.fibonacci import analyze_fibonacci
from app.analysis.liquidity_smc import analyze_liquidity_smc
from app.analysis.macd import analyze_macd
from app.analysis.market_structure import analyze_market_structure
from app.analysis.multi_timeframe import analyze_multi_timeframe
from app.analysis.price_action import analyze_price_action
from app.analysis.rsi_momentum import analyze_rsi_momentum
from app.analysis.support_resistance import analyze_support_resistance
from app.analysis.volatility import analyze_volatility
from app.core.enums import Timeframe
from app.market_data.mock import MockProvider


def _print_result(result: object) -> None:
    data = asdict(result)  # type: ignore[call-overload]
    direction = data["direction"].value
    confidence = data["confidence"]
    strategy = data["strategy"].value
    print(f"[{strategy:<20}] {direction:<7} confidence={confidence:.2f}  {data['reason']}")
    if data["levels"]:
        print(f"{'':24}levels: {data['levels']}")


async def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    timeframe = Timeframe(sys.argv[2]) if len(sys.argv) > 2 else Timeframe.M15

    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles(symbol, timeframe, limit=300)
    tick = await provider.get_current_price(symbol)

    print(f"=== {symbol} {timeframe.value} - {len(candles)} candles, last price {tick.price} ===\n")

    _print_result(analyze_market_structure(candles, timeframe))
    _print_result(analyze_support_resistance(candles, timeframe))
    _print_result(analyze_ema_trend(candles, timeframe))
    _print_result(analyze_rsi_momentum(candles, timeframe))
    _print_result(analyze_macd(candles, timeframe))
    _print_result(analyze_volatility(candles, timeframe))
    _print_result(analyze_fibonacci(candles, timeframe))
    _print_result(analyze_price_action(candles, timeframe))
    _print_result(analyze_liquidity_smc(candles, timeframe))

    print("\n--- multi_timeframe (bias per timeframe, from market_structure) ---")
    bias = {}
    for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M30, Timeframe.M15, Timeframe.M5):
        tf_candles = await provider.get_candles(symbol, tf, limit=300)
        tf_result = analyze_market_structure(tf_candles, tf)
        direction = tf_result.direction
        bias[tf] = (direction, max(tf_result.confidence, 0.5))
        print(
            f"  {tf.value:<4} -> {direction.value} ({tf_result.confidence:.2f}) - {tf_result.reason}"
        )
    _print_result(analyze_multi_timeframe(bias, timeframe))


if __name__ == "__main__":
    asyncio.run(main())
