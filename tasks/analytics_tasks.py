import logging
from django.db import models
from celery import shared_task


logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.analytics_tasks.flush_view_counters_task",
    soft_time_limit=120,
    time_limit=180,
)
def flush_view_counters_task() -> dict:
    """
    Scheduled every 5 minutes via Celery beat.
    Flushes Redis view counters to the database.
    """
    from services.analytics_service import flush_view_counters

    logger.info("flush_view_counters_task: starting")
    updated = flush_view_counters()
    logger.info("flush_view_counters_task: completed | posts_updated=%d", updated)
    return {"posts_updated": updated}


# tasks/analytics_tasks.py — N+1 muammosiz versiya

@shared_task(
    name="tasks.analytics_tasks.aggregate_daily_stats_task",
    soft_time_limit=300,
    time_limit=360,
)
def aggregate_daily_stats_task() -> dict:
    from django.utils import timezone
    from django.db.models import Count
    from apps.analytics.models import PostView, DailyChannelStats
    from apps.channels.models import Channel

    yesterday = (timezone.now() - timezone.timedelta(days=1)).date()
    logger.info("aggregate_daily_stats_task: starting | date=%s", yesterday)

    # Barcha kanallar uchun bir SQL bilan views aggregatsiya
    view_stats = dict(
        PostView.objects
        .filter(viewed_at__date=yesterday, post__channel__is_active=True)
        .values("post__channel_id")
        .annotate(total=Count("id"), unique=Count("visitor_id", distinct=True))
        .values_list("post__channel_id", "total", "unique")
    )

    # Post countlar ham bir query da
    post_counts = dict(
        Channel.objects
        .filter(is_active=True)
        .annotate(
            count=Count(
                "posts",
                filter=models.Q(
                    posts__created_at__date=yesterday,
                    posts__is_published=True,
                )
            )
        )
        .values_list("id", "count")
    )

    channels = Channel.objects.filter(is_active=True).only("id")
    bulk_data = []

    for channel in channels:
        stats = view_stats.get(channel.id, {})
        bulk_data.append(
            DailyChannelStats(
                channel=channel,
                date=yesterday,
                total_views=stats.get("total", 0),
                unique_visitors=stats.get("unique", 0),
                post_count=post_counts.get(channel.id, 0),
            )
        )

    # Bulk upsert — bir query
    DailyChannelStats.objects.bulk_create(
        bulk_data,
        update_conflicts=True,
        unique_fields=["channel", "date"],
        update_fields=["total_views", "unique_visitors", "post_count"],
    )

    logger.info(
        "aggregate_daily_stats_task: completed | date=%s channels=%d",
        yesterday, len(bulk_data),
    )
    return {"date": str(yesterday), "channels_updated": len(bulk_data)}