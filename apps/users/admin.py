from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from apps.users.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for Telegram-based User model.
    Replaces email/password fields with telegram_id based layout.
    """

    # ── List view ────────────────────────────────────────────────────────────
    list_display = [
        "telegram_id",
        "username",
        "full_name",
        "phone_number",
        "is_active",
        "is_staff",
        "date_joined",
        "profile_photo_preview",
    ]
    list_filter = [
        "is_active",
        "is_staff",
        "is_superuser",
        "date_joined",
    ]
    search_fields = [
        "telegram_id",
        "username",
        "first_name",
        "last_name",
        "phone_number",
    ]
    ordering = ["-date_joined"]
    readonly_fields = [
        "id",
        "telegram_id",
        "date_joined",
        "last_login",
        "profile_photo_preview",
    ]

    # ── Detail view layout ───────────────────────────────────────────────────
    fieldsets = (
        (
            "Telegram Identity",
            {
                "fields": (
                    "id",
                    "telegram_id",
                    "username",
                )
            },
        ),
        (
            "Profile",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                    "bio",
                    "profile_photo",
                    "profile_photo_preview",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Important Dates",
            {
                "fields": (
                    "date_joined",
                    "last_login",
                )
            },
        ),
    )

    # add_fieldsets: used when creating a user via admin
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "telegram_id",
                    "first_name",
                    "last_name",
                    "username",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    # Override parent — we don't use password-based auth
    filter_horizontal = ("groups", "user_permissions")

    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            return format_html(
                '<img src="{}" width="48" height="48" '
                'style="border-radius:50%;object-fit:cover;" />',
                obj.profile_photo,
            )
        return "—"

    profile_photo_preview.short_description = "Photo"