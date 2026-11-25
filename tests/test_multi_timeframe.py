from app.analysis.multi_timeframe import analyze_multi_timeframe
from app.core.enums import Direction, Timeframe


def test_buy_when_all_timeframes_agree_bullish() -> None:
    bias = {
        Timeframe.H4: (Direction.BUY, 0.8),
        Timeframe.H1: (Direction.BUY, 0.8),
        Timeframe.M30: (Direction.BUY, 0.75),
        Timeframe.M15: (Direction.BUY, 0.75),
        Timeframe.M5: (Direction.BUY, 0.6),
    }

    result = analyze_multi_timeframe(bias, Timeframe.M15)

    assert result.direction == Direction.BUY
    assert result.confidence > 0.7
    assert "htf_veto" not in result.metadata


def test_lower_timeframe_cannot_override_a_confident_higher_timeframe_bias() -> None:
    # H4/H1 solidly bearish; only the low-weight M1/M5 disagree - net direction must
    # stay SELL, and a fresh M1 wiggle must never flip it (Section 4).
    bias = {
        Timeframe.H4: (Direction.SELL, 0.85),
        Timeframe.H1: (Direction.SELL, 0.85),
        Timeframe.M30: (Direction.SELL, 0.7),
        Timeframe.M15: (Direction.SELL, 0.65),
        Timeframe.M5: (Direction.BUY, 0.6),
        Timeframe.M1: (Direction.BUY, 0.6),
    }

    result = analyze_multi_timeframe(bias, Timeframe.M15)

    assert result.direction == Direction.SELL
    assert "htf_veto" not in result.metadata


def test_confidence_is_slashed_when_higher_timeframe_strongly_disagrees() -> None:
    # Lower timeframes lean BUY, but H1 is confidently SELL - Section 16: "nếu H1/H4
    # chống lại mạnh thì phải giảm confidence".
    bias = {
        Timeframe.H1: (Direction.SELL, 0.75),
        Timeframe.M30: (Direction.BUY, 0.7),
        Timeframe.M15: (Direction.BUY, 0.7),
        Timeframe.M5: (Direction.BUY, 0.65),
    }

    result = analyze_multi_timeframe(bias, Timeframe.M15)

    assert "htf_veto" in result.metadata
    assert result.metadata["htf_veto"] == ["H1"]
    if result.direction is not Direction.NEUTRAL:
        assert result.confidence <= 0.5


def test_neutral_on_tied_buy_and_sell_weight() -> None:
    bias = {
        Timeframe.H1: (Direction.BUY, 0.7),
        Timeframe.H4: (Direction.SELL, 0.7),
    }
    weights = {Timeframe.H1: 0.5, Timeframe.H4: 0.5}

    result = analyze_multi_timeframe(bias, Timeframe.M15, weights=weights)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_no_bias_supplied() -> None:
    result = analyze_multi_timeframe({}, Timeframe.M15)

    assert result.direction == Direction.NEUTRAL
    assert "no timeframe bias" in result.reason
