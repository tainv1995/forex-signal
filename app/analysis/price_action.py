from collections.abc import Sequence

from app.analysis.base import AnalysisResult, neutral_result
from app.analysis.indicators import atr, candles_to_frame
from app.analysis.swings import confirmed_swings, find_swings, swing_highs, swing_lows
from app.core.enums import Direction, StrategyName, Timeframe
from app.market_data.base import Candle

NEAR_ZONE_CONFIDENCE = 0.78
ISOLATED_CONFIDENCE = 0.52
DOJI_BODY_RATIO_MAX = 0.1
PIN_WICK_RATIO_MIN = 0.66
PIN_BODY_RATIO_MAX = 0.30
STAR_BODY_RATIO_MAX = 0.35
STRONG_BODY_RATIO_MIN = 0.5
MOMENTUM_ATR_MULT = 1.2


def _body(c: Candle) -> float:
    return abs(c.close - c.open)


def _range(c: Candle) -> float:
    return c.high - c.low


def _upper_wick(c: Candle) -> float:
    return c.high - max(c.open, c.close)


def _lower_wick(c: Candle) -> float:
    return min(c.open, c.close) - c.low


def _is_bullish(c: Candle) -> bool:
    return c.close > c.open


def _is_bearish(c: Candle) -> bool:
    return c.close < c.open


def is_doji(c: Candle) -> bool:
    r = _range(c)
    return r > 0 and _body(c) / r <= DOJI_BODY_RATIO_MAX


def is_pin_bar(c: Candle) -> tuple[bool, bool]:
    """Returns (bullish_pin, bearish_pin). A hammer/shooting star IS a pin bar -
    which one it "means" depends on where it sits in the trend, handled by the caller."""
    r = _range(c)
    if r == 0:
        return False, False
    body_ratio = _body(c) / r
    upper_ratio, lower_ratio = _upper_wick(c) / r, _lower_wick(c) / r
    bullish_pin = lower_ratio >= PIN_WICK_RATIO_MIN and body_ratio <= PIN_BODY_RATIO_MAX
    bearish_pin = upper_ratio >= PIN_WICK_RATIO_MIN and body_ratio <= PIN_BODY_RATIO_MAX
    return bullish_pin, bearish_pin


def is_bullish_engulfing(prev: Candle, curr: Candle) -> bool:
    return (
        _is_bearish(prev)
        and _is_bullish(curr)
        and curr.open <= prev.close
        and curr.close >= prev.open
        and _body(curr) > _body(prev)
    )


def is_bearish_engulfing(prev: Candle, curr: Candle) -> bool:
    return (
        _is_bullish(prev)
        and _is_bearish(curr)
        and curr.open >= prev.close
        and curr.close <= prev.open
        and _body(curr) > _body(prev)
    )


def is_inside_bar(prev: Candle, curr: Candle) -> bool:
    return curr.high <= prev.high and curr.low >= prev.low


def is_outside_bar(prev: Candle, curr: Candle) -> bool:
    return curr.high >= prev.high and curr.low <= prev.low


def is_morning_star(c1: Candle, c2: Candle, c3: Candle) -> bool:
    r1, r2, r3 = _range(c1), _range(c2), _range(c3)
    if r1 == 0 or r2 == 0 or r3 == 0:
        return False
    return (
        _is_bearish(c1)
        and _body(c1) / r1 >= STRONG_BODY_RATIO_MIN
        and _body(c2) / r2 <= STAR_BODY_RATIO_MAX
        and max(c2.open, c2.close) < c1.close
        and _is_bullish(c3)
        and _body(c3) / r3 >= STRONG_BODY_RATIO_MIN
        and c3.close > (c1.open + c1.close) / 2
    )


def is_evening_star(c1: Candle, c2: Candle, c3: Candle) -> bool:
    r1, r2, r3 = _range(c1), _range(c2), _range(c3)
    if r1 == 0 or r2 == 0 or r3 == 0:
        return False
    return (
        _is_bullish(c1)
        and _body(c1) / r1 >= STRONG_BODY_RATIO_MIN
        and _body(c2) / r2 <= STAR_BODY_RATIO_MAX
        and min(c2.open, c2.close) > c1.close
        and _is_bearish(c3)
        and _body(c3) / r3 >= STRONG_BODY_RATIO_MIN
        and c3.close < (c1.open + c1.close) / 2
    )


def is_momentum_candle(c: Candle, atr_value: float) -> tuple[bool, bool]:
    r = _range(c)
    if r == 0 or atr_value <= 0:
        return False, False
    strong = _body(c) >= atr_value * MOMENTUM_ATR_MULT and _body(c) / r >= STRONG_BODY_RATIO_MIN
    return strong and _is_bullish(c), strong and _is_bearish(c)


def _near_zone(price: float, zone_price: float, proximity: float) -> bool:
    return abs(price - zone_price) <= proximity


def analyze_price_action(
    candles: Sequence[Candle],
    timeframe: Timeframe,
    swing_left: int = 2,
    swing_right: int = 2,
    zone_proximity_atr_mult: float = 0.5,
) -> AnalysisResult:
    min_len = swing_left + swing_right + 20
    if len(candles) < min_len:
        return neutral_result(
            StrategyName.PRICE_ACTION, timeframe, "not enough candles for price action"
        )

    df = candles_to_frame(candles)
    atr_series = atr(df, period=14).dropna()
    current_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0

    last = candles[-1]
    prev = candles[-2]

    pattern: str | None = None
    direction = Direction.NEUTRAL

    if is_bullish_engulfing(prev, last):
        pattern, direction = "bullish_engulfing", Direction.BUY
    elif is_bearish_engulfing(prev, last):
        pattern, direction = "bearish_engulfing", Direction.SELL
    elif len(candles) >= 3 and is_morning_star(candles[-3], candles[-2], candles[-1]):
        pattern, direction = "morning_star", Direction.BUY
    elif len(candles) >= 3 and is_evening_star(candles[-3], candles[-2], candles[-1]):
        pattern, direction = "evening_star", Direction.SELL
    else:
        bullish_pin, bearish_pin = is_pin_bar(last)
        bullish_momentum, bearish_momentum = is_momentum_candle(last, current_atr)
        if bullish_pin:
            pattern, direction = "bullish_pin_bar", Direction.BUY
        elif bearish_pin:
            pattern, direction = "bearish_pin_bar", Direction.SELL
        elif bullish_momentum:
            pattern, direction = "bullish_momentum_candle", Direction.BUY
        elif bearish_momentum:
            pattern, direction = "bearish_momentum_candle", Direction.SELL
        elif is_doji(last):
            pattern = "doji"

    metadata: dict[str, object] = {
        "pattern": pattern,
        "inside_bar": is_inside_bar(prev, last),
        "outside_bar": is_outside_bar(prev, last),
        "atr": current_atr,
    }

    if pattern is None or direction is Direction.NEUTRAL:
        return neutral_result(
            StrategyName.PRICE_ACTION,
            timeframe,
            f"{timeframe.value} no significant price action pattern at the last candle"
            + (f" ({pattern})" if pattern else ""),
            metadata=metadata,
        )

    # Context: a reversal pattern is only strong right at a support/resistance zone
    # (Section 12: engulfing in the middle of a range is weak; at a swing level, strong).
    swings = confirmed_swings(find_swings(candles, left=swing_left, right=swing_right))
    proximity = current_atr * zone_proximity_atr_mult
    near_zone = False
    if direction is Direction.BUY:
        lows = swing_lows(swings)
        near_zone = bool(lows) and _near_zone(last.close, lows[-1].price, proximity)
    else:
        highs = swing_highs(swings)
        near_zone = bool(highs) and _near_zone(last.close, highs[-1].price, proximity)

    metadata["near_swing_zone"] = near_zone
    confidence = NEAR_ZONE_CONFIDENCE if near_zone else ISOLATED_CONFIDENCE
    location = "at a swing zone" if near_zone else "in isolation (no nearby swing zone)"

    return AnalysisResult(
        strategy=StrategyName.PRICE_ACTION,
        direction=direction,
        confidence=confidence,
        timeframe=timeframe,
        reason=f"{timeframe.value} {pattern.replace('_', ' ')} {location}",
        metadata=metadata,
    )
