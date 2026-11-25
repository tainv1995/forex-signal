from app.analysis.price_action import (
    is_bearish_engulfing,
    is_bullish_engulfing,
    is_doji,
    is_evening_star,
    is_inside_bar,
    is_momentum_candle,
    is_morning_star,
    is_outside_bar,
    is_pin_bar,
)
from app.market_data.base import Candle
from tests.helpers import candles_from_ohlc


def _c(o: float, h: float, low: float, c: float) -> Candle:
    return candles_from_ohlc([(o, h, low, c)])[0]


def test_doji_has_tiny_body_relative_to_range() -> None:
    assert is_doji(_c(100, 101, 99, 100.05)) is True
    assert is_doji(_c(100, 101, 99, 100.8)) is False


def test_bullish_pin_bar_has_long_lower_wick_small_body() -> None:
    bullish, bearish = is_pin_bar(_c(100, 100.3, 96, 100.2))
    assert bullish is True
    assert bearish is False


def test_bearish_pin_bar_has_long_upper_wick_small_body() -> None:
    bullish, bearish = is_pin_bar(_c(100, 104, 99.7, 100.2))
    assert bullish is False
    assert bearish is True


def test_bullish_engulfing_body_fully_covers_prior_bearish_body() -> None:
    prev = _c(102, 102.5, 99.5, 100)  # bearish
    curr = _c(99.5, 103.5, 99, 103)  # bullish, engulfs prev's body
    assert is_bullish_engulfing(prev, curr) is True
    assert is_bearish_engulfing(prev, curr) is False


def test_bearish_engulfing_body_fully_covers_prior_bullish_body() -> None:
    prev = _c(100, 102.5, 99.5, 102)  # bullish
    curr = _c(102.5, 103, 98.5, 99)  # bearish, engulfs prev's body
    assert is_bearish_engulfing(prev, curr) is True


def test_inside_bar_is_fully_contained_by_previous_bar() -> None:
    prev = _c(100, 105, 95, 102)
    curr = _c(101, 103, 98, 101.5)
    assert is_inside_bar(prev, curr) is True
    assert is_outside_bar(prev, curr) is False


def test_outside_bar_fully_contains_previous_bar() -> None:
    prev = _c(101, 103, 98, 101.5)
    curr = _c(100, 106, 94, 105)
    assert is_outside_bar(prev, curr) is True
    assert is_inside_bar(prev, curr) is False


def test_morning_star_reverses_a_downtrend() -> None:
    c1 = _c(105, 105.2, 99, 99.5)  # strong bearish
    c2 = _c(98.8, 99.0, 98.3, 98.75)  # small-bodied star gapping below c1's close
    c3 = _c(99.0, 104, 98.8, 103.5)  # strong bullish closing back into c1's body
    assert is_morning_star(c1, c2, c3) is True
    assert is_evening_star(c1, c2, c3) is False


def test_evening_star_reverses_an_uptrend() -> None:
    c1 = _c(99, 105.2, 98.8, 105)  # strong bullish
    c2 = _c(105.5, 106.0, 105.3, 105.55)  # small-bodied star gapping above c1's close
    c3 = _c(105.4, 105.6, 100, 100.5)  # strong bearish closing back into c1's body
    assert is_evening_star(c1, c2, c3) is True
    assert is_morning_star(c1, c2, c3) is False


def test_momentum_candle_needs_large_body_relative_to_atr() -> None:
    big_bullish = _c(100, 105.2, 99.8, 105)
    small_bullish = _c(100, 100.3, 99.9, 100.2)
    assert is_momentum_candle(big_bullish, atr_value=1.0) == (True, False)
    assert is_momentum_candle(small_bullish, atr_value=1.0) == (False, False)
