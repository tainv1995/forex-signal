from app.analysis.base import AnalysisResult, neutral_result
from app.core.enums import Direction, StrategyName, Timeframe
from app.core.timeframes import TIMEFRAME_WEIGHTS

# Higher timeframes carry veto power - a lower-timeframe majority can never overrule a
# confident H1/H4 stance (Section 4: "M1 tuyệt đối không được tự mình đảo bias H1/H4").
HTF_VETO_TIMEFRAMES = (Timeframe.H4, Timeframe.H1)
HTF_VETO_CONFIDENCE_THRESHOLD = 0.6
HTF_VETO_PENALTY = 0.35
MAX_CONFIDENCE = 0.95

TimeframeBias = dict[Timeframe, tuple[Direction, float]]


def analyze_multi_timeframe(
    bias_by_timeframe: TimeframeBias,
    primary_timeframe: Timeframe,
    weights: dict[Timeframe, float] | None = None,
) -> AnalysisResult:
    """Combine each timeframe's own directional bias (e.g. from market_structure)
    into one weighted confluence call. `bias_by_timeframe` is supplied by the
    caller/orchestrator, since this is the one method that spans timeframes rather
    than reading candles for a single one."""
    weights = weights or TIMEFRAME_WEIGHTS
    if not bias_by_timeframe:
        return neutral_result(
            StrategyName.MULTI_TIMEFRAME, primary_timeframe, "no timeframe bias supplied"
        )

    buy_score = 0.0
    sell_score = 0.0
    total_weight = 0.0
    for timeframe, (direction, confidence) in bias_by_timeframe.items():
        weight = weights.get(timeframe, 0.0)
        total_weight += weight
        if direction is Direction.BUY:
            buy_score += weight * confidence
        elif direction is Direction.SELL:
            sell_score += weight * confidence

    if total_weight <= 0:
        return neutral_result(
            StrategyName.MULTI_TIMEFRAME, primary_timeframe, "no weighted timeframes supplied"
        )

    buy_pct = buy_score / total_weight
    sell_pct = sell_score / total_weight

    metadata: dict[str, object] = {
        "buy_score": round(buy_pct, 3),
        "sell_score": round(sell_pct, 3),
        "timeframes_considered": [tf.value for tf in bias_by_timeframe],
    }

    if buy_pct <= 0 and sell_pct <= 0:
        return neutral_result(
            StrategyName.MULTI_TIMEFRAME,
            primary_timeframe,
            "no directional bias across timeframes",
            metadata=metadata,
        )

    if buy_pct == sell_pct:
        return neutral_result(
            StrategyName.MULTI_TIMEFRAME,
            primary_timeframe,
            "buy and sell timeframe weight are tied",
            metadata=metadata,
        )

    direction = Direction.BUY if buy_pct > sell_pct else Direction.SELL
    confidence = buy_pct if direction is Direction.BUY else sell_pct

    opposing_htf = [
        tf
        for tf in HTF_VETO_TIMEFRAMES
        if tf in bias_by_timeframe
        and bias_by_timeframe[tf][0] is not Direction.NEUTRAL
        and bias_by_timeframe[tf][0] is not direction
        and bias_by_timeframe[tf][1] >= HTF_VETO_CONFIDENCE_THRESHOLD
    ]
    if opposing_htf:
        confidence = max(0.0, confidence - HTF_VETO_PENALTY)
        metadata["htf_veto"] = [tf.value for tf in opposing_htf]
        if confidence <= 0.5:
            return neutral_result(
                StrategyName.MULTI_TIMEFRAME,
                primary_timeframe,
                f"{primary_timeframe.value} MTF bias overridden - higher timeframe "
                f"({', '.join(tf.value for tf in opposing_htf)}) strongly disagrees",
                metadata=metadata,
            )

    return AnalysisResult(
        strategy=StrategyName.MULTI_TIMEFRAME,
        direction=direction,
        confidence=min(confidence, MAX_CONFIDENCE),
        timeframe=primary_timeframe,
        reason=(
            f"Multi-timeframe confluence: {buy_pct:.0%} buy weight vs {sell_pct:.0%} sell weight "
            f"across {len(bias_by_timeframe)} timeframes"
        ),
        metadata=metadata,
    )
