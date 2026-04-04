from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from apps.channels.models import Channel


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):

    # ── List view ────────────────────────────────────────────────────────────
    list_display = [
        "name",
        "slug",
        "owner_link",
        "is_active",
        "is_verified",
        "telegram_channel_id",
        "subscriber_count",
        "post_count",
        "created_at",
        "avatar_preview",
    ]
    list_filter = [
        "is_active",
        "is_verified",
        "created_at",
    ]
    search_fields = [
        "name",
        "slug",
        "owner__username",
        "owner__telegram_id",
        "telegram_channel_id",
        "telegram_channel_username",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "slug",
        "created_at",
        "updated_at",
        "post_count",
        "avatar_preview",
        "banner_preview",
    ]
    raw_id_fields = ["owner"]

    # ── Detail layout ────────────────────────────────────────────────────────
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "id",
                    "owner",
                    "name",
                    "slug",
                    "description",
                )
            },
        ),
        (
            "Media",
            {
                "fields": (
                    "avatar",
                    "avatar_preview",
                    "banner",
                    "banner_preview",
                )
            },
        ),
        (
            "Telegram",
            {
                "fields": (
                    "telegram_channel_id",
                    "telegram_channel_username",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                    "is_verified",
                    "subscriber_count",
                    "post_count",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(_post_count=Count("posts"))
        )

    def post_count(self, obj):
        return obj._post_count

    post_count.short_description = "Posts"
    post_count.admin_order_field = "_post_count"

    def owner_link(self, obj):
        return format_html(
            '<a href="/admin/users/user/{}/change/">{}</a>',
            obj.owner.id,
            obj.owner.display_name,
        )

    owner_link.short_description = "Owner"

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" width="60" height="60" '
                'style="border-radius:8px;object-fit:cover;" />',
                obj.avatar.url,
            )
        return "—"

    avatar_preview.short_description = "Avatar"

    def banner_preview(self, obj):
        if obj.banner:
            return format_html(
                '<img src="{}" width="200" height="60" '
                'style="object-fit:cover;border-radius:4px;" />',
                obj.banner.url,
            )
        return "—"

    banner_preview.short_description = "Banner"

    # Admin actions
    actions = ["activate_channels", "deactivate_channels", "verify_channels"]

    @admin.action(description="Activate selected channels")
    def activate_channels(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} channel(s) activated.")

    @admin.action(description="Deactivate selected channels")
    def deactivate_channels(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} channel(s) deactivated.")

    @admin.action(description="Mark selected channels as verified")
    def verify_channels(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} channel(s) verified.")