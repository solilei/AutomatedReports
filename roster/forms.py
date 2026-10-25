from django import forms
from django.conf import settings
from openpyxl.utils import get_column_letter

from .models import RosterColumnPreference
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


class ColumnForm(forms.Form):
    group_col = forms.ChoiceField(label="Group column")
    name_col = forms.ChoiceField(label="Name column")
    id_col = forms.ChoiceField(label="Cadet ID column", required=False)

    def __init__(self, headers, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (str(i), h or f"(column {get_column_letter(i + 1)}, no header)")
            for i, h in enumerate(headers)
        ]
        self.fields["group_col"].choices = choices
        self.fields["name_col"].choices = choices
        self.fields["id_col"].choices = [("", "— none —")] + choices
        pref = RosterColumnPreference.get()
        normalised = [h.strip().lower() for h in headers]
        for field, remembered in [
            ("group_col", pref.group_header),
            ("name_col", pref.name_header),
            ("id_col", pref.id_header),
        ]:
            remembered = remembered.strip().lower()
            if remembered and remembered in normalised:
                self.fields[field].initial = str(normalised.index(remembered))

    def clean(self):
        data = super().clean()
        group, name, id_col = (data.get(k) for k in ("group_col", "name_col", "id_col"))
        if group and name and (group == name or (id_col and id_col in (group, name))):
            raise forms.ValidationError(
                "Group, Name and Cadet ID must be different columns."
            )
        return data
