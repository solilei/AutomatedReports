import secrets
import time

from audit import actions
from audit.service import log

from .models import User

MAX_FAILED_SIGN_INS = 5
SIGN_IN_LOCK_SECONDS = 15 * 60
LOCKED_MESSAGE = "Too many failed sign-in attempts. Try again in 15 minutes or ask an admin to reset your account."


def is_sign_in_locked(user):
    return user.sign_in_locked_until is not None and time.time() < user.sign_in_locked_until


def record_failed_sign_in(user):
    """Count a wrong password or authenticator code; the fifth in a row locks the account."""
    user.failed_sign_ins += 1
    if user.failed_sign_ins >= MAX_FAILED_SIGN_INS:
        user.failed_sign_ins = 0
        user.sign_in_locked_until = time.time() + SIGN_IN_LOCK_SECONDS
        log(
            None,
            actions.ACCOUNT_LOCKED,
            f"{user.username} locked for 15 minutes after {MAX_FAILED_SIGN_INS} failed sign-in attempts",
            details={"username": user.username},
            actor_label="sign-in",
        )
    user.save(update_fields=["failed_sign_ins", "sign_in_locked_until"])


def clear_failed_sign_ins(user):
    if user.failed_sign_ins or user.sign_in_locked_until is not None:
        user.failed_sign_ins = 0
        user.sign_in_locked_until = None
        user.save(update_fields=["failed_sign_ins", "sign_in_locked_until"])


def active_admin_count():
    return User.objects.filter(role=User.Role.ADMIN, is_active=True, is_approved=True).count()


def is_last_admin(user):
    return user.is_admin and user.is_active and user.is_approved and active_admin_count() <= 1


def generate_temp_password():
    return secrets.token_urlsafe(12)
