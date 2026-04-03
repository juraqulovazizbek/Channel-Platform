import logging
from typing import Optional

from django.db import transaction, IntegrityError
from django.utils.text import slugify

from apps.channels.models import Channel
from apps.users.models import User
from services.telegram_service import get_chat_info

logger = logging.getLogger(__name__)


def create_channel(user: User, validated_data: dict) -> Channel:
    """
    Create a new Channel owned by the given user.

    WHY THIS EXISTS:
        Slug generation needs collision handling — that logic must not
        live in a serializer or view. If the slug "my-channel" exists,
        we try "my-channel-2", "my-channel-3", etc.

    WHEN IT'S USED:
        POST /api/channels/ → ChannelView → here.

    RETURNS:
        The newly created Channel instance.

    RAISES:
        ValueError if the user already has a channel with the same name
        (catches the DB unique constraint and surfaces a clean error).
    """
    name = validated_data["name"]
    base_slug = slugify(name)
    slug = _resolve_unique_slug(base_slug)

    try:
        with transaction.atomic():
            channel = Channel.objects.create(
                owner=user,
                name=name,
                slug=slug,
                description=validated_data.get("description", ""),
                avatar=validated_data.get("avatar"),
                banner=validated_data.get("banner"),
            )
    except IntegrityError as e:
        # This should be rare after slug resolution, but guard anyway.
        logger.error(
            "Channel creation IntegrityError for user=%s name=%r: %s",
            user.telegram_id,
            name,
            e,
        )
        raise ValueError(
            "A channel with this name already exists. Please choose a different name."
        )

    logger.info(
        "Channel created: id=%s slug=%s owner=%d",
        channel.id,
        channel.slug,
        user.telegram_id,
    )
    return channel


def update_channel(channel: Channel, validated_data: dict) -> Channel:
    """
    Update mutable fields on an existing channel.

    WHY THIS EXISTS:
        Only updates fields that are present in validated_data.
        Partial updates (PATCH) work correctly — missing keys are ignored.
        Slug is NOT updatable here. Slug changes are a separate operation
        because they break URLs and require explicit user intent.

    WHEN IT'S USED:
        PUT/PATCH /api/channels/{slug}/ → ChannelDetailView → here.
    """
    updatable_fields = ["name", "description", "avatar", "banner"]
    updated = []

    for field in updatable_fields:
        if field in validated_data:
            new_value = validated_data[field]
            if getattr(channel, field) != new_value:
                setattr(channel, field, new_value)
                updated.append(field)

    if updated:
        channel.save(update_fields=updated + ["updated_at"])
        logger.info(
            "Channel updated: slug=%s fields=%s",
            channel.slug,
            updated,
        )
    else:
        logger.debug("Channel update called but no fields changed: slug=%s", channel.slug)

    return channel


@transaction.atomic
def link_telegram_channel(channel: Channel, telegram_username: str) -> Channel:
    """
    Link a Telegram channel to a platform Channel record.

    HOW IT WORKS:
        1. Call Telegram Bot API to resolve the username → numeric chat ID.
        2. Verify the bot is an admin of that Telegram channel.
        3. Store the telegram_channel_id on the Channel record.

    WHY THIS EXISTS:
        The bot uses telegram_channel_id (not username) to route incoming posts.
        Usernames can change. Numeric IDs never change.

    WHEN IT'S USED:
        POST /api/channels/{slug}/link-telegram/ → here.

    RAISES:
        ValueError for any linkage failure (bot not admin, channel not found, etc.)
        This keeps error handling consistent — views catch ValueError and return 400.
    """
    # Resolve username to chat metadata via Telegram API
    chat_info = get_chat_info(telegram_username)

    if not chat_info:
        raise ValueError(
            f"Could not find Telegram channel @{telegram_username}. "
            "Make sure the username is correct and the bot is a member."
        )

    chat_id = chat_info.get("id")
    chat_type = chat_info.get("type")

    if chat_type not in ("channel", "supergroup"):
        raise ValueError(
            "Only Telegram channels and supergroups can be linked."
        )

    # Check the bot has admin rights (required for reading channel posts)
    bot_is_admin = chat_info.get("_bot_is_admin", False)
    if not bot_is_admin:
        raise ValueError(
            f"The bot is not an admin of @{telegram_username}. "
            "Please add the bot as an admin first."
        )

    # Check this Telegram channel isn't already linked to another platform channel
    existing = (
        Channel.objects
        .filter(telegram_channel_id=chat_id)
        .exclude(id=channel.id)
        .first()
    )
    if existing:
        raise ValueError(
            "This Telegram channel is already linked to another platform channel."
        )

    channel.telegram_channel_id = chat_id
    channel.telegram_channel_username = telegram_username
    channel.save(update_fields=["telegram_channel_id", "telegram_channel_username", "updated_at"])

    logger.info(
        "Telegram channel linked: platform_channel=%s tg_id=%d tg_username=@%s",
        channel.slug,
        chat_id,
        telegram_username,
    )
    return channel


def deactivate_channel(channel: Channel) -> None:
    """
    Soft-delete a channel by marking it inactive.

    WHY SOFT DELETE:
        Hard deletes cascade to posts, analytics, etc.
        Soft delete preserves history and allows recovery.
        Active posts remain in DB but won't appear in public queries
        (all list views filter is_active=True).
    """
    if not channel.is_active:
        logger.debug("deactivate_channel called on already-inactive channel: %s", channel.slug)
        return

    channel.is_active = False
    channel.save(update_fields=["is_active", "updated_at"])
    logger.info("Channel deactivated: slug=%s", channel.slug)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_unique_slug(base_slug: str) -> str:
    """
    Generate a unique slug by appending a numeric suffix if needed.

    Example:
        "my-channel"     → taken → "my-channel-2" → taken → "my-channel-3"

    WHY NOT UUID SLUGS:
        "my-channel-507f1f77" is ugly. Numeric suffixes are human-readable
        and predictable. The loop is bounded — in practice it runs once or twice.
    """
    slug = base_slug
    counter = 2

    while Channel.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
        if counter > 999:
            # Safety valve — should never happen in practice
            raise ValueError(f"Cannot generate unique slug for base: {base_slug}")

    return slug