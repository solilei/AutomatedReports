from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Q
from django.contrib.auth.validators import UnicodeUsernameValidator

from scoring.models import Subject

from .models import User


class PasswordSetForm(SetPasswordForm):
    """Sets a new password with no old-password check; validators come from AUTH_PASSWORD_VALIDATORS."""


class SubjectChecklistForm(forms.Form):
    """Checklist of subjects. Offers active subjects of active programmes, plus any
    subject the user already has, so saving never drops one silently."""

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = Q(is_active=True, programme__is_active=True)
        if user is not None and user.pk:
            allowed |= Q(instructors=user)
            self.fields["subjects"].initial = list(user.assigned_subjects.values_list("pk", flat=True))
        self.fields["subjects"].queryset = (
            Subject.objects.filter(allowed).select_related("programme").distinct()
        )

    def grouped_subjects(self):
        """[(programme, [(subject, checked), ...]), ...] for the template."""
        if self.is_bound:
            checked = {str(v) for v in self.data.getlist(self.add_prefix("subjects"))}
        else:
            checked = {str(v) for v in self.fields["subjects"].initial or []}
        groups = {}
        for subject in self.fields["subjects"].queryset.order_by("programme__name", "name"):
            groups.setdefault(subject.programme, []).append((subject, str(subject.pk) in checked))
        return list(groups.items())


class UserCreateForm(SubjectChecklistForm):
    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    full_name = forms.CharField(max_length=150, required=False)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username
