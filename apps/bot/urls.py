from django.urls import path
from apps.bot.views import TelegramWebhookView, WebhookHealthView

app_name = "bot"

urlpatterns = [
    path("webhook/", TelegramWebhookView.as_view(), name="telegram-webhook"),
    path("health/", WebhookHealthView.as_view(), name="webhook-health"),
]