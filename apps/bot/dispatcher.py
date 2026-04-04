"""
Update dispatcher — routes normalized Telegram updates to the
correct handler based on update type.

WHY A SEPARATE MODULE:
    TelegramWebhookView should not know about update types.
    Handlers should not know about each other.
    The dispatcher is the only place that knows both.

    views.py  →  dispatcher.py  →  handlers/*
                                →  tasks/*  (for heavy work)
"""

import logging

from services.telegram_service import parse_webhook_update
from apps.bot.handlers.channel_handler import handle_channel_post
from apps.bot.handlers.message_handler import handle_direct_message
from apps.bot.handlers.media_handler import handle_media_message
from apps.bot.handlers.edit_handler import handle_edited_post

logger = logging.getLogger(__name__)


def dispatch_update(update: dict) -> None:
    """
    Normalize the raw Telegram update and route to the correct handler.

    All handlers receive a normalized dict (not the raw Telegram structure).
    Handlers are synchronous here — heavy work is dispatched to Celery
    inside the handlers themselves.
    """
# dispatcher.py — to'g'ri versiya:
def dispatch_update(update: dict) -> None:
    normalized = parse_webhook_update(update)
    if normalized is None:
        return

    update_type = normalized.get("update_type")
    is_edit = normalized.get("is_edit", False)

    if is_edit:
        handle_edited_post(normalized)
        return

    if update_type == "channel_post":
        handle_channel_post(normalized)   # ← endi chaqiriladi
        return

    if update_type == "message":
        _route_by_media_type(normalized, source="bot")
        return

def _route_by_media_type(normalized: dict, source: str) -> None:
    """
    Sub-route by post type within a channel_post or message update.
    Text goes to message handler, media goes to media handler.
    """
    post_type = normalized.get("post_type", "text")

    if post_type == "text":
        handle_direct_message(normalized)
    elif post_type in ("image", "video", "reel", "carousel"):
        handle_media_message(normalized, source=source)
    else:
        logger.debug(
            "Dispatcher: unhandled post_type=%s", post_type
        )