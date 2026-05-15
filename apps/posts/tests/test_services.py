# apps/posts/tests/test_services.py

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from apps.users.models import User
from apps.channels.models import Channel
from apps.posts.models import Post, PostMedia, PostType, PostSource
from services.post_service import (
    create_post_from_bot,
    create_manual_post,
    get_published_posts,
    _get_channel_by_telegram_id,
    _create_carousel_items,
)


# ─────────────────────────────────────────────────────────────────────────────
# Yordamchi funksiyalar
# ─────────────────────────────────────────────────────────────────────────────

def make_user(telegram_id=999001001, first_name="Owner"):
    return User.objects.create_user(
        telegram_id=telegram_id, first_name=first_name
    )


def make_channel(owner, slug="test-ch", telegram_channel_id=None):
    return Channel.objects.create(
        owner=owner,
        name="Test Channel",
        slug=slug,
        telegram_channel_id=telegram_channel_id,
    )


def make_bot_data(
    channel_id=-1001234567890,
    message_id=42,
    post_type="text",
    content="Hello",
    file_id="",
    source="channel",
):
    """create_post_from_bot uchun standart test ma'lumoti."""
    return {
        "channel_id": channel_id,
        "telegram_message_id": message_id,
        "type": post_type,
        "content": content,
        "title": "",
        "file_id": file_id,
        "source": source,
        "date": int(timezone.now().timestamp()),
        "media_group": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# create_post_from_bot — asosiy holat
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePostFromBot(TestCase):

    def setUp(self):
        self.user = make_user()
        self.channel = make_channel(
            self.user,
            telegram_channel_id=-1001234567890,
        )

    @patch("services.post_service.process_media_file")
    def test_creates_text_post_successfully(self, mock_task):
        """Oddiy text post yaratilishi kerak."""
        data = make_bot_data()
        post = create_post_from_bot(data)

        self.assertIsNotNone(post)
        self.assertEqual(post.type, PostType.TEXT)
        self.assertEqual(post.content, "Hello")
        self.assertEqual(post.source, PostSource.CHANNEL)
        self.assertTrue(post.is_published)
        self.assertEqual(post.channel, self.channel)

    @patch("services.post_service.process_media_file")
    def test_post_saved_to_database(self, mock_task):
        """Post bazaga saqlanishi kerak."""
        data = make_bot_data(message_id=100)
        post = create_post_from_bot(data)
        self.assertTrue(Post.objects.filter(id=post.id).exists())

    @patch("services.post_service.process_media_file")
    def test_telegram_message_id_saved(self, mock_task):
        """telegram_message_id saqlangan bo'lishi kerak."""
        data = make_bot_data(message_id=77)
        post = create_post_from_bot(data)
        self.assertEqual(post.telegram_message_id, 77)

    def test_unknown_channel_returns_none(self):
        """Noma'lum telegram_channel_id bo'lsa None qaytarishi kerak."""
        data = make_bot_data(channel_id=-9999999999)
        result = create_post_from_bot(data)
        self.assertIsNone(result)

    def test_unknown_channel_creates_no_post(self):
        """Noma'lum kanal uchun post yaratilmasligi kerak."""
        initial_count = Post.objects.count()
        data = make_bot_data(channel_id=-9999999999)
        create_post_from_bot(data)
        self.assertEqual(Post.objects.count(), initial_count)

    @patch("services.post_service.process_media_file")
    def test_inactive_channel_returns_none(self, mock_task):
        """Nofaol kanal uchun post yaratilmasligi kerak."""
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])
        data = make_bot_data()
        result = create_post_from_bot(data)
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# create_post_from_bot — deduplication (idempotency)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePostFromBotDeduplication(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999001002)
        self.channel = make_channel(
            self.user,
            slug="dedup-ch",
            telegram_channel_id=-1001111111111,
        )

    @patch("services.post_service.process_media_file")
    def test_duplicate_message_id_returns_none(self, mock_task):
        """
        Bir xil telegram_message_id ikkinchi kelganda None qaytarishi kerak.
        Bu webhook retry holati.
        """
        data = make_bot_data(channel_id=-1001111111111, message_id=999)
        first = create_post_from_bot(data)
        second = create_post_from_bot(data)

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    @patch("services.post_service.process_media_file")
    def test_duplicate_does_not_create_extra_post(self, mock_task):
        """Duplicate webhook faqat 1 ta post yaratishi kerak."""
        data = make_bot_data(channel_id=-1001111111111, message_id=888)
        create_post_from_bot(data)
        create_post_from_bot(data)
        count = Post.objects.filter(
            channel=self.channel,
            telegram_message_id=888,
        ).count()
        self.assertEqual(count, 1)

    @patch("services.post_service.process_media_file")
    def test_different_message_ids_create_separate_posts(self, mock_task):
        """Har xil message_id lar alohida post yaratishi kerak."""
        data1 = make_bot_data(channel_id=-1001111111111, message_id=101)
        data2 = make_bot_data(channel_id=-1001111111111, message_id=102)
        post1 = create_post_from_bot(data1)
        post2 = create_post_from_bot(data2)

        self.assertIsNotNone(post1)
        self.assertIsNotNone(post2)
        self.assertNotEqual(post1.id, post2.id)


# ─────────────────────────────────────────────────────────────────────────────
# create_post_from_bot — media va Celery task dispatch
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePostFromBotMediaDispatch(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999001003)
        self.channel = make_channel(
            self.user,
            slug="media-ch",
            telegram_channel_id=-1002222222222,
        )

    @patch("services.post_service.process_media_file")
    def test_media_task_dispatched_when_file_id_present(self, mock_task):
        """
        file_id mavjud bo'lsa process_media_file.delay() chaqirilishi kerak.
        """
        data = make_bot_data(
            channel_id=-1002222222222,
            message_id=200,
            post_type="image",
            file_id="AgACAgIAAxkB",
        )
        post = create_post_from_bot(data)
        self.assertIsNotNone(post)
        mock_task.delay.assert_called_once_with(str(post.id), "AgACAgIAAxkB")

    @patch("services.post_service.process_media_file")
    def test_media_task_not_dispatched_for_text_post(self, mock_task):
        """file_id bo'lmasa (text post) Celery task chaqirilmasligi kerak."""
        data = make_bot_data(
            channel_id=-1002222222222,
            message_id=201,
            post_type="text",
            file_id="",
        )
        create_post_from_bot(data)
        mock_task.delay.assert_not_called()

    @patch("services.post_service.process_media_file")
    def test_post_type_image_saved_correctly(self, mock_task):
        data = make_bot_data(
            channel_id=-1002222222222,
            message_id=202,
            post_type="image",
            file_id="some_file_id",
        )
        post = create_post_from_bot(data)
        self.assertEqual(post.type, PostType.IMAGE)
        self.assertEqual(post.telegram_file_id, "some_file_id")

    @patch("services.post_service.process_media_file")
    def test_source_bot_saved_correctly(self, mock_task):
        """source='bot' bo'lsa PostSource.BOT saqlanishi kerak."""
        data = make_bot_data(
            channel_id=-1002222222222,
            message_id=203,
            source="bot",
        )
        post = create_post_from_bot(data)
        self.assertEqual(post.source, PostSource.BOT)


# ─────────────────────────────────────────────────────────────────────────────
# create_post_from_bot — carousel
# ─────────────────────────────────────────────────────────────────────────────

class TestCreatePostFromBotCarousel(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999001004)
        self.channel = make_channel(
            self.user,
            slug="carousel-ch",
            telegram_channel_id=-1003333333333,
        )

    @patch("services.post_service.process_media_file")
    def test_carousel_creates_post_media_items(self, mock_task):
        """Carousel post uchun PostMedia yozuvlari yaratilishi kerak."""
        data = make_bot_data(
            channel_id=-1003333333333,
            message_id=300,
            post_type="carousel",
        )
        data["media_group"] = [
            {"file_id": "file_1"},
            {"file_id": "file_2"},
            {"file_id": "file_3"},
        ]
        post = create_post_from_bot(data)

        self.assertIsNotNone(post)
        self.assertEqual(post.type, PostType.CAROUSEL)
        items = PostMedia.objects.filter(post=post).order_by("order")
        self.assertEqual(items.count(), 3)
        self.assertEqual(items[0].telegram_file_id, "file_1")
        self.assertEqual(items[1].telegram_file_id, "file_2")
        self.assertEqual(items[2].telegram_file_id, "file_3")

    @patch("services.post_service.process_media_file")
    def test_carousel_items_have_correct_order(self, mock_task):
        """Carousel item lari to'g'ri tartibda saqlanishi kerak."""
        data = make_bot_data(
            channel_id=-1003333333333,
            message_id=301,
            post_type="carousel",
        )
        data["media_group"] = [{"file_id": "a"}, {"file_id": "b"}]
        post = create_post_from_bot(data)
        items = PostMedia.objects.filter(post=post).order_by("order")
        self.assertEqual(items[0].order, 0)
        self.assertEqual(items[1].order, 1)

    @patch("services.post_service.process_media_file")
    def test_carousel_empty_media_group_creates_no_items(self, mock_task):
        """media_group bo'sh bo'lsa PostMedia yaratilmasligi kerak."""
        data = make_bot_data(
            channel_id=-1003333333333,
            message_id=302,
            post_type="carousel",
        )
        data["media_group"] = []
        post = create_post_from_bot(data)
        self.assertEqual(PostMedia.objects.filter(post=post).count(), 0)


# ─────────────────────────────────────────────────────────────────────────────
# create_manual_post
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateManualPost(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999002001)
        self.channel = make_channel(self.user, slug="manual-ch")

    def test_creates_text_post(self):
        """Oddiy text post to'g'ri yaratilishi kerak."""
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "title": "My Title",
            "content": "My Content",
            "is_published": True,
            "is_pinned": False,
        }
        post = create_manual_post(self.user, validated_data)

        self.assertIsNotNone(post)
        self.assertEqual(post.source, PostSource.MANUAL)
        self.assertEqual(post.title, "My Title")
        self.assertEqual(post.content, "My Content")
        self.assertTrue(post.is_published)

    def test_source_is_always_manual(self):
        """Manual post source MANUAL bo'lishi kerak."""
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "Text",
            "is_published": True,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertEqual(post.source, PostSource.MANUAL)

    def test_published_at_set_when_is_published_true(self):
        """is_published=True bo'lsa published_at o'rnatilishi kerak."""
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "Published",
            "is_published": True,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertIsNotNone(post.published_at)

    def test_published_at_none_when_is_published_false(self):
        """is_published=False bo'lsa published_at None bo'lishi kerak."""
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "Draft",
            "is_published": False,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertIsNone(post.published_at)

    def test_inactive_channel_raises_value_error(self):
        """Nofaol kanal uchun ValueError chiqishi kerak."""
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])

        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "Blocked",
            "is_published": True,
        }
        with self.assertRaises(ValueError) as ctx:
            create_manual_post(self.user, validated_data)

        self.assertIn("inactive", str(ctx.exception).lower())

    def test_pinned_post_saved_correctly(self):
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "Pinned Post",
            "is_published": True,
            "is_pinned": True,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertTrue(post.is_pinned)

    def test_post_saved_to_database(self):
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "DB check",
            "is_published": True,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertTrue(Post.objects.filter(id=post.id).exists())

    def test_telegram_message_id_not_set(self):
        """Manual post da telegram_message_id bo'lmasligi kerak."""
        validated_data = {
            "channel": self.channel,
            "type": PostType.TEXT,
            "content": "No TG id",
            "is_published": True,
        }
        post = create_manual_post(self.user, validated_data)
        self.assertIsNone(post.telegram_message_id)


# ─────────────────────────────────────────────────────────────────────────────
# get_published_posts
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPublishedPosts(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999003001)
        self.channel = make_channel(self.user, slug="pub-ch")

    def _make_post(self, title, is_published=True, is_pinned=False, post_type=PostType.TEXT):
        return Post.objects.create(
            channel=self.channel,
            type=post_type,
            title=title,
            content="Content",
            is_published=is_published,
            is_pinned=is_pinned,
        )

    def test_returns_only_published_posts(self):
        """Faqat is_published=True postlar qaytarilishi kerak."""
        pub = self._make_post("Published", is_published=True)
        self._make_post("Draft", is_published=False)

        qs = get_published_posts(self.channel)
        ids = list(qs.values_list("id", flat=True))
        self.assertIn(pub.id, ids)
        self.assertEqual(len(ids), 1)

    def test_draft_posts_excluded(self):
        self._make_post("Draft 1", is_published=False)
        self._make_post("Draft 2", is_published=False)
        qs = get_published_posts(self.channel)
        self.assertEqual(qs.count(), 0)

    def test_pinned_posts_appear_first(self):
        """is_pinned=True postlar birinchi bo'lishi kerak."""
        normal = self._make_post("Normal")
        pinned = self._make_post("Pinned", is_pinned=True)

        qs = list(get_published_posts(self.channel))
        self.assertEqual(qs[0].id, pinned.id)
        self.assertEqual(qs[1].id, normal.id)

    def test_filter_by_post_type_text(self):
        """post_type='text' faqat text postlarni qaytarishi kerak."""
        text_post = self._make_post("Text Post")
        self._make_post("Image Post", post_type=PostType.IMAGE)

        text_qs = get_published_posts(self.channel, post_type="text")
        self.assertEqual(text_qs.count(), 1)
        self.assertEqual(text_qs.first().id, text_post.id)

    def test_filter_by_post_type_image(self):
        """post_type='image' faqat image postlarni qaytarishi kerak."""
        self._make_post("Text Post")
        image_post = self._make_post("Image Post", post_type=PostType.IMAGE)

        image_qs = get_published_posts(self.channel, post_type="image")
        self.assertEqual(image_qs.count(), 1)
        self.assertEqual(image_qs.first().id, image_post.id)

    def test_no_type_filter_returns_all_published(self):
        """post_type=None barcha published postlarni qaytarishi kerak."""
        self._make_post("T1")
        self._make_post("I1", post_type=PostType.IMAGE)
        qs = get_published_posts(self.channel)
        self.assertEqual(qs.count(), 2)

    def test_only_returns_posts_for_given_channel(self):
        """Boshqa kanaldagi postlar qaytarilmasligi kerak."""
        other_user = make_user(telegram_id=999003099)
        other_channel = make_channel(other_user, slug="other-ch")
        self._make_post("My Post")
        Post.objects.create(
            channel=other_channel,
            type=PostType.TEXT,
            title="Other Post",
            content="",
            is_published=True,
        )
        qs = get_published_posts(self.channel)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().title, "My Post")

    def test_queryset_has_select_related_channel(self):
        """
        select_related('channel') bo'lishi kerak — N+1 oldini olish uchun.
        Post.channel ga murojaat qo'shimcha query chaqirmasligi kerak.
        """
        self._make_post("With Channel")
        qs = get_published_posts(self.channel)
        # select_related ishlasa — channel allaqachon yuklangan
        post = qs.first()
        with self.assertNumQueries(0):
            _ = post.channel.slug


# ─────────────────────────────────────────────────────────────────────────────
# _get_channel_by_telegram_id (internal helper)
# ─────────────────────────────────────────────────────────────────────────────

class TestGetChannelByTelegramId(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999004001)

    def test_returns_channel_when_found(self):
        channel = make_channel(
            self.user,
            slug="tg-ch",
            telegram_channel_id=-1009999999999,
        )
        found = _get_channel_by_telegram_id(-1009999999999)
        self.assertEqual(found.id, channel.id)

    def test_returns_none_when_not_found(self):
        result = _get_channel_by_telegram_id(-1008888888888)
        self.assertIsNone(result)

    def test_returns_none_for_inactive_channel(self):
        """Nofaol kanal topilmasligi kerak."""
        channel = make_channel(
            self.user,
            slug="inactive-tg",
            telegram_channel_id=-1007777777777,
        )
        channel.is_active = False
        channel.save(update_fields=["is_active"])
        result = _get_channel_by_telegram_id(-1007777777777)
        self.assertIsNone(result)


# ─────────────────────────────────────────────────────────────────────────────
# _create_carousel_items (internal helper)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateCarouselItems(TestCase):

    def setUp(self):
        self.user = make_user(telegram_id=999005001)
        self.channel = make_channel(self.user, slug="carousel-helper")
        self.post = Post.objects.create(
            channel=self.channel,
            type=PostType.CAROUSEL,
            content="",
        )

    def test_creates_items_with_correct_order(self):
        media_items = [
            {"file_id": "f1"},
            {"file_id": "f2"},
            {"file_id": "f3"},
        ]
        _create_carousel_items(self.post, media_items)
        items = PostMedia.objects.filter(post=self.post).order_by("order")
        self.assertEqual(items.count(), 3)
        self.assertEqual(items[0].order, 0)
        self.assertEqual(items[1].order, 1)
        self.assertEqual(items[2].order, 2)

    def test_creates_items_with_correct_file_ids(self):
        media_items = [{"file_id": "abc"}, {"file_id": "xyz"}]
        _create_carousel_items(self.post, media_items)
        items = PostMedia.objects.filter(post=self.post).order_by("order")
        self.assertEqual(items[0].telegram_file_id, "abc")
        self.assertEqual(items[1].telegram_file_id, "xyz")

    def test_empty_list_creates_nothing(self):
        _create_carousel_items(self.post, [])
        self.assertEqual(PostMedia.objects.filter(post=self.post).count(), 0)

    def test_missing_file_id_defaults_to_empty_string(self):
        """file_id bo'lmasa bo'sh string saqlanishi kerak."""
        media_items = [{"something": "else"}]
        _create_carousel_items(self.post, media_items)
        item = PostMedia.objects.get(post=self.post)
        self.assertEqual(item.telegram_file_id, "")