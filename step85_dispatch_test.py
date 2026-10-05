import asyncio
from pathlib import Path
from software_notifier import telegram_configured, send_telegram_message

async def main():
    print("CONFIGURED:", telegram_configured())
    result = await send_telegram_message(
        "STEP 85 — GEMINI AUDITOR BOT-1 DISPATCH TEST"
    )
    print("DISPATCH_RESULT:", result)

asyncio.run(main())
