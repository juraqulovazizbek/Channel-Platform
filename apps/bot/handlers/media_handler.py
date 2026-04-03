"""
Handles direct messages sent to the bot by users.

Supports command parsing (/start, /help, /link) and plain
text messages forwarded by channel owners.
"""

import logging

from apps.bot.handlers._base import BaseHandler
from services.telegram_service import send_message
from services.post_service import create_post_from_bot
from services.telegram_service import extract_message_data

logger = logging.getLogger(__name__)

# Command registry — maps /command → handler method name
COMMAND_MAP = {
    "/start": "_cmd_start",
    "/help": "_cmd_help",
    "/status": "_cmd_status",
}


def handle_direct_message(normalized: dict) -> None:
    handler = DirectMessageHandler(normalized)
    handler.handle()


class DirectMessageHandler(BaseHandler):

    def handle(self) -> None:
        text = self.normalized.get("text", "").strip()
        chat_id = self.normalized.get("chat_id")

        if not chat_id:
            return

        # ── Command routing ───────────────────────────────────────────────
        if text.startswith("/"):
            command = text.split()[0].lower()
            # Strip bot mention: /start@mybot → /start
            command = command.split("@")[0]
            method_name = COMMAND_MAP.get(command)
            if method_name:
                getattr(self, method_name)(chat_id, text)
            else:
                self._unknown_command(chat_id, command)
            return

        # ── Plain text forwarded by channel owner ─────────────────────────
        # If the message comes from a linked channel context,
        # treat it as a text post.
        if self.normalized.get("source") == "bot":
            post_data = extract_message_data(self.normalized)
            post_data["source"] = "bot"
            post = create_post_from_bot(post_data)
            if post:
                logger.info(
                    "DirectMessageHandler: text post created via bot | "
                    "post_id=%s chat_id=%s",
                    post.id,
                    chat_id,
                )

    # ── Command handlers ─────────────────────────────────────────────────

    def _cmd_start(self, chat_id: int, text: str) -> None:
        send_message(
            chat_id,
            (
                "<b>Welcome to Telegram Channel Platform</b>\n\n"
                "Add me as an admin to your Telegram channel, then "
                "link it from your dashboard to start syncing posts.\n\n"
                "Use /help to see available commands."
            ),
        )

    def _cmd_help(self, chat_id: int, text: str) -> None:
        send_message(
            chat_id,
            (
                "<b>Available commands</b>\n\n"
                "/start — Introduction\n"
                "/help  — Show this message\n"
                "/status — Check bot status\n\n"
                "To sync your channel, add me as admin and "
                "link the channel from your dashboard."
            ),
        )

    def _cmd_status(self, chat_id: int, text: str) -> None:
        send_message(
            chat_id,
            "<b>Bot status:</b> Online and operational.",
        )

    def _unknown_command(self, chat_id: int, command: str) -> None:
        send_message(
            chat_id,
            f"Unknown command: <code>{command}</code>\n"
            f"Use /help to see available commands.",
        )