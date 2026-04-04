# utils/telegram.py
"""
Telegram-specific utility helpers.
Pure functions — no Django imports, no model imports.
"""

import hashlib
import hmac
import time


def build_check_string(data: dict) -> str:
    """
    Telegram Login Widget hash verification uchun check string yaratadi.
    Barcha fieldlar 'hash' dan tashqari, sorted va newline bilan birlashtiriladi.
    """
    check_fields = {
        k: str(v)
        for k, v in data.items()
        if k != "hash" and v is not None
    }
    return "\n".join(f"{k}={v}" for k, v in sorted(check_fields.items()))


def compute_telegram_hash(check_string: str, bot_token: str) -> str:
    """
    Telegram spesifikatsiyasiga ko'ra hash hisoblash.
    Secret key = SHA256(bot_token).
    """
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    return hmac.new(
        secret_key,
        msg=check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def is_auth_data_fresh(auth_date: int, max_age_seconds: int = 86400) -> bool:
    """
    Telegram auth_date ning muddati o'tmagan-o'tmaganligini tekshiradi.
    Default: 24 soat (Telegram tavsiyasi).
    """
    return (time.time() - auth_date) <= max_age_seconds


def infer_mime_type(file_name: str) -> str:
    """Fayl kengaytmasidan MIME type aniqlash."""
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "avi": "video/x-msvideo",
        "pdf": "application/pdf",
    }
    return mime_map.get(ext, "application/octet-stream")