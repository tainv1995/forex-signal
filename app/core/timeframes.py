from datetime import UTC, datetime, timedelta

from app.core.enums import Timeframe

TIMEFRAME_DURATIONS: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}

# Default weight of each timeframe in multi-timeframe confluence (Section 4/17).
# Configurable in Settings; this is only the built-in fallback.
TIMEFRAME_WEIGHTS: dict[Timeframe, float] = {
    Timeframe.D1: 0.05,
    Timeframe.H4: 0.15,
    Timeframe.H1: 0.25,
    Timeframe.M30: 0.20,
    Timeframe.M15: 0.20,
    Timeframe.M5: 0.12,
    Timeframe.M1: 0.03,
}

# TradingView alert `{{interval}}` placeholder -> our Timeframe enum.
TRADINGVIEW_INTERVAL_MAP: dict[str, Timeframe] = {
    "1": Timeframe.M1,
    "5": Timeframe.M5,
    "15": Timeframe.M15,
    "30": Timeframe.M30,
    "60": Timeframe.H1,
    "240": Timeframe.H4,
    "D": Timeframe.D1,
    "1D": Timeframe.D1,
}


def floor_to_interval(timestamp: datetime, interval: timedelta) -> datetime:
    epoch_seconds = timestamp.timestamp()
    interval_seconds = interval.total_seconds()
    floored = epoch_seconds - (epoch_seconds % interval_seconds)
    return datetime.fromtimestamp(floored, tz=timestamp.tzinfo or UTC)
