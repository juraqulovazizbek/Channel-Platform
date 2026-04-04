from django.urls import path
from apps.users.views import (
    TelegramAuthView,
    TokenRefreshView,
    TokenBlacklistView,
    MeView,
    UserPublicProfileView,
)

app_name = "users"

urlpatterns = [
    # Auth
    path(
        "telegram/",
        TelegramAuthView.as_view(),
        name="telegram-auth",
    ),
    path(
        "token/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),
    path(
        "logout/",
        TokenBlacklistView.as_view(),
        name="logout",
    ),

    # Profile
    path(
        "me/",
        MeView.as_view(),
        name="me",
    ),
    path(
        "users/<int:telegram_id>/",
        UserPublicProfileView.as_view(),
        name="user-public-profile",
    ),
]