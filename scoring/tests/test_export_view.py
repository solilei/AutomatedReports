from io import BytesIO

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Group
from roster.tests.helpers import make_group

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ExportViewTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.instructor = make_user("teach")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.url = reverse("scoring:export", args=["C216"])

    def test_instructor_forbidden(self):
        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(AuditEvent.objects.filter(action=actions.EXPORT_DOWNLOADED).count(), 0)

    def test_admin_downloads_valid_xlsx_with_filename(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_TYPE)
        filename = f"Cadet_Soft_Skills_C216_{timezone.localdate():%Y-%m-%d}.xlsx"
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="{filename}"')
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.active.title, "C216")

    def test_export_logged(self):
        self.client.force_login(self.admin)
        self.client.get(self.url)
        event = AuditEvent.objects.get(action=actions.EXPORT_DOWNLOADED)
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(
            event.details,
            {"filename": f"Cadet_Soft_Skills_C216_{timezone.localdate():%Y-%m-%d}.xlsx"},
        )

    def test_export_allowed_for_locked_and_archived(self):
        self.client.force_login(self.admin)
        for status in (Group.Status.LOCKED, Group.Status.ARCHIVED):
            with self.subTest(status=status):
                Group.objects.filter(pk=self.group.pk).update(status=status)
                self.assertEqual(self.client.get(self.url).status_code, 200)
