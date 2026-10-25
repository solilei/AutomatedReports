from django.contrib.auth.forms import SetPasswordForm


class PasswordSetForm(SetPasswordForm):
    """Sets a new password with no old-password check; validators come from AUTH_PASSWORD_VALIDATORS."""
