import uuid
from django.db import models
from apps.posts.models import Post
from apps.channels.models import Channel


class PostView(models.Model):
    """
    Individual view event for a post.

    In production, we do NOT write one row per view directly.
    That would destroy the DB at scale.

    Strategy:
    1. Each view increments a Redis counter: `post:views:{post_id}`
    2. A Celery beat task runs every 5 minutes, reads all counters,
       flushes them to Post.views_count and writes aggregated
       PostView records for historical analytics.

    visitor_id is a hashed identifier — either the JWT user ID
    or a fingerprinted anonymous session. Never store raw IPs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="view_events",
        db_index=True,
    )
    visitor_id = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Hashed user or session ID. Not a raw IP.",
    )
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "post_views"
        verbose_name = "Post View"
        verbose_name_plural = "Post Views"
        indexes = [
            models.Index(fields=["post", "viewed_at"], name="idx_view_post_time"),
            models.Index(fields=["visitor_id", "post"], name="idx_view_visitor_post"),
        ]

    def __str__(self):
        return f"View on {self.post_id} at {self.viewed_at}"


class DailyChannelStats(models.Model):
    """
    Aggregated daily stats per channel.
    Pre-aggregated by Celery — never computed on-the-fly in views.

    Drives the analytics dashboard without expensive GROUP BY queries.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    date = models.DateField(db_index=True)
    total_views = models.PositiveIntegerField(default=0)
    unique_visitors = models.PositiveIntegerField(default=0)
    post_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of posts published on this date.",
    )

    class Meta:
        db_table = "daily_channel_stats"
        verbose_name = "Daily Channel Stats"
        verbose_name_plural = "Daily Channel Stats"
        ordering = ["-date"]
        indexes = [
            models.Index(
                fields=["channel", "date"],
                name="idx_daily_stats_channel_date",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "date"],
                name="uq_channel_daily_stats",
            )
        ]

    def __str__(self):
        return f"{self.channel.slug} — {self.date}"