import logging
from typing import Optional

from django.db import transaction, IntegrityError
from django.utils import timezone

from apps.channels.models import Channel
from apps.posts.models import Post, PostMedia, PostType, PostSource
from apps.users.models import User
from tasks.media_tasks import process_media_file

logger = logging.getLogger(__name__)


def create_post_from_bot(data: dict) -> Optional[Post]:
    """
    Create a Post from an incoming Telegram webhook event.

    WHY THIS EXISTS:
        Bot-originated posts have different fields and rules than manual posts.
        They include telegram_message_id (for deduplication), telegram_file_id
        (for lazy media download), and always have source=BOT or source=CHANNEL.

    IDEMPOTENCY:
        The (channel, telegram_message_id) unique constraint in the DB is the
        final guard. But we do a pre-check here to avoid hitting the constraint
        on every webhook retry — IntegrityError is caught as a fallback.

    WHEN IT'S USED:
        bot/handlers/channel_handler.py → telegram_service.parse_webhook_update
        → here. Called for every channel_post event.

    RETURNS:
        The created Post, or None if this message was already processed
        (idempotent — not an error condition).
    """
    channel_id = data.get("channel_id")
    telegram_message_id = data.get("telegram_message_id")

    # --- Resolve channel ---
    channel = _get_channel_by_telegram_id(channel_id)
    if not channel:
        logger.warning(
            "Ignoring post from unknown Telegram channel: tg_channel_id=%s",
            channel_id,
        )
        return None

    # --- Deduplication pre-check ---
    # Cheaper than catching IntegrityError — avoids a failed transaction rollback
    if telegram_message_id and Post.objects.filter(
        channel=channel,
        telegram_message_id=telegram_message_id,
    ).exists():
        logger.debug(
            "Duplicate webhook event ignored: channel=%s message_id=%s",
            channel.slug,
            telegram_message_id,
        )
        return None

    post_type = data.get("type", PostType.TEXT)
    source = data.get("source", PostSource.CHANNEL)

    try:
        with transaction.atomic():
            post = Post.objects.create(
                channel=channel,
                type=post_type,
                title=data.get("title", ""),
                content=data.get("content", ""),
                telegram_message_id=telegram_message_id,
                telegram_file_id=data.get("file_id", ""),
                source=source,
                is_published=True,
                published_at=data.get("date") or timezone.now(),
            )

            # For carousel posts, create PostMedia records
            if post_type == PostType.CAROUSEL:
                media_items = data.get("media_group", [])
                _create_carousel_items(post, media_items)

    except IntegrityError:
        # Race condition: two webhook deliveries arrived simultaneously.
        # The constraint caught it — this is not an error.
        logger.info(
            "Duplicate post caught by DB constraint: channel=%s message_id=%s",
            channel.slug,
            telegram_message_id,
        )
        return None

    logger.info(
        "Post created from bot: id=%s type=%s channel=%s",
        post.id,
        post.type,
        channel.slug,
    )

    # Dispatch async media processing if this post has a Telegram file
    if post.telegram_file_id:
        process_media_file.delay(str(post.id), post.telegram_file_id)

    return post


def create_manual_post(user: User, validated_data: dict) -> Post:
    """
    Create a Post via the web dashboard (not from Telegram).

    WHY THIS EXISTS:
        Manual posts don't have telegram_message_id or file_id.
        They may have directly uploaded media files.
        Source is always MANUAL.

    AUTHORIZATION NOTE:
        Channel ownership is validated in PostWriteSerializer.validate_channel.
        We do NOT re-check here — that would duplicate logic. But we DO
        assert channel.is_active to prevent posting to archived channels.

    WHEN IT'S USED:
        POST /api/posts/ → PostListCreateView → here.
    """
    channel = validated_data["channel"]

    if not channel.is_active:
        raise ValueError("Cannot create posts in an inactive channel.")

    with transaction.atomic():
        post = Post.objects.create(
            channel=channel,
            type=validated_data["type"],
            title=validated_data.get("title", ""),
            content=validated_data.get("content", ""),
            media_file=validated_data.get("media_file"),
            source=PostSource.MANUAL,
            is_published=validated_data.get("is_published", True),
            is_pinned=validated_data.get("is_pinned", False),
            published_at=validated_data.get("published_at") or (
                timezone.now() if validated_data.get("is_published", True) else None
            ),
        )

    logger.info(
        "Manual post created: id=%s type=%s channel=%s user=%d",
        post.id,
        post.type,
        channel.slug,
        user.telegram_id,
    )

    # Trigger thumbnail generation for video/reel uploads
    if post.type in (PostType.VIDEO, PostType.REEL) and post.media_file:
        process_media_file.delay(str(post.id), None)

    return post


def handle_media_download_and_attach(post: Post, telegram_file_id: str) -> bool:
    """
    Download a file from Telegram's servers and attach it to a Post.

    WHY THIS EXISTS:
        Telegram file_ids don't give you a direct URL immediately.
        You must call getFile → get a temporary path → download the bytes.
        This is always done asynchronously (called from Celery task) because:
        - Telegram download can take 1–10 seconds
        - We never block the webhook response thread

    FLOW:
        1. Call Telegram API: getFile(file_id) → file_path
        2. Download from https://api.telegram.org/file/bot{token}/{file_path}
        3. Save to Django FileField (which routes to S3 in production)
        4. Clear telegram_file_id (signal that media is fully processed)

    WHEN IT'S USED:
        tasks/media_tasks.py → process_media_file → here.

    RETURNS:
        True if successful, False if the download failed (task will retry).
    """
    from services.telegram_service import download_file

    if not telegram_file_id:
        logger.warning("handle_media_download_and_attach called with empty file_id: post=%s", post.id)
        return False

    file_content, file_name, mime_type = download_file(telegram_file_id)

    if not file_content:
        logger.error(
            "Failed to download media from Telegram: post=%s file_id=%s",
            post.id,
            telegram_file_id,
        )
        return False

    from django.core.files.base import ContentFile

    # Determine which field to populate based on post type
    if post.type in (PostType.IMAGE, PostType.VIDEO, PostType.REEL):
        post.media_file.save(file_name, ContentFile(file_content), save=False)

    # Clear the telegram_file_id to mark download as complete.
    # This prevents the Celery task from retrying a successful operation.
    post.telegram_file_id = ""
    post.save(update_fields=["media_file", "telegram_file_id", "updated_at"])

    logger.info(
        "Media attached to post: id=%s file=%s",
        post.id,
        file_name,
    )
    return True


def get_published_posts(channel: Channel, post_type: Optional[str] = None):
    """
    Return an optimized queryset of published posts for a channel.

    WHY THIS IS A SERVICE FUNCTION (not just a queryset on the model):
        Views should never construct querysets with business logic baked in.
        "Published posts" is a business concept — the rule may evolve
        (e.g. scheduled posts, member-only posts). One place to change it.

    WHEN IT'S USED:
        Channel website public feed, post list API.
    """
    qs = (
        Post.objects
        .filter(channel=channel, is_published=True)
        .select_related("channel")
        .order_by("-is_pinned", "-created_at")
    )

    if post_type:
        qs = qs.filter(type=post_type)

    return qs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_channel_by_telegram_id(telegram_channel_id: int) -> Optional[Channel]:
    """
    Look up a Channel by its Telegram channel ID.
    Cached by the ORM query cache for the duration of the request.
    """
    try:
        return Channel.objects.get(
            telegram_channel_id=telegram_channel_id,
            is_active=True,
        )
    except Channel.DoesNotExist:
        return None


def _create_carousel_items(post: Post, media_items: list) -> None:
    """
    Bulk-create PostMedia records for a carousel post.
    Uses bulk_create for efficiency — one INSERT for all items.
    """
    if not media_items:
        return

    items = [
        PostMedia(
            post=post,
            order=index,
            telegram_file_id=item.get("file_id", ""),
        )
        for index, item in enumerate(media_items)
    ]

    PostMedia.objects.bulk_create(items)
    logger.debug("Created %d carousel items for post=%s", len(items), post.id)