# apps/channels/tests/test_services.py

from django.test import TestCase
from apps.users.models import User
from apps.channels.models import Channel
from services.channel_service import (
    create_channel,
    update_channel,
    deactivate_channel,
    _resolve_unique_slug,
)


class TestCreateChannel(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=111000111,
            first_name="Owner",
        )

    def test_creates_channel_with_slug(self):
        channel = create_channel(
            user=self.user,
            validated_data={"name": "My Channel", "description": ""},
        )
        self.assertEqual(channel.name, "My Channel")
        self.assertEqual(channel.slug, "my-channel")
        self.assertEqual(channel.owner, self.user)

    def test_slug_collision_resolved(self):
        Channel.objects.create(
            owner=self.user, name="Tech", slug="tech"
        )
        channel = create_channel(
            user=self.user,
            validated_data={"name": "Tech", "description": ""},
        )
        self.assertEqual(channel.slug, "tech-2")

    def test_resolve_unique_slug_increments(self):
        Channel.objects.create(
            owner=self.user, name="X", slug="x"
        )
        Channel.objects.create(
            owner=self.user, name="X2", slug="x-2"
        )
        slug = _resolve_unique_slug("x")
        self.assertEqual(slug, "x-3")


class TestUpdateChannel(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=222000222, first_name="Owner"
        )
        self.channel = Channel.objects.create(
            owner=self.user, name="Old Name", slug="old-name"
        )

    def test_updates_name(self):
        updated = update_channel(
            self.channel, {"name": "New Name"}
        )
        self.assertEqual(updated.name, "New Name")
        self.assertEqual(updated.slug, "old-name")  # slug o'zgarmaydi

    def test_no_change_no_save(self):
        """O'zgarish bo'lmasa save chaqirilmasligi kerak."""
        original_updated = self.channel.updated_at
        update_channel(self.channel, {"name": "Old Name"})
        self.channel.refresh_from_db()
        self.assertEqual(self.channel.updated_at, original_updated)


class TestDeactivateChannel(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=333000333, first_name="Owner"
        )
        self.channel = Channel.objects.create(
            owner=self.user, name="Active", slug="active"
        )

    def test_deactivates_channel(self):
        deactivate_channel(self.channel)
        self.channel.refresh_from_db()
        self.assertFalse(self.channel.is_active)

    def test_idempotent_on_already_inactive(self):
        """Allaqachon nofaol kanalda xato bo'lmasligi kerak."""
        self.channel.is_active = False
        self.channel.save()
        deactivate_channel(self.channel)  # xato bo'lmasligi kerak
        self.channel.refresh_from_db()
        self.assertFalse(self.channel.is_active)