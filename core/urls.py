from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

# ---------------------------------------------------------------------------
# API v1 routes
# ---------------------------------------------------------------------------

api_v1_patterns = [
    # Auth
    path("auth/", include("apps.users.urls")),

    # Domain resources
    path("channels/", include("apps.channels.urls")),
    path("posts/", include("apps.posts.urls")),
    path("analytics/", include("apps.analytics.urls")),

    # API schema endpoints
    path(
        "schema/",
        SpectacularAPIView.as_view(),
        name="api-schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs-swagger",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="api-schema"),
        name="api-docs-redoc",
    ),
]

# ---------------------------------------------------------------------------
# Root URL configuration
# ---------------------------------------------------------------------------

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # All API routes under /api/v1/
    path("api/v1/", include((api_v1_patterns, "api"), namespace="api")),

    # Telegram bot webhook — lives outside /api/ intentionally:
    # - Not a REST resource (no versioning, no auth headers, no DRF)
    # - Telegram pings this URL directly — we control the path
    # - The secret token in the header is the only security layer
    path("bot/", include("apps.bot.urls")),
]

# ---------------------------------------------------------------------------
# Development-only additions
# ---------------------------------------------------------------------------

if settings.DEBUG:
    # Serve media files via Django in development
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT,
    )

    # Debug toolbar
    try:
        import debug_toolbar
        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass