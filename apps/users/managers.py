from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Manager for telegram_id-based auth.
    Email and password are not part of our auth flow,
    but Django's admin still needs create_superuser.
    """

    def create_user(self, telegram_id, first_name="", **extra_fields):
        if not telegram_id:
            raise ValueError("telegram_id is required")
        user = self.model(
            telegram_id=telegram_id,
            first_name=first_name,
            **extra_fields,
        )
        # No password for normal Telegram users.
        # They authenticate via Telegram — not a password.
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, first_name="", **extra_fields):
        """Only used for Django admin access during development."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(telegram_id, first_name, **extra_fields)