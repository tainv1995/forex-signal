from collections.abc import Sequence

from app.core.enums import Direction
from app.engines.signal import Signal, TargetLevel

SUPERSCRIPT = {1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵"}


def format_price_value(price: float) -> str:
    text = f"{price:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _target_lines(targets: Sequence[TargetLevel]) -> list[str]:
    return [f"TP {SUPERSCRIPT[t.level]} {format_price_value(t.price)}" for t in targets]


def format_entry_range(signal: Signal) -> str:
    """BUY lists the near boundary (price falls into it from above) first: high/low.
    SELL lists the near boundary (price rises into it from below) first: low/high."""
    if signal.direction is Direction.BUY:
        return f"{format_price_value(signal.entry_high)}/{format_price_value(signal.entry_low)}"
    return f"{format_price_value(signal.entry_low)}/{format_price_value(signal.entry_high)}"


def format_entry_dash_range(signal: Signal) -> str:
    """Plain ascending low-high range (used by "Entry:" and "Best Signal:" lines,
    as opposed to format_entry_range's direction-dependent header order)."""
    return f"{format_price_value(signal.entry_low)}–{format_price_value(signal.entry_high)}"


def _header(signal: Signal, label: str) -> str:
    return f"{label} {signal.direction.value} {format_entry_range(signal)}"


def format_new_signal(signal: Signal, symbol_label: str, show_metadata: bool) -> str:
    emoji = "🟢" if signal.direction is Direction.BUY else "🔴"
    header = _header(signal, symbol_label)
    lines = [f"{emoji} {header}" if show_metadata else header, ""]
    lines += _target_lines(signal.targets)
    lines += ["", f"SL    {format_price_value(signal.stop_loss)}"]
    if show_metadata:
        lines += ["", f"#{signal.id}"]
    return "\n".join(lines)


def format_entry_activated(signal: Signal, symbol_label: str, current_price: float) -> str:
    lines = [
        f"🟡 {symbol_label} {signal.direction.value} ACTIVATED",
        "",
        f"Entry: {format_entry_dash_range(signal)}",
        f"Current: {format_price_value(current_price)}",
        "",
        f"#{signal.id}",
    ]
    return "\n".join(lines)


def format_tp_hit(signal: Signal, symbol_label: str, level: int) -> str:
    hit = next(t for t in signal.targets if t.level == level)
    remaining = [t for t in signal.targets if t.level > level]

    lines = [
        f"✅ {symbol_label} {signal.direction.value} TP {SUPERSCRIPT[level]} HIT",
        "",
        f"Entry: {format_entry_range(signal)}",
        f"TP {SUPERSCRIPT[level]}: {format_price_value(hit.price)}",
    ]
    if remaining:
        lines += ["", "Còn lại:", ""]
        lines += _target_lines(remaining)
    lines += ["", f"#{signal.id}"]
    return "\n".join(lines)


def format_full_tp(signal: Signal, symbol_label: str) -> str:
    lines = [f"🏆 {symbol_label} {signal.direction.value} FULL TP", ""]
    lines += [f"TP {SUPERSCRIPT[t.level]} ✅" for t in signal.targets]
    lines += ["", f"#{signal.id}"]
    return "\n".join(lines)


def format_stop_loss(signal: Signal, symbol_label: str) -> str:
    lines = [
        f"❌ {symbol_label} {signal.direction.value} STOP LOSS",
        "",
        f"Entry: {format_entry_range(signal)}",
        "",
        f"SL: {format_price_value(signal.stop_loss)}",
        "",
        "Result: SL",
        "",
        f"#{signal.id}",
    ]
    return "\n".join(lines)


def format_cancelled(signal: Signal, symbol_label: str, reason_lines: list[str]) -> str:
    lines = [
        f"⚠️ {symbol_label} SIGNAL CANCELLED",
        "",
        "Previous:",
        "",
        _header(signal, symbol_label),
        "",
        "Reason:",
        "",
        *reason_lines,
        "",
        f"#{signal.id}",
    ]
    return "\n".join(lines)
