from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.analysis.bias import gather_bias_and_confidence
from app.core.config import Settings
from app.db.repositories.signal_repository import SignalRepository
from app.db.repositories.system_health_repository import SystemHealthRepository
from app.market_data.base import MarketDataProvider
from app.reports.statistics import SignalStatistics, compute_statistics, outcome_of
from app.telegram.formatter import SUPERSCRIPT, format_entry_dash_range


@dataclass(frozen=True, slots=True)
class DailyReportData:
    report_date: date
    symbol_label: str
    stats: SignalStatistics
    bias_by_timeframe: dict[str, str]
    uptime_percentage: float | None = None


def format_daily_report(data: DailyReportData) -> str:
    """Section 38. No lot size is configured anywhere in this project, so this never
    fabricates a USD profit figure - only R multiples, win/loss counts and TP rates,
    all of which come straight out of SignalStatistics."""
    stats = data.stats

    lines = [
        f"📊 {data.symbol_label} DAILY REPORT",
        data.report_date.strftime("%d/%m/%Y"),
        "",
        f"Tổng signal: {stats.total_signals}",
        "",
        f"BUY: {stats.buy_count}",
        f"SELL: {stats.sell_count}",
        "",
        f"✅ Win: {stats.win_count}",
        f"❌ SL: {stats.sl_count}",
        f"⚪ Cancelled: {stats.cancelled_count}",
        "",
    ]
    lines += [
        f"TP {SUPERSCRIPT[level]}: {stats.tp_hit_counts.get(level, 0)}" for level in range(1, 6)
    ]
    lines.append("")
    lines.append(
        f"Win Rate: {stats.win_rate:.0%}" if stats.win_rate is not None else "Win Rate: N/A"
    )

    if stats.best_signal is not None and outcome_of(stats.best_signal) == "WIN":
        best = stats.best_signal
        best_level = max(t.level for t in best.targets if t.hit)
        lines += [
            "",
            "Best Signal:",
            f"{best.direction.value} {format_entry_dash_range(best)} → TP{best_level}",
        ]

    lines += ["", "Market Bias:", ""]
    lines += [f"{tf}: {label.capitalize()}" for tf, label in data.bias_by_timeframe.items()]

    lines += [
        "",
        (
            f"Average Confidence: {stats.average_confidence:.1%}"
            if stats.average_confidence is not None
            else "Average Confidence: N/A"
        ),
        "",
        f"Average R:R: {stats.average_rr:.2f}"
        if stats.average_rr is not None
        else "Average R:R: N/A",
        "",
        (
            f"Bot Uptime: {data.uptime_percentage:.1%}"
            if data.uptime_percentage is not None
            else "Bot Uptime: N/A"
        ),
    ]
    return "\n".join(lines)


async def build_daily_report(
    settings: Settings,
    provider: MarketDataProvider,
    signal_repo: SignalRepository,
    health_repo: SystemHealthRepository,
    report_date: date,
) -> DailyReportData:
    """Gathers everything format_daily_report() needs: signals closed during
    `report_date` in the configured report timezone, freshly recomputed market bias,
    and real recorded uptime (Section 38 runs this at REPORT_TIME/REPORT_TIMEZONE)."""
    tz = ZoneInfo(settings.report_timezone)
    start_local = datetime.combine(report_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    signals = await signal_repo.get_closed_between(settings.symbol, start_utc, end_utc)
    stats = compute_statistics(signals)
    bias, _, _ = await gather_bias_and_confidence(provider, settings.symbol)
    uptime = await health_repo.uptime_percentage(start_utc, end_utc)

    return DailyReportData(
        report_date=report_date,
        symbol_label=settings.telegram_symbol_label,
        stats=stats,
        bias_by_timeframe=bias,
        uptime_percentage=uptime,
    )
