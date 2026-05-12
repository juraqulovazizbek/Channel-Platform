from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from apps.users.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):

    list_display = (
        "telegram_id",
        "username",
        "first_name",
        "is_staff",
        "is_active",
        "date_joined",
    )

    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
    )

    search_fields = (
        "telegram_id",
        "username",
        "first_name",
        "last_name",
    )

    ordering = ("-date_joined",)

    readonly_fields = (
        "id",
        "date_joined",
        "last_login",
        "profile_photo_preview",
    )

    fieldsets = (
        (
            "Telegram Info",
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
            "Password",
            {
                "fields": (
                    "password",
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
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    filter_horizontal = (
        "groups",
        "user_permissions",
    )

    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius:50%; object-fit:cover;" />',
                obj.profile_photo.url,
            )
        return "No Photo"

    profile_photo_preview.short_description = "Profile Photo"