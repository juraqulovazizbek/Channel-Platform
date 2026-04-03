import logging

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


@shared_task(
    name="tasks.analytics_tasks.aggregate_daily_stats_task",
    soft_time_limit=300,
    time_limit=360,
)
def aggregate_daily_stats_task() -> dict:
    """
    Scheduled daily via Celery beat.
    Aggregates PostView records into DailyChannelStats.
    """
    from django.utils import timezone
    from django.db.models import Count
    from apps.analytics.models import PostView, DailyChannelStats
    from apps.channels.models import Channel

    yesterday = (timezone.now() - timezone.timedelta(days=1)).date()

    logger.info(
        "aggregate_daily_stats_task: starting | date=%s", yesterday
    )

    channels_updated = 0

    for channel in Channel.objects.filter(is_active=True).iterator():
        views_qs = PostView.objects.filter(
            post__channel=channel,
            viewed_at__date=yesterday,
        )
        total_views = views_qs.count()
        unique_visitors = (
            views_qs
            .values("visitor_id")
            .distinct()
            .count()
        )
        post_count = (
            channel.posts
            .filter(created_at__date=yesterday, is_published=True)
            .count()
        )

        DailyChannelStats.objects.update_or_create(
            channel=channel,
            date=yesterday,
            defaults={
                "total_views": total_views,
                "unique_visitors": unique_visitors,
                "post_count": post_count,
            },
        )
        channels_updated += 1

    logger.info(
        "aggregate_daily_stats_task: completed | "
        "date=%s channels=%d",
        yesterday,
        channels_updated,
    )
    return {"date": str(yesterday), "channels_updated": channels_updated}