import hashlib
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from apps.channels.models import Channel
from apps.posts.models import Post, PostType
from apps.posts.serializers import (
    PostDetailSerializer,
    PostListSerializer,
    PostWriteSerializer,
)
from services.post_service import (
    create_manual_post,
    get_published_posts,
)
from services.analytics_service import increment_post_view
from utils.pagination import StandardResultsPagination

logger = logging.getLogger(__name__)


class ChannelPostListView(APIView):
    """
    GET /api/v1/posts/channel/{slug}/
    Kanal postlari ommaviy lenti.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        channel = get_object_or_404(
            Channel, slug=slug, is_active=True
        )

        post_type = request.query_params.get("type")
        if post_type and post_type not in PostType.values:
            return Response(
                {
                    "detail": (
                        f"Invalid type. Choices: "
                        f"{', '.join(PostType.values)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = get_published_posts(channel, post_type=post_type)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PostListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PostListCreateView(APIView):
    """
    GET  /api/v1/posts/           — foydalanuvchi postlari (dashboard)
    POST /api/v1/posts/           — yangi post yaratish (manual)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            Post.objects
            .filter(channel__owner=request.user)
            .select_related("channel")
            .order_by("-created_at")
        )

        # Filter by channel
        channel_slug = request.query_params.get("channel")
        if channel_slug:
            queryset = queryset.filter(channel__slug=channel_slug)

        # Filter by type
        post_type = request.query_params.get("type")
        if post_type and post_type in PostType.values:
            queryset = queryset.filter(type=post_type)

        # Filter by published status
        is_published = request.query_params.get("is_published")
        if is_published is not None:
            queryset = queryset.filter(
                is_published=is_published.lower() == "true"
            )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PostListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = PostWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            post = create_manual_post(
                user=request.user,
                validated_data=serializer.validated_data,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            PostDetailSerializer(post).data,
            status=status.HTTP_201_CREATED,
        )


class PostDetailView(APIView):
    """
    GET    /api/v1/posts/{id}/    — post detallari (ommaviy)
    PATCH  /api/v1/posts/{id}/    — postni yangilash (owner)
    DELETE /api/v1/posts/{id}/    — postni o'chirish (owner)
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def _get_post(self, post_id):
        return get_object_or_404(
            Post.objects
            .select_related("channel", "channel__owner")
            .prefetch_related("carousel_items"),
            id=post_id,
            is_published=True,
        )

    def get(self, request, post_id):
        post = self._get_post(post_id)
        serializer = PostDetailSerializer(post)
        return Response(serializer.data)

    def patch(self, request, post_id):
        post = self._get_post(post_id)

        if post.channel.owner != request.user:
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PostWriteSerializer(
            post,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

       # TO'G'RI — yangilangan instanceni ishlatish:
        updated_post = serializer.save()
        return Response(
            PostDetailSerializer(updated_post).data,
            status=status.HTTP_200_OK,
        )
    
    def delete(self, request, post_id):
        post = self._get_post(post_id)

        if post.channel.owner != request.user:
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostViewTrackView(APIView):
    """
    POST /api/v1/posts/{id}/view/
    Ko'rishni qayd etish — faqat Redis, DB yozuvi yo'q.
    """

    permission_classes = [AllowAny]

    def post(self, request, post_id):
        if not Post.objects.filter(
            id=post_id, is_published=True
        ).exists():
            return Response(status=status.HTTP_404_NOT_FOUND)

        visitor_id = self._build_visitor_id(request)

        try:
            increment_post_view(
                post_id=str(post_id),
                visitor_id=visitor_id,
            )
        except Exception:
            logger.exception(
                "PostViewTrackView: tracking failed silently | post_id=%s",
                post_id,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _build_visitor_id(request) -> str:
        if request.user.is_authenticated:
            raw = str(request.user.id)
        else:
            session_key = request.session.session_key or ""
            ip = request.META.get("REMOTE_ADDR", "")
            ip_partial = (
                ".".join(ip.split(".")[:3]) + ".0"
                if "." in ip
                else ip
            )
            raw = f"{session_key}:{ip_partial}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


class PinnedPostsView(APIView):
    """
    GET /api/v1/posts/channel/{slug}/pinned/
    Kanalning pinlangan postlari.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        channel = get_object_or_404(
            Channel, slug=slug, is_active=True
        )
        posts = (
            Post.objects
            .filter(
                channel=channel,
                is_published=True,
                is_pinned=True,
            )
            .select_related("channel")
            .prefetch_related("carousel_items")
            .order_by("-created_at")
        )
        serializer = PostDetailSerializer(posts, many=True)
        return Response(serializer.data)


class SearchPostsView(APIView):
    """
    GET /api/v1/posts/search/?q=keyword
    Postlar bo'yicha qidiruv.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Response(
                {"detail": "Search query must be at least 2 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = (
            Post.objects
            .filter(
                is_published=True,
                channel__is_active=True,
            )
            .filter(
                Q(text__icontains=query) |
                Q(content__icontains=query)
            )
            .select_related("channel")
            .order_by("-views_count", "-created_at")
        )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PostListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)