from django import forms

from roster.models import Group

from .models import ScoreSet, Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = Subject.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
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
