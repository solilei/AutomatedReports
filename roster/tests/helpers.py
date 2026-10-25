from io import BytesIO

from django.conf import settings
from openpyxl import Workbook

from roster.models import Cadet, Group

SAMPLE_ROSTER = settings.BASE_DIR / "samples" / "sample_roster_C216.xlsx"


def make_xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_group(
    number="C216",
    cadets=("Alice Ng", "Bob Ray"),
    status="active",
    identity_mode="name",
):
    group = Group.objects.create(
        number=number,
        status=status,
        identity_mode=identity_mode,
    )
    for position, name in enumerate(cadets, start=1):
        Cadet.objects.create(group=group, name=name, external_id="", position=position)
    return group
