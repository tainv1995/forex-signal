from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.enums import Direction
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TradeTicket:
    ticket_id: str
    symbol: str
    direction: Direction
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float


class ExecutionProvider(ABC):
    """Section 50: prepared now so a real broker (MT4/MT5/OANDA order execution) can
    be plugged in later without touching analysis/signal/tracking code - none of
    which call this today; PAPER_MODE means no real capital is ever at risk."""

    @abstractmethod
    async def open_trade(
        self,
        symbol: str,
        direction: Direction,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> TradeTicket: ...

    @abstractmethod
    async def modify_trade(
        self, ticket_id: str, stop_loss: float | None = None, take_profit: float | None = None
    ) -> None: ...

    @abstractmethod
    async def close_trade(self, ticket_id: str) -> None: ...


class PaperExecutionProvider(ExecutionProvider):
    """The only ExecutionProvider actually wired in today (Section 50 / PAPER_MODE):
    records what would have happened without sending any order anywhere."""

    async def open_trade(
        self,
        symbol: str,
        direction: Direction,
        volume: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> TradeTicket:
        ticket = TradeTicket(
            ticket_id=f"PAPER-{symbol}-{entry_price:.2f}-{direction.value}",
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        logger.info(
            "[PAPER] would open %s %s vol=%s entry=%s sl=%s tp=%s",
            symbol,
            direction.value,
            volume,
            entry_price,
            stop_loss,
            take_profit,
        )
        return ticket

    async def modify_trade(
        self, ticket_id: str, stop_loss: float | None = None, take_profit: float | None = None
    ) -> None:
        logger.info("[PAPER] would modify %s sl=%s tp=%s", ticket_id, stop_loss, take_profit)

    async def close_trade(self, ticket_id: str) -> None:
        logger.info("[PAPER] would close %s", ticket_id)
