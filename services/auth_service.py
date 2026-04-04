import hashlib
import hmac
import logging
import time
from typing import Optional

from django.conf import settings
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# These are the only functions views and bot handlers should call.
# ---------------------------------------------------------------------------


def verify_telegram_auth(data: dict) -> bool:
    """
    Cryptographically verify a Telegram Login Widget or bot auth payload.

    WHY THIS EXISTS:
        Telegram sends user data + a hash. Anyone can forge user data without
        the hash check. This function is the security gate — if it returns
        False, we reject the request entirely before touching the database.

    HOW IT WORKS:
        1. Extract the 'hash' field from the payload.
        2. Build a sorted key=value string from all OTHER fields.
        3. HMAC-SHA256 sign it with SHA256(BOT_TOKEN) as the key.
        4. Compare our result with Telegram's hash (constant-time compare).

    WHEN IT'S USED:
        - Telegram Login Widget callback (web auth)
        - Bot-based phone auth flow
        - Any endpoint that accepts Telegram identity data

    IMPORTANT:
        We also check auth_date here as a second line of defense.
        The serializer already rejects payloads older than 24h,
        but services must never trust that validation ran.
    """
    received_hash = data.get("hash")
    if not received_hash:
        logger.warning("Telegram auth rejected: missing hash field.")
        return False

    # SAFE auth_date parsing
    try:
        auth_date = int(data.get("auth_date", 0))
    except (ValueError, TypeError):
        logger.warning("Telegram auth rejected: invalid auth_date.")
        return False

    # 24h expiry check
    if time.time() - auth_date > 86400:
        logger.warning("Telegram auth rejected: auth expired.")
        return False

    # STRICT Telegram spec filtering
    check_fields = {}
    for k, v in data.items():
        if k == "hash":
            continue
        if v is None:
            continue
        check_fields[k] = str(v)

    check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(check_fields.items())
    )

    # Telegram requires SHA256(bot_token)
    bot_token = settings.TELEGRAM_BOT_TOKEN.strip()
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    expected_hash = hmac.new(
        secret_key,
        msg=check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    is_valid = hmac.compare_digest(expected_hash, received_hash)

    if not is_valid:
        logger.warning(
            "Telegram auth rejected: hash mismatch telegram_id=%s",
            data.get("id"),
        )

    return is_valid


@transaction.atomic
def create_or_update_user(telegram_data: dict) -> User:
    """
    Upsert a User record from verified Telegram auth data.

    WHY THIS EXISTS:
        User records must stay in sync with Telegram's source of truth.
        A user might change their username or profile photo between sessions.
        We update on every login — not just on first create.

    IDEMPOTENCY:
        Uses get_or_create on telegram_id. Safe to call multiple times
        with the same data. The result is always consistent.

    WHEN IT'S USED:
        - After verify_telegram_auth passes
        - During bot interactions when a new user contacts the bot

    RETURNS:
        The User instance (created or updated).
    """
    telegram_id = int(telegram_data["id"])

    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            "first_name": telegram_data.get("first_name", ""),
            "last_name": telegram_data.get("last_name", ""),
            "username": telegram_data.get("username", ""),
            "profile_photo": telegram_data.get("photo_url", ""),
        },
    )

    if created:
        logger.info(
            "New user created: telegram_id=%d username=%s",
            telegram_id,
            user.username or "(none)",
        )
    else:
        # Update mutable profile fields on every login.
        # Telegram users change usernames and photos — we must reflect that.
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
            logger.debug(
                "User updated: telegram_id=%d fields=%s",
                telegram_id,
                updated_fields,
            )

    return user


def generate_jwt_tokens(user: User) -> dict:
    """
    Issue a JWT access + refresh token pair for a user.

    WHY THIS EXISTS:
        Centralizes token generation. If we ever need to add custom claims
        (e.g. channel_ids, role), we do it in ONE place — here.

    RETURNS:
        {
            "access": "<access_token>",
            "refresh": "<refresh_token>",
            "user": { ...basic user data... }
        }

    WHEN IT'S USED:
        - Immediately after successful Telegram auth
        - After phone verification completes
    """
    refresh = RefreshToken.for_user(user)

    # Inject custom claims into the access token payload.
    # These are readable client-side (JWT is signed, not encrypted)
    # so we only put non-sensitive, useful data here.
    refresh.access_token["telegram_id"] = user.telegram_id
    refresh.access_token["username"] = user.username
    refresh.access_token["display_name"] = user.display_name

    logger.info("JWT tokens issued for user: telegram_id=%d", user.telegram_id)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.username,
            "display_name": user.display_name,
            "profile_photo": user.profile_photo,
        },
    }


# ---------------------------------------------------------------------------
# Internal helpers
# Not part of the public API — prefix with _ signals "don't call from views"
# ---------------------------------------------------------------------------


def _build_check_string(data: dict) -> str:
    """
    Extracted for testability.
    Builds the canonical check string Telegram expects us to verify.
    """
    check_fields = {k: v for k, v in data.items() if k != "hash" and v}
    return "\n".join(f"{k}={v}" for k, v in sorted(check_fields.items()))