from rest_framework import serializers
from apps.users.models import User


class UserPublicSerializer(serializers.ModelSerializer):
    """
    Safe read-only representation of a user.
    Exposed to other users — e.g. channel owner profile on a channel page.
    Never includes phone_number or internal flags.
    """

    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "display_name",
            "profile_photo",
            "bio",
        ]
        read_only_fields = fields


class UserPrivateSerializer(serializers.ModelSerializer):
    """
    Full representation for the authenticated user's own profile.
    Includes sensitive fields like phone_number and internal state.
    Only returned to the user themselves — never to third parties.
    """

    full_name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "telegram_id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "display_name",
            "phone_number",
            "profile_photo",
            "bio",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "telegram_id",
            "is_active",
            "date_joined",
            "last_login",
            "full_name",
            "display_name",
        ]


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Restricted write serializer — only fields the user can change themselves.
    telegram_id is Telegram's data; we don't let users overwrite it here.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "bio"]

    def validate_first_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("First name cannot be blank.")
        return value


class TelegramAuthSerializer(serializers.Serializer):
    """
    Validates the payload sent by Telegram Login Widget or bot auth flow.

    Telegram sends a dict of user fields + a hash we must verify server-side.
    We validate structure here; cryptographic hash check happens in auth_service.
    """

    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    username = serializers.CharField(required=False, allow_blank=True, default="")
    photo_url = serializers.URLField(required=False, allow_blank=True, default="")
    auth_date = serializers.IntegerField(
        help_text="Unix timestamp. We reject payloads older than 24 hours.",
    )
    hash = serializers.CharField(
        help_text="HMAC-SHA256 signature from Telegram. Verified in auth_service.",
    )

    def validate_auth_date(self, value):
        """
        Reject stale auth payloads.
        Telegram's own recommendation: reject if older than 1 day.
        This prevents replay attacks using captured login data.
        """
        import time
        max_age_seconds = 86400  # 24 hours
        if time.time() - value > max_age_seconds:
            raise serializers.ValidationError(
                "Auth data is expired. Please log in again."
            )
        return value