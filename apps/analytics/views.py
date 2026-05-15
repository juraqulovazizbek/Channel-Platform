import logging

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.models import Channel
from apps.analytics.serializers import ChannelStatsOverviewSerializer
from apps.posts.serializers import PostListSerializer
from services.analytics_service import get_channel_stats, get_top_posts
from utils.permissions import IsChannelOwner

logger = logging.getLogger(__name__)


class ChannelStatsView(APIView):
    """
    GET /api/v1/analytics/channels/{slug}/
    To'liq kanal statistikasi — faqat owner.
    """

    permission_classes = [IsAuthenticated, IsChannelOwner]

    def get(self, request, slug):
        channel = get_object_or_404(
            Channel, slug=slug, is_active=True
        )
        self.check_object_permissions(request, channel)
        stats = get_channel_stats(channel)
        serializer = ChannelStatsOverviewSerializer(stats)
        return Response(serializer.data)


class TopPostsView(APIView):
    """
    GET /api/v1/analytics/channels/{slug}/top-posts/?limit=10
    Eng ko'p ko'rilgan postlar — ommaviy.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        channel = get_object_or_404(
            Channel, slug=slug, is_active=True
        )

        try:
            limit = min(int(request.query_params.get("limit", 10)), 50)
        except (ValueError, TypeError):
            limit = 10

        posts = get_top_posts(channel, limit=limit)
        serializer = PostListSerializer(posts, many=True)
        return Response(serializer.data)