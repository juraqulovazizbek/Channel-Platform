from django.urls import path
from apps.users.views import TelegramAuthView, MeView, TokenRefreshView

app_name = "users"

urlpatterns = [
    path("telegram/", TelegramAuthView.as_view(), name="telegram-auth"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
]