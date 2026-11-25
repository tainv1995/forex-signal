from app.analysis.market_structure import analyze_market_structure
from app.core.enums import Direction, Timeframe
from tests.helpers import candles_from_ohlc

# Confirmed bullish structure: swing high #1=112 (idx2), swing low #1=90 (idx4),
# swing high #2=118 HH (idx6), swing low #2=93 HL (idx8). idx9-10 are neutral filler
# that exist only so idx8 gets its right-side confirmation without becoming a new
# pivot itself. Each test appends its own final candle(s) to probe a fresh break.
_BULLISH_STRUCTURE_ROWS = [
    (97, 100, 95, 98),
    (98, 101, 96, 99),
    (107, 112, 105, 110),
    (104, 106, 98, 101),
    (95, 104, 90, 93),
    (97, 107, 95, 104),
    (104, 118, 100, 115),
    (108, 109, 97, 101),
    (100, 108, 93, 95),
    (98, 105, 96, 101),
    (100, 103, 94, 101),
]


def test_bullish_bos_after_higher_high_higher_low() -> None:
    rows = [*_BULLISH_STRUCTURE_ROWS, (117, 125, 115, 124)]  # closes above HH (118)
    candles = candles_from_ohlc(rows)

    result = analyze_market_structure(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.BUY
    assert result.metadata["event"] == "BOS"
    assert result.confidence >= 0.7


def test_bearish_choch_breaks_bullish_structure() -> None:
    rows = [*_BULLISH_STRUCTURE_ROWS, (100, 101, 85, 88)]  # closes below HL (93)
    candles = candles_from_ohlc(rows)

    result = analyze_market_structure(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.SELL
    assert result.metadata["event"] == "CHoCH"
    assert result.metadata["trend"] == "bullish"


def test_neutral_when_not_enough_swing_structure() -> None:
    rows = [(100.0, 100.5, 99.5, 100.0)] * 6
    candles = candles_from_ohlc(rows)

    result = analyze_market_structure(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.NEUTRAL


def test_neutral_when_trend_established_but_no_fresh_break() -> None:
    rows = [*_BULLISH_STRUCTURE_ROWS, (100, 103, 96, 100)]  # stays inside the range
    candles = candles_from_ohlc(rows)

    result = analyze_market_structure(candles, Timeframe.M15, left=2, right=2)

    assert result.direction == Direction.NEUTRAL
    assert result.metadata["trend"] == "bullish"
