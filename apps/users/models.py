import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from apps.users.managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model built around Telegram identity.

    We deliberately avoid using email as the primary identifier —
    Telegram users may never share their email with us. The telegram_id
    is the immutable, unique identity anchor for every user.

    phone_number is optional: only populated when the user authenticates
    via the bot's phone-share flow, not the Login Widget.
    """

    # --- Identity ---
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Internal UUID. Never expose sequential IDs in APIs.",
    )
    telegram_id = models.BigIntegerField(
        unique=True,
        db_index=True,
        help_text="Telegram's own user ID. Immutable. Used for all bot interactions.",
    )
    username = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Telegram @username. Optional — not all users have one.",
    )

    # --- Profile ---
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64, blank=True)
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="E.164 format preferred. Populated via bot contact share.",
    )
    profile_photo = models.URLField(
        blank=True,
        help_text="Telegram CDN URL. Refresh periodically — Telegram URLs expire.",
    )
    bio = models.TextField(blank=True)

    # --- Django auth plumbing ---
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)

    # AbstractBaseUser requires these
    USERNAME_FIELD = "telegram_id"
    REQUIRED_FIELDS = ["first_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["telegram_id"], name="idx_user_telegram_id"),
            models.Index(fields=["username"], name="idx_user_username"),
        ]

    def __str__(self):
        return f"@{self.username}" if self.username else f"tg:{self.telegram_id}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        """Best available name for UI display."""
        return self.full_name or self.username or str(self.telegram_id)