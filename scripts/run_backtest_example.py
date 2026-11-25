"""Example output for Phase 9's backtest engine: runs the walk-forward backtest
against MockProvider candles and prints the resulting statistics.

Usage:
    python scripts/run_backtest_example.py [SYMBOL] [TIMEFRAME] [CANDLE_COUNT]

Note on the numbers you'll see here: MockProvider is a memoryless random walk, so
it essentially never produces the kind of coordinated, high-confidence multi-method
alignment this system requires (Section 16's >=6/10 agreement at >=68% confidence) -
running this against 1000-5000 Mock candles typically yields zero signals, and that
is the correct, honest result, not a bug (see tests/test_backtest.py and
tests/test_backtest_metrics.py for the walk-forward mechanics and the statistics
math each verified independently with deterministic data). A backtest that means
something requires real historical XAUUSD data - see the "Market Data Provider"
section of the README for how to switch to OANDA/TradingView once confirmed.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.backtest.engine import run_backtest
from app.core.enums import Timeframe
from app.market_data.mock import MockProvider


async def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    timeframe = Timeframe(sys.argv[2]) if len(sys.argv) > 2 else Timeframe.M15
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 1500

    provider = MockProvider(base_price=2650.0)
    candles = await provider.get_candles(symbol, timeframe, limit=count)
    print(f"Backtesting {symbol} {timeframe.value} over {len(candles)} candles (Mock data)...\n")

    result = await run_backtest(candles, timeframe, symbol)
    stats = result.stats

    print(f"Total signals:      {stats.total_signals}")
    print(f"BUY / SELL:         {stats.buy_count} / {stats.sell_count}")
    print(f"Win / SL / Cancel:  {stats.win_count} / {stats.sl_count} / {stats.cancelled_count}")
    print(
        f"Win Rate:           {stats.win_rate:.1%}"
        if stats.win_rate is not None
        else "Win Rate:           N/A"
    )
    print(
        f"SL Rate:            {result.sl_rate:.1%}"
        if result.sl_rate is not None
        else "SL Rate:            N/A"
    )
    for level in range(1, 6):
        print(f"  TP{level} rate:       {result.tp_hit_rates.get(level, 0.0):.1%}")
    print(
        f"Average R:          {stats.average_rr:.2f}"
        if stats.average_rr is not None
        else "Average R:          N/A"
    )
    print(
        f"Expectancy:         {result.expectancy:.2f}R"
        if result.expectancy is not None
        else "Expectancy:         N/A"
    )
    print(f"Max consec. losses: {result.max_consecutive_losses}")
    print(f"Signals / day:      {result.signals_per_day:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
