from django import forms
from django.conf import settings
from openpyxl.utils import get_column_letter

from scoring.models import Programme
from scoring.programmes import ATPL_NAME

from .models import Group, RosterColumnPreference
from .services import GROUP_NUMBER_RE, HEADER_SEARCH_ROWS, RosterError, read_sheet


class UploadForm(forms.Form):
    file = forms.FileField()
    group_number = forms.CharField(
        label="Group number (e.g. C216)", max_length=20, strip=True
    )

    programme = forms.ModelChoiceField(queryset=Programme.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["programme"]
        field.queryset = Programme.objects.filter(is_active=True)
        atpl = Programme.objects.filter(name=ATPL_NAME, is_active=True).first()
        field.initial = atpl.pk if atpl else None
        field.empty_label = None

    def clean(self):
        data = super().clean()
        number, programme = data.get("group_number"), data.get("programme")
        if number and programme:
            if not programme.accepts_number(number):
                prefix = programme.group_prefix
                self.add_error(
                    "group_number",
                    f"{programme.name} group numbers are {prefix} followed by digits "
                    f"(for example {prefix}216).",
                )
            else:
                group = Group.objects.select_related("programme").filter(number=number).first()
                if group and group.programme_id != programme.pk:
                    self.add_error(
                        "programme", f"Group {number} belongs to {group.programme.name}."
                    )
        return data

    def clean_group_number(self):
        number = self.cleaned_data["group_number"].upper()
        if not GROUP_NUMBER_RE.fullmatch(number):
            raise forms.ValidationError(
                "Use only letters, digits, '.', '_' and '-', with at least one letter or digit "
                "(max 20 characters)."
            )
        return number

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
        if not any(headers):
            raise forms.ValidationError(
                "The first row must contain column headers. Only a Name column is needed; "
                f"title rows above it are skipped (up to {HEADER_SEARCH_ROWS} rows)."
            )
        self.content = content
        return file


class ColumnForm(forms.Form):
    name_col = forms.ChoiceField(label="Name column")

    def __init__(self, headers, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (str(i), h or f"(column {get_column_letter(i + 1)}, no header)")
            for i, h in enumerate(headers)
        ]
        self.fields["name_col"].choices = choices
        normalised = [h.strip().lower() for h in headers]
        remembered = RosterColumnPreference.get().name_header.strip().lower()
        if remembered and remembered in normalised:
            self.fields["name_col"].initial = str(normalised.index(remembered))
