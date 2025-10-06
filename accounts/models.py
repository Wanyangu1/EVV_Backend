from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from accounts.managers import UserManager


class User(AbstractUser):
    # Remove fields from AbstractUser that you don't need
    first_name = None
    last_name = None
    username = None

    # Custom fields
    name = models.CharField(max_length=128, null=True, blank=True)
    email = models.EmailField(null=False, blank=False, max_length=128, unique=True)
    phone = models.CharField(max_length=255, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    # Override groups and user_permissions fields to avoid clashes
    groups = models.ManyToManyField(
        Group,
        related_name="custom_user_groups",  # Custom related name
        blank=True
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="custom_user_permissions",  # Custom related name
        blank=True
    )

    # Configure fields for authentication
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    # Custom manager
    objects = UserManager()

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.user.name
