from datetime import UTC, datetime

from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, hit_target
from app.engines.targets import TakeProfit
from app.telegram.formatter import (
    format_cancelled,
    format_entry_activated,
    format_full_tp,
    format_new_signal,
    format_stop_loss,
    format_tp_hit,
)

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def _buy_signal() -> Signal:
    tps = [TakeProfit(i, 4393.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
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


def _sell_signal() -> Signal:
    tps = [TakeProfit(i, 4405.0 - i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        "GOLD-20260817-002",
        "XAUUSD",
        Direction.SELL,
        4405.0,
        4407.0,
        StopLoss(4414.0, "t"),
        tps,
        0.85,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )


def test_buy_signal_shows_high_over_low_in_entry_range() -> None:
    text = format_new_signal(_buy_signal(), "GOLD", show_metadata=True)

    assert text.startswith("🟢 GOLD BUY 4393/4391")
    assert "TP ¹ 4395" in text
    assert "TP ⁵ 4403" in text
    assert "SL    4384" in text
    assert "Confidence" not in text
    assert "Confluence" not in text
    assert text.endswith("#GOLD-20260817-001")


def test_sell_signal_shows_low_over_high_in_entry_range() -> None:
    text = format_new_signal(_sell_signal(), "GOLD", show_metadata=True)

    assert text.startswith("🔴 GOLD SELL 4405/4407")
    assert "TP ¹ 4403" in text
    assert "TP ⁵ 4395" in text
    assert "SL    4414" in text


def test_show_metadata_false_hides_emoji_confidence_and_hashtag() -> None:
    text = format_new_signal(_buy_signal(), "GOLD", show_metadata=False)

    assert text.startswith("GOLD BUY 4393/4391")
    assert "🟢" not in text
    assert "Confidence" not in text
    assert "Confluence" not in text
    assert "#GOLD" not in text


def test_entry_activated_message() -> None:
    text = format_entry_activated(_buy_signal(), "GOLD", current_price=4392.4)

    assert "🟡 GOLD BUY ACTIVATED" in text
    assert "Entry: 4391–4393" in text
    assert "Current: 4392.4" in text
    assert "#GOLD-20260817-001" in text


def test_tp_hit_message_lists_remaining_targets() -> None:
    signal = hit_target(activate(_buy_signal(), NOW), level=1, at=NOW)

    text = format_tp_hit(signal, "GOLD", level=1)

    assert "✅ GOLD BUY TP ¹ HIT" in text
    assert "TP ¹: 4395" in text
    assert "Còn lại:" in text
    assert "TP ² 4397" in text
    assert "TP ⁵ 4403" in text


def test_tp5_hit_message_has_no_remaining_section() -> None:
    signal = activate(_buy_signal(), NOW)
    for level in range(1, 6):
        signal = hit_target(signal, level, NOW)

    text = format_tp_hit(signal, "GOLD", level=5)

    assert "Còn lại" not in text


def test_full_tp_message_checks_off_every_level() -> None:
    signal = activate(_buy_signal(), NOW)
    for level in range(1, 6):
        signal = hit_target(signal, level, NOW)

    text = format_full_tp(signal, "GOLD")

    assert "🏆 GOLD BUY FULL TP" in text
    for i in range(1, 6):
        assert f"TP {'¹²³⁴⁵'[i - 1]} ✅" in text


def test_stop_loss_message() -> None:
    text = format_stop_loss(_buy_signal(), "GOLD")

    assert "❌ GOLD BUY STOP LOSS" in text
    assert "SL: 4384" in text
    assert "Result: SL" in text


def test_cancelled_message_includes_previous_signal_and_reasons() -> None:
    text = format_cancelled(
        _buy_signal(),
        "GOLD",
        ["Market Structure Invalidated", "Strong Bearish Reversal Confirmed"],
    )

    assert "⚠️ GOLD SIGNAL CANCELLED" in text
    assert "GOLD BUY 4393/4391" in text
    assert "Market Structure Invalidated" in text
    assert "Strong Bearish Reversal Confirmed" in text
