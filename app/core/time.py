import re
from datetime import datetime

# datetime.fromisoformat supports at most microsecond (6-digit) precision; OANDA emits
# up to 9-digit nanosecond fractional seconds, so truncate before parsing rather than
# relying on any particular Python version's leniency with the raw string.
_FRACTIONAL_SECONDS_RE = re.compile(r"(\.\d{6})\d*")


def parse_iso8601(raw: str) -> datetime:
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    normalized = _FRACTIONAL_SECONDS_RE.sub(r"\1", normalized)
    return datetime.fromisoformat(normalized)
