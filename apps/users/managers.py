from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom manager for Telegram-based authentication.

    Normal users authenticate via Telegram.
    Superusers/admins authenticate with password.
    """

    def create_user(self, telegram_id, first_name="", password=None, **extra_fields):
        """
        Create regular Telegram user.
        """

        if not telegram_id:
            raise ValueError("telegram_id is required")

        user = self.model(
            telegram_id=telegram_id,
            first_name=first_name,
            **extra_fields,
        )

        # Telegram users usually don't have passwords.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, first_name="Admin", password=None, **extra_fields):
        """
        Create Django admin superuser.
        """

        if not password:
            raise ValueError("Superuser must have a password")

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self.create_user(
            telegram_id=telegram_id,
            first_name=first_name,
            password=password,
            **extra_fields,
        )