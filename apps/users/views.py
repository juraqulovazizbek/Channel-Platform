import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.users.models import User
from apps.users.serializers import (
    TelegramAuthSerializer,
    UserPrivateSerializer,
    UserPublicSerializer,
    UserUpdateSerializer,
)
from services.auth_service import (
    verify_telegram_auth,
    create_or_update_user,
    generate_jwt_tokens,
)
from utils.pagination import StandardResultsPagination

logger = logging.getLogger(__name__)


class TelegramAuthView(APIView):
    """
    POST /api/v1/auth/telegram/
    Telegram Login Widget va bot auth uchun asosiy endpoint.
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = TelegramAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        if not verify_telegram_auth(data):
            logger.warning(
                "TelegramAuthView: hash mismatch | ip=%s",
                request.META.get("REMOTE_ADDR"),
            )
            return Response(
                {"detail": "Invalid Telegram auth data."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = create_or_update_user(data)
        tokens = generate_jwt_tokens(user)

        logger.info(
            "TelegramAuthView: login success | telegram_id=%d",
            user.telegram_id,
        )
        return Response(tokens, status=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/refresh/
    Access token yangilash.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh", "").strip()
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            return Response(
                {"access": str(token.access_token)},
                status=status.HTTP_200_OK,
            )
        except TokenError as e:
            logger.info("TokenRefreshView: invalid token | error=%s", e)
            return Response(
                {"detail": "Token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class TokenBlacklistView(APIView):
    """
    POST /api/v1/auth/logout/
    Refresh tokenni blacklistga qo'shish (logout).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh", "").strip()
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info(
                "TokenBlacklistView: logout | user_id=%s",
                request.user.id,
            )
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_200_OK,
            )
        except TokenError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class MeView(APIView):
    """
    GET   /api/v1/auth/me/  — o'z profilini ko'rish
    PATCH /api/v1/auth/me/  — o'z profilini yangilash
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserPrivateSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response(
            UserPrivateSerializer(request.user).data,
            status=status.HTTP_200_OK,
        )


class UserPublicProfileView(APIView):
    """
    GET /api/v1/auth/users/{telegram_id}/
    Foydalanuvchining ommaviy profili.
    """

    permission_classes = [AllowAny]

    def get(self, request, telegram_id):
        try:
            user = User.objects.get(
                telegram_id=telegram_id,
                is_active=True,
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserPublicSerializer(user)
        return Response(serializer.data)