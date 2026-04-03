"""
WSGI entry point.

Used by Gunicorn in production:
    gunicorn core.wsgi:application --workers 4 --worker-class sync

The DJANGO_SETTINGS_MODULE environment variable selects which
settings file to use. Set it in the systemd unit, Docker entrypoint,
or shell before running Gunicorn.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.production")

application = get_wsgi_application()