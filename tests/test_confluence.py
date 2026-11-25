from app.analysis.base import AnalysisResult
from app.core.enums import Direction, SignalTier, StrategyName, Timeframe
from app.engines.confluence import compute_confluence

ALL_STRATEGIES = list(StrategyName)


def _result(strategy: StrategyName, direction: Direction, confidence: float) -> AnalysisResult:
    return AnalysisResult(
        strategy=strategy,
        direction=direction,
        confidence=confidence,
        timeframe=Timeframe.M15,
        reason=f"{strategy.value} says {direction.value}",
    )


def test_strong_majority_buy_reaches_strong_or_higher_tier() -> None:
    results = [_result(s, Direction.BUY, 0.85) for s in ALL_STRATEGIES]

    confluence = compute_confluence(results)

    assert confluence.direction == Direction.BUY
    assert confluence.agreement == 10
    assert confluence.tier in (SignalTier.STRONG, SignalTier.VERY_STRONG)
    assert confluence.is_tradeable


def test_below_minimum_agreement_ratio_forces_no_trade_even_with_high_scores() -> None:
    # Only 1 method votes BUY (very confident) against 3 voting SELL (less confident) -
    # BUY still wins on weighted score, but the agreement gate is a ratio of the winning
    # side's votes over ALL voting (non-NEUTRAL) methods: 1/4 = 25%, below the >50% floor,
    # so Section 16's agreement gate must still block it regardless of the score.
    buy_strategies = [StrategyName.MARKET_STRUCTURE]
    sell_strategies = [
        StrategyName.LIQUIDITY_SMC,
        StrategyName.MULTI_TIMEFRAME,
        StrategyName.SUPPORT_RESISTANCE,
    ]
    voting = buy_strategies + sell_strategies
    results = [_result(s, Direction.BUY, 0.95) for s in buy_strategies]
    results += [_result(s, Direction.SELL, 0.6) for s in sell_strategies]
    results += [_result(s, Direction.NEUTRAL, 0.0) for s in ALL_STRATEGIES if s not in voting]

    confluence = compute_confluence(results)

    assert confluence.tier == SignalTier.NO_TRADE
    assert confluence.direction == Direction.NEUTRAL
    assert not confluence.is_tradeable


def test_strong_tier_downgraded_to_valid_without_seventy_percent_ratio() -> None:
    # 4 BUY vs 3 SELL voters (3 NEUTRAL) = 4/7 ~= 57% agreement ratio - clears the >50%
    # floor for a normal signal, but Section 16 requires >70% agreement for a STRONG
    # tier, so a STRONG-level confidence gets capped down to VALID.
    buy_strategies = [
        StrategyName.MARKET_STRUCTURE,
        StrategyName.LIQUIDITY_SMC,
        StrategyName.MULTI_TIMEFRAME,
        StrategyName.SUPPORT_RESISTANCE,
    ]
    sell_strategies = [StrategyName.PRICE_ACTION, StrategyName.FIBONACCI, StrategyName.MACD]
    voting = buy_strategies + sell_strategies
    results = [_result(s, Direction.BUY, 0.85) for s in buy_strategies]
    results += [_result(s, Direction.SELL, 0.5) for s in sell_strategies]
    results += [_result(s, Direction.NEUTRAL, 0.0) for s in ALL_STRATEGIES if s not in voting]

    confluence = compute_confluence(results)

    assert confluence.agreement == 4
    assert confluence.tier == SignalTier.VALID
    assert confluence.direction == Direction.BUY


def test_single_priority_method_is_enough_to_trade() -> None:
    # market_structure, support_resistance and price_action (the 3 highest-weighted
    # active methods) are trusted enough to carry a signal alone.
    results = [_result(StrategyName.MARKET_STRUCTURE, Direction.BUY, 0.85)]
    results += [
        _result(s, Direction.NEUTRAL, 0.0)
        for s in ALL_STRATEGIES
        if s != StrategyName.MARKET_STRUCTURE
    ]

    confluence = compute_confluence(results)

    assert confluence.agreement == 1
    assert confluence.direction == Direction.BUY
    assert confluence.is_tradeable


def test_single_non_priority_method_is_not_enough_to_trade() -> None:
    # macd is not in PRIORITY_STRATEGIES - non-priority methods need >= 2 agreeing
    # votes even at high confidence.
    results = [_result(StrategyName.MACD, Direction.SELL, 0.85)]
    results += [
        _result(s, Direction.NEUTRAL, 0.0) for s in ALL_STRATEGIES if s != StrategyName.MACD
    ]

    confluence = compute_confluence(results)

    assert confluence.tier == SignalTier.NO_TRADE
    assert confluence.direction == Direction.NEUTRAL
    assert not confluence.is_tradeable


def test_two_non_priority_methods_is_enough_to_trade() -> None:
    results = [
        _result(StrategyName.EMA_TREND, Direction.SELL, 0.85),
        _result(StrategyName.MACD, Direction.SELL, 0.8),
    ]
    results += [
        _result(s, Direction.NEUTRAL, 0.0)
        for s in ALL_STRATEGIES
        if s not in (StrategyName.EMA_TREND, StrategyName.MACD)
    ]

    confluence = compute_confluence(results)

    assert confluence.agreement == 2
    assert confluence.direction == Direction.SELL
    assert confluence.is_tradeable


def test_tied_buy_and_sell_score_is_neutral() -> None:
    results = [
        _result(StrategyName.MARKET_STRUCTURE, Direction.BUY, 0.8),
        _result(StrategyName.LIQUIDITY_SMC, Direction.SELL, 0.8),
    ]
    weights = {StrategyName.MARKET_STRUCTURE: 1.0, StrategyName.LIQUIDITY_SMC: 1.0}

    confluence = compute_confluence(results, weights=weights)

    assert confluence.direction == Direction.NEUTRAL


def test_no_trade_when_no_results() -> None:
    confluence = compute_confluence([])

    assert confluence.tier == SignalTier.NO_TRADE
    assert confluence.direction == Direction.NEUTRAL
    assert confluence.total_methods == 0


def test_reasons_only_include_the_winning_direction() -> None:
    results = [
        _result(StrategyName.MARKET_STRUCTURE, Direction.BUY, 0.9),
        _result(StrategyName.LIQUIDITY_SMC, Direction.BUY, 0.9),
        _result(StrategyName.EMA_TREND, Direction.SELL, 0.9),
    ]

    confluence = compute_confluence(results)

    assert confluence.direction == Direction.BUY
    assert len(confluence.reasons) == 2
    assert all("BUY" not in r or "sell" not in r.lower() for r in confluence.reasons)
