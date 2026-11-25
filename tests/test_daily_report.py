from datetime import UTC, date, datetime

from app.core.enums import Direction, SignalTier
from app.engines.risk import StopLoss
from app.engines.signal import Signal, activate, build_signal, cancel, hit_target, stop_out
from app.engines.targets import TakeProfit
from app.reports.daily import DailyReportData, format_daily_report
from app.reports.statistics import compute_statistics

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _signal(signal_id: str, direction: Direction = Direction.BUY) -> Signal:
    tps = [TakeProfit(i, 4391.0 + i * 2, float(i), "t") for i in range(1, 6)]
    return build_signal(
        signal_id,
        "XAUUSD",
        direction,
        4389.0,
        4391.0,
        StopLoss(4384.0, "t"),
        tps,
        0.8,
        SignalTier.STRONG,
        8,
        ["r"],
        "M15",
        NOW,
    )


def test_format_daily_report_matches_expected_shape() -> None:
    win = activate(_signal("GOLD-1"), NOW)
    for level in range(1, 6):
        win = hit_target(win, level, NOW)
    loss = stop_out(activate(_signal("GOLD-2"), NOW), NOW)
    cancelled = cancel(_signal("GOLD-3"), NOW, reason="test")

    stats = compute_statistics([win, loss, cancelled])
    data = DailyReportData(
        report_date=date(2026, 8, 17),
        symbol_label="GOLD",
        stats=stats,
        bias_by_timeframe={"H4": "BULLISH", "H1": "BULLISH", "M15": "NEUTRAL"},
        uptime_percentage=0.999,
    )

    text = format_daily_report(data)

    assert text.startswith("📊 GOLD DAILY REPORT\n17/08/2026")
    assert "Tổng signal: 3" in text
    assert "BUY: 3" in text
    assert "✅ Win: 1" in text
    assert "❌ SL: 1" in text
    assert "⚪ Cancelled: 1" in text
    assert "TP ¹: 1" in text
    assert "TP ⁵: 1" in text
    assert "Win Rate: 50%" in text
    assert "Best Signal:" in text
    assert "BUY 4389–4391 → TP5" in text
    assert "H4: Bullish" in text
    assert "Average Confidence: 80.0%" in text
    assert "Bot Uptime: 99.9%" in text


def test_no_best_signal_section_when_nobody_won() -> None:
    loss = stop_out(activate(_signal("GOLD-1"), NOW), NOW)
    stats = compute_statistics([loss])
    data = DailyReportData(date(2026, 8, 17), "GOLD", stats, {})

    text = format_daily_report(data)

    assert "Best Signal" not in text


def test_missing_optional_metrics_show_as_not_available() -> None:
    stats = compute_statistics([])
    data = DailyReportData(date(2026, 8, 17), "GOLD", stats, {})

    text = format_daily_report(data)

    assert "Win Rate: N/A" in text
    assert "Average Confidence: N/A" in text
    assert "Average R:R: N/A" in text
    assert "Bot Uptime: N/A" in text
