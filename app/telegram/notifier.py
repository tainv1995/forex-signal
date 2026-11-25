from datetime import date
from typing import Protocol

from app.core.logging import get_logger
from app.engines.signal import Signal
from app.telegram.client import TelegramClient, TelegramError
from app.telegram.formatter import (
    format_cancelled,
    format_entry_activated,
    format_full_tp,
    format_new_signal,
    format_stop_loss,
    format_tp_hit,
)

logger = get_logger(__name__)


class TelegramMessageStore(Protocol):
    """Structural interface satisfied by TelegramMessageRepository (and by a fake
    in tests) - the notifier only needs these three operations."""

    async def try_reserve(
        self, idempotency_key: str, signal_id: str | None, event: str, chat_id: str, text: str
    ) -> int | None: ...

    async def mark_sent(self, row_id: int, telegram_message_id: int) -> None: ...

    async def mark_failed(self, row_id: int, error: str) -> None: ...


class TelegramNotifier:
    """Formats + sends signal notifications, with a reserve-before-send idempotency
    check (Section 47) so the same event is never posted to the channel twice."""

    def __init__(
        self,
        client: TelegramClient,
        message_repo: TelegramMessageStore,
        chat_id: str,
        symbol_label: str,
        show_metadata: bool,
    ) -> None:
        self._client = client
        self._message_repo = message_repo
        self._chat_id = chat_id
        self._symbol_label = symbol_label
        self._show_metadata = show_metadata

    async def _send_once(
        self, idempotency_key: str, signal_id: str | None, event: str, text: str
    ) -> int | None:
        row_id = await self._message_repo.try_reserve(
            idempotency_key, signal_id, event, self._chat_id, text
        )
        if row_id is None:
            logger.info("skipping duplicate telegram send for %s", idempotency_key)
            return None
        try:
            message_id = await self._client.send_message(self._chat_id, text)
        except TelegramError as exc:
            await self._message_repo.mark_failed(row_id, str(exc))
            raise
        await self._message_repo.mark_sent(row_id, message_id)
        return message_id

    async def notify_new_signal(self, signal: Signal) -> int | None:
        text = format_new_signal(signal, self._symbol_label, self._show_metadata)
        return await self._send_once(
            f"{signal.id}:SIGNAL_CREATED", signal.id, "SIGNAL_CREATED", text
        )

    async def notify_entry_activated(self, signal: Signal, current_price: float) -> int | None:
        text = format_entry_activated(signal, self._symbol_label, current_price)
        return await self._send_once(f"{signal.id}:ENTRY_TOUCHED", signal.id, "ENTRY_TOUCHED", text)

    async def notify_tp_hit(self, signal: Signal, level: int) -> int | None:
        # TP5 is the last target - send the FULL TP celebration instead of a
        # redundant "TP5 HIT" message right on top of it (Section 25 vs 27).
        if level == 5:
            text = format_full_tp(signal, self._symbol_label)
            event = "TP5_HIT"
        else:
            text = format_tp_hit(signal, self._symbol_label, level)
            event = f"TP{level}_HIT"
        return await self._send_once(f"{signal.id}:{event}", signal.id, event, text)

    async def notify_stop_loss(self, signal: Signal) -> int | None:
        text = format_stop_loss(signal, self._symbol_label)
        return await self._send_once(f"{signal.id}:SL_HIT", signal.id, "SL_HIT", text)

    async def notify_cancelled(self, signal: Signal, reason_lines: list[str]) -> int | None:
        text = format_cancelled(signal, self._symbol_label, reason_lines)
        return await self._send_once(
            f"{signal.id}:SIGNAL_CANCELLED", signal.id, "SIGNAL_CANCELLED", text
        )

    async def notify_daily_report(self, report_date: date, text: str) -> int | None:
        key = f"DAILY_REPORT:{report_date.isoformat()}"
        return await self._send_once(key, None, "DAILY_REPORT", text)
