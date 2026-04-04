import logging
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum, Count

from apps.analytics.models import PostView, DailyChannelStats
from apps.channels.models import Channel
from apps.posts.models import Post

logger = logging.getLogger(__name__)

# Redis key patterns — centralised so they're easy to change and grep
_VIEW_COUNTER_KEY = "post:views:{post_id}"          # Incremented on every view
_VIEW_DEDUP_KEY = "post:viewed:{post_id}:{visitor}" # TTL-based dedup per visitor


def increment_post_view(post_id: str, visitor_id: str) -> None:
    """
    Record a post view — fast path via Redis, no DB write.

    WHY REDIS INSTEAD OF DB:
        A popular post can receive hundreds of views per minute.
        Writing a DB row on every view would saturate connections
        and create write contention on the posts table.

    DEDUPLICATION:
        We track (post_id, visitor_id) in Redis with a 1-hour TTL.
        The same visitor watching the same post multiple times in
        an hour counts as ONE view. After 1 hour, it counts again.
        This is the YouTube-style approach — simple and effective.

    FLUSH STRATEGY:
        The actual Post.views_count and PostView records are written
        by analytics_tasks.flush_view_counters (Celery beat, every 5 min).
        This function ONLY touches Redis.

    WHEN IT'S USED:
        POST /api/posts/{id}/view/ → PostViewView → here.
    """
    dedup_key = _VIEW_DEDUP_KEY.format(post_id=post_id, visitor=visitor_id)

    # nx=True: only set if not exists. Returns True if the key was new.
    # This is atomic in Redis — no race condition.
    is_new_view = cache.set(dedup_key, 1, timeout=3600, nx=True) if hasattr(cache, 'set') else True

    # Fallback for cache backends that don't support nx:
    # Check existence first (slightly less atomic, acceptable for analytics)
    if is_new_view is None:
        if cache.get(dedup_key):
            return  # Already viewed within dedup window
        cache.set(dedup_key, 1, timeout=3600)

    if not is_new_view:
        logger.debug("Duplicate view skipped: post=%s visitor=%s", post_id, visitor_id)
        return

    # Increment the shared counter for this post
    counter_key = _VIEW_COUNTER_KEY.format(post_id=post_id)
    try:
        cache.incr(counter_key)
    except ValueError:
        # Key doesn't exist yet — initialize it
        cache.set(counter_key, 1, timeout=None)

    logger.debug("View counted: post=%s visitor=%s", post_id, visitor_id)


def flush_view_counters() -> int:
    from django.core.cache import cache as django_cache
    from django.conf import settings

    # Access the raw Redis client for SCAN + GETDEL
    # (django-redis exposes this via cache.client.get_client())
    try:
        redis_client = django_cache.client.get_client()
    except AttributeError:
        logger.warning("flush_view_counters: Redis client not available.")
        return 0

    pattern = _VIEW_COUNTER_KEY.format(post_id="*")
    updated_count = 0
    posts_to_update = []

    # SCAN is non-blocking — safe to use on production Redis
    for key in redis_client.scan_iter(pattern):
        raw_count = redis_client.getdel(key)
        if not raw_count:
            continue

        count = int(raw_count)
        if count <= 0:
            continue

        # Extract post_id from the key string
        post_id = key.decode().split(":")[-1]

        posts_to_update.append((post_id, count))

    if not posts_to_update:
        return 0

    # Bulk update using a single query per post (F expression avoids race conditions)
    from django.db.models import F

    for post_id, count in posts_to_update:
        rows = Post.objects.filter(id=post_id).update(
            views_count=F("views_count") + count
        )
        if rows:
            updated_count += 1
        else:
            logger.warning("flush_view_counters: Post not found: id=%s", post_id)

    logger.info("View counters flushed: %d posts updated.", updated_count)
    return updated_count


def get_channel_stats(channel: Channel) -> dict:
    """
    Return aggregated stats for a channel's analytics dashboard.

    WHY PRE-AGGREGATED DATA:
        We query DailyChannelStats (pre-computed by Celery) for the time-series.
        We compute totals via aggregate() — one DB round-trip.
        We NEVER do GROUP BY on raw PostView for dashboard queries.

    WHEN IT'S USED:
        GET /api/channels/{slug}/analytics/ → ChannelAnalyticsView → here.

    RETURNS:
        Dict matching ChannelStatsOverviewSerializer shape.
    """
    # Totals from pre-aggregated table
    totals = DailyChannelStats.objects.filter(channel=channel).aggregate(
        total_views=Sum("total_views"),
        total_unique=Sum("unique_visitors"),
        total_posts=Sum("post_count"),
    )

    # Top post — single query, uses the idx_post_views_count index
    top_post = (
        Post.objects
        .filter(channel=channel, is_published=True)
        .order_by("-views_count")
        .only("id", "title", "views_count")
        .first()
    )

    # Last 30 days of daily stats for the chart
    daily_stats = (
        DailyChannelStats.objects
        .filter(channel=channel)
        .order_by("-date")[:30]
    )

    total_views = totals["total_views"] or 0
    total_posts = totals["total_posts"] or 0

    return {
        "total_views": total_views,
        "total_posts": total_posts,
        "total_unique_visitors": totals["total_unique"] or 0,
        "avg_views_per_post": round(total_views / total_posts, 2) if total_posts else 0.0,
        "top_post_id": top_post.id if top_post else None,
        "top_post_title": top_post.title if top_post else "",
        "top_post_views": top_post.views_count if top_post else 0,
        "daily_stats": daily_stats,
    }


def get_top_posts(channel: Channel, limit: int = 10):
    """
    Return the top posts by view count for a channel.

    OPTIMIZATION:
        .only() fetches just the columns we need.
        The idx_post_views_count index makes this fast even at scale.

    WHEN IT'S USED:
        Analytics dashboard widget, "popular posts" sidebar.
    """
    return (
        Post.objects
        .filter(channel=channel, is_published=True)
        .only("id", "title", "type", "thumbnail", "views_count", "created_at")
        .order_by("-views_count")[:limit]
    )