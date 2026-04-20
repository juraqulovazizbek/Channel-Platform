import hashlib
import hmac
import logging
import time
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


def verify_telegram_auth(data: dict) -> bool:
    received_hash = data.get("hash")
    if not received_hash:
        logger.warning("Telegram auth rejected: missing hash field.")
        return False

    try:
        auth_date = int(data.get("auth_date", 0))
    except (ValueError, TypeError):
        return False

    if time.time() - auth_date > 86400:
        logger.warning("Telegram auth rejected: expired")
        return False

    check_fields = {
        k: str(v)
        for k, v in data.items()
        if k != "hash" and v is not None
    }

    check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(check_fields.items())
    )

    bot_token = settings.TELEGRAM_BOT_TOKEN.strip()
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    expected_hash = hmac.new(
        secret_key,
        msg=check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hash, received_hash)


@transaction.atomic
def create_or_update_user(telegram_data: dict) -> "User":
    telegram_id = int(telegram_data.get("id"))

    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "first_name": telegram_data.get("first_name", ""),
            "last_name": telegram_data.get("last_name", ""),
            "username": telegram_data.get("username", ""),
            "profile_photo": telegram_data.get("photo_url", ""),
            "is_active": True,
        },
    )

    # UPDATE only changed fields
    updated_fields = []

    new_first = telegram_data.get("first_name", "")
    new_last = telegram_data.get("last_name", "")
    new_username = telegram_data.get("username", "")
    new_photo = telegram_data.get("photo_url", "")

    if user.first_name != new_first:
        user.first_name = new_first
        updated_fields.append("first_name")

    if user.last_name != new_last:
        user.last_name = new_last
        updated_fields.append("last_name")

    if new_username and user.username != new_username:
        user.username = new_username
        updated_fields.append("username")

    if new_photo and user.profile_photo != new_photo:
        user.profile_photo = new_photo
        updated_fields.append("profile_photo")

    if updated_fields:
        user.save(update_fields=updated_fields)

    return user


def generate_jwt_tokens(user: "User") -> dict:
    refresh = RefreshToken.for_user(user)

    display_name = f"{user.first_name} {user.last_name}".strip()

    # safe claims
    refresh.access_token["telegram_id"] = user.telegram_id
    refresh.access_token["username"] = user.username or ""
    refresh.access_token["display_name"] = display_name

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.username,
            "display_name": display_name,
            "profile_photo": user.profile_photo,
        },
    }