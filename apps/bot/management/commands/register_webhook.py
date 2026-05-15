"""
Management command to register the bot webhook with Telegram.

Usage:
    python manage.py register_webhook
    python manage.py register_webhook --delete   # Remove webhook
    python manage.py register_webhook --info     # Show current webhook

Run this once after deployment whenever the webhook URL changes.
"""

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Register, delete, or inspect the Telegram bot webhook."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Remove the currently configured webhook.",
        )
        parser.add_argument(
            "--info",
            action="store_true",
            help="Show current webhook configuration from Telegram.",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="",
            help=(
                "Override the webhook URL. "
                "Defaults to TELEGRAM_WEBHOOK_URL from settings."
            ),
        )

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        base = f"https://api.telegram.org/bot{token}"

        if options["info"]:
            self._get_webhook_info(base)
            return

        if options["delete"]:
            self._delete_webhook(base)
            return

        webhook_url = options["url"] or settings.TELEGRAM_WEBHOOK_URL
        if not webhook_url:
            raise CommandError(
                "TELEGRAM_WEBHOOK_URL is not set. "
                "Set it in .env or pass --url."
            )

        self._set_webhook(base, webhook_url, secret)

    def _set_webhook(self, base: str, url: str, secret: str) -> None:
        self.stdout.write(f"Registering webhook: {url}")

        payload = {
            "url": url,
            "secret_token": secret,
            # Only receive update types we actually handle.
            # Filtering reduces webhook volume significantly.
            "allowed_updates": [
                "message",
                "edited_message",
                "channel_post",
                "edited_channel_post",
            ],
            "drop_pending_updates": True,   # Discard queued updates on re-register
            "max_connections": 40,          # Telegram's max: 100. 40 is safe default.
        }

        try:
            resp = httpx.post(
                f"{base}/setWebhook",
                json=payload,
                timeout=15.0,
            )
            data = resp.json()
        except httpx.HTTPError as e:
            raise CommandError(f"HTTP error: {e}")

        if data.get("ok"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Webhook registered successfully.\n"
                    f"Description: {data.get('description', '')}"
                )
            )
        else:
            raise CommandError(
                f"Telegram API error: {data.get('description', 'Unknown error')}"
            )

    def _delete_webhook(self, base: str) -> None:
        self.stdout.write("Deleting webhook...")
        try:
            resp = httpx.post(
                f"{base}/deleteWebhook",
                json={"drop_pending_updates": True},
                timeout=10.0,
            )
            data = resp.json()
        except httpx.HTTPError as e:
            raise CommandError(f"HTTP error: {e}")

        if data.get("ok"):
            self.stdout.write(
                self.style.SUCCESS("Webhook deleted successfully.")
            )
        else:
            raise CommandError(
                f"Telegram API error: {data.get('description')}"
            )

    def _get_webhook_info(self, base: str) -> None:
        try:
            resp = httpx.get(f"{base}/getWebhookInfo", timeout=10.0)
            data = resp.json()
        except httpx.HTTPError as e:
            raise CommandError(f"HTTP error: {e}")

        if not data.get("ok"):
            raise CommandError("Failed to fetch webhook info.")

        result = data.get("result", {})
        url = result.get("url", "(none)")
        pending = result.get("pending_update_count", 0)
        last_error = result.get("last_error_message", "(none)")
        last_error_date = result.get("last_error_date", None)
        max_conn = result.get("max_connections", 0)
        allowed = result.get("allowed_updates", [])

        self.stdout.write(
            f"\nWebhook Info:\n"
            f"  URL:              {url}\n"
            f"  Pending updates:  {pending}\n"
            f"  Max connections:  {max_conn}\n"
            f"  Allowed updates:  {', '.join(allowed)}\n"
            f"  Last error:       {last_error}\n"
            f"  Last error date:  {last_error_date}\n"
        )