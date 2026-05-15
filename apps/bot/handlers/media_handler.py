# apps/bot/handlers/media_handler.py
"""
Handles media messages — photo, video, reel (video_note), carousel.

The critical design rule:
    Media processing NEVER happens synchronously.
    This handler creates the Post record immediately (fast),
    then dispatches Celery tasks for all heavy operations.

MUHIM: Bu fayl avval DirectMessageHandler ni o'z ichiga olgan —
       bu noto'g'ri. Media handler faqat media bilan shug'ullanadi.
"""

import logging

from apps.bot.handlers._base import BaseHandler
from services.post_service import create_post_from_bot
from services.telegram_service import extract_message_data

logger = logging.getLogger(__name__)


def handle_media_message(normalized: dict, source: str = "channel") -> None:
    """
    Media (photo, video, reel, carousel) update ni qayta ishlash.
    """
    handler = MediaMessageHandler(normalized, source=source)
    handler.handle()


class MediaMessageHandler(BaseHandler):

    def __init__(self, normalized: dict, source: str = "channel"):
        super().__init__(normalized)
        self.source = source

    def handle(self) -> None:
        post_type = self.normalized.get("post_type")
        chat_id = self.normalized.get("chat_id")
        message_id = self.normalized.get("message_id")
        media_group_id = self.normalized.get("media_group_id")

        logger.debug(
            "MediaHandler: processing | type=%s chat_id=%s "
            "message_id=%s media_group_id=%s",
            post_type,
            chat_id,
            message_id,
            media_group_id,
        )

        # Carousel messages arrive as a sequence of individual updates
        # all sharing the same media_group_id. We buffer them in Redis
        # and process when the group is complete.
        if media_group_id:
            self._handle_carousel(media_group_id)
            return

        # Single media item — create the post immediately
        post_data = extract_message_data(self.normalized)
        post_data["source"] = self.source
        post = create_post_from_bot(post_data)

        if post:
            logger.info(
                "MediaHandler: %s post created | post_id=%s "
                "chat_id=%s message_id=%s",
                post_type,
                post.id,
                chat_id,
                message_id,
            )

    def _handle_carousel(self, media_group_id: str) -> None:
        """
        Buffer carousel items in Redis and dispatch a Celery task
        to assemble and create the carousel post.

        Telegram sends carousel items as N separate updates, all with
        the same media_group_id but different message_ids and file_ids.
        We must collect all of them before creating a single Post.

        Strategy:
            1. Add this item to a Redis list keyed by media_group_id
            2. Reset a 10-second expiry on the key
            3. Dispatch a Celery task with countdown=3 that will
               read the buffer and create the carousel post.
        """
        from tasks.media_tasks import assemble_carousel_post
        from django.core.cache import cache

        buffer_key = f"carousel:buffer:{media_group_id}"

        # Add this item to the Redis buffer
        existing = cache.get(buffer_key) or []
        existing.append({
            "file_id": self.normalized.get("file_id", ""),
            "message_id": self.normalized.get("message_id"),
            "content": self.normalized.get("text", ""),
        })
        # 10 second TTL — generous buffer for slow Telegram delivery
        cache.set(buffer_key, existing, timeout=10)

        # Re-dispatch the assembly task each time (countdown resets).
        # The task is idempotent — the first execution that finds all
        # items creates the post; subsequent ones find the buffer empty.
        assemble_carousel_post.apply_async(
            kwargs={
                "media_group_id": media_group_id,
                "chat_id": self.normalized.get("chat_id"),
                "source": self.source,
                "first_message_id": self.normalized.get("message_id"),
            },
            countdown=3,
        )

        logger.debug(
            "MediaHandler: carousel item buffered | "
            "media_group_id=%s count=%d",
            media_group_id,
            len(existing),
        )