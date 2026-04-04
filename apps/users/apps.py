from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    app_label = "users"
    name = "apps.users"
    verbose_name = "Users"

    def ready(self):
        # Signal handlers import — prevents circular imports
        import apps.users.signals  # noqa: F401