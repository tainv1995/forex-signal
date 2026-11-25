from app.analysis.base import AnalysisResult
from app.core.enums import Direction, StrategyName, Timeframe
from app.engines.risk import calculate_stop_loss, meets_minimum_rr, reward_to_risk, risk_distance


def _result(strategy: StrategyName, levels: dict[str, float]) -> AnalysisResult:
    return AnalysisResult(
        strategy=strategy,
        direction=Direction.BUY,
        confidence=0.6,
        timeframe=Timeframe.M15,
        reason="test",
        levels=levels,
    )


def test_buy_stop_loss_sits_below_market_structure_swing_low_with_atr_buffer() -> None:
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2640.0})]

    sl = calculate_stop_loss(Direction.BUY, entry_reference=2645.0, results=results, atr_value=2.0)

    assert sl is not None
    assert sl.basis == "market_structure_swing"
    assert sl.price == 2640.0 - 2.0 * 0.25


def test_sell_stop_loss_sits_above_market_structure_swing_high_with_atr_buffer() -> None:
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_high": 2660.0})]

    sl = calculate_stop_loss(Direction.SELL, entry_reference=2655.0, results=results, atr_value=2.0)

    assert sl is not None
    assert sl.price == 2660.0 + 2.0 * 0.25


def test_picks_the_nearest_invalidation_level_below_entry() -> None:
    results = [
        _result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2630.0}),
        _result(StrategyName.SUPPORT_RESISTANCE, {"support": 2642.0}),
    ]

    sl = calculate_stop_loss(Direction.BUY, entry_reference=2645.0, results=results, atr_value=1.0)

    assert sl is not None
    assert sl.basis == "support_resistance_zone"
    assert sl.price == 2642.0 - 0.25


def test_rejects_sell_when_only_fallback_candidate_lands_below_entry() -> None:
    # Real incident (GOLD-20260909-001), SELL side: every known invalidation level
    # was BELOW the entry reference. The fallback picked the highest of them anyway
    # and added the buffer, landing at 4361.69 - still below the 4364.65-4366.50
    # entry zone. A "stop loss" below entry on a SELL is on the profit side, not the
    # loss side - must reject outright, not just check its distance.
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_high": 2640.0})]

    sl = calculate_stop_loss(Direction.SELL, entry_reference=2645.0, results=results, atr_value=1.0)

    assert sl is None


def test_rejects_when_only_fallback_candidate_lands_on_the_wrong_side_of_entry() -> None:
    # Real incident (GOLD-20260909-001): every known invalidation level for a BUY is
    # ABOVE the entry reference (unusual - normally the SL candidate is below entry).
    # The old fallback picked it anyway and just subtracted the buffer, which can
    # still land above entry - a "stop loss" that's actually in the profit direction.
    # That's never usable no matter its distance; must reject outright.
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2650.0})]

    sl = calculate_stop_loss(Direction.BUY, entry_reference=2645.0, results=results, atr_value=1.0)

    assert sl is None


def test_falls_back_to_lowest_candidate_when_it_still_lands_below_entry() -> None:
    # The fallback candidate is above entry, but the buffer is big enough to pull it
    # back below entry with enough distance to still clear MIN_SL_ATR_MULT - a
    # usable (if unusually tight) stop, so it's kept.
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2646.0})]

    sl = calculate_stop_loss(
        Direction.BUY, entry_reference=2645.0, results=results, atr_value=1.0, buffer_atr_mult=2.0
    )

    assert sl is not None
    assert sl.price == 2646.0 - 2.0


def test_none_when_no_invalidation_candidates() -> None:
    results = [_result(StrategyName.RSI_MOMENTUM, {})]

    sl = calculate_stop_loss(Direction.BUY, entry_reference=2645.0, results=results, atr_value=1.0)

    assert sl is None


def test_none_when_invalidation_level_is_too_close_to_entry() -> None:
    # Real incident (GOLD-20260830-001): the S/R zone used for entry sat right next
    # to the invalidation level too, so buffer alone left only ~0.07 of risk against
    # an ATR of 2.0 - RR blew up to 100+ on a stop that would clip on pure noise.
    # calculate_stop_loss must reject this instead of returning an unusably tight SL.
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_high": 2655.05})]

    sl = calculate_stop_loss(Direction.SELL, entry_reference=2655.0, results=results, atr_value=2.0)

    assert sl is None


def test_none_for_neutral_direction() -> None:
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2640.0})]

    sl = calculate_stop_loss(
        Direction.NEUTRAL, entry_reference=2645.0, results=results, atr_value=1.0
    )

    assert sl is None


def test_reward_to_risk_and_minimum_rr_gate() -> None:
    results = [_result(StrategyName.MARKET_STRUCTURE, {"swing_low": 2640.0})]
    sl = calculate_stop_loss(Direction.BUY, entry_reference=2645.0, results=results, atr_value=1.0)
    assert sl is not None

    risk = risk_distance(2645.0, sl)
    assert risk == 2645.0 - sl.price

    rr = reward_to_risk(2645.0, sl, target_price=2645.0 + risk * 2)
    assert rr == 2.0
    assert meets_minimum_rr(rr, min_rr=1.5) is True
    assert meets_minimum_rr(1.2, min_rr=1.5) is False
