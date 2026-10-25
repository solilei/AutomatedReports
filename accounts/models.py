from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        INSTRUCTOR = "instructor", "Instructor"

    class Source(models.TextChoices):
        LOCAL = "local", "Local"
        MICROSOFT = "microsoft", "Microsoft"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.INSTRUCTOR)
    auth_source = models.CharField(max_length=20, choices=Source.choices, default=Source.LOCAL)
    full_name = models.CharField(max_length=150, blank=True)
    is_approved = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=32, blank=True, default="")
    totp_confirmed = models.BooleanField(default=False)
    entra_object_id = models.CharField(max_length=36, unique=True, null=True, blank=True)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def display_name(self):
        return self.full_name or self.username
