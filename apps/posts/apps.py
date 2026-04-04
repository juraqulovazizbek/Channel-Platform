from django.apps import AppConfig


class PostsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    app_label = "posts"
    name = "apps.posts"
    verbose_name = "Posts"