from rest_framework import serializers
from apps.analytics.models import DailyChannelStats


class DailyChannelStatsSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for the analytics dashboard.
    All these fields are pre-aggregated by Celery — never computed here.
    """

    class Meta:
        model = DailyChannelStats
        fields = [
            "date",
            "total_views",
            "unique_visitors",
            "post_count",
        ]
        read_only_fields = fields


class ChannelStatsOverviewSerializer(serializers.Serializer):
    """
    Summary stats returned by the channel analytics endpoint.
    Not a ModelSerializer — this aggregates across multiple sources.
    Computed by analytics_service, serialized here.
    """

    total_views = serializers.IntegerField()
    total_posts = serializers.IntegerField()
    total_unique_visitors = serializers.IntegerField()
    avg_views_per_post = serializers.FloatField()
    top_post_id = serializers.UUIDField(allow_null=True)
    top_post_title = serializers.CharField(allow_blank=True)
    top_post_views = serializers.IntegerField()
    daily_stats = DailyChannelStatsSerializer(many=True)
    