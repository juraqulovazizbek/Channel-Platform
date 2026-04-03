# Ensure Celery app is loaded when Django starts.
# This is required for @shared_task to register correctly.
from core.celery import app as celery_app

__all__ = ("celery_app",)