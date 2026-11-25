import pandas as pd
import pytest

from app.analysis.indicators import atr, bollinger_bands, candles_to_frame, ema, macd, rsi
from app.core.enums import Timeframe
from tests.helpers import make_candles


def test_candles_to_frame_preserves_order_and_columns() -> None:
    candles = make_candles([100, 101, 102], timeframe=Timeframe.M5)
    df = candles_to_frame(candles)

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert list(df["close"]) == [100, 101, 102]
    assert df.index.is_monotonic_increasing


def test_ema_converges_toward_constant_series() -> None:
    series = pd.Series([100.0] * 30)
    result = ema(series, period=10)

    assert result.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_is_100_for_strictly_increasing_series() -> None:
    series = pd.Series([float(i) for i in range(100, 130)])
    result = rsi(series, period=14)

    assert result.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_is_0_for_strictly_decreasing_series() -> None:
    series = pd.Series([float(i) for i in range(130, 100, -1)])
    result = rsi(series, period=14)

    assert result.dropna().iloc[-1] == pytest.approx(0.0)


def test_rsi_is_bounded_between_0_and_100() -> None:
    prices = [100, 102, 101, 105, 103, 108, 104, 110, 107, 112, 109, 115, 111, 118, 113, 120]
    series = pd.Series([float(p) for p in prices])
    result = rsi(series, period=14).dropna()

    assert (result >= 0.0).all()
    assert (result <= 100.0).all()


def test_macd_histogram_is_difference_of_macd_and_signal() -> None:
    prices = [100 + i * 0.5 + (2 if i % 5 == 0 else 0) for i in range(60)]
    series = pd.Series(prices)
    macd_line, signal_line, histogram = macd(series)

    valid = histogram.dropna().index
    pd.testing.assert_series_equal(
        histogram.loc[valid], (macd_line - signal_line).loc[valid], check_names=False
    )


def test_atr_is_positive_for_volatile_series() -> None:
    candles = make_candles(
        [100, 102, 99, 103, 101, 105, 102, 106, 103, 108], timeframe=Timeframe.M5
    )
    df = candles_to_frame(candles)
    result = atr(df, period=5).dropna()

    assert (result > 0).all()


def test_bollinger_bands_upper_above_middle_above_lower() -> None:
    prices = [
        100,
        101,
        99,
        102,
        98,
        103,
        97,
        104,
        96,
        105,
        95,
        106,
        94,
        107,
        93,
        108,
        92,
        109,
        91,
        110,
    ]
    series = pd.Series([float(p) for p in prices])
    upper, middle, lower = bollinger_bands(series, period=10, num_std=2.0)

    valid = middle.dropna().index
    assert (upper.loc[valid] >= middle.loc[valid]).all()
    assert (middle.loc[valid] >= lower.loc[valid]).all()
