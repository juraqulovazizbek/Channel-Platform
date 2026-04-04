from django.contrib import admin
from apps.analytics.models import PostView, DailyChannelStats


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):

    list_display = [
        "id",
        "post_title",
        "visitor_id_short",
        "viewed_at",
    ]
    list_filter = ["viewed_at"]
    search_fields = [
        "post__title",
        "post__channel__name",
        "visitor_id",
    ]
    readonly_fields = [
        "id",
        "post",
        "visitor_id",
        "viewed_at",
    ]
    ordering = ["-viewed_at"]
    date_hierarchy = "viewed_at"

    # PostView records are never edited manually
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def post_title(self, obj):
        return str(obj.post)[:60]

    post_title.short_description = "Post"

    def visitor_id_short(self, obj):
        return obj.visitor_id[:16] + "..."

    visitor_id_short.short_description = "Visitor ID"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("post", "post__channel")
        )


@admin.register(DailyChannelStats)
class DailyChannelStatsAdmin(admin.ModelAdmin):

    list_display = [
        "channel_name",
        "date",
        "total_views",
        "unique_visitors",
        "post_count",
    ]
    list_filter = ["date", "channel__is_active"]
    search_fields = ["channel__name", "channel__slug"]
    readonly_fields = [
        "id",
        "channel",
        "date",
        "total_views",
        "unique_visitors",
        "post_count",
    ]
    ordering = ["-date"]
    date_hierarchy = "date"
    raw_id_fields = []

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def channel_name(self, obj):
        return obj.channel.name

    channel_name.short_description = "Channel"
    channel_name.admin_order_field = "channel__name"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("channel")
        )