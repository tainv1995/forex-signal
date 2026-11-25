from datetime import UTC, datetime, timedelta

from app.core.enums import Timeframe
from app.market_data.base import Candle, PriceTick
from app.market_data.quality import has_blocking_issues, is_price_stale, validate_candles


def _candle(ts: datetime, price: float = 2650.0) -> Candle:
    return Candle(
        symbol="XAUUSD",
        timeframe=Timeframe.M5,
        timestamp=ts,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price,
    )


def test_validate_candles_clean_series_has_no_issues() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [_candle(start + timedelta(minutes=5 * i)) for i in range(10)]

    assert validate_candles(candles) == []


def test_validate_candles_detects_duplicate_timestamp() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [_candle(start), _candle(start), _candle(start + timedelta(minutes=5))]

    issues = validate_candles(candles)

    assert any(issue.kind == "duplicate_candle" for issue in issues)
    assert has_blocking_issues(issues)


def test_validate_candles_detects_missing_gap() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [_candle(start), _candle(start + timedelta(minutes=20))]

    issues = validate_candles(candles)

    assert any(issue.kind == "missing_gap" for issue in issues)


def test_validate_candles_detects_out_of_order() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [_candle(start + timedelta(minutes=5)), _candle(start)]

    issues = validate_candles(candles)

    assert any(issue.kind == "out_of_order" for issue in issues)


def test_validate_candles_detects_future_timestamp() -> None:
    far_future = datetime.now(UTC) + timedelta(days=1)
    candles = [_candle(far_future)]

    issues = validate_candles(candles)

    assert any(issue.kind == "future_timestamp" for issue in issues)
    assert has_blocking_issues(issues)


def test_is_price_stale() -> None:
    fresh = PriceTick(symbol="XAUUSD", price=2650.0, timestamp=datetime.now(UTC))
    stale = PriceTick(
        symbol="XAUUSD", price=2650.0, timestamp=datetime.now(UTC) - timedelta(minutes=10)
    )

    assert not is_price_stale(fresh, timedelta(minutes=1))
    assert is_price_stale(stale, timedelta(minutes=1))
