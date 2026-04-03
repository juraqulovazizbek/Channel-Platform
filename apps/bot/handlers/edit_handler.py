"""
Handles edited_message and edited_channel_post updates.

When a Telegram user edits a message, we update the corresponding
Post record's content. We do NOT re-download media on edits —
media edits are not supported by Telegram's Bot API.
"""

import logging

from apps.bot.handlers._base import BaseHandler

logger = logging.getLogger(__name__)


def handle_edited_post(normalized: dict) -> None:
    handler = EditHandler(normalized)
    handler.handle()


class EditHandler(BaseHandler):

    def handle(self) -> None:
        from apps.posts.models import Post
        from apps.channels.models import Channel

        chat_id = self.normalized.get("chat_id")
        message_id = self.normalized.get("message_id")
        new_content = self.normalized.get("text", "")

        if not chat_id or not message_id:
            logger.debug(
                "EditHandler: missing chat_id or message_id | "
                "update_id=%s",
                self.update_id,
            )
            return

        # Resolve the channel — silently skip if not linked
        try:
            channel = Channel.objects.get(
                telegram_channel_id=chat_id,
                is_active=True,
            )
        except Channel.DoesNotExist:
            logger.debug(
                "EditHandler: no linked channel for chat_id=%s", chat_id
            )
            return

        # Find the existing post — silently skip if not found
        # (happens when edits arrive for posts that predate the sync)
        try:
            post = Post.objects.get(
                channel=channel,
                telegram_message_id=message_id,
            )
        except Post.DoesNotExist:
            logger.debug(
                "EditHandler: post not found | chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )
            return

        if not new_content or post.content == new_content:
            logger.debug(
                "EditHandler: no content change | post_id=%s", post.id
            )
            return

        post.content = new_content
        post.save(update_fields=["content", "updated_at"])

        logger.info(
            "EditHandler: post content updated | post_id=%s", post.id
        )