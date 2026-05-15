import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.users.models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Fires after every User save.
    Used for first-time setup logic without polluting the service layer.
    """
    if created:
        logger.info(
            "New user registered: telegram_id=%d username=%s",
            instance.telegram_id,
            instance.username or "(none)",
        )