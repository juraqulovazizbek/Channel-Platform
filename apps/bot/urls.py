from django.urls import path
from apps.bot.views import TelegramWebhookView

app_name = "bot"

urlpatterns = [
    # Telegram sends POST requests to this URL.
    # The path segment after /bot/ is intentionally not guessable.
    # Use TELEGRAM_WEBHOOK_SECRET env var as the additional security layer.
    path(
        "webhook/",
        TelegramWebhookView.as_view(),
        name="telegram-webhook",
    ),
]