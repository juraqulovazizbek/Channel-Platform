import logging
from django.core.cache import cache
from typing import Optional, Tuple

import httpx
from django.conf import settings

from apps.posts.models import PostType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telegram Bot API base URL.
# All requests go through this — centralised so rotating tokens is a 1-line change.
# ---------------------------------------------------------------------------

def _bot_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def _file_url(file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{settings.TELEGRAM_BOT_TOKEN}/{file_path}"


# ---------------------------------------------------------------------------
# Webhook parsing
# ---------------------------------------------------------------------------


# services/telegram_service.py — faqat BITTA parse_webhook_update bo'lishi kerak

def parse_webhook_update(update_json: dict) -> Optional[dict]:
    """
    Parse a raw Telegram webhook update into a normalized dict.
    update_type field qo'shilgan — dispatcher routing uchun zarur.
    """
    update_id = update_json.get("update_id")

    if "channel_post" in update_json:
        message = update_json["channel_post"]
        normalized = _normalize_message(
            message, source="channel", update_id=update_id
        )
        if normalized:
            normalized["update_type"] = "channel_post"
        return normalized

    if "edited_channel_post" in update_json:
        message = update_json["edited_channel_post"]
        normalized = _normalize_message(
            message, source="channel", update_id=update_id
        )
        if normalized:
            normalized["update_type"] = "channel_post"
            normalized["is_edit"] = True
        return normalized

    if "message" in update_json:
        message = update_json["message"]
        normalized = _normalize_message(
            message, source="bot", update_id=update_id
        )
        if normalized:
            normalized["update_type"] = "message"
        return normalized

    if "edited_message" in update_json:
        message = update_json["edited_message"]
        normalized = _normalize_message(
            message, source="bot", update_id=update_id
        )
        if normalized:
            normalized["update_type"] = "message"
            normalized["is_edit"] = True
        return normalized

    logger.debug(
        "Unhandled update type: update_id=%s keys=%s",
        update_id,
        list(update_json.keys()),
    )
    return None

def extract_message_data(update: dict) -> dict:
    """
    Extract the fields post_service.create_post_from_bot expects.

    WHY SEPARATE FROM parse_webhook_update:
        parse_webhook_update normalizes the raw Telegram structure.
        extract_message_data maps that to our domain language.
        Two concerns — two functions.

    RETURNS:
        Dict ready to pass directly to post_service.create_post_from_bot.
    """
    return {
        "channel_id": update.get("chat_id"),
        "telegram_message_id": update.get("message_id"),
        "type": update.get("post_type", PostType.TEXT),
        "content": update.get("text", ""),
        "title": update.get("title", ""),
        "file_id": update.get("file_id", ""),
        "source": update.get("source", "channel"),
        "date": update.get("date"),
        "media_group": update.get("media_group", []),
    }


def detect_message_type(message: dict) -> str:
    """
    Determine the PostType for an incoming Telegram message.

    PRIORITY ORDER matters — a message can technically have both
    'photo' and 'caption'. We classify by the most specific type first.

    WHEN IT'S USED:
        _normalize_message → here → stored on the normalized dict.
    """
    if "video_note" in message:
        return PostType.REEL          # Telegram's circular "video note" → we treat as Reel

    if "video" in message:
        return PostType.VIDEO

    if "photo" in message:
        # media_group_id signals this is part of a carousel
        if message.get("media_group_id"):
            return PostType.CAROUSEL
        return PostType.IMAGE

    if "document" in message:
        # Documents can be files of any type.
        # We map them to IMAGE or VIDEO based on mime_type if present.
        mime = message.get("document", {}).get("mime_type", "")
        if mime.startswith("video/"):
            return PostType.VIDEO
        if mime.startswith("image/"):
            return PostType.IMAGE

    # Default: plain text
    return PostType.TEXT


# ---------------------------------------------------------------------------
# Telegram Bot API calls
# ---------------------------------------------------------------------------


def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> Optional[dict]:
    """
    Send a text message via the bot.

    WHY parse_mode defaults to HTML:
        HTML is safer than Markdown for user-generated content.
        Telegram's MarkdownV2 requires escaping almost every character —
        HTML is more predictable in production.

    WHEN IT'S USED:
        - Confirming successful channel link
        - Error messages back to the user
        - Command responses
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    response = _post("sendMessage", payload)
    if response:
        logger.debug("Message sent: chat_id=%d", chat_id)
    return response


def download_file(file_id: str) -> Tuple[Optional[bytes], str, str]:
    """
    Download a file from Telegram's servers.

    FLOW:
        1. getFile(file_id) → temporary file_path (valid for 1 hour)
        2. Download raw bytes from the CDN URL

    RETURNS:
        (file_bytes, file_name, mime_type)
        Returns (None, "", "") on any failure — caller handles the None case.

    TIMEOUT:
        30 seconds. Telegram files can be up to 2GB (bots: 50MB).
        In practice, channel media is usually under 20MB.

    WHEN IT'S USED:
        services/post_service.handle_media_download_and_attach
        Called from Celery task — never from the webhook thread.
    """
    # Step 1: resolve file_id → file_path
    file_info = _get("getFile", {"file_id": file_id})
    if not file_info or "result" not in file_info:
        logger.error("getFile failed for file_id=%s", file_id)
        return None, "", ""

    result = file_info["result"]
    file_path = result.get("file_path", "")
    file_size = result.get("file_size", 0)

    if not file_path:
        logger.error("Empty file_path from getFile: file_id=%s", file_id)
        return None, "", ""

    # Step 2: download the actual bytes
    download_url = _file_url(file_path)
    file_name = file_path.split("/")[-1]

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPError as e:
        logger.error("File download failed: file_id=%s error=%s", file_id, e)
        return None, "", ""

    mime_type = _infer_mime_type(file_name)

    logger.info(
        "File downloaded: file_id=%s name=%s size=%d",
        file_id,
        file_name,
        file_size,
    )
    return content, file_name, mime_type


def get_chat_info(username: str) -> Optional[dict]:
    """
    Resolve a Telegram channel username to its metadata.

    Also checks whether the bot is an admin of that chat.
    Returns a dict with standard chat fields + '_bot_is_admin' flag.

    WHEN IT'S USED:
        channel_service.link_telegram_channel → here.
    """
    chat_data = _get("getChat", {"chat_id": f"@{username}"})

    if not chat_data or not chat_data.get("ok"):
        logger.warning("getChat failed for @%s", username)
        return None

    result = chat_data["result"]
    chat_id = result["id"]

    # Check bot admin status by fetching its ChatMember record
    bot_member = _get("getChatMember", {
        "chat_id": chat_id,
        "user_id": _get_bot_id(),
    })

    is_admin = False
    if bot_member and bot_member.get("ok"):
        status = bot_member["result"].get("status", "")
        is_admin = status in ("administrator", "creator")

    result["_bot_is_admin"] = is_admin
    return result


# ---------------------------------------------------------------------------
# HTTP helpers — thin wrappers around httpx
# ---------------------------------------------------------------------------


def _post(method: str, payload: dict) -> Optional[dict]:
    """
    POST to a Telegram Bot API method.
    Returns parsed JSON or None on failure.
    """
    url = _bot_url(method)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("Telegram API POST failed: method=%s error=%s", method, e)
        return None


def _get(method: str, params: dict) -> Optional[dict]:
    """
    GET from a Telegram Bot API method.
    Returns parsed JSON or None on failure.
    """
    url = _bot_url(method)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("Telegram API GET failed: method=%s error=%s", method, e)
        return None


def _get_bot_id() -> int:
    cache_key = "telegram:bot_id"
    bot_id = cache.get(cache_key)
    if bot_id:
        return bot_id

    data = _get("getMe", {})
    if data and data.get("ok"):
        bot_id = data["result"]["id"]
        cache.set(cache_key, bot_id, timeout=86400)  # 24 soat
        return bot_id

    raise RuntimeError("Could not fetch bot ID from Telegram.")

def _normalize_message(message: dict, source: str, update_id: int) -> Optional[dict]:
    """
    Convert a raw Telegram message object into our normalized dict.

    Handles:
    - Text messages
    - Photo messages (largest available size is always last in the array)
    - Video messages
    - Video notes (reels)
    - Documents
    - Media groups (carousel — partial, grouped by media_group_id)
    """
    if not message:
        return None

    chat = message.get("chat", {})
    post_type = detect_message_type(message)

    # Extract the best available file_id based on message type
    file_id = _extract_file_id(message, post_type)

    # Caption is the "content" for media posts; text is for text posts
    text = message.get("text") or message.get("caption") or ""

    # Attempt to parse a title from the first line of long messages
    title = ""
    if text and "\n" in text:
        first_line = text.split("\n")[0].strip()
        if len(first_line) <= 128:
            title = first_line

    return {
        "update_id": update_id,
        "message_id": message.get("message_id"),
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "chat_username": chat.get("username", ""),
        "post_type": post_type,
        "text": text,
        "title": title,
        "file_id": file_id,
        "source": source,
        "date": message.get("date"),
        "media_group_id": message.get("media_group_id"),
        "is_edit": False,
    }

def _extract_file_id(message: dict, post_type: str) -> str:
    """
    Extract the most appropriate file_id from a Telegram message.

    For photos, Telegram sends an array of PhotoSize objects in ascending
    resolution order — we always want the last one (highest resolution).
    """
    if post_type == PostType.IMAGE or post_type == PostType.CAROUSEL:
        photos = message.get("photo", [])
        if photos:
            return photos[-1].get("file_id", "")  # Last = largest

    if post_type == PostType.VIDEO:
        video = message.get("video", {})
        return video.get("file_id", "")

    if post_type == PostType.REEL:
        video_note = message.get("video_note", {})
        return video_note.get("file_id", "")

    if "document" in message:
        return message["document"].get("file_id", "")

    return ""


def _infer_mime_type(file_name: str) -> str:
    """Infer MIME type from file extension."""
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif",
        "webp": "image/webp", "mp4": "video/mp4",
        "mov": "video/quicktime", "avi": "video/x-msvideo",
        "pdf": "application/pdf",
    }
    return mime_map.get(ext, "application/octet-stream")