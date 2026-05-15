# apps/users/tests/test_models.py

import uuid
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone
from apps.users.models import User


# ─────────────────────────────────────────────────────────────────────────────
# User model — field defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestUserFieldDefaults(TestCase):
    """
    User yaratilganda barcha default qiymatlar to'g'ri o'rnatilishini tekshiradi.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=100000001,
            first_name="Alisher",
        )

    def test_id_is_uuid(self):
        """Primary key UUID formatida bo'lishi kerak."""
        self.assertIsInstance(self.user.id, uuid.UUID)

    def test_is_active_true_by_default(self):
        """Yangi user faol bo'lishi kerak."""
        self.assertTrue(self.user.is_active)

    def test_is_staff_false_by_default(self):
        """Yangi user staff bo'lmasligi kerak."""
        self.assertFalse(self.user.is_staff)

    def test_is_superuser_false_by_default(self):
        """Yangi user superuser bo'lmasligi kerak."""
        self.assertFalse(self.user.is_superuser)

    def test_last_name_blank_by_default(self):
        self.assertEqual(self.user.last_name, "")

    def test_username_blank_by_default(self):
        self.assertEqual(self.user.username, "")

    def test_phone_number_blank_by_default(self):
        self.assertEqual(self.user.phone_number, "")

    def test_profile_photo_blank_by_default(self):
        self.assertEqual(self.user.profile_photo, "")

    def test_bio_blank_by_default(self):
        self.assertEqual(self.user.bio, "")

    def test_date_joined_set_automatically(self):
        """date_joined avtomatik o'rnatilishi kerak."""
        self.assertIsNotNone(self.user.date_joined)
        self.assertLessEqual(self.user.date_joined, timezone.now())

    def test_last_login_null_by_default(self):
        """Birinchi marta login qilinmagan user uchun last_login null."""
        self.assertIsNone(self.user.last_login)

    def test_password_unusable_by_default(self):
        """
        Telegram autentifikatsiyasi ishlatiladi — parol bo'lmasligi kerak.
        set_unusable_password() chaqirilganini tekshiramiz.
        """
        self.assertFalse(self.user.has_usable_password())


# ─────────────────────────────────────────────────────────────────────────────
# User model — properties
# ─────────────────────────────────────────────────────────────────────────────

class TestUserProperties(TestCase):
    """
    User modelining property metodlarini tekshiradi.
    """

    def test_full_name_first_and_last(self):
        user = User.objects.create_user(
            telegram_id=200000001,
            first_name="Jasur",
            last_name="Toshmatov",
        )
        self.assertEqual(user.full_name, "Jasur Toshmatov")

    def test_full_name_only_first(self):
        """last_name bo'lmasa faqat first_name qaytaradi."""
        user = User.objects.create_user(
            telegram_id=200000002,
            first_name="Malika",
        )
        self.assertEqual(user.full_name, "Malika")

    def test_full_name_strips_whitespace(self):
        """last_name bo'sh string bo'lsa ortiqcha bo'shliq bo'lmasligi kerak."""
        user = User.objects.create_user(
            telegram_id=200000003,
            first_name="Sarvar",
            last_name="",
        )
        self.assertEqual(user.full_name, "Sarvar")

    def test_display_name_uses_full_name_when_available(self):
        user = User.objects.create_user(
            telegram_id=200000004,
            first_name="Dilnoza",
            last_name="Karimova",
            username="dilnoza_k",
        )
        # full_name mavjud — uni qaytarishi kerak
        self.assertEqual(user.display_name, "Dilnoza Karimova")

    def test_display_name_falls_back_to_username(self):
        """full_name bo'lmasa username ishlatiladi."""
        user = User.objects.create_user(
            telegram_id=200000005,
            first_name="",
            username="botuser99",
        )
        user.first_name = ""
        user.save(update_fields=["first_name"])
        self.assertEqual(user.display_name, "botuser99")

    def test_display_name_falls_back_to_telegram_id(self):
        """Hech narsa bo'lmasa telegram_id string qaytaradi."""
        user = User.objects.create_user(
            telegram_id=200000006,
            first_name="",
        )
        user.first_name = ""
        user.save(update_fields=["first_name"])
        self.assertEqual(user.display_name, "200000006")


# ─────────────────────────────────────────────────────────────────────────────
# User model — __str__
# ─────────────────────────────────────────────────────────────────────────────

class TestUserStr(TestCase):

    def test_str_with_username(self):
        user = User.objects.create_user(
            telegram_id=300000001,
            first_name="Test",
            username="myusername",
        )
        self.assertEqual(str(user), "@myusername")

    def test_str_without_username(self):
        """Username bo'lmasa telegram_id ishlatiladi."""
        user = User.objects.create_user(
            telegram_id=300000002,
            first_name="Test",
        )
        self.assertEqual(str(user), "tg:300000002")


# ─────────────────────────────────────────────────────────────────────────────
# User model — uniqueness va constraints
# ─────────────────────────────────────────────────────────────────────────────

class TestUserUniqueness(TestCase):

    def test_telegram_id_unique(self):
        """Bir xil telegram_id ikki marta saqlanmasligi kerak."""
        User.objects.create_user(telegram_id=400000001, first_name="First")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(telegram_id=400000001, first_name="Second")

    def test_different_telegram_ids_allowed(self):
        """Har xil telegram_id lar uchun bir nechta user bo'lishi mumkin."""
        u1 = User.objects.create_user(telegram_id=400000002, first_name="One")
        u2 = User.objects.create_user(telegram_id=400000003, first_name="Two")
        self.assertNotEqual(u1.id, u2.id)

    def test_username_not_unique_allows_duplicates(self):
        """
        Username unique emas (blank bo'lishi mumkin, Telegram da ham o'zgaradi).
        Bir nechta user bir xil username ga ega bo'la oladi.
        """
        User.objects.create_user(
            telegram_id=400000004, first_name="A", username="shared"
        )
        # Bu IntegrityError bermasligi kerak
        User.objects.create_user(
            telegram_id=400000005, first_name="B", username="shared"
        )
        count = User.objects.filter(username="shared").count()
        self.assertEqual(count, 2)


# ─────────────────────────────────────────────────────────────────────────────
# UserManager
# ─────────────────────────────────────────────────────────────────────────────

class TestUserManager(TestCase):

    def test_create_user_requires_telegram_id(self):
        """telegram_id bo'lmasa ValueError chiqishi kerak."""
        with self.assertRaises(ValueError):
            User.objects.create_user(telegram_id=None, first_name="Test")

    def test_create_user_zero_telegram_id_raises(self):
        """0 ham falsy qiymat — ValueError chiqishi kerak."""
        with self.assertRaises(ValueError):
            User.objects.create_user(telegram_id=0, first_name="Test")

    def test_create_superuser_sets_staff_and_superuser(self):
        superuser = User.objects.create_superuser(
            telegram_id=500000001, first_name="Admin"
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)

    def test_create_user_stores_extra_fields(self):
        user = User.objects.create_user(
            telegram_id=500000002,
            first_name="Bonus",
            username="bonususer",
            phone_number="+998901234567",
        )
        self.assertEqual(user.username, "bonususer")
        self.assertEqual(user.phone_number, "+998901234567")

    def test_create_user_is_not_staff_by_default(self):
        user = User.objects.create_user(
            telegram_id=500000003, first_name="Plain"
        )
        self.assertFalse(user.is_staff)

    def test_create_user_saves_to_db(self):
        User.objects.create_user(telegram_id=500000004, first_name="Saved")
        self.assertTrue(User.objects.filter(telegram_id=500000004).exists())