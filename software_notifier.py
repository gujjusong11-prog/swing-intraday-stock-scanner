import os
from telegram import Bot
from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT1_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()


def telegram_configured() -> bool:
    return bool(BOT_TOKEN and ADMIN_CHAT_ID and ADMIN_CHAT_ID.lstrip("-").isdigit())


async def send_telegram_message(message: str) -> bool:
    if not telegram_configured():
        return False

    try:
        bot = Bot(token=BOT_TOKEN)

        async with bot:
            await bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=message,
            )

        return True

    except Exception:
        return False


async def notify_scanner_event(
    event: str,
    details: str = "",
) -> bool:
    message = f"📊 SWING & INTRADAY SCANNER\n\n{event}"

    if details:
        message += f"\n\n{details}"

    return await send_telegram_message(message)


if __name__ == "__main__":
    print("software_notifier.py loaded")
    print(f"Telegram configured: {telegram_configured()}")
