from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.validators import UnicodeUsernameValidator

from .models import User


class PasswordSetForm(SetPasswordForm):
    """Sets a new password with no old-password check; validators come from AUTH_PASSWORD_VALIDATORS."""


class UserCreateForm(forms.Form):
    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    full_name = forms.CharField(max_length=150, required=False)
    role = forms.ChoiceField(choices=User.Role.choices)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username
