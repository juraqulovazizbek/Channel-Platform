# apps/bot/tests/test_webhook.py

import json
import hmac
import hashlib
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from django.conf import settings


class TestTelegramWebhookView(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = "/bot/webhook/"
        self.secret = settings.TELEGRAM_WEBHOOK_SECRET

    def _make_headers(self):
        return {
            "HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": self.secret,
            "CONTENT_TYPE": "application/json",
        }

    def _channel_post_payload(self):
        return {
            "update_id": 100000001,
            "channel_post": {
                "message_id": 42,
                "chat": {
                    "id": -1001234567890,
                    "type": "channel",
                    "username": "testchannel",
                },
                "date": 1700000000,
                "text": "Hello from channel",
            },
        }

    def test_missing_secret_token_returns_200(self):
        """Secret token yo'q — 200 qaytarish kerak (Telegram retry oldini olish)."""
        response = self.client.post(
            self.url,
            data=json.dumps(self._channel_post_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_secret_token_returns_200(self):
        """Noto'g'ri secret token — 200 qaytarish kerak."""
        response = self.client.post(
            self.url,
            data=json.dumps(self._channel_post_payload()),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong_secret",
        )
        self.assertEqual(response.status_code, 200)

    def test_valid_request_returns_200(self):
        """To'g'ri so'rov — 200 qaytarishi kerak."""
        with patch("apps.bot.views.dispatch_update") as mock_dispatch:
            response = self.client.post(
                self.url,
                data=json.dumps(self._channel_post_payload()),
                content_type="application/json",
                **self._make_headers(),
            )
        self.assertEqual(response.status_code, 200)
        mock_dispatch.assert_called_once()

    def test_invalid_json_returns_200(self):
        """Noto'g'ri JSON — 200 qaytarishi kerak, crash bo'lmasligi kerak."""
        response = self.client.post(
            self.url,
            data="not valid json {{{",
            content_type="application/json",
            **self._make_headers(),
        )
        self.assertEqual(response.status_code, 200)

    def test_dispatch_error_still_returns_200(self):
        """dispatch_update xato berse ham — 200 qaytarishi kerak."""
        with patch(
            "apps.bot.views.dispatch_update",
            side_effect=RuntimeError("Unexpected error"),
        ):
            response = self.client.post(
                self.url,
                data=json.dumps(self._channel_post_payload()),
                content_type="application/json",
                **self._make_headers(),
            )
        self.assertEqual(response.status_code, 200)

    def test_health_endpoint(self):
        """Health check endpoint 200 qaytarishi kerak."""
        response = self.client.get("/bot/health/")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")