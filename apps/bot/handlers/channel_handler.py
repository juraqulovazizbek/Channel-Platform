"""
Handles channel_post updates — posts that arrive from a linked
Telegram channel where the bot is an admin.

These are the backbone of the auto-sync feature:
every post published in the Telegram channel becomes a Post record.
"""

import logging

from apps.bot.handlers._base import BaseHandler
from services.post_service import create_post_from_bot
from services.telegram_service import extract_message_data

logger = logging.getLogger(__name__)


def handle_channel_post(normalized: dict) -> None:
    """
    Process a channel_post update.

    Flow:
        normalized update
        → extract_message_data  (maps normalized → post_service input)
        → create_post_from_bot  (handles dedup, DB write, task dispatch)

    Heavy work (media download, thumbnail generation) is dispatched
    to Celery inside create_post_from_bot — this function returns fast.
    """
    handler = ChannelPostHandler(normalized)
    handler.handle()


class ChannelPostHandler(BaseHandler):

    def handle(self) -> None:
        chat_id = self.normalized.get("chat_id")
        message_id = self.normalized.get("message_id")

        if not chat_id:
            logger.warning(
                "ChannelPostHandler: missing chat_id | update_id=%s",
                self.update_id,
            )
            return

        post_data = extract_message_data(self.normalized)
        post = create_post_from_bot(post_data)

        if post:
            logger.info(
                "ChannelPostHandler: post created | "
                "post_id=%s chat_id=%s message_id=%s",
                post.id,
                chat_id,
                message_id,
            )
        else:
            logger.debug(
                "ChannelPostHandler: post skipped (duplicate or no channel) | "
                "chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )