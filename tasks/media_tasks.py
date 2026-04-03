"""
Media processing tasks.

All tasks follow the same pattern:
    - Accept primitive arguments (IDs, strings) — never model instances.
      Celery serializes arguments; model instances don't serialize cleanly.
    - Re-fetch the model instance inside the task.
    - Use self.retry() with exponential backoff for transient failures.
    - Log start, success, and failure explicitly.
"""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,     # Initial retry delay: 60 seconds
    soft_time_limit=300,        # 5 minutes soft limit
    time_limit=360,             # 6 minutes hard limit
    name="tasks.media_tasks.process_media_file",
)
def process_media_file(self, post_id: str, telegram_file_id: str) -> dict:
    """
    Download a file from Telegram's CDN and attach it to a Post.

    Called after create_post_from_bot() when the post has a
    telegram_file_id that hasn't been downloaded yet.

    Retry strategy:
        Attempt 1:  60 seconds after failure
        Attempt 2:  120 seconds (default_retry_delay × 2^retry_count)
        Attempt 3:  240 seconds
        After 3 failures: task moves to failed state, logged for alerting.
    """
    from apps.posts.models import Post
    from services.post_service import handle_media_download_and_attach

    logger.info(
        "process_media_file: starting | post_id=%s file_id=%s",
        post_id,
        telegram_file_id,
    )

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        # Post was deleted between task dispatch and execution — not an error
        logger.warning(
            "process_media_file: post not found | post_id=%s", post_id
        )
        return {"status": "skipped", "reason": "post_not_found"}

    # Skip if media was already downloaded by a previous task execution
    if post.media_file and not post.telegram_file_id:
        logger.debug(
            "process_media_file: already processed | post_id=%s", post_id
        )
        return {"status": "skipped", "reason": "already_processed"}

    try:
        success = handle_media_download_and_attach(post, telegram_file_id)

        if success:
            logger.info(
                "process_media_file: completed | post_id=%s", post_id
            )
            # Dispatch thumbnail generation for video/reel posts
            from apps.posts.models import PostType
            if post.type in (PostType.VIDEO, PostType.REEL):
                generate_video_thumbnail.delay(post_id)

            return {"status": "success", "post_id": post_id}
        else:
            # Download returned False — retry
            raise ValueError(
                f"handle_media_download_and_attach returned False "
                f"for post_id={post_id}"
            )

    except SoftTimeLimitExceeded:
        logger.error(
            "process_media_file: soft time limit exceeded | post_id=%s",
            post_id,
        )
        raise  # Do not retry on timeout — likely a very large file

    except Exception as exc:
        logger.warning(
            "process_media_file: failed (attempt %d/%d) | "
            "post_id=%s error=%s",
            self.request.retries + 1,
            self.max_retries + 1,
            post_id,
            exc,
        )
        # Exponential backoff: 60s → 120s → 240s
        raise self.retry(
            exc=exc,
            countdown=self.default_retry_delay * (2 ** self.request.retries),
        )


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
    name="tasks.media_tasks.generate_video_thumbnail",
)
def generate_video_thumbnail(self, post_id: str) -> dict:
    """
    Extract a thumbnail frame from a video or reel post.

    Uses ffmpeg (must be installed on the server/container).
    Extracts the frame at the 1-second mark — avoids black opening frames.

    ffmpeg must be in PATH. Dockerfile should include:
        RUN apt-get install -y ffmpeg
    """
    import subprocess
    import tempfile
    import os
    from django.core.files.base import ContentFile
    from apps.posts.models import Post

    logger.info(
        "generate_video_thumbnail: starting | post_id=%s", post_id
    )

    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        logger.warning(
            "generate_video_thumbnail: post not found | post_id=%s", post_id
        )
        return {"status": "skipped", "reason": "post_not_found"}

    if not post.media_file:
        logger.warning(
            "generate_video_thumbnail: no media file | post_id=%s", post_id
        )
        return {"status": "skipped", "reason": "no_media_file"}

    if post.thumbnail:
        logger.debug(
            "generate_video_thumbnail: thumbnail exists | post_id=%s", post_id
        )
        return {"status": "skipped", "reason": "already_has_thumbnail"}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input_video")
            thumb_path = os.path.join(tmpdir, "thumbnail.jpg")

            # Download the video file to a temporary path
            with post.media_file.open("rb") as f:
                with open(input_path, "wb") as out:
                    out.write(f.read())

            # Extract frame at 1 second
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i", input_path,
                    "-ss", "00:00:01.000",
                    "-vframes", "1",
                    "-vf", "scale=640:-1",    # Scale width to 640, preserve aspect ratio
                    "-q:v", "2",              # High quality JPEG
                    thumb_path,
                ],
                capture_output=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed: {result.stderr.decode()[:500]}"
                )

            with open(thumb_path, "rb") as f:
                thumbnail_content = f.read()

        post.thumbnail.save(
            f"thumb_{post_id}.jpg",
            ContentFile(thumbnail_content),
            save=True,
        )

        logger.info(
            "generate_video_thumbnail: completed | post_id=%s", post_id
        )
        return {"status": "success", "post_id": post_id}

    except subprocess.TimeoutExpired:
        logger.error(
            "generate_video_thumbnail: ffmpeg timeout | post_id=%s", post_id
        )
        return {"status": "failed", "reason": "ffmpeg_timeout"}

    except Exception as exc:
        logger.warning(
            "generate_video_thumbnail: failed (attempt %d/%d) | "
            "post_id=%s error=%s",
            self.request.retries + 1,
            self.max_retries + 1,
            post_id,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=self.default_retry_delay * (2 ** self.request.retries),
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=600,
    time_limit=660,
    name="tasks.media_tasks.assemble_carousel_post",
)
def assemble_carousel_post(
    self,
    media_group_id: str,
    chat_id: int,
    source: str,
    first_message_id: int,
) -> dict:
    """
    Assemble a carousel post from buffered media group items.

    Called with countdown=3 from MediaMessageHandler._handle_carousel().
    By the time this runs, all items in the media group should be in
    the Redis buffer.

    Idempotent — checks for existing post before creating.
    """
    from django.core.cache import cache
    from services.post_service import create_post_from_bot

    logger.info(
        "assemble_carousel_post: starting | "
        "media_group_id=%s chat_id=%s",
        media_group_id,
        chat_id,
    )

    buffer_key = f"carousel:buffer:{media_group_id}"
    media_items = cache.get(buffer_key)

    if not media_items:
        logger.warning(
            "assemble_carousel_post: buffer empty | "
            "media_group_id=%s",
            media_group_id,
        )
        return {"status": "skipped", "reason": "buffer_empty"}

    try:
        post_data = {
            "channel_id": chat_id,
            "telegram_message_id": first_message_id,
            "type": "carousel",
            "source": source,
            "content": media_items[0].get("content", "") if media_items else "",
            "media_group": media_items,
        }

        post = create_post_from_bot(post_data)

        if post:
            # Clear the buffer — successfully processed
            cache.delete(buffer_key)

            # Dispatch individual media downloads for each carousel item
            from apps.posts.models import PostMedia
            items = PostMedia.objects.filter(post=post)
            for index, item in enumerate(items):
                if item.telegram_file_id:
                    process_carousel_item_media.delay(
                        str(item.id),
                        item.telegram_file_id,
                    )

            logger.info(
                "assemble_carousel_post: completed | "
                "post_id=%s item_count=%d",
                post.id,
                len(media_items),
            )
            return {
                "status": "success",
                "post_id": str(post.id),
                "item_count": len(media_items),
            }
        else:
            logger.info(
                "assemble_carousel_post: duplicate skipped | "
                "media_group_id=%s",
                media_group_id,
            )
            cache.delete(buffer_key)
            return {"status": "skipped", "reason": "duplicate"}

    except Exception as exc:
        logger.warning(
            "assemble_carousel_post: failed (attempt %d/%d) | "
            "media_group_id=%s error=%s",
            self.request.retries + 1,
            self.max_retries + 1,
            media_group_id,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=self.default_retry_delay * (2 ** self.request.retries),
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    name="tasks.media_tasks.process_carousel_item_media",
)
def process_carousel_item_media(
    self, carousel_item_id: str, telegram_file_id: str
) -> dict:
    """
    Download and attach media for a single PostMedia (carousel item).

    Mirrors process_media_file but operates on PostMedia not Post.
    """
    from apps.posts.models import PostMedia
    from services.telegram_service import download_file
    from django.core.files.base import ContentFile

    logger.info(
        "process_carousel_item_media: starting | item_id=%s",
        carousel_item_id,
    )

    try:
        item = PostMedia.objects.get(id=carousel_item_id)
    except PostMedia.DoesNotExist:
        logger.warning(
            "process_carousel_item_media: item not found | id=%s",
            carousel_item_id,
        )
        return {"status": "skipped", "reason": "not_found"}

    if item.file:
        logger.debug(
            "process_carousel_item_media: already processed | id=%s",
            carousel_item_id,
        )
        return {"status": "skipped", "reason": "already_processed"}

    try:
        file_content, file_name, _ = download_file(telegram_file_id)

        if not file_content:
            raise ValueError(f"Empty file content for file_id={telegram_file_id}")

        item.file.save(file_name, ContentFile(file_content), save=False)
        item.telegram_file_id = ""
        item.save(update_fields=["file", "telegram_file_id"])

        logger.info(
            "process_carousel_item_media: completed | item_id=%s",
            carousel_item_id,
        )
        return {"status": "success", "item_id": carousel_item_id}

    except Exception as exc:
        logger.warning(
            "process_carousel_item_media: failed (attempt %d/%d) | "
            "item_id=%s error=%s",
            self.request.retries + 1,
            self.max_retries + 1,
            carousel_item_id,
            exc,
        )
        raise self.retry(
            exc=exc,
            countdown=self.default_retry_delay * (2 ** self.request.retries),
        )