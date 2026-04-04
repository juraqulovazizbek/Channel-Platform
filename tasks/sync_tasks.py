import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.sync_tasks.sync_all_channel_subscriber_counts",
    soft_time_limit=600,
    time_limit=660,
)
def sync_all_channel_subscriber_counts() -> dict:
    """
    Scheduled hourly via Celery beat.
    Updates subscriber_count on all active linked channels.
    Uses rate-limited Telegram API calls — 1 second sleep between requests.
    """
    import time
    from apps.channels.models import Channel
    from services.telegram_service import get_chat_info

    logger.info("sync_subscriber_counts: starting")

    linked_channels = Channel.objects.filter(
        is_active=True,
        telegram_channel_id__isnull=False,
    ).only("id", "telegram_channel_id", "subscriber_count")

    updated = 0
    failed = 0

    for channel in linked_channels.iterator():
        try:
            chat_info = get_chat_info(
                str(channel.telegram_channel_id)
            )
            if chat_info:
                member_count = chat_info.get("member_count", 0)
                if member_count and channel.subscriber_count != member_count:
                    channel.subscriber_count = member_count
                    channel.save(update_fields=["subscriber_count"])
                    updated += 1
            # Telegram Bot API: 30 requests/second max.
            # Sleep 0.1s between calls for safety.
            time.sleep(0.1)
        except Exception as e:
            logger.warning(
                "sync_subscriber_counts: failed for channel_id=%s | error=%s",
                channel.id,
                e,
            )
            failed += 1
            continue

    logger.info(
        "sync_subscriber_counts: completed | updated=%d failed=%d",
        updated,
        failed,
    )
    return {"updated": updated, "failed": failed}