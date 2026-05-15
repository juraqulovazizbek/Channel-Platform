import logging

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.models import Channel
from apps.channels.serializers import (
    ChannelDetailSerializer,
    ChannelListSerializer,
    ChannelWriteSerializer,
    ChannelTelegramLinkSerializer,
)
from services.channel_service import (
    create_channel,
    update_channel,
    link_telegram_channel,
    deactivate_channel,
)
from services.analytics_service import get_channel_stats
from apps.analytics.serializers import ChannelStatsOverviewSerializer
from utils.pagination import StandardResultsPagination
from utils.permissions import IsChannelOwner

logger = logging.getLogger(__name__)


class ChannelListCreateView(APIView):
    """
    GET  /api/v1/channels/        — barcha aktiv kanallar ro'yxati
    POST /api/v1/channels/        — yangi kanal yaratish
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        queryset = (
            Channel.objects
            .filter(is_active=True)
            .annotate(post_count=Count("posts"))
            .select_related("owner")
            .order_by("-created_at")
        )

        # Search
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Verified only filter
        if request.query_params.get("verified") == "true":
            queryset = queryset.filter(is_verified=True)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = ChannelListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ChannelWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            channel = create_channel(
                user=request.user,
                validated_data=serializer.validated_data,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ChannelDetailSerializer(channel).data,
            status=status.HTTP_201_CREATED,
        )


class ChannelDetailView(APIView):
    """
    GET    /api/v1/channels/{slug}/  — kanal detallari
    PATCH  /api/v1/channels/{slug}/  — kanalani yangilash (owner)
    DELETE /api/v1/channels/{slug}/  — kanalni o'chirish (owner)
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsChannelOwner()]

    # channels/views.py — to'g'rilash:
    def _get_channel(self, slug):
        if self.request.method == "GET":
            # Ommaviy: faqat faol kanallar
            return get_object_or_404(
                Channel.objects.filter(is_active=True)
                .annotate(post_count=Count("posts"))
                .select_related("owner"),
                slug=slug,
            )
        else:
            # Owner: faol va nofaol kanallarni ham ko'ra oladi
            return get_object_or_404(
                Channel.objects
                .annotate(post_count=Count("posts"))
                .select_related("owner"),
                slug=slug,
                owner=self.request.user,  # owner tekshiruvi bu yerda
            )

    def get(self, request, slug):
        channel = self._get_channel(slug)
        serializer = ChannelDetailSerializer(channel)
        return Response(serializer.data)

    def patch(self, request, slug):
        channel = self._get_channel(slug)
        self.check_object_permissions(request, channel)

        serializer = ChannelWriteSerializer(
            channel,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated = update_channel(
            channel=channel,
            validated_data=serializer.validated_data,
        )
        return Response(
            ChannelDetailSerializer(updated).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, slug):
        channel = self._get_channel(slug)
        self.check_object_permissions(request, channel)
        deactivate_channel(channel)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChannelTelegramLinkView(APIView):
    """
    POST /api/v1/channels/{slug}/link-telegram/
    Telegram kanalini platforma kanaliga ulash.
    """

    permission_classes = [IsAuthenticated, IsChannelOwner]

    def post(self, request, slug):
        channel = get_object_or_404(
            Channel, slug=slug, is_active=True
        )
        self.check_object_permissions(request, channel)

        serializer = ChannelTelegramLinkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = link_telegram_channel(
                channel=channel,
                telegram_username=serializer.validated_data[
                    "telegram_channel_username"
                ],
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ChannelDetailSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class MyChannelsView(APIView):
    """
    GET /api/v1/channels/mine/
    Foydalanuvchining o'z kanallari (faol + nofaol).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            Channel.objects
            .filter(owner=request.user)
            .annotate(post_count=Count("posts"))
            .order_by("-created_at")
        )
        serializer = ChannelListSerializer(queryset, many=True)
        return Response(serializer.data)


class ChannelAnalyticsView(APIView):
    """
    GET /api/v1/channels/{slug}/analytics/
    Kanal statistikasi (faqat owner).
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