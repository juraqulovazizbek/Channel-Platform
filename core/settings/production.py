import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from .base import *  # noqa: F401, F403
from .base import env, LOGGING, INSTALLED_APPS, MIDDLEWARE

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# Verify the secret key is explicitly set — never use a default in production.
SECRET_KEY = env("DJANGO_SECRET_KEY")

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = 31536000             # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 1209600              # 2 weeks

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "strict-origin-when-cross-origin"

# ---------------------------------------------------------------------------
# Database — production PostgreSQL with connection pooling
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db("DATABASE_URL")
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["OPTIONS"] = {
    "connect_timeout": 10,
    "sslmode": env("DB_SSLMODE", default="require"),
}

# ---------------------------------------------------------------------------
# Cache — Redis (full config, inherits from base but explicit here)
# ---------------------------------------------------------------------------

REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "RETRY_ON_TIMEOUT": True,
            "MAX_CONNECTIONS": 100,
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,      # Degrade gracefully on Redis failure
        },
        "KEY_PREFIX": "tgplatform_prod",
        "TIMEOUT": 300,
    }
}

# ---------------------------------------------------------------------------
# Static & Media — AWS S3
# ---------------------------------------------------------------------------

AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
AWS_S3_CUSTOM_DOMAIN = env(
    "AWS_S3_CUSTOM_DOMAIN",
    default=f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com",
)
AWS_DEFAULT_ACL = "private"
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 3600
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}

# Separate paths for static and media
AWS_STATIC_LOCATION = "static"
AWS_MEDIA_LOCATION = "media"

STATICFILES_STORAGE = "utils.storage.StaticStorage"
DEFAULT_FILE_STORAGE = "utils.storage.MediaStorage"

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_STATIC_LOCATION}/"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/"

# ---------------------------------------------------------------------------
# Email — production SMTP
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="smtp.sendgrid.net")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="apikey")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="no-reply@telegramplatform.com",
)

# ---------------------------------------------------------------------------
# CORS — explicit origin whitelist in production
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")

# ---------------------------------------------------------------------------
# Logging — structured JSON for log aggregation (Datadog, CloudWatch)
# ---------------------------------------------------------------------------

LOGGING["formatters"]["json"] = {  # noqa: F405
    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
    "format": (
        "%(asctime)s %(levelname)s %(name)s %(process)d "
        "%(funcName)s %(lineno)d %(message)s"
    ),
}

LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405
LOGGING["handlers"]["mail_admins"] = {  # noqa: F405
    "level": "ERROR",
    "class": "django.utils.log.AdminEmailHandler",
    "filters": ["require_debug_false"],
}
LOGGING["loggers"]["django.request"]["handlers"].append(  # noqa: F405
    "mail_admins"
)

# ---------------------------------------------------------------------------
# Sentry — error tracking and performance monitoring
# ---------------------------------------------------------------------------

SENTRY_DSN = env("SENTRY_DSN", default="")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        profiles_sample_rate=env.float(
            "SENTRY_PROFILES_SAMPLE_RATE", default=0.1
        ),
        send_default_pii=False,          # GDPR: never send PII to Sentry
        environment=env("ENVIRONMENT", default="production"),
        release=env("APP_VERSION", default="unknown"),
    )

# ---------------------------------------------------------------------------
# DRF — no browsable API in production
# ---------------------------------------------------------------------------

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]

# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

ADMINS = [
    (name, email)
    for name, email in zip(
        env.list("ADMIN_NAMES", default=[]),
        env.list("ADMIN_EMAILS", default=[]),
    )
]