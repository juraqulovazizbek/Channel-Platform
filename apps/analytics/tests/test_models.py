# apps/analytics/tests/test_models.py

import uuid
from datetime import date, timedelta
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone
from apps.users.models import User
from apps.channels.models import Channel
from apps.posts.models import Post, PostType
from apps.analytics.models import PostView, DailyChannelStats


# ─────────────────────────────────────────────────────────────────────────────
# Yordamchi funksiyalar
# ─────────────────────────────────────────────────────────────────────────────

def make_user(telegram_id, first_name="User"):
    return User.objects.create_user(telegram_id=telegram_id, first_name=first_name)


def make_channel(owner, slug="test-ch"):
    return Channel.objects.create(owner=owner, name="Test", slug=slug)


def make_post(channel, title="Post", post_type=PostType.TEXT):
    return Post.objects.create(
        channel=channel,
        type=post_type,
        title=title,
        content="Content",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PostView model — field defaults va yaratish
# ─────────────────────────────────────────────────────────────────────────────

class TestPostViewModel(TestCase):

    def setUp(self):
        self.user = make_user(200000001)
        self.channel = make_channel(self.user)
        self.post = make_post(self.channel)

    def test_id_is_uuid(self):
        view = PostView.objects.create(
            post=self.post,
            visitor_id="abc123",
        )
        self.assertIsInstance(view.id, uuid.UUID)

    def test_viewed_at_set_automatically(self):
        view = PostView.objects.create(
            post=self.post,
            visitor_id="visitor_x",
        )
        self.assertIsNotNone(view.viewed_at)
        self.assertLessEqual(view.viewed_at, timezone.now())

    def test_str_representation(self):
        view = PostView.objects.create(
            post=self.post,
            visitor_id="visitor_y",
        )
        result = str(view)
        self.assertIn(str(self.post.id), result)

    def test_visitor_id_stored_correctly(self):
        hashed_id = "a" * 32
        view = PostView.objects.create(
            post=self.post,
            visitor_id=hashed_id,
        )
        self.assertEqual(view.visitor_id, hashed_id)

    def test_multiple_views_same_post_allowed(self):
        """Bir post uchun bir nechta PostView bo'lishi mumkin."""
        PostView.objects.create(post=self.post, visitor_id="v1")
        PostView.objects.create(post=self.post, visitor_id="v2")
        PostView.objects.create(post=self.post, visitor_id="v3")
        self.assertEqual(PostView.objects.filter(post=self.post).count(), 3)

    def test_multiple_views_same_visitor_allowed(self):
        """
        Bir visitor bir post ni bir nechta marta ko'ra oladi (model darajasida).
        Deduplication Redis da boshqariladi — model constraint yo'q.
        """
        PostView.objects.create(post=self.post, visitor_id="same-visitor")
        PostView.objects.create(post=self.post, visitor_id="same-visitor")
        count = PostView.objects.filter(
            post=self.post, visitor_id="same-visitor"
        ).count()
        self.assertEqual(count, 2)


# ─────────────────────────────────────────────────────────────────────────────
# PostView model — relationships
# ─────────────────────────────────────────────────────────────────────────────

class TestPostViewRelationships(TestCase):

    def setUp(self):
        self.user = make_user(200000002)
        self.channel = make_channel(self.user, slug="ch-view-rel")
        self.post = make_post(self.channel)

    def test_post_deletion_cascades_to_views(self):
        """Post o'chirilsa uning view lari ham o'chishi kerak."""
        view = PostView.objects.create(post=self.post, visitor_id="del-test")
        view_id = view.id
        self.post.delete()
        self.assertFalse(PostView.objects.filter(id=view_id).exists())

    def test_view_events_related_name(self):
        """view_events related_name orqali murojaat qilish mumkin."""
        PostView.objects.create(post=self.post, visitor_id="rel-1")
        PostView.objects.create(post=self.post, visitor_id="rel-2")
        self.assertEqual(self.post.view_events.count(), 2)

    def test_views_for_different_posts_are_separate(self):
        post2 = make_post(self.channel, title="Post 2")
        PostView.objects.create(post=self.post, visitor_id="v-p1")
        PostView.objects.create(post=post2, visitor_id="v-p2")
        self.assertEqual(self.post.view_events.count(), 1)
        self.assertEqual(post2.view_events.count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# DailyChannelStats model — field defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyChannelStatsDefaults(TestCase):

    def setUp(self):
        self.user = make_user(300000001)
        self.channel = make_channel(self.user, slug="stats-ch")

    def test_id_is_uuid(self):
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        self.assertIsInstance(stats.id, uuid.UUID)

    def test_total_views_zero_by_default(self):
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        self.assertEqual(stats.total_views, 0)

    def test_unique_visitors_zero_by_default(self):
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        self.assertEqual(stats.unique_visitors, 0)

    def test_post_count_zero_by_default(self):
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        self.assertEqual(stats.post_count, 0)

    def test_str_representation(self):
        today = date.today()
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=today,
        )
        result = str(stats)
        self.assertIn(self.channel.slug, result)
        self.assertIn(str(today), result)


# ─────────────────────────────────────────────────────────────────────────────
# DailyChannelStats model — unique constraint
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyChannelStatsConstraints(TestCase):

    def setUp(self):
        self.user = make_user(300000002)
        self.channel = make_channel(self.user, slug="stats-unique")

    def test_unique_constraint_channel_date(self):
        """
        Bir kanal uchun bir kunda faqat bitta stats yozuvi bo'lishi kerak.
        uq_channel_daily_stats constraint.
        """
        today = date.today()
        DailyChannelStats.objects.create(channel=self.channel, date=today)
        with self.assertRaises(IntegrityError):
            DailyChannelStats.objects.create(channel=self.channel, date=today)

    def test_different_dates_allowed_same_channel(self):
        """Bir kanal uchun har xil kunlarda alohida yozuv bo'lishi mumkin."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        DailyChannelStats.objects.create(channel=self.channel, date=today)
        DailyChannelStats.objects.create(channel=self.channel, date=yesterday)
        count = DailyChannelStats.objects.filter(channel=self.channel).count()
        self.assertEqual(count, 2)

    def test_same_date_different_channels_allowed(self):
        """Bir xil kunda turli kanallar uchun alohida yozuv bo'lishi mumkin."""
        user2 = make_user(300000099)
        channel2 = make_channel(user2, slug="stats-ch-2")
        today = date.today()
        DailyChannelStats.objects.create(channel=self.channel, date=today)
        DailyChannelStats.objects.create(channel=channel2, date=today)
        self.assertEqual(
            DailyChannelStats.objects.filter(date=today).count(), 2
        )

    def test_update_or_create_on_duplicate(self):
        """
        update_or_create ikkinchi marta chaqirilganda yangilash kerak.
        Xato bermasligi kerak.
        """
        today = date.today()
        DailyChannelStats.objects.update_or_create(
            channel=self.channel,
            date=today,
            defaults={"total_views": 10, "unique_visitors": 5},
        )
        obj, created = DailyChannelStats.objects.update_or_create(
            channel=self.channel,
            date=today,
            defaults={"total_views": 25, "unique_visitors": 12},
        )
        self.assertFalse(created)
        self.assertEqual(obj.total_views, 25)
        self.assertEqual(obj.unique_visitors, 12)


# ─────────────────────────────────────────────────────────────────────────────
# DailyChannelStats model — relationships
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyChannelStatsRelationships(TestCase):

    def setUp(self):
        self.user = make_user(300000003)
        self.channel = make_channel(self.user, slug="stats-rel")

    def test_channel_deletion_cascades_to_stats(self):
        """Kanal o'chirilsa uning statistikasi ham o'chishi kerak."""
        stats = DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        stats_id = stats.id
        self.channel.delete()
        self.assertFalse(DailyChannelStats.objects.filter(id=stats_id).exists())

    def test_daily_stats_related_name(self):
        """daily_stats related_name orqali murojaat qilish mumkin."""
        DailyChannelStats.objects.create(
            channel=self.channel,
            date=date.today(),
        )
        self.assertEqual(self.channel.daily_stats.count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# DailyChannelStats model — ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyChannelStatsOrdering(TestCase):

    def setUp(self):
        self.user = make_user(300000004)
        self.channel = make_channel(self.user, slug="stats-order")

    def test_default_ordering_newest_date_first(self):
        """Meta.ordering = ["-date"] — eng yangi sana birinchi."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        DailyChannelStats.objects.create(channel=self.channel, date=two_days_ago)
        DailyChannelStats.objects.create(channel=self.channel, date=yesterday)
        DailyChannelStats.objects.create(channel=self.channel, date=today)

        stats = list(DailyChannelStats.objects.filter(channel=self.channel))
        self.assertEqual(stats[0].date, today)
        self.assertEqual(stats[1].date, yesterday)
        self.assertEqual(stats[2].date, two_days_ago)