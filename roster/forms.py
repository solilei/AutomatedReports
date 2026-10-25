from django import forms
from django.conf import settings

from .services import RosterError, read_sheet


class UploadForm(forms.Form):
    file = forms.FileField()
    course_number = forms.CharField(max_length=50, strip=True)

    def clean_file(self):
        file = self.cleaned_data["file"]
        if not file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Only .xlsx files are accepted.")
        if file.size > settings.ROSTER_MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"File is larger than {settings.ROSTER_MAX_UPLOAD_BYTES // 1048576} MB."
            )
        content = file.read()
        try:
            headers, _ = read_sheet(content)
        except RosterError:
            raise forms.ValidationError("File is not a valid .xlsx workbook.")
        if sum(1 for h in headers if h) < 2:
            raise forms.ValidationError("The first row must contain column headers.")
        self.content = content
        return file
