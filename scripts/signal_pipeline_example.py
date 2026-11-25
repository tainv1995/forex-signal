"""End-to-end demo of the Phase 4 pipeline: candles -> 10 methods -> confluence ->
entry zone -> stop loss -> take profits -> R:R gate.

Usage:
    python scripts/signal_pipeline_example.py [SYMBOL] [TIMEFRAME]

Runs against MockProvider data (no live market data required) so the full decision
chain can be inspected end-to-end, the same shape the future analysis worker uses.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis.base import AnalysisResult
from app.analysis.ema_trend import analyze_ema_trend
from app.analysis.fibonacci import analyze_fibonacci
from app.analysis.liquidity_smc import analyze_liquidity_smc
from app.analysis.macd import analyze_macd
from app.analysis.market_structure import analyze_market_structure
from app.analysis.price_action import analyze_price_action
from app.analysis.rsi_momentum import analyze_rsi_momentum
from app.analysis.support_resistance import analyze_support_resistance
from app.analysis.volatility import analyze_volatility
from app.core.enums import Direction, Timeframe
from app.engines.confluence import compute_confluence
from app.engines.entry import find_entry_zone
from app.engines.risk import calculate_stop_loss, meets_minimum_rr
from app.engines.targets import calculate_take_profits
from app.market_data.base import Candle
from app.market_data.mock import MockProvider


def _run_single_timeframe_methods(
    candles: list[Candle], timeframe: Timeframe
) -> list[AnalysisResult]:
    return [
        analyze_market_structure(candles, timeframe),
        analyze_support_resistance(candles, timeframe),
        analyze_ema_trend(candles, timeframe),
        analyze_rsi_momentum(candles, timeframe),
        analyze_macd(candles, timeframe),
        analyze_volatility(candles, timeframe),
        analyze_fibonacci(candles, timeframe),
        analyze_price_action(candles, timeframe),
        analyze_liquidity_smc(candles, timeframe),
    ]


async def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    timeframe = Timeframe(sys.argv[2]) if len(sys.argv) > 2 else Timeframe.M15

    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles(symbol, timeframe, limit=300)
    current_price = candles[-1].close

    print(f"=== {symbol} {timeframe.value} pipeline - current price {current_price} ===\n")

    results = _run_single_timeframe_methods(candles, timeframe)
    for r in results:
        print(f"  [{r.strategy.value:<20}] {r.direction.value:<7} {r.confidence:.2f}  {r.reason}")

    confluence = compute_confluence(results)
    print(
        f"\nConfluence: {confluence.direction.value} tier={confluence.tier.value} "
        f"confidence={confluence.confidence:.2f} agreement={confluence.agreement}/{confluence.total_methods}"
    )

    if not confluence.is_tradeable:
        print("\n=> NO TRADE (không đủ đồng thuận hoặc confidence quá thấp)")
        return

    atr_value = next((r.metadata.get("atr") for r in results if "atr" in r.metadata), None)
    if not isinstance(atr_value, int | float) or atr_value <= 0:
        print("\n=> NO TRADE (không xác định được ATR)")
        return

    entry = find_entry_zone(confluence.direction, current_price, results, float(atr_value))
    if entry is None or not entry.reachable:
        print(f"\n=> MISSED_ENTRY hoặc không tìm được entry zone hợp lý (entry={entry})")
        return
    print(f"\nEntry zone: {entry.low:.2f} - {entry.high:.2f} (basis={entry.basis})")

    stop_loss = calculate_stop_loss(confluence.direction, entry.mid, results, float(atr_value))
    if stop_loss is None:
        print("\n=> NO TRADE (không tính được Stop Loss từ cấu trúc thị trường)")
        return
    print(f"Stop loss: {stop_loss.price:.2f} (basis={stop_loss.basis})")

    targets = calculate_take_profits(confluence.direction, entry.mid, stop_loss, results)
    if targets is None:
        print("\n=> NO TRADE (không tính được Take Profit)")
        return

    for tp in targets:
        print(f"  TP{tp.level}: {tp.price:.2f}  R:R={tp.rr:.2f}  ({tp.basis})")

    if not meets_minimum_rr(targets[0].rr, min_rr=1.5):
        print(f"\n=> REJECTED: TP1 R:R={targets[0].rr:.2f} < 1.5 (Section 21)")
        return

    direction_label = "BUY" if confluence.direction is Direction.BUY else "SELL"
    print(
        f"\n=> {direction_label} {entry.high:.2f}/{entry.low:.2f}  SL {stop_loss.price:.2f}  "
        f"TP1 {targets[0].price:.2f}  ({confluence.tier.value}, {confluence.confidence:.0%})"
    )


if __name__ == "__main__":
    asyncio.run(main())
