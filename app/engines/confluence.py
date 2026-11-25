from collections.abc import Sequence
from dataclasses import dataclass, field

from app.analysis.base import AnalysisResult
from app.core.enums import Direction, SignalTier, StrategyName
from app.core.strategy_weights import DEFAULT_STRATEGY_WEIGHTS

DEFAULT_THRESHOLDS: dict[SignalTier, float] = {
    SignalTier.VERY_STRONG: 0.90,
    SignalTier.STRONG: 0.82,
    SignalTier.VALID: 0.75,
    SignalTier.WATCH: 0.68,
}
DEFAULT_MIN_AGREEMENT_RATIO = 0.5
DEFAULT_STRONG_AGREEMENT_RATIO = 0.7

# The confluence-voting methods are now market_structure, support_resistance,
# liquidity_smc, price_action (EMA/MACD/Volatility/Fibonacci moved to passive,
# entry/risk/targets-only roles - see app/workers/analysis_worker.py). Of those 4,
# the 3 highest-weighted (DEFAULT_STRATEGY_WEIGHTS: market_structure 1.30,
# liquidity_smc 1.30, support_resistance 1.15) are trusted enough to fire on just 1
# agreeing vote; price_action (1.00, the lowest of the 4) needs >= 2. Note:
# support_resistance was the sole method behind the GOLD-20260830-001 incident (a
# signal built on just 1 vote) and is in this set by explicit request - what
# actually prevents a repeat of that specific failure (a near-zero-risk stop) now
# is the MIN_SL_ATR_MULT floor in risk.py, not this vote-count gate.
PRIORITY_STRATEGIES = {
    StrategyName.MARKET_STRUCTURE,
    StrategyName.LIQUIDITY_SMC,
    StrategyName.SUPPORT_RESISTANCE,
}
PRIORITY_MIN_COUNT = 1
DEFAULT_MIN_COUNT = 2


@dataclass(frozen=True, slots=True)
class ConfluenceResult:
    direction: Direction
    tier: SignalTier
    confidence: float
    agreement: int
    total_methods: int
    buy_score: float
    sell_score: float
    reasons: list[str] = field(default_factory=list)
    results: list[AnalysisResult] = field(default_factory=list)

    @property
    def is_tradeable(self) -> bool:
        return self.tier is not SignalTier.NO_TRADE and self.direction is not Direction.NEUTRAL


def _tier_for(confidence: float, thresholds: dict[SignalTier, float]) -> SignalTier:
    if confidence >= thresholds[SignalTier.VERY_STRONG]:
        return SignalTier.VERY_STRONG
    if confidence >= thresholds[SignalTier.STRONG]:
        return SignalTier.STRONG
    if confidence >= thresholds[SignalTier.VALID]:
        return SignalTier.VALID
    if confidence >= thresholds[SignalTier.WATCH]:
        return SignalTier.WATCH
    return SignalTier.NO_TRADE


def compute_confluence(
    results: Sequence[AnalysisResult],
    weights: dict[StrategyName, float] | None = None,
    min_agreement: float = DEFAULT_MIN_AGREEMENT_RATIO,
    strong_agreement: float = DEFAULT_STRONG_AGREEMENT_RATIO,
    thresholds: dict[SignalTier, float] | None = None,
) -> ConfluenceResult:
    """Combine the active methods' AnalysisResults into one BUY/SELL/NO_TRADE call.

    Quality over quantity (Section 16): a high weighted score alone isn't enough -
    the agreement gate is a ratio of the winning direction's vote count over methods
    that actually took a stance (NEUTRAL methods don't count toward the denominator
    either). A normal signal needs that ratio > min_agreement, a STRONG/VERY_STRONG
    tier needs > strong_agreement, or it gets capped down to VALID. On top of the
    ratio, an absolute vote-count floor applies too: PRIORITY_STRATEGIES can carry a
    signal alone (>= PRIORITY_MIN_COUNT), everything else needs >= DEFAULT_MIN_COUNT
    agreeing votes - a single non-priority method agreeing with itself is not enough,
    no matter how confident.
    """
    weights = weights or DEFAULT_STRATEGY_WEIGHTS
    thresholds = thresholds or DEFAULT_THRESHOLDS

    buy_weighted_confidence = 0.0
    buy_total_weight = 0.0
    sell_weighted_confidence = 0.0
    sell_total_weight = 0.0
    buy_agreement = 0
    sell_agreement = 0
    buy_reasons: list[str] = []
    sell_reasons: list[str] = []
    buy_strategies: list[StrategyName] = []
    sell_strategies: list[StrategyName] = []

    for result in results:
        weight = weights.get(result.strategy, 0.0)
        reason = f"[{result.strategy.value}] {result.reason}"
        if result.direction is Direction.BUY:
            buy_weighted_confidence += weight * result.confidence
            buy_total_weight += weight
            buy_agreement += 1
            buy_reasons.append(reason)
            buy_strategies.append(result.strategy)
        elif result.direction is Direction.SELL:
            sell_weighted_confidence += weight * result.confidence
            sell_total_weight += weight
            sell_agreement += 1
            sell_reasons.append(reason)
            sell_strategies.append(result.strategy)

    # Score = weighted-average confidence *among methods that actually took a stance*.
    # A method sitting out (NEUTRAL) doesn't dilute how confident the others are - it
    # only shows up via the separate agreement-count gate below.
    buy_score = buy_weighted_confidence / buy_total_weight if buy_total_weight > 0 else 0.0
    sell_score = sell_weighted_confidence / sell_total_weight if sell_total_weight > 0 else 0.0

    if buy_score <= 0.0 and sell_score <= 0.0:
        return ConfluenceResult(
            Direction.NEUTRAL,
            SignalTier.NO_TRADE,
            0.0,
            0,
            len(results),
            buy_score,
            sell_score,
            [],
            list(results),
        )

    if buy_score == sell_score:
        direction = Direction.NEUTRAL
        confidence = 0.0
        agreement = 0
        reasons: list[str] = []
        winning_strategies: list[StrategyName] = []
    elif buy_score > sell_score:
        direction, confidence, agreement, reasons, winning_strategies = (
            Direction.BUY,
            buy_score,
            buy_agreement,
            buy_reasons,
            buy_strategies,
        )
    else:
        direction, confidence, agreement, reasons, winning_strategies = (
            Direction.SELL,
            sell_score,
            sell_agreement,
            sell_reasons,
            sell_strategies,
        )

    tier = _tier_for(confidence, thresholds)

    if direction is not Direction.NEUTRAL:
        voting_methods = buy_agreement + sell_agreement
        agreement_ratio = agreement / voting_methods if voting_methods > 0 else 0.0
        min_count = (
            PRIORITY_MIN_COUNT
            if any(s in PRIORITY_STRATEGIES for s in winning_strategies)
            else DEFAULT_MIN_COUNT
        )
        if agreement_ratio <= min_agreement or agreement < min_count:
            tier = SignalTier.NO_TRADE
        elif (
            tier in (SignalTier.STRONG, SignalTier.VERY_STRONG)
            and agreement_ratio <= strong_agreement
        ):
            tier = SignalTier.VALID

    if tier is SignalTier.NO_TRADE:
        direction = Direction.NEUTRAL

    return ConfluenceResult(
        direction=direction,
        tier=tier,
        confidence=confidence,
        agreement=agreement,
        total_methods=len(results),
        buy_score=buy_score,
        sell_score=sell_score,
        reasons=reasons,
        results=list(results),
    )
