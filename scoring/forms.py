from django import forms

from .models import Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicates = Subject.objects.filter(name__iexact=name).exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("A subject with this name already exists.")
        return name
