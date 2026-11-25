"""Send one real Telegram message using TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from
.env - proof the bot can actually reach your chat, not just pass mocked tests.

Usage:
    python scripts/send_test_telegram_message.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.telegram.client import TelegramClient


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    client = TelegramClient(settings.telegram_bot_token)
    try:
        message_id = await client.send_message(
            settings.telegram_chat_id,
            "🤖 Gold Signal Bot - test message from scripts/send_test_telegram_message.py",
        )
        print(f"Sent OK, message_id={message_id}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
