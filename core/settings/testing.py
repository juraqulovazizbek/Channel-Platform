from .base import *  # noqa: F401, F403
from .base import CELERY_BEAT_SCHEDULE

# ---------------------------------------------------------------------------
# Core — fast, isolated, no external dependencies
# ---------------------------------------------------------------------------

DEBUG = False

SECRET_KEY = "test-secret-key-not-used-in-production"

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Database — in-memory SQLite for speed
# Isolated per test run — no shared state between runs.
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {},
        "CONN_MAX_AGE": 0,
    }
}

# ---------------------------------------------------------------------------
# Password hashing — MD5 is fast (security irrelevant in tests)
# Bcrypt in tests makes suites 10-15x slower.
# ---------------------------------------------------------------------------

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# Cache — dummy (no Redis required in CI)
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# ---------------------------------------------------------------------------
# Celery — execute tasks synchronously in tests
# Prevents test flakiness from async worker timing.
# task_always_eager=True makes .delay() run inline.
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True  # Raise exceptions immediately
CELERY_BEAT_SCHEDULE = {}            # No periodic tasks in tests

# ---------------------------------------------------------------------------
# Media — temporary directory, cleaned up by tests
# ---------------------------------------------------------------------------

import tempfile

MEDIA_ROOT = tempfile.mkdtemp()

# Use local filesystem storage — no S3 calls in tests
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ---------------------------------------------------------------------------
# Email — suppress all email output
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ---------------------------------------------------------------------------
# Logging — silence in tests (unless explicitly debugging)
# Noisy test output hides actual failures.
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {"class": "logging.NullHandler"},
    },
    "root": {
        "handlers": ["null"],
        "level": "CRITICAL",
    },
}

# ---------------------------------------------------------------------------
# DRF — no browsable API overhead in tests
# ---------------------------------------------------------------------------

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
]

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405 — no throttling in tests

# ---------------------------------------------------------------------------
# Telegram — dummy values (all API calls must be mocked in tests)
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = "0000000000:test-bot-token-replace-in-tests"
TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
TELEGRAM_WEBHOOK_URL = "https://example.com/bot/webhook/"

# ---------------------------------------------------------------------------
# CORS — allow everything in tests
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = True