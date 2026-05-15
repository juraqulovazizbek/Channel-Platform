from django.apps import AppConfig


class BotConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    app_label = "bot"
    name = "apps.bot"
    verbose_name = "Telegram Bot"