"""
BaseHandler — shared state and helpers for all bot handlers.

Every handler receives a normalized dict (output of
telegram_service.parse_webhook_update). BaseHandler stores
it and exposes commonly accessed fields as properties.
"""


class BaseHandler:

    def __init__(self, normalized: dict):
        self.normalized = normalized

    @property
    def update_id(self):
        return self.normalized.get("update_id", "unknown")

    @property
    def chat_id(self):
        return self.normalized.get("chat_id")

    @property
    def message_id(self):
        return self.normalized.get("message_id")

    @property
    def post_type(self):
        return self.normalized.get("post_type", "text")

    def handle(self) -> None:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement handle()"
        )