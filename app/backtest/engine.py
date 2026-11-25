from collections.abc import Sequence

from app.analysis.ema_trend import analyze_ema_trend
from app.analysis.fibonacci import analyze_fibonacci
from app.analysis.indicators import atr as atr_indicator
from app.analysis.indicators import candles_to_frame
from app.analysis.liquidity_smc import analyze_liquidity_smc
from app.analysis.macd import analyze_macd
from app.analysis.market_structure import analyze_market_structure
from app.analysis.price_action import analyze_price_action
from app.analysis.support_resistance import analyze_support_resistance
from app.analysis.volatility import analyze_volatility
from app.backtest.metrics import BacktestResult, summarize_backtest
from app.core.enums import Direction, SignalStatus, Timeframe
from app.engines.confluence import compute_confluence
from app.engines.entry import find_entry_zone
from app.engines.risk import calculate_stop_loss, meets_minimum_rr
from app.engines.signal import Signal, activate, build_signal, stop_out
from app.engines.targets import calculate_take_profits, rr_ladder_for
from app.market_data.base import Candle
from app.tracking.signal_tracker import evaluate_active_signal

# Direction/confluence voters (mirrors app/workers/analysis_worker.py exactly -
# Section 41 forbids a separate "backtest-only" strategy). RSI Momentum and
# Multi-timeframe stay removed entirely.
BACKTEST_METHODS = (
    analyze_market_structure,
    analyze_support_resistance,
    analyze_liquidity_smc,
    analyze_price_action,
)

# EMA Trend, MACD, Volatility and Fibonacci are purely passive here too - no
# confluence vote, only real price levels for entry/risk/targets.
STRUCTURAL_ONLY_METHODS = (
    analyze_ema_trend,
    analyze_macd,
    analyze_volatility,
    analyze_fibonacci,
)

DEFAULT_MIN_LOOKBACK = 250
DEFAULT_COOLDOWN_BARS = 4


def _latest_atr(window: Sequence[Candle]) -> float | None:
    series = atr_indicator(candles_to_frame(window), period=14).dropna()
    return float(series.iloc[-1]) if not series.empty else None


def _advance_signal(signal: Signal, bar: Candle) -> tuple[Signal, bool]:
    """Steps one open signal forward by one historical bar, using that bar's
    high/low (not just its close) so entry/TP/SL touches are simulated the way
    real intrabar price action would trigger them. If a single bar's range covers
    both the SL and a TP, the SL is assumed to have printed first - the standard
    conservative assumption for OHLC-only backtesting (we can't know the true
    intrabar order from open/high/low/close alone)."""
    if signal.status is SignalStatus.WAITING_ENTRY:
        touched = bar.low <= signal.entry_high and bar.high >= signal.entry_low
        if touched:
            return activate(signal, bar.timestamp), False
        return signal, False

    adverse = bar.low if signal.direction is Direction.BUY else bar.high
    hit_sl = (
        adverse <= signal.stop_loss
        if signal.direction is Direction.BUY
        else adverse >= signal.stop_loss
    )
    if hit_sl:
        return stop_out(signal, bar.timestamp), True

    # Reuses the exact same production tracker used for live signals - a big bar
    # that clears several TPs at once is handled identically here (Section 25).
    favorable = bar.high if signal.direction is Direction.BUY else bar.low
    current = signal
    for step in evaluate_active_signal(signal, favorable, bar.timestamp):
        current = step.signal

    return current, current.is_terminal


async def run_backtest(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    symbol: str,
    signal_id_prefix: str = "BT",
    min_lookback: int = DEFAULT_MIN_LOOKBACK,
    cooldown_bars: int = DEFAULT_COOLDOWN_BARS,
    min_rr: float = 1.5,
) -> BacktestResult:
    """Walks forward through `candles` one bar at a time, at each step handing only
    `candles[:i+1]` to the analysis pipeline - the same no-look-ahead discipline
    Section 42 requires. Runs the exact production analyze_* / compute_confluence /
    find_entry_zone / calculate_stop_loss / calculate_take_profits functions; this
    file adds no separate scoring logic of its own, only the walk-forward loop and
    a bar-by-bar entry/TP/SL simulator (see _advance_signal).

    Single timeframe only - see BACKTEST_METHODS for why multi_timeframe is skipped.
    Only one position open at a time (a new setup is not evaluated while one is
    already live), consistent with Section 51's "never two active signals at once".
    """
    if len(candles) <= min_lookback:
        return summarize_backtest([], days_covered=0.0)

    signals: list[Signal] = []
    open_signal: Signal | None = None
    sequence = 0
    last_signal_bar: int | None = None

    for i in range(min_lookback, len(candles)):
        window = candles[: i + 1]
        bar = window[-1]

        if open_signal is not None:
            open_signal, closed = _advance_signal(open_signal, bar)
            if closed:
                signals.append(open_signal)
                open_signal = None
            continue

        if last_signal_bar is not None and i - last_signal_bar < cooldown_bars:
            continue

        results = [method(window, timeframe) for method in BACKTEST_METHODS]
        confluence = compute_confluence(results)
        if not confluence.is_tradeable:
            continue

        atr_value = _latest_atr(window)
        if atr_value is None or atr_value <= 0:
            continue

        structural_extra = [method(window, timeframe) for method in STRUCTURAL_ONLY_METHODS]
        level_sources = results + structural_extra

        entry = find_entry_zone(confluence.direction, bar.close, level_sources, atr_value)
        if entry is None or not entry.reachable:
            continue

        stop_loss = calculate_stop_loss(confluence.direction, entry.mid, level_sources, atr_value)
        if stop_loss is None:
            continue

        targets = calculate_take_profits(
            confluence.direction,
            entry.mid,
            stop_loss,
            level_sources,
            rr_ladder=rr_ladder_for(min_rr),
        )
        if targets is None or not meets_minimum_rr(targets[0].rr, min_rr):
            continue

        sequence += 1
        new_signal = build_signal(
            signal_id=f"{signal_id_prefix}-{sequence:04d}",
            symbol=symbol,
            direction=confluence.direction,
            entry_low=entry.low,
            entry_high=entry.high,
            stop_loss=stop_loss,
            take_profits=targets,
            confidence=confluence.confidence,
            confluence_tier=confluence.tier,
            agreement=confluence.agreement,
            reasons=confluence.reasons,
            timeframe=timeframe.value,
            created_at=bar.timestamp,
        )
        open_signal = new_signal
        last_signal_bar = i

    if open_signal is not None:
        signals.append(open_signal)

    days_covered = (candles[-1].timestamp - candles[min_lookback].timestamp).total_seconds() / 86400
    return summarize_backtest(signals, days_covered=max(days_covered, 1e-9))
