from .base import *  # noqa: F401, F403
from .base import env, LOGGING

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = True

ALLOWED_HOSTS = ["*"]

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-key-change-this-in-production-immediately",
)

# ---------------------------------------------------------------------------
# Database
# Local development uses the DATABASE_URL env var if set,
# falls back to a local PostgreSQL instance.
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/telegram_platform_dev",
    )
}

# ---------------------------------------------------------------------------
# Cache
# Use LocMemCache in development — no Redis required to get started.
# Switch to Redis by setting REDIS_URL in your .env.
# ---------------------------------------------------------------------------

_use_redis = env.bool("USE_REDIS_IN_DEV", default=False)

if _use_redis:
    pass  # Redis config inherited from base.py
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-dev-cache",
        }
    }

# ---------------------------------------------------------------------------
# Email
# Prints to console — never accidentally sends real emails in dev.
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------

MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405
STATICFILES_DIRS = []

# ---------------------------------------------------------------------------
# CORS
# Allow all origins in dev — no frontend port restrictions.
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# DRF
# Enable Browsable API in development for easy manual testing.
# ---------------------------------------------------------------------------

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Relax throttling in dev — hitting rate limits while testing is annoying.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "10000/hour",
    "user": "10000/hour",
}

# ---------------------------------------------------------------------------
# Django Extensions (optional — install separately if desired)
# ---------------------------------------------------------------------------

try:
    import django_extensions  # noqa: F401

    INSTALLED_APPS += ["django_extensions"]  # noqa: F405
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# Verbose output in dev — see exactly what's happening.
# ---------------------------------------------------------------------------

LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["services"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["tasks"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["django"]["level"] = "INFO"  # noqa: F405

# ---------------------------------------------------------------------------
# Debug Toolbar (optional — install separately if desired)
# ---------------------------------------------------------------------------

try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(  # noqa: F405
        MIDDLEWARE.index(  # noqa: F405
            "django.middleware.common.CommonMiddleware"
        ),
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    )
    INTERNAL_IPS = ["127.0.0.1", "localhost"]
except ImportError:
    pass