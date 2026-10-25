import secrets

from .models import User


def active_admin_count():
    return User.objects.filter(role=User.Role.ADMIN, is_active=True, is_approved=True).count()


def is_last_admin(user):
    return user.is_admin and user.is_active and user.is_approved and active_admin_count() <= 1


def generate_temp_password():
    return secrets.token_urlsafe(12)
