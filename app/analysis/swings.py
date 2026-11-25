from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.market_data.base import Candle

SwingKind = Literal["high", "low"]


@dataclass(frozen=True, slots=True)
class Swing:
    index: int
    timestamp: datetime
    price: float
    kind: SwingKind
    confirmed: bool


def find_swings(candles: Sequence[Candle], left: int = 2, right: int = 2) -> list[Swing]:
    """Fractal swing high/low detection (not "every local wiggle is a swing").

    A candle at index i is a swing high/low only if it is strictly the most extreme
    point among `left` candles before and `right` candles after it. The most recent
    `right` candles cannot be confirmed yet - reported with confirmed=False, since
    treating them as final would be look-ahead bias (Section 42): a later candle could
    still break the extreme.
    """
    n = len(candles)
    swings: list[Swing] = []
    for i in range(left, n):
        available_right = n - 1 - i
        window = min(right, available_right)
        left_highs = [candles[j].high for j in range(i - left, i)]
        left_lows = [candles[j].low for j in range(i - left, i)]
        right_highs = [candles[j].high for j in range(i + 1, i + 1 + window)]
        right_lows = [candles[j].low for j in range(i + 1, i + 1 + window)]

        high = candles[i].high
        low = candles[i].low
        confirmed = available_right >= right

        if all(high > h for h in left_highs) and all(high > h for h in right_highs):
            swings.append(Swing(i, candles[i].timestamp, high, "high", confirmed))
        if all(low < v for v in left_lows) and all(low < v for v in right_lows):
            swings.append(Swing(i, candles[i].timestamp, low, "low", confirmed))

    return swings


def confirmed_swings(swings: Sequence[Swing]) -> list[Swing]:
    return [s for s in swings if s.confirmed]


def swing_highs(swings: Sequence[Swing]) -> list[Swing]:
    return [s for s in swings if s.kind == "high"]


def swing_lows(swings: Sequence[Swing]) -> list[Swing]:
    return [s for s in swings if s.kind == "low"]


def cluster_by_price(swings: Sequence[Swing], tolerance: float) -> list[list[Swing]]:
    """Merge swings within `tolerance` of each other into price clusters.

    Shared by support/resistance zone-building and equal-high/low liquidity pool
    detection - both are "nearby price levels collapse into one zone" (Section 6).
    """
    if not swings:
        return []
    ordered = sorted(swings, key=lambda s: s.price)
    clusters: list[list[Swing]] = [[ordered[0]]]
    for swing in ordered[1:]:
        if swing.price - clusters[-1][-1].price <= tolerance:
            clusters[-1].append(swing)
        else:
            clusters.append([swing])
    return clusters
