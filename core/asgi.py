"""
ASGI entry point.

Currently used for standard HTTP only (Django Channels not required yet).
Structured to support WebSockets in the future — swap the application
assignment for a Channels URLRouter without touching this file's imports.

Used by Uvicorn or Daphne:
    uvicorn core.asgi:application --host 0.0.0.0 --port 8000
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.production")

# Standard Django ASGI app — handles all HTTP requests
django_asgi_app = get_asgi_application()

application = django_asgi_app

# ---------------------------------------------------------------------------
# Future WebSocket support (uncomment when django-channels is added):
#
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# from apps.notifications.routing import websocket_urlpatterns
#
# application = ProtocolTypeRouter({
#     "http": django_asgi_app,
#     "websocket": AuthMiddlewareStack(
#         URLRouter(websocket_urlpatterns)
#     ),
# })
# ---------------------------------------------------------------------------