import re

from django import forms

from roster.models import Group

from .models import Programme, ScoreSet, Subject


class ProgrammeForm(forms.ModelForm):
    class Meta:
        model = Programme
        fields = ["name", "group_prefix"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Existing group numbers were checked against the prefix, so it is fixed once
        # the programme has a group. A disabled field ignores any posted value.
        if self.instance.pk and self.instance.groups.exists():
            field = self.fields["group_prefix"]
            field.disabled = True
            field.help_text = "Locked: this programme already has groups."

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Programme.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A programme with this name already exists.")
        return name

    def clean_group_prefix(self):
        prefix = self.cleaned_data["group_prefix"].strip()
        if prefix and not re.fullmatch(r"[A-Za-z0-9]+", prefix):
            raise forms.ValidationError("Use letters and digits only.")
        return prefix.upper()


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name"]

    def __init__(self, *args, programme=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.programme = programme or self.instance.programme

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = Subject.objects.filter(programme=self.programme, name__iexact=name).exclude(
            pk=self.instance.pk
        )
        if duplicates.exists():
            raise forms.ValidationError("A subject with this name already exists.")
        if self.instance.pk and name != self.instance.name and self._used_by_closed_group():
            raise forms.ValidationError(
                "This subject is used by a locked or archived group, so it cannot be renamed "
                "without changing that group's report. Create a new subject instead."
            )
        return name

    def _used_by_closed_group(self):
        closed = [Group.Status.LOCKED, Group.Status.ARCHIVED]
        return ScoreSet.objects.filter(subject=self.instance, group__status__in=closed).exists()
