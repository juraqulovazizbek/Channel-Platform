# apps/posts/serializers.py

from rest_framework import serializers
from apps.posts.models import Post, PostMedia, PostType


class PostMediaSerializer(serializers.ModelSerializer):
    """
    Carousel item serializer.
    Used nested inside PostDetailSerializer for CAROUSEL type posts.
    """

    class Meta:
        model = PostMedia
        fields = [
            "id",
            "file",
            "thumbnail",
            "order",
        ]
        read_only_fields = ["id"]


class PostListSerializer(serializers.ModelSerializer):
    """
    Compact representation for feed/list views.
    Deliberately omits:
    - Full content (use detail endpoint)
    - carousel_items (expensive nested query)
    - Channel object (caller already knows the channel in most list contexts)
    """

    channel_slug = serializers.SlugRelatedField(
        source="channel",
        slug_field="slug",
        read_only=True,
    )

    class Meta:
        model = Post
        fields = [
            "id",
            "channel_slug",
            "type",
            "title",
            "thumbnail",
            "views_count",
            "is_pinned",
            "source",
            "created_at",
            "published_at",
        ]
        read_only_fields = fields


class PostDetailSerializer(serializers.ModelSerializer):
    """
    Full post representation.
    Includes channel summary and carousel items (prefetched in view).
    carousel_items is only populated when type == CAROUSEL.
    """

    # Import here to avoid circular import at module level.
    # channels.serializers → posts.serializers davriy import bo'lishi mumkin.
    # Bu lazy import pattern — class darajasida emas, __init__ ichida.
    channel = serializers.SerializerMethodField()
    carousel_items = PostMediaSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "channel",
            "type",
            "title",
            "content",
            "media_file",
            "thumbnail",
            "carousel_items",
            "telegram_message_id",
            "views_count",
            "source",
            "is_published",
            "is_pinned",
            "created_at",
            "updated_at",
            "published_at",
        ]
        read_only_fields = [
            "id",
            "channel",
            "telegram_message_id",
            "views_count",
            "source",
            "created_at",
            "updated_at",
        ]

    def get_channel(self, obj):
        from apps.channels.serializers import ChannelListSerializer
        return ChannelListSerializer(obj.channel).data

    def to_representation(self, instance):
        """
        Omit carousel_items from the response entirely
        when the post type is not CAROUSEL.
        Keeps the API response clean for consumers.
        """
        data = super().to_representation(instance)
        if instance.type != PostType.CAROUSEL:
            data.pop("carousel_items", None)
        return data


class PostWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for manual post creation via dashboard.

    channel is passed as a UUID and validated against the requesting
    user's owned channels in the validate_channel method.

    MUHIM: __import__() anti-pattern ishlatilmaydi.
    Circular import muammosini hal qilish uchun PrimaryKeyRelatedField
    queryset ni get_queryset() orqali lazy yuklash ishlatiladi.
    """

    channel = serializers.PrimaryKeyRelatedField(
        # queryset=None — get_queryset() orqali o'rnatiladi
        queryset=None,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Circular importni oldini olish: Channel ni bu yerda import qilamiz
        from apps.channels.models import Channel
        self.fields["channel"].queryset = Channel.objects.all()

    class Meta:
        model = Post
        fields = [
            "channel",
            "type",
            "title",
            "content",
            "media_file",
            "is_published",
            "is_pinned",
            "published_at",
        ]

    def validate_channel(self, channel):
        """
        Ensure the requesting user owns this channel.
        request is injected via serializer context in the view:
            serializer = PostWriteSerializer(data=request.data, context={'request': request})
        """
        request = self.context.get("request")
        if request and channel.owner != request.user:
            raise serializers.ValidationError(
                "You do not own this channel."
            )
        return channel

    def validate(self, attrs):
        post_type = attrs.get("type")
        media_file = attrs.get("media_file")
        content = attrs.get("content", "")

        # TEXT posts must have content
        if post_type == PostType.TEXT and not content.strip():
            raise serializers.ValidationError(
                {"content": "Text posts require content."}
            )

        # Media posts must have a file
        if post_type in (PostType.IMAGE, PostType.VIDEO, PostType.REEL):
            if not media_file:
                raise serializers.ValidationError(
                    {"media_file": f"{post_type} posts require a media file."}
                )

        return attrs


class PostCarouselItemWriteSerializer(serializers.ModelSerializer):
    """
    Used when adding or updating individual carousel items.
    Separate from PostWriteSerializer to keep concerns clean.
    """

    class Meta:
        model = PostMedia
        fields = ["file", "order"]

    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Order must be 0 or greater.")
        return value