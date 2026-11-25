from collections.abc import Sequence
from dataclasses import dataclass, field

from app.engines.signal import Signal
from app.telegram.formatter import format_entry_range, format_price_value

ADMIN_COMMANDS = ("/status", "/price", "/signal", "/analysis", "/report", "/pause", "/resume")


def parse_command(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    first_word = stripped.split()[0].lower()
    return first_word.split("@")[0]  # strip a "@BotName" suffix, e.g. "/status@gold_bot"


def is_admin(user_id: int, admin_ids: Sequence[int]) -> bool:
    return user_id in admin_ids


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    symbol: str
    running: bool
    last_price: float | None
    bias_by_timeframe: dict[str, str] = field(default_factory=dict)
    buy_confidence: float = 0.0
    sell_confidence: float = 0.0
    active_signal_id: str | None = None
    market_data_ok: bool = False
    telegram_ok: bool = False
    database_ok: bool = False


def format_status(snapshot: StatusSnapshot) -> str:
    lines = [
        "🤖 GOLD BOT",
        "",
        f"Status: {'RUNNING' if snapshot.running else 'PAUSED'}",
        "",
        f"{snapshot.symbol}: {format_price_value(snapshot.last_price) if snapshot.last_price is not None else 'N/A'}",
        "",
    ]
    lines += [f"{tf}: {bias}" for tf, bias in snapshot.bias_by_timeframe.items()]
    lines += [
        "",
        f"BUY Confidence: {snapshot.buy_confidence:.0%}",
        f"SELL Confidence: {snapshot.sell_confidence:.0%}",
        "",
        "Active Signal:",
        snapshot.active_signal_id or "None",
        "",
        f"Market Data: {'✅' if snapshot.market_data_ok else '❌'}",
        f"Telegram: {'✅' if snapshot.telegram_ok else '❌'}",
        f"Database: {'✅' if snapshot.database_ok else '❌'}",
    ]
    return "\n".join(lines)


def format_price(symbol: str, price: float) -> str:
    return f"{symbol}: {format_price_value(price)}"


def format_active_signal(signal: Signal | None) -> str:
    if signal is None:
        return "Không có tín hiệu đang hoạt động."
    lines = [
        f"#{signal.id}",
        f"{signal.direction.value} {format_entry_range(signal)}",
        f"Status: {signal.status.value}",
        f"SL: {format_price_value(signal.stop_loss)}",
    ]
    return "\n".join(lines)


def format_pause() -> str:
    return "⏸ Bot đã tạm dừng phát tín hiệu mới (tín hiệu đang chạy vẫn được theo dõi)."


def format_resume() -> str:
    return "▶️ Bot đã tiếp tục phát tín hiệu mới."


def format_report_not_ready() -> str:
    return "📊 Báo cáo cuối ngày chưa khả dụng."


def format_unknown_command(command: str) -> str:
    return f"Không nhận diện được lệnh: {command}"


def format_unauthorized() -> str:
    return "Bạn không có quyền sử dụng lệnh này."
