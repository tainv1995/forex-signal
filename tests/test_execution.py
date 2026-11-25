import pytest

from app.core.enums import Direction
from app.execution.base import PaperExecutionProvider


@pytest.mark.asyncio
async def test_paper_open_trade_returns_a_ticket_without_sending_any_order() -> None:
    provider = PaperExecutionProvider()

    ticket = await provider.open_trade(
        symbol="XAUUSD",
        direction=Direction.BUY,
        volume=0.1,
        entry_price=2650.0,
        stop_loss=2640.0,
        take_profit=2670.0,
    )

    assert ticket.symbol == "XAUUSD"
    assert ticket.direction is Direction.BUY
    assert ticket.entry_price == 2650.0
    assert ticket.ticket_id.startswith("PAPER-")


@pytest.mark.asyncio
async def test_paper_modify_and_close_do_not_raise() -> None:
    provider = PaperExecutionProvider()
    ticket = await provider.open_trade("XAUUSD", Direction.SELL, 0.1, 2650.0, 2660.0, 2630.0)

    await provider.modify_trade(ticket.ticket_id, stop_loss=2655.0)
    await provider.close_trade(ticket.ticket_id)
