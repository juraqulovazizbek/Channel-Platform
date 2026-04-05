# apps/channels/tests/test_models.py

import uuid
from django.test import TestCase
from django.db import IntegrityError
from apps.users.models import User
from apps.channels.models import Channel


# ─────────────────────────────────────────────────────────────────────────────
# Yordamchi funksiya
# ─────────────────────────────────────────────────────────────────────────────

def make_user(telegram_id, first_name="Owner"):
    return User.objects.create_user(
        telegram_id=telegram_id,
        first_name=first_name,
    )


def make_channel(owner, name="Test Channel", slug="test-channel", **kwargs):
    return Channel.objects.create(
        owner=owner,
        name=name,
        slug=slug,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — field defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelFieldDefaults(TestCase):

    def setUp(self):
        self.user = make_user(100000001)
        self.channel = make_channel(self.user)

    def test_id_is_uuid(self):
        self.assertIsInstance(self.channel.id, uuid.UUID)

    def test_is_active_true_by_default(self):
        self.assertTrue(self.channel.is_active)

    def test_is_verified_false_by_default(self):
        self.assertFalse(self.channel.is_verified)

    def test_subscriber_count_zero_by_default(self):
        self.assertEqual(self.channel.subscriber_count, 0)

    def test_description_blank_by_default(self):
        self.assertEqual(self.channel.description, "")

    def test_telegram_channel_id_null_by_default(self):
        self.assertIsNone(self.channel.telegram_channel_id)

    def test_telegram_channel_username_blank_by_default(self):
        self.assertEqual(self.channel.telegram_channel_username, "")

    def test_avatar_null_by_default(self):
        self.assertFalse(bool(self.channel.avatar))

    def test_banner_null_by_default(self):
        self.assertFalse(bool(self.channel.banner))

    def test_created_at_set_automatically(self):
        self.assertIsNotNone(self.channel.created_at)

    def test_updated_at_set_automatically(self):
        self.assertIsNotNone(self.channel.updated_at)

    def test_owner_is_set_correctly(self):
        self.assertEqual(self.channel.owner, self.user)


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — __str__ va slug
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelStr(TestCase):

    def setUp(self):
        self.user = make_user(100000002)

    def test_str_format(self):
        channel = make_channel(self.user, name="My Blog", slug="my-blog")
        self.assertEqual(str(channel), "My Blog (my-blog)")

    def test_slug_auto_generated_on_create(self):
        """
        Slug berilmasa save() avtomatik yaratishi kerak.
        slugify("Hello World") → "hello-world"
        """
        channel = Channel(owner=self.user, name="Hello World")
        channel.save()
        self.assertEqual(channel.slug, "hello-world")

    def test_slug_not_changed_on_update(self):
        """
        save() chaqirilsa slug o'zgarmasligi kerak (faqat birinchi yaratishda).
        """
        channel = make_channel(self.user, name="Original", slug="original")
        channel.name = "Changed Name"
        channel.save()
        channel.refresh_from_db()
        # Slug o'zgarmaydi — slug bor bo'lsa if not self.slug: bloki ishlamaydi
        self.assertEqual(channel.slug, "original")


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — unique constraints
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelUniqueConstraints(TestCase):

    def setUp(self):
        self.user = make_user(100000003)

    def test_slug_must_be_unique(self):
        """Bir xil slug ikki marta saqlanmasligi kerak."""
        make_channel(self.user, slug="unique-slug")
        with self.assertRaises(IntegrityError):
            make_channel(self.user, slug="unique-slug", name="Other")

    def test_different_slugs_allowed(self):
        """Har xil sluglar bilan bir nechta kanal bo'lishi mumkin."""
        ch1 = make_channel(self.user, name="Ch1", slug="ch-one")
        ch2 = make_channel(self.user, name="Ch2", slug="ch-two")
        self.assertNotEqual(ch1.id, ch2.id)

    def test_telegram_channel_id_unique_across_users(self):
        """
        Bir xil telegram_channel_id ikki foydalanuvchiga biriktirilmasligi kerak.
        """
        user2 = make_user(100000099)
        make_channel(
            self.user, slug="ch-a",
            telegram_channel_id=-1001000000001,
        )
        with self.assertRaises(IntegrityError):
            make_channel(
                user2, slug="ch-b",
                telegram_channel_id=-1001000000001,
            )

    def test_multiple_channels_without_telegram_id_allowed(self):
        """
        telegram_channel_id=NULL bo'lgan bir nechta kanal bo'lishi mumkin.
        NULL != NULL PostgreSQL da, shuning uchun unique constraint ishlamaydi.
        """
        make_channel(self.user, slug="no-tg-1")
        make_channel(self.user, slug="no-tg-2")
        count = Channel.objects.filter(
            owner=self.user, telegram_channel_id__isnull=True
        ).count()
        self.assertEqual(count, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — relationships
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelRelationships(TestCase):

    def setUp(self):
        self.user = make_user(100000004)

    def test_owner_deletion_cascades_to_channels(self):
        """User o'chirilsa uning kanallari ham o'chishi kerak."""
        channel = make_channel(self.user)
        channel_id = channel.id
        self.user.delete()
        self.assertFalse(Channel.objects.filter(id=channel_id).exists())

    def test_one_user_can_own_multiple_channels(self):
        make_channel(self.user, name="C1", slug="c1")
        make_channel(self.user, name="C2", slug="c2")
        make_channel(self.user, name="C3", slug="c3")
        self.assertEqual(self.user.channels.count(), 3)

    def test_channel_posts_related_name(self):
        """posts related_name orqali postlarga murojaat qilish mumkin."""
        channel = make_channel(self.user)
        # Hech qanday post yo'q
        self.assertEqual(channel.posts.count(), 0)

    def test_channel_daily_stats_related_name(self):
        """daily_stats related_name mavjud."""
        channel = make_channel(self.user)
        self.assertEqual(channel.daily_stats.count(), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — is_active (soft delete)
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelSoftDelete(TestCase):

    def setUp(self):
        self.user = make_user(100000005)
        self.channel = make_channel(self.user)

    def test_channel_is_active_true_initially(self):
        self.assertTrue(self.channel.is_active)

    def test_deactivated_channel_not_in_active_queryset(self):
        """is_active=False bo'lgan kanal faol filtrda ko'rinmasligi kerak."""
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])
        active = Channel.objects.filter(is_active=True, owner=self.user)
        self.assertNotIn(self.channel, active)

    def test_deactivated_channel_still_in_db(self):
        """Nofaol kanal bazadan o'chinmasligi kerak."""
        channel_id = self.channel.id
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])
        self.assertTrue(Channel.objects.filter(id=channel_id).exists())


# ─────────────────────────────────────────────────────────────────────────────
# Channel model — ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelOrdering(TestCase):

    def setUp(self):
        self.user = make_user(100000006)

    def test_default_ordering_newest_first(self):
        """
        Meta.ordering = ["-created_at"] — yangi kanal birinchi bo'lishi kerak.
        """
        ch1 = make_channel(self.user, name="First", slug="first")
        ch2 = make_channel(self.user, name="Second", slug="second")
        channels = list(Channel.objects.filter(owner=self.user))
        # ch2 keyinroq yaratilgan — birinchi bo'lishi kerak
        self.assertEqual(channels[0].id, ch2.id)
        self.assertEqual(channels[1].id, ch1.id)