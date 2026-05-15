from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    app_label = "analytics"
    name = "apps.analytics"
    verbose_name = "Analytics"