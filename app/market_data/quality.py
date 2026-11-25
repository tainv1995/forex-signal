from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.timeframes import TIMEFRAME_DURATIONS
from app.market_data.base import Candle, PriceTick

# How far a candle timestamp may sit in the future before it's rejected as clock skew.
FUTURE_TOLERANCE = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    kind: str
    detail: str


def validate_candles(candles: Sequence[Candle]) -> list[DataQualityIssue]:
    """Check a candle series for duplicate/missing/out-of-order/future timestamps.

    OHLC integrity (high >= max(o,c), low <= min(o,c)) is already enforced by
    Candle.__post_init__, so it isn't re-checked here.
    """
    issues: list[DataQualityIssue] = []
    if not candles:
        return issues

    timeframe = candles[0].timeframe
    interval = TIMEFRAME_DURATIONS[timeframe]
    now = datetime.now(UTC)
    seen: set[datetime] = set()

    previous = candles[0]
    for candle in candles:
        if candle.timeframe != timeframe:
            issues.append(
                DataQualityIssue(
                    "mixed_timeframe",
                    f"expected {timeframe}, got {candle.timeframe} at {candle.timestamp}",
                )
            )
            continue

        if candle.timestamp in seen:
            issues.append(
                DataQualityIssue("duplicate_candle", f"duplicate timestamp {candle.timestamp}")
            )
        seen.add(candle.timestamp)

        if candle.timestamp > now + FUTURE_TOLERANCE:
            issues.append(
                DataQualityIssue("future_timestamp", f"candle timestamp {candle.timestamp} > now")
            )

        if candle is not previous:
            gap = candle.timestamp - previous.timestamp
            if gap < interval:
                issues.append(
                    DataQualityIssue(
                        "out_of_order",
                        f"{candle.timestamp} follows {previous.timestamp} with gap {gap} < {interval}",
                    )
                )
            elif gap > interval:
                missed = int(gap / interval) - 1
                issues.append(
                    DataQualityIssue(
                        "missing_gap",
                        f"{missed} candle(s) missing between {previous.timestamp} and {candle.timestamp}",
                    )
                )
        previous = candle

    return issues


def is_price_stale(tick: PriceTick, max_age: timedelta) -> bool:
    return datetime.now(UTC) - tick.timestamp > max_age


def has_blocking_issues(issues: Sequence[DataQualityIssue]) -> bool:
    """Issues that must suppress signal generation (Section 46: stale/invalid data => NO SIGNAL)."""
    blocking_kinds = {"duplicate_candle", "future_timestamp", "mixed_timeframe"}
    return any(issue.kind in blocking_kinds for issue in issues)
