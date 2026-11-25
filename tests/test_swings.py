from app.analysis.swings import confirmed_swings, find_swings, swing_highs, swing_lows
from tests.helpers import candles_from_ohlc, make_candles


def test_finds_a_confirmed_swing_high_at_local_peak() -> None:
    # (open, high, low, close) - index 2 is an unambiguous, isolated peak.
    rows = [
        (100, 100.5, 99.5, 100),
        (100, 102.0, 99.8, 101.5),
        (101.5, 105.0, 101.0, 104.5),
        (104.5, 104.8, 102.0, 103),
        (103, 103.2, 100.5, 101),
        (101, 101.2, 99.5, 100),
        (100, 100.2, 98.5, 99),
    ]
    candles = candles_from_ohlc(rows)

    swings = find_swings(candles, left=2, right=2)
    highs = swing_highs(confirmed_swings(swings))

    assert any(s.index == 2 for s in highs)


def test_finds_a_confirmed_swing_low_at_local_trough() -> None:
    rows = [
        (105, 105.5, 104.5, 105),
        (105, 105.2, 102.5, 103),
        (103, 103.5, 99.0, 100),
        (100, 102.5, 99.5, 102),
        (102, 104.5, 101.5, 104),
        (104, 106.5, 103.5, 106),
        (106, 108.5, 105.5, 108),
    ]
    candles = candles_from_ohlc(rows)

    swings = find_swings(candles, left=2, right=2)
    lows = swing_lows(confirmed_swings(swings))

    assert any(s.index == 2 for s in lows)


def test_most_recent_candles_are_unconfirmed_provisional_swings() -> None:
    closes = [100, 102, 105, 103, 101]
    candles = make_candles(closes)

    swings = find_swings(candles, left=2, right=2)
    unconfirmed = [s for s in swings if not s.confirmed]

    assert unconfirmed
    assert all(s.index >= len(candles) - 2 for s in unconfirmed)


def test_flat_series_has_no_swings() -> None:
    rows = [(100.0, 100.5, 99.5, 100.0)] * 10
    candles = candles_from_ohlc(rows)

    swings = find_swings(candles, left=2, right=2)

    assert swings == []


def test_does_not_treat_every_small_wiggle_as_a_swing() -> None:
    # A gentle monotonic climb with tiny noise should not produce a swing at every bar.
    closes = [100, 100.1, 100.2, 100.1, 100.3, 100.4, 100.3, 100.5, 100.6]
    candles = make_candles(closes)

    swings = find_swings(candles, left=2, right=2)

    assert len(swings) < len(candles)
