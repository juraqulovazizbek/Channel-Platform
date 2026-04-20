import json
import logging
import hmac

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from apps.bot.dispatcher import dispatch_update

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(
    ratelimit(key="ip", rate="120/m", method="POST", block=True),
    name="dispatch",
)
class TelegramWebhookView(View):
    """
    POST /bot/webhook/

    Single entry point for all Telegram updates.

    CONTRACT: Always returns HTTP 200.
    Any non-200 triggers Telegram's exponential retry loop.

    SECURITY:
        X-Telegram-Bot-Api-Secret-Token header validated before
        any processing begins. Invalid token → silent 200 discard.

    DESIGN: Plain Django View (not DRF APIView).
        - No DRF exception handler that could return 4xx/5xx
        - No DRF authentication/permission overhead
        - Full control over response — always HttpResponse(200)
    """

    def post(self, request):
        # ── 1. Security gate ─────────────────────────────────────────────
        if not self._validate_secret_token(request):
            logger.warning(
                "Webhook: invalid secret token | ip=%s",
                request.META.get("REMOTE_ADDR"),
            )
            # Return 200 intentionally — don't leak endpoint existence
            return HttpResponse(status=200)

        # ── 2. Parse body ────────────────────────────────────────────────
        try:
            update = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Webhook: failed to parse body | error=%s", e)
            return HttpResponse(status=200)

        if not isinstance(update, dict):
            logger.error("Webhook: body is not a JSON object")
            return HttpResponse(status=200)

        # ── 3. Dispatch ───────────────────────────────────────────────────
        update_id = update.get("update_id", "unknown")
        try:
            dispatch_update(update)
        except Exception:
            logger.exception(
                "Webhook: unhandled error | update_id=%s", update_id
            )
            # Still return 200 — logging is enough, no retry needed

        return HttpResponse(status=200)

    @staticmethod
    def _validate_secret_token(request) -> bool:
        """
        Constant-time comparison against TELEGRAM_WEBHOOK_SECRET.
        Prevents timing-based enumeration of the secret.
        """
        incoming = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token", ""
        )
        expected = settings.TELEGRAM_WEBHOOK_SECRET

        if not incoming or not expected:
            return False

        return hmac.compare_digest(
            incoming.encode("utf-8"),
            expected.encode("utf-8"),
        )


class WebhookHealthView(View):
    """
    GET /bot/health/

    Public health check endpoint.
    Used by load balancers and uptime monitors.
    Returns 200 if the server is reachable.
    Does NOT verify Telegram connectivity — that's a separate check.
    """

    def get(self, request):
        return HttpResponse(
            '{"status": "ok"}',
            content_type="application/json",
            status=200,
        )