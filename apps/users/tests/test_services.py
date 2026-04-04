import time
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.users.models import User
from services.auth_service import (
    verify_telegram_auth,
    create_or_update_user,
    generate_jwt_tokens,
)


class TestVerifyTelegramAuth(TestCase):

    def _make_valid_payload(self):
        """Real Telegram auth payload strukturasi."""
        return {
            "id": 123456789,
            "first_name": "John",
            "username": "johndoe",
            "auth_date": int(time.time()),
            "hash": "test_hash",
        }

    def test_missing_hash_returns_false(self):
        data = {"id": 123, "auth_date": int(time.time())}
        self.assertFalse(verify_telegram_auth(data))

    def test_old_auth_date_returns_false(self):
        data = {
            "id": 123,
            "auth_date": int(time.time()) - 90000,  # 25 soat oldin
            "hash": "somehash",
        }
        self.assertFalse(verify_telegram_auth(data))

    @patch("services.auth_service.settings")
    def test_invalid_hash_returns_false(self, mock_settings):
        mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
        data = {
            "id": 123,
            "first_name": "John",
            "auth_date": int(time.time()),
            "hash": "invalid_hash_value",
        }
        self.assertFalse(verify_telegram_auth(data))


class TestCreateOrUpdateUser(TestCase):

    def test_creates_new_user(self):
        data = {
            "id": 111222333,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser",
            "photo_url": "",
        }
        user = create_or_update_user(data)
        self.assertEqual(user.telegram_id, 111222333)
        self.assertEqual(user.first_name, "Test")
        self.assertTrue(User.objects.filter(telegram_id=111222333).exists())

    def test_updates_existing_user(self):
        User.objects.create_user(
            telegram_id=444555666,
            first_name="Old Name",
            username="oldusername",
        )
        data = {
            "id": 444555666,
            "first_name": "New Name",
            "username": "newusername",
            "photo_url": "",
        }
        user = create_or_update_user(data)
        self.assertEqual(user.first_name, "New Name")
        self.assertEqual(user.username, "newusername")

    def test_idempotent_same_data(self):
        data = {
            "id": 777888999,
            "first_name": "Same",
            "username": "same",
            "photo_url": "",
        }
        user1 = create_or_update_user(data)
        user2 = create_or_update_user(data)
        self.assertEqual(user1.id, user2.id)
        self.assertEqual(User.objects.filter(telegram_id=777888999).count(), 1)


class TestGenerateJwtTokens(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            telegram_id=123123123,
            first_name="JWT",
        )

    def test_returns_access_and_refresh(self):
        tokens = generate_jwt_tokens(self.user)
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.assertIn("user", tokens)

    def test_user_data_in_response(self):
        tokens = generate_jwt_tokens(self.user)
        self.assertEqual(tokens["user"]["telegram_id"], 123123123)