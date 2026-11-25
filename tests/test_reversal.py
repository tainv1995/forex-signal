from datetime import UTC, datetime

from app.core.enums import Direction, SignalStatus, SignalTier
from app.engines.confluence import ConfluenceResult
from app.engines.reversal import evaluate_signal_health
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal
from app.engines.targets import TakeProfit

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _confluence(
    direction: Direction, buy_score: float, sell_score: float, agreement: int = 8
) -> ConfluenceResult:
    tier = SignalTier.STRONG if direction is not Direction.NEUTRAL else SignalTier.NO_TRADE
    confidence = buy_score if direction is Direction.BUY else sell_score
    return ConfluenceResult(
        direction=direction,
        tier=tier,
        confidence=confidence,
        agreement=agreement,
        total_methods=10,
        buy_score=buy_score,
        sell_score=sell_score,
    )


def _buy_signal(status: SignalStatus = SignalStatus.ACTIVE) -> Signal:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    signal = build_signal(
        "GOLD-20260817-001",
        "XAUUSD",
        Direction.BUY,
        4391.0,
        4393.0,
        StopLoss(4384.0, "t"),
        tps,
        0.86,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )
    if status is SignalStatus.ACTIVE:
        signal = activate(signal, NOW)
    return signal


def test_keeps_signal_when_own_confidence_still_healthy() -> None:
    signal = _buy_signal()
    confluence = _confluence(Direction.BUY, buy_score=0.80, sell_score=0.20)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "KEEP"
    assert decision.reason_lines == []


def test_closes_when_own_confidence_drops_but_no_strong_opposite() -> None:
    signal = _buy_signal()
    # Own (BUY) confidence collapsed, but the opposite side hasn't taken over.
    confluence = _confluence(Direction.NEUTRAL, buy_score=0.40, sell_score=0.50)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "CLOSE"
    assert "Market Structure Invalidated" in decision.reason_lines
    assert any("40%" in line for line in decision.reason_lines)


def test_reverses_when_opposite_confluence_is_strong_and_confident() -> None:
    signal = _buy_signal()
    confluence = _confluence(Direction.SELL, buy_score=0.42, sell_score=0.86)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "REVERSE"
    assert decision.reason_lines == [
        "Market Structure Invalidated",
        "Strong Bearish Reversal Confirmed",
    ]


def test_does_not_reverse_on_a_single_weak_wobble() -> None:
    # Own confidence dipped only slightly (still above the invalidation floor) even
    # though the opposite side ticked up - Section 29: never flip on a small wobble.
    signal = _buy_signal()
    confluence = _confluence(Direction.BUY, buy_score=0.60, sell_score=0.55)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "KEEP"


def test_does_not_reverse_when_opposite_confidence_is_not_high_enough() -> None:
    # Structure flipped direction-wise, but the opposite side's own confidence is
    # still below the (higher) reversal bar - close, don't reverse.
    signal = _buy_signal()
    confluence = _confluence(Direction.SELL, buy_score=0.40, sell_score=0.70)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "CLOSE"


def test_sell_signal_reverses_to_bullish_wording() -> None:
    tps = [TakeProfit(i, 4405.0 - i * 2, float(i), "t") for i in range(1, 6)]
    signal = build_signal(
        "GOLD-20260817-002",
        "XAUUSD",
        Direction.SELL,
        4405.0,
        4407.0,
        StopLoss(4414.0, "t"),
        tps,
        0.85,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )
    confluence = _confluence(Direction.BUY, buy_score=0.88, sell_score=0.35)

    decision = evaluate_signal_health(signal, confluence)

    assert decision.action == "REVERSE"
    assert "Strong Bullish Reversal Confirmed" in decision.reason_lines


def test_custom_thresholds_are_respected() -> None:
    signal = _buy_signal()
    confluence = _confluence(Direction.SELL, buy_score=0.65, sell_score=0.75)

    # Default floor (0.55) would KEEP this; a stricter custom floor should CLOSE it.
    decision = evaluate_signal_health(signal, confluence, invalidation_floor=0.70)

    assert decision.action in ("CLOSE", "REVERSE")
