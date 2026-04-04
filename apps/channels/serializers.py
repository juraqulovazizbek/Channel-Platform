from rest_framework import serializers
from apps.channels.models import Channel
from apps.users.serializers import UserPublicSerializer


class ChannelListSerializer(serializers.ModelSerializer):
    """
    Lightweight representation for list endpoints.
    No nested owner object — just the fields needed for a channel card.
    Avoids N+1 by keeping the serializer flat.
    """

    post_count = serializers.IntegerField(read_only=True)  # Annotated in view queryset

    class Meta:
        model = Channel
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "avatar",
            "is_verified",
            "subscriber_count",
            "post_count",
            "created_at",
        ]
        read_only_fields = fields


class ChannelDetailSerializer(serializers.ModelSerializer):
    """
    Full representation for channel detail page.
    Includes nested owner (public profile only).
    Only used on GET — write operations use ChannelWriteSerializer.
    """

    owner = UserPublicSerializer(read_only=True)
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Channel
        fields = [
            "id",
            "owner",
            "name",
            "slug",
            "description",
            "avatar",
            "banner",
            "is_active",
            "is_verified",
            "telegram_channel_username",
            "subscriber_count",
            "post_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "slug",
            "is_verified",
            "subscriber_count",
            "post_count",
            "created_at",
            "updated_at",
        ]


class ChannelWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for channel create and update.

    Intentionally excludes:
    - owner: set from request.user in the service layer
    - slug: auto-generated from name; intentional renames go through a separate endpoint
    - telegram_channel_id: set via bot verification flow, not direct user input
    - is_verified: admin-only field
    - subscriber_count: synced from Telegram, not user-editable
    """

    class Meta:
        model = Channel
        fields = [
            "name",
            "description",
            "avatar",
            "banner",
        ]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "Channel name must be at least 2 characters."
            )
        return value


class ChannelTelegramLinkSerializer(serializers.Serializer):
    """
    Used when linking a Telegram channel to an existing platform channel.
    The user provides their Telegram channel username; we resolve the ID via bot.
    """

    telegram_channel_username = serializers.CharField(
        max_length=64,
        help_text="Public @username of the Telegram channel (without @).",
    )

    def validate_telegram_channel_username(self, value):
        # Strip @ prefix if the user included it
        return value.lstrip("@").strip()