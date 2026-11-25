"""One-off verification of TelegramMessageRepository's idempotency guarantee against
a real Postgres instance (same convention as verify_signal_repository.py):

    DATABASE_URL="postgresql+asyncpg://gold:gold@localhost:5433/goldbot" \\
        python scripts/verify_telegram_message_repository.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.repositories.telegram_message_repository import TelegramMessageRepository
from app.db.session import get_session_factory


async def main() -> None:
    session_factory = get_session_factory()
    idempotency_key = f"VERIFY:{uuid.uuid4()}"

    async def _reserve() -> int | None:
        async with session_factory() as session:
            return await TelegramMessageRepository(session).try_reserve(
                idempotency_key, None, "TEST_EVENT", "123", "hello"
            )

    # Two workers racing to reserve the exact same idempotency key.
    result_a, result_b = await asyncio.gather(_reserve(), _reserve())
    winners = [r for r in (result_a, result_b) if r is not None]
    assert len(winners) == 1, f"expected exactly one winner, got {result_a}, {result_b}"
    print(f"race check ok: worker A={result_a} worker B={result_b} (exactly one non-None)")

    async with session_factory() as session:
        repo = TelegramMessageRepository(session)
        await repo.mark_sent(winners[0], telegram_message_id=999)
    print(f"marked row {winners[0]} as sent")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
