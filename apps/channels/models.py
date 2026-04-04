import uuid
from django.db import models
from django.utils.text import slugify
from apps.users.models import User


class Channel(models.Model):
    """
    A Channel maps a Telegram channel to a website.

    One user can own multiple channels. The slug becomes the
    public-facing URL path: /channels/{slug}/

    telegram_channel_id is the numeric ID Telegram assigns to every channel
    (negative number, e.g. -1001234567890). This is how the bot identifies
    which Channel DB record a post belongs to when it arrives via webhook.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="channels",
    )

    # --- Identity ---
    name = models.CharField(max_length=128)
    slug = models.SlugField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Auto-generated from name. Used in public URLs.",
    )
    description = models.TextField(blank=True)

    # --- Media ---
    avatar = models.ImageField(
        upload_to="channels/avatars/%Y/%m/",
        blank=True,
        null=True,
    )
    banner = models.ImageField(
        upload_to="channels/banners/%Y/%m/",
        blank=True,
        null=True,
    )

    # --- Telegram linkage ---
    telegram_channel_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Telegram's numeric channel ID (e.g. -1001234567890). "
            "Set when bot is added as admin. Used to route incoming posts."
        ),
    )
    telegram_channel_username = models.CharField(
        max_length=64,
        blank=True,
        help_text="Public @username of the channel, if it has one.",
    )

    # --- State ---
    is_active = models.BooleanField(default=True, db_index=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="Manually verified channels get a badge.",
    )
    subscriber_count = models.PositiveIntegerField(
        default=0,
        help_text="Cached from Telegram. Refreshed by periodic Celery task.",
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channels"
        verbose_name = "Channel"
        verbose_name_plural = "Channels"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"], name="idx_channel_slug"),
            models.Index(fields=["owner", "is_active"], name="idx_channel_owner_active"),
            models.Index(
                fields=["telegram_channel_id"],
                name="idx_channel_tg_id",
            ),
        ]
    # models.py — to'g'rilangan:
    constraints = [
        models.UniqueConstraint(
            fields=["owner", "telegram_channel_id"],
            condition=models.Q(telegram_channel_id__isnull=False),  # ← NULL larni o'tkazib yuborish
            name="uq_owner_telegram_channel",
        )
    ]
    def __str__(self):
        return f"{self.name} ({self.slug})"

    def save(self, *args, **kwargs):
        # Auto-generate slug only on creation, not on every update.
        # Changing slugs breaks existing URLs — services handle intentional renames.
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)