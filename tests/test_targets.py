from itertools import pairwise

from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName, Timeframe
from app.engines.risk import StopLoss, meets_minimum_rr
from app.engines.targets import calculate_take_profits, rr_ladder_for


def _result(
    strategy: StrategyName, levels: dict[str, float], direction: Direction = Direction.BUY
) -> AnalysisResult:
    return AnalysisResult(
        strategy=strategy,
        direction=direction,
        confidence=0.6,
        timeframe=Timeframe.M15,
        reason="test",
        levels=levels,
    )


def test_pure_rr_projection_ladder_when_no_structural_levels() -> None:
    sl = StopLoss(price=2640.0, basis="test")
    targets = calculate_take_profits(
        Direction.BUY, entry_reference=2645.0, stop_loss=sl, results=[]
    )

    assert targets is not None
    assert [t.level for t in targets] == [1, 2, 3, 4, 5]
    assert all(t.basis == "rr_projection" for t in targets)
    prices = [t.price for t in targets]
    assert prices == sorted(prices)
    assert prices[0] < prices[-1]


def test_targets_are_strictly_increasing_for_buy() -> None:
    sl = StopLoss(price=2640.0, basis="test")
    targets = calculate_take_profits(
        Direction.BUY, entry_reference=2645.0, stop_loss=sl, results=[]
    )

    assert targets is not None
    prices = [t.price for t in targets]
    assert all(b > a for a, b in pairwise(prices))
    assert all(t.rr > 0 for t in targets)


def test_targets_are_strictly_decreasing_for_sell() -> None:
    sl = StopLoss(price=2660.0, basis="test")
    targets = calculate_take_profits(
        Direction.SELL, entry_reference=2655.0, stop_loss=sl, results=[]
    )

    assert targets is not None
    prices = [t.price for t in targets]
    assert all(b < a for a, b in pairwise(prices))


def test_structural_resistance_level_is_used_when_close_to_a_rung() -> None:
    sl = StopLoss(price=2640.0, basis="test")  # risk = 5
    # TP2 rung is entry + 1.5*risk = 2645 + 7.5 = 2652.5; put resistance right there.
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"resistance": 2652.5})]

    targets = calculate_take_profits(
        Direction.BUY, entry_reference=2645.0, stop_loss=sl, results=results
    )

    assert targets is not None
    structural = [t for t in targets if t.basis == "structural"]
    assert len(structural) == 1
    assert structural[0].price == 2652.5


def test_a_distant_structural_level_does_not_get_claimed_by_an_early_rung() -> None:
    # Real incident (GOLD-20260903-001): a structural level far beyond TP1's 1.0R
    # rung (here 3.08R) used to get greedily claimed by the first rung whose *lower*
    # bound it cleared, leaving TP2-TP5 with no candidates left and forcing them into
    # a bunched-up monotonic patch right after TP1. It must instead land on the rung
    # it's actually close to (3.0R -> TP4), leaving TP1-TP3 as normal, well-separated
    # R-multiple projections.
    sl = StopLoss(price=2640.0, basis="test")  # risk = 5
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"resistance": 2645.0 + 3.08 * 5})]

    targets = calculate_take_profits(
        Direction.BUY, entry_reference=2645.0, stop_loss=sl, results=results
    )

    assert targets is not None
    assert targets[0].basis == "rr_projection"
    assert targets[0].price == 2645.0 + 1.0 * 5
    assert targets[1].basis == "rr_projection"
    assert targets[1].price == 2645.0 + 1.5 * 5
    assert targets[2].basis == "rr_projection"
    assert targets[2].price == 2645.0 + 2.0 * 5
    assert targets[3].basis == "structural"
    assert targets[3].price == 2645.0 + 3.08 * 5
    prices = [t.price for t in targets]
    assert prices == sorted(prices)


def test_fibonacci_extensions_are_valid_target_candidates() -> None:
    sl = StopLoss(price=2640.0, basis="test")
    results = [_result(StrategyName.FIBONACCI, {"fib_ext_1.272": 2660.0, "fib_ext_1.618": 2670.0})]

    targets = calculate_take_profits(
        Direction.BUY, entry_reference=2645.0, stop_loss=sl, results=results
    )

    assert targets is not None
    structural_prices = {t.price for t in targets if t.basis == "structural"}
    assert 2660.0 in structural_prices or 2670.0 in structural_prices


def test_rr_ladder_for_scales_tp1_to_exactly_min_rr() -> None:
    # Real incident (2026-09-08): DEFAULT_RR_LADDER's first rung is 1.0, and
    # STRUCTURAL_MATCH_UPPER_TOLERANCE caps TP1 at 1.3x that rung - with the fixed
    # ladder and MIN_RR at its default 1.5, TP1 could never legally clear
    # meets_minimum_rr(), so every single signal was silently rejected for 5 days.
    # rr_ladder_for(min_rr) must put TP1 at exactly min_rr (passes with equality).
    sl = StopLoss(price=2640.0, basis="test")  # risk = 5
    min_rr = 1.5

    targets = calculate_take_profits(
        Direction.BUY,
        entry_reference=2645.0,
        stop_loss=sl,
        results=[],
        rr_ladder=rr_ladder_for(min_rr),
    )

    assert targets is not None
    assert targets[0].rr == min_rr
    assert meets_minimum_rr(targets[0].rr, min_rr) is True
    prices = [t.price for t in targets]
    assert prices == sorted(prices)


def test_structural_tp1_below_min_rr_is_rejected_in_favor_of_projection() -> None:
    # Found while verifying the fix above: a structural level between 80% and 100%
    # of TP1's rung (rr_ladder_for(min_rr)'s exact min_rr) used to pass TP1's
    # [80%, 130%] band while its own rr still fell short of min_rr - defeating the
    # whole point of scaling the ladder. TP1's lower bound must be the ratio itself
    # (min_rr), not 80% of it; a candidate at 0.9x min_rr must be skipped in favor of
    # the plain projection, which lands at exactly min_rr.
    sl = StopLoss(price=2640.0, basis="test")  # risk = 5
    min_rr = 1.5
    # 0.9 * min_rr = 1.35R - inside the old [1.2, 1.95] band but below min_rr itself.
    results = [_result(StrategyName.SUPPORT_RESISTANCE, {"resistance": 2645.0 + 0.9 * min_rr * 5})]

    targets = calculate_take_profits(
        Direction.BUY,
        entry_reference=2645.0,
        stop_loss=sl,
        results=results,
        rr_ladder=rr_ladder_for(min_rr),
    )

    assert targets is not None
    assert targets[0].basis == "rr_projection"
    assert targets[0].rr == min_rr
    assert meets_minimum_rr(targets[0].rr, min_rr) is True


def test_none_for_neutral_direction() -> None:
    sl = StopLoss(price=2640.0, basis="test")
    assert calculate_take_profits(Direction.NEUTRAL, 2645.0, sl, []) is None


def test_none_when_risk_is_zero() -> None:
    sl = StopLoss(price=2645.0, basis="test")
    assert calculate_take_profits(Direction.BUY, 2645.0, sl, []) is None
