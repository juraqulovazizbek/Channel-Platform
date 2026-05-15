from django.contrib import admin
from django.utils.html import format_html
from apps.posts.models import Post, PostMedia


class PostMediaInline(admin.TabularInline):
    """
    Inline carousel items shown inside Post detail page.
    Only visible and relevant for CAROUSEL type posts.
    """

    model = PostMedia
    extra = 0
    fields = ["order", "file", "thumbnail", "telegram_file_id"]
    readonly_fields = ["telegram_file_id"]
    ordering = ["order"]


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):

    # ── List view ────────────────────────────────────────────────────────────
    list_display = [
        "short_title",
        "type",
        "source",
        "channel_link",
        "is_published",
        "is_pinned",
        "views_count",
        "media_status",
        "created_at",
    ]
    list_filter = [
        "type",
        "source",
        "is_published",
        "is_pinned",
        "created_at",
        "channel__is_active",
    ]
    search_fields = [
        "title",
        "content",
        "channel__name",
        "channel__slug",
        "telegram_message_id",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "views_count",
        "telegram_message_id",
        "telegram_file_id",
        "created_at",
        "updated_at",
        "thumbnail_preview",
    ]
    raw_id_fields = ["channel"]
    inlines = [PostMediaInline]
    date_hierarchy = "created_at"

    # ── Detail layout ────────────────────────────────────────────────────────
    fieldsets = (
        (
            "Content",
            {
                "fields": (
                    "id",
                    "channel",
                    "type",
                    "title",
                    "content",
                )
            },
        ),
        (
            "Media",
            {
                "fields": (
                    "media_file",
                    "thumbnail",
                    "thumbnail_preview",
                )
            },
        ),
        (
            "Telegram Metadata",
            {
                "fields": (
                    "telegram_message_id",
                    "telegram_file_id",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "source",
                    "is_published",
                    "is_pinned",
                    "views_count",
                    "published_at",
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
            .select_related("channel", "channel__owner")
        )

    def short_title(self, obj):
        title = obj.title or obj.content[:60] or f"[{obj.type}]"
        return title[:60] + "..." if len(title) > 60 else title

    short_title.short_description = "Title"

    def channel_link(self, obj):
        return format_html(
            '<a href="/admin/channels/channel/{}/change/">{}</a>',
            obj.channel.id,
            obj.channel.name,
        )

    channel_link.short_description = "Channel"

    def media_status(self, obj):
        if obj.telegram_file_id:
            return format_html(
                '<span style="color:orange;">⏳ Pending download</span>'
            )
        if obj.media_file:
            return format_html(
                '<span style="color:green;">✓ Uploaded</span>'
            )
        return "—"

    media_status.short_description = "Media"

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" width="160" height="90" '
                'style="object-fit:cover;border-radius:4px;" />',
                obj.thumbnail.url,
            )
        return "—"

    thumbnail_preview.short_description = "Thumbnail Preview"

    # Admin actions
    actions = [
        "publish_posts",
        "unpublish_posts",
        "pin_posts",
        "unpin_posts",
        "reprocess_media",
    ]

    @admin.action(description="Publish selected posts")
    def publish_posts(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(is_published=False).update(
            is_published=True,
            published_at=timezone.now(),
        )
        self.message_user(request, f"{updated} post(s) published.")

    @admin.action(description="Unpublish selected posts")
    def unpublish_posts(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} post(s) unpublished.")

    @admin.action(description="Pin selected posts")
    def pin_posts(self, request, queryset):
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f"{updated} post(s) pinned.")

    @admin.action(description="Unpin selected posts")
    def unpin_posts(self, request, queryset):
        updated = queryset.update(is_pinned=False)
        self.message_user(request, f"{updated} post(s) unpinned.")

    @admin.action(description="Re-trigger media processing for selected posts")
    def reprocess_media(self, request, queryset):
        from tasks.media_tasks import process_media_file
        count = 0
        for post in queryset.exclude(telegram_file_id=""):
            process_media_file.delay(str(post.id), post.telegram_file_id)
            count += 1
        self.message_user(
            request,
            f"Media reprocessing triggered for {count} post(s).",
        )


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):

    list_display = [
        "id",
        "post_link",
        "order",
        "media_status",
    ]
    readonly_fields = ["id", "telegram_file_id"]
    raw_id_fields = ["post"]
    ordering = ["post", "order"]

    def post_link(self, obj):
        return format_html(
            '<a href="/admin/posts/post/{}/change/">{}</a>',
            obj.post.id,
            str(obj.post)[:40],
        )

    post_link.short_description = "Post"

    def media_status(self, obj):
        if obj.telegram_file_id:
            return format_html(
                '<span style="color:orange;">⏳ Pending</span>'
            )
        if obj.file:
            return format_html(
                '<span style="color:green;">✓ Ready</span>'
            )
        return "—"

    media_status.short_description = "Status"