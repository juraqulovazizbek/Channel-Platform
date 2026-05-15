import hashlib
import logging

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.channels.models import Channel
from apps.posts.models import Post, PostType
from apps.posts.serializers import (
    PostDetailSerializer,
    PostListSerializer,
    PostWriteSerializer,
)
from services.analytics_service import increment_post_view
from services.post_service import create_manual_post, get_published_posts
from utils.pagination import StandardResultsPagination

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC FEED
# ─────────────────────────────────────────────────────────────────────────────


class ChannelPostListView(APIView):
    """
    GET /api/v1/posts/channel/{slug}/

    Kanal postlarining ommaviy lenti.
    Ixtiyoriy ?type= filtri qo'llab-quvvatlanadi (text, image, video, reel, carousel).
    Autentifikatsiya talab qilinmaydi — bu public endpoint.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        channel = get_object_or_404(Channel, slug=slug, is_active=True)

        # ?type= filtrini tekshirish — noto'g'ri qiymat 400 qaytaradi
        post_type = request.query_params.get("type")
        if post_type and post_type not in PostType.values:
            return Response(
                {
                    "detail": (
                        f"Invalid type. "
                        f"Valid choices: {', '.join(PostType.values)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = get_published_posts(channel, post_type=post_type)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PostListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PinnedPostsView(APIView):
    """
    GET /api/v1/posts/channel/{slug}/pinned/

    Kanalning barcha pinlangan postlari.
    Dashboard "featured" bo'limi uchun ishlatiladi.
    Pagination yo'q — pinlangan postlar doim kam bo'ladi.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        channel = get_object_or_404(Channel, slug=slug, is_active=True)

        posts = (
            Post.objects.filter(
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

    Title va content bo'yicha ommaviy qidiruv.
    Minimum 2 ta belgi talab qilinadi.
    Natijalar views_count bo'yicha tartiblangan.
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
            Post.objects.filter(
                is_published=True,
                channel__is_active=True,
            )
            .filter(
                # Post modelida "text" field yo'q — "title" va "content" bor
                Q(title__icontains=query) | Q(content__icontains=query)
            )
            .select_related("channel")
            .order_by("-views_count", "-created_at")
        )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(queryset, request)
        serializer = PostListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
# POST DETAIL
# ─────────────────────────────────────────────────────────────────────────────


class PostDetailView(APIView):
    """
    GET    /api/v1/posts/{id}/   — post detallari (ommaviy, faqat published)
    PATCH  /api/v1/posts/{id}/   — postni yangilash (faqat channel owner)
    DELETE /api/v1/posts/{id}/   — postni o'chirish (faqat channel owner)

    GET uchun autentifikatsiya talab qilinmaydi.
    PATCH/DELETE uchun IsAuthenticated va channel ownership tekshiriladi.

    Muhim farq:
        _get_post_public()   → faqat is_published=True postlar (GET uchun)
        _get_post_for_owner() → draft postlar ham (PATCH/DELETE uchun)
    """

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    # ── Queryset helpers ──────────────────────────────────────────────────────

    def _get_post_public(self, post_id):
        """
        Ommaviy ko'rish uchun — faqat publish qilingan postlar.
        Anonymous foydalanuvchilar ham ko'ra oladi.
        """
        return get_object_or_404(
            Post.objects.select_related(
                "channel", "channel__owner"
            ).prefetch_related("carousel_items"),
            id=post_id,
            is_published=True,
        )

    def _get_post_for_owner(self, post_id, user):
        """
        Owner uchun — draft postlar ham ko'rinadi.
        channel__owner=user: ownership va mavjudlik bir so'rovda tekshiriladi.
        Noto'g'ri owner 404 oladi (403 emas — security best practice).
        """
        return get_object_or_404(
            Post.objects.select_related(
                "channel", "channel__owner"
            ).prefetch_related("carousel_items"),
            id=post_id,
            channel__owner=user,
        )

    # ── HTTP methods ──────────────────────────────────────────────────────────

    def get(self, request, post_id):
        post = self._get_post_public(post_id)
        serializer = PostDetailSerializer(post)
        return Response(serializer.data)

    def patch(self, request, post_id):
        # _get_post_for_owner owner tekshiruvini o'z ichiga oladi
        post = self._get_post_for_owner(post_id, request.user)

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

        # save() yangilangan instanceni qaytaradi
        # post o'zgaruvchisini EMAS, updated_post ni serializ qilamiz
        updated_post = serializer.save()
        return Response(
            PostDetailSerializer(updated_post).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, post_id):
        post = self._get_post_for_owner(post_id, request.user)
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD (AUTHENTICATED)
# ─────────────────────────────────────────────────────────────────────────────


class PostListCreateView(APIView):
    """
    GET  /api/v1/posts/   — owner ning barcha kanallardagi postlari (dashboard)
    POST /api/v1/posts/   — yangi manual post yaratish

    Faqat autentifikatsiya qilingan foydalanuvchilar uchun.
    GET: request.user ga tegishli kanallardagi postlar qaytariladi.

    Filtrlar:
        ?channel={slug}        — muayyan kanal bo'yicha
        ?type={post_type}      — post turi bo'yicha
        ?is_published=true     — nashr holati bo'yicha
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            Post.objects.filter(channel__owner=request.user)
            .select_related("channel")
            .order_by("-created_at")
        )

        # Kanal bo'yicha filtrlash
        channel_slug = request.query_params.get("channel")
        if channel_slug:
            queryset = queryset.filter(channel__slug=channel_slug)

        # Post turi bo'yicha filtrlash
        post_type = request.query_params.get("type")
        if post_type and post_type in PostType.values:
            queryset = queryset.filter(type=post_type)

        # Nashr holati bo'yicha filtrlash
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
        # context={"request": request} — PostWriteSerializer.validate_channel
        # uchun zarur: u request.user ni channel.owner bilan solishtiradi
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
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            PostDetailSerializer(post).data,
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────


class PostViewTrackView(APIView):
    """
    POST /api/v1/posts/{id}/view/

    Post ko'rishini qayd etish.

    MUHIM:
        - Bu endpoint faqat Redis ga yozadi, DB ga emas
        - Deduplication: bir visitor bir soat ichida bir marta hisoblanadi
        - Analytics xatosi hech qachon foydalanuvchiga qaytarilmaydi
        - Javob har doim 204 — client retry qilmasligi uchun

    visitor_id:
        - Autentifikatsiya qilingan: user UUID ning SHA256 hash i
        - Anonymous: session_key + IP subnet ning SHA256 hash i
        Raw IP hech qachon saqlanmaydi — GDPR/privacy talabi
    """

    permission_classes = [AllowAny]

    def post(self, request, post_id):
        # Post mavjudligini tekshirish — to'liq object yuklamasdan
        if not Post.objects.filter(id=post_id, is_published=True).exists():
            return Response(status=status.HTTP_404_NOT_FOUND)

        visitor_id = self._build_visitor_id(request)

        try:
            increment_post_view(
                post_id=str(post_id),
                visitor_id=visitor_id,
            )
        except Exception:
            # Analytics xatosi foydalanuvchiga ko'rsatilmaydi
            logger.exception(
                "PostViewTrackView: tracking error (silent) | post_id=%s",
                post_id,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _build_visitor_id(request) -> str:
        """
        Privacy-safe va barqaror visitor identifikatori yaratish.

        Autentifikatsiya qilingan foydalanuvchi: user.id (UUID) → hash
        Anonymous foydalanuvchi: session_key + IP /24 subnet → hash

        IP ni to'liq saqlamaslik uchun faqat birinchi 3 octet ishlatiladi:
        192.168.1.42 → 192.168.1.0 (oxirgi octet 0 ga almashtiriladi)
        """
        if request.user.is_authenticated:
            raw = str(request.user.id)
        else:
            session_key = request.session.session_key or ""
            ip = request.META.get("REMOTE_ADDR", "")
            # Faqat /24 subnet — individual IP ni bermaydi
            ip_subnet = (
                ".".join(ip.split(".")[:3]) + ".0" if "." in ip else ip
            )
            raw = f"{session_key}:{ip_subnet}"

        # 32 ta hex belgi (128 bit) — dedup uchun yetarli
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]