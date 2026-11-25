from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName, Timeframe
from app.engines.entry import find_entry_zone


def _result(
    strategy: StrategyName, levels: dict[str, float], direction: Direction = Direction.BUY
) -> AnalysisResult:
    return AnalysisResult(
        strategy=strategy,
        direction=direction,
        confidence=0.6 if direction is not Direction.NEUTRAL else 0.0,
        timeframe=Timeframe.M15,
        reason="test",
        levels=levels,
    )


def test_buy_entry_zone_centers_on_nearest_support_below_price() -> None:
    results = [
        _result(StrategyName.SUPPORT_RESISTANCE, {"support": 2640.0}),
        _result(StrategyName.EMA_TREND, {"ema20": 2635.0}),
    ]

    zone = find_entry_zone(Direction.BUY, current_price=2650.0, results=results, atr_value=6.0)

    assert zone is not None
    assert zone.basis == "support_zone"
    assert zone.low < 2640.0 < zone.high
    assert zone.reachable is True


def test_sell_entry_zone_centers_on_nearest_resistance_above_price() -> None:
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"resistance": 2660.0})]

    zone = find_entry_zone(Direction.SELL, current_price=2650.0, results=results, atr_value=2.0)

    assert zone is not None
    assert zone.basis == "support_zone"
    assert zone.low < 2660.0 < zone.high


def test_unreachable_when_price_has_run_too_far_from_any_pullback_level() -> None:
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"support": 2500.0})]

    zone = find_entry_zone(Direction.BUY, current_price=2650.0, results=results, atr_value=2.0)

    assert zone is not None
    assert zone.reachable is False


def test_fibonacci_golden_zone_is_a_valid_entry_candidate() -> None:
    results = [
        _result(StrategyName.FIBONACCI, {"fib_0.5": 2644.0, "fib_0.618": 2642.0}),
    ]

    zone = find_entry_zone(Direction.BUY, current_price=2650.0, results=results, atr_value=2.0)

    assert zone is not None
    assert zone.basis == "fib_golden_zone"
    assert zone.mid == 2643.0


def test_none_when_no_candidate_levels_available() -> None:
    results = [_result(StrategyName.RSI_MOMENTUM, {})]

    zone = find_entry_zone(Direction.BUY, current_price=2650.0, results=results, atr_value=2.0)

    assert zone is None


def test_none_for_neutral_direction() -> None:
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"support": 2640.0})]

    zone = find_entry_zone(Direction.NEUTRAL, current_price=2650.0, results=results, atr_value=2.0)

    assert zone is None
