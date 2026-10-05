from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# BOT-1 SECURITY FOUNDATION
# TASK-013
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load secrets only from the local protected .env file.
load_dotenv(ENV_FILE)

BOT_TOKEN = os.getenv("TELEGRAM_BOT1_TOKEN", "").strip()
ADMIN_CHAT_ID_RAW = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()


# ------------------------------------------------------------
# Fail-closed credential validation
# ------------------------------------------------------------

if not BOT_TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT1_TOKEN is missing. Bot startup blocked."
    )

if not ADMIN_CHAT_ID_RAW:
    raise RuntimeError(
        "TELEGRAM_ADMIN_CHAT_ID is missing. Bot startup blocked."
    )

try:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
except ValueError as exc:
    raise RuntimeError(
        "TELEGRAM_ADMIN_CHAT_ID must be numeric. Bot startup blocked."
    ) from exc


# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("bot1_manager")


# ------------------------------------------------------------
# Authorization
# ------------------------------------------------------------

def is_authorized(update: Update) -> bool:
    """
    Allow commands only from the configured administrator Chat ID.
    """
    if update.effective_chat is None:
        return False

    return update.effective_chat.id == ADMIN_CHAT_ID


async def reject_unauthorized(update: Update) -> None:
    """
    Reject unauthorized requests without exposing security details.
    """
    if update.effective_message:
        await update.effective_message.reply_text(
            "Access denied."
        )


# ------------------------------------------------------------
# /start
# ------------------------------------------------------------

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update):
        await reject_unauthorized(update)
        return

    await update.effective_message.reply_text(
        "Bot-1 Security Foundation is active.\n"
        "Use /help to view available commands."
    )


# ------------------------------------------------------------
# /help
# ------------------------------------------------------------

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update):
        await reject_unauthorized(update)
        return

    await update.effective_message.reply_text(
        "Bot-1 Commands:\n\n"
        "/start - Start Bot-1\n"
        "/status - Security/system status\n"
        "/help - Show available commands"
    )


# ------------------------------------------------------------
# /status
# ------------------------------------------------------------

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update):
        await reject_unauthorized(update)
        return

    await update.effective_message.reply_text(
        "BOT-1 STATUS\n"
        "Authentication: ACTIVE\n"
        "Authorization: ACTIVE\n"
        "Secret source: Local .env\n"
        "Execution mode: Read-only foundation\n"
        "Software update access: DISABLED"
    )


# ------------------------------------------------------------
# Error handler
# ------------------------------------------------------------

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    # Never log the bot token or environment secrets.
    logger.error(
        "Bot update processing error: %s",
        context.error,
    )


# ------------------------------------------------------------
# Application
# ------------------------------------------------------------

def build_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start_command)
    )
    application.add_handler(
        CommandHandler("help", help_command)
    )
    application.add_handler(
        CommandHandler("status", status_command)
    )

    application.add_error_handler(error_handler)

    return application


def main() -> None:
    logger.info("Bot-1 starting.")
    logger.info("Authentication foundation loaded.")
    logger.info("Software update access is disabled.")

    application = build_application()

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
