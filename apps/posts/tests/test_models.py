# apps/posts/tests/test_models.py

import uuid
from django.test import TestCase
from apps.users.models import User
from apps.channels.models import Channel
from apps.posts.models import Post, PostMedia, PostType, PostSource


class TestPostModel(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=999001001,
            first_name="Test",
        )
        self.channel = Channel.objects.create(
            owner=self.user,
            name="Test Channel",
            slug="test-channel",
        )

    def test_post_creation_defaults(self):
        post = Post.objects.create(
            channel=self.channel,
            type=PostType.TEXT,
            content="Hello World",
        )
        self.assertEqual(post.type, PostType.TEXT)
        self.assertEqual(post.source, PostSource.MANUAL)
        self.assertTrue(post.is_published)
        self.assertFalse(post.is_pinned)
        self.assertEqual(post.views_count, 0)

    def test_post_str_representation(self):
        post = Post.objects.create(
            channel=self.channel,
            title="My Post",
            type=PostType.TEXT,
        )
        self.assertIn("text", str(post))
        self.assertIn("My Post", str(post))

    def test_deduplication_constraint(self):
        """Bir xil telegram_message_id ikki marta saqlanmasligi kerak."""
        from django.db import IntegrityError
        Post.objects.create(
            channel=self.channel,
            telegram_message_id=12345,
            type=PostType.TEXT,
        )
        with self.assertRaises(IntegrityError):
            Post.objects.create(
                channel=self.channel,
                telegram_message_id=12345,
                type=PostType.TEXT,
            )

    def test_post_media_requires_file_nullable(self):
        """PostMedia file field null bo'lishi mumkin (Celery yuklaguncha)."""
        post = Post.objects.create(
            channel=self.channel,
            type=PostType.CAROUSEL,
        )
        item = PostMedia.objects.create(
            post=post,
            order=0,
            telegram_file_id="some_file_id",
        )
        # file null — hali yuklanmagan
        self.assertFalse(bool(item.file))