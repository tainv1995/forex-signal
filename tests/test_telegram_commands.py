from datetime import UTC, datetime

from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import build_signal
from app.engines.targets import TakeProfit
from app.telegram.commands import (
    StatusSnapshot,
    format_active_signal,
    format_pause,
    format_price,
    format_resume,
    format_status,
    format_unauthorized,
    format_unknown_command,
    is_admin,
    parse_command,
)

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def test_parse_command_lowercases_and_strips_bot_suffix() -> None:
    assert parse_command("/Status") == "/status"
    assert parse_command("/status@gold_signal_bot") == "/status"
    assert parse_command("  /price  ") == "/price"
    assert parse_command("") == ""
    assert parse_command("hello world") == "hello"


def test_is_admin() -> None:
    assert is_admin(111, [111, 222]) is True
    assert is_admin(333, [111, 222]) is False


def test_format_status_shows_running_and_bias_lines() -> None:
    snapshot = StatusSnapshot(
        symbol="XAUUSD",
        running=True,
        last_price=4393.42,
        bias_by_timeframe={"H4": "BULLISH", "H1": "BULLISH", "M15": "NEUTRAL"},
        buy_confidence=0.74,
        sell_confidence=0.21,
        active_signal_id=None,
        market_data_ok=True,
        telegram_ok=True,
        database_ok=True,
    )

    text = format_status(snapshot)

    assert "Status: RUNNING" in text
    assert "XAUUSD: 4393.42" in text
    assert "H4: BULLISH" in text
    assert "BUY Confidence: 74%" in text
    assert "SELL Confidence: 21%" in text
    assert "None" in text
    assert "Market Data: ✅" in text


def test_format_status_shows_paused() -> None:
    snapshot = StatusSnapshot(symbol="XAUUSD", running=False, last_price=None)

    text = format_status(snapshot)

    assert "Status: PAUSED" in text
    assert "XAUUSD: N/A" in text


def test_format_price() -> None:
    assert format_price("XAUUSD", 4393.42) == "XAUUSD: 4393.42"


def test_format_active_signal_none() -> None:
    assert "Không có" in format_active_signal(None)


def test_format_active_signal_present() -> None:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    signal = build_signal(
        "GOLD-20260817-001",
        "XAUUSD",
        Direction.BUY,
        4391.0,
        4393.0,
        StopLoss(4384.0, "t"),
        tps,
        0.86,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )

    text = format_active_signal(signal)

    assert "#GOLD-20260817-001" in text
    assert "BUY" in text
    assert "WAITING_ENTRY" in text


def test_pause_resume_and_error_messages_are_non_empty() -> None:
    assert format_pause()
    assert format_resume()
    assert format_unauthorized()
    assert "/foo" in format_unknown_command("/foo")
