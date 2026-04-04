# apps/bot/dispatcher.py

"""
Update dispatcher — routes normalized Telegram updates to the
correct handler based on update type.
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
    Heavy work is dispatched to Celery inside the handlers themselves.
    """
    normalized = parse_webhook_update(update)

    if normalized is None:
        logger.debug(
            "Dispatcher: skipping unhandled update | update_id=%s keys=%s",
            update.get("update_id"),
            list(update.keys()),
        )
        return

    update_type = normalized.get("update_type")
    is_edit = normalized.get("is_edit", False)

    logger.debug(
        "Dispatcher: routing | update_id=%s type=%s is_edit=%s",
        normalized.get("update_id"),
        update_type,
        is_edit,
    )

    if is_edit:
        handle_edited_post(normalized)
        return

    if update_type == "channel_post":
        handle_channel_post(normalized)
        return

    if update_type == "message":
        _route_by_media_type(normalized, source="bot")
        return

    logger.debug("Dispatcher: no handler for update_type=%s", update_type)


def _route_by_media_type(normalized: dict, source: str) -> None:
    """
    Sub-route by post type within a message update.
    Text → message handler. Media → media handler.
    """
    post_type = normalized.get("post_type", "text")

    if post_type == "text":
        handle_direct_message(normalized)
    elif post_type in ("image", "video", "reel", "carousel"):
        handle_media_message(normalized, source=source)
    else:
        logger.debug("Dispatcher: unhandled post_type=%s", post_type)