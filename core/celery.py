"""
Celery application entry point.

Import this in core/__init__.py so Celery is initialized
when Django starts — required for @shared_task decorators to work.
"""

import os
from celery import Celery
from celery.signals import setup_logging

@setup_logging.connect
def configure_logging(loglevel, logfile, format, colorize, **kwargs):
    import logging.config
    from django.conf import settings
    logging.config.dictConfig(settings.LOGGING)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "core.settings.development"
)

app = Celery("telegram_platform")

# Load all CELERY_* settings from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all INSTALLED_APPS and in the top-level tasks/ package
app.autodiscover_tasks(
    packages=["tasks"],
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task for verifying Celery is running."""
    print(f"Request: {self.request!r}")