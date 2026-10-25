from datetime import date, datetime
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import RosterUpload
from roster.services import RosterError, cell_text, read_sheet
from roster.tests.helpers import SAMPLE_ROSTER, make_xlsx

URL = reverse("roster:upload")
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def xlsx_file(rows=None, name="roster.xlsx"):
    rows = rows if rows is not None else [["Name", "ID"], ["Alice Ng", "1"]]
    return SimpleUploadedFile(name, make_xlsx(rows), content_type=XLSX_TYPE)


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class UploadFileTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def post(self, file, group_number="C216"):
        return self.client.post(URL, {"file": file, "group_number": group_number})

    def test_instructor_forbidden(self):
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.post(xlsx_file()).status_code, 403)
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_nav_link_shown_to_admins_only(self):
        self.assertContains(self.client.get(reverse("home")), URL)
        self.client.force_login(make_user("inst"))
        self.assertNotContains(self.client.get(reverse("home")), URL)

    def test_rejects_non_xlsx_extension(self):
        file = SimpleUploadedFile("roster.csv", b"Name,ID\nAlice,1\n")
        response = self.post(file)
        self.assertContains(response, "Only .xlsx files are accepted.")
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_extension_check_is_case_insensitive(self):
        response = self.post(xlsx_file(name="ROSTER.XLSX"))
        self.assertEqual(response.status_code, 302)

    @override_settings(ROSTER_MAX_UPLOAD_BYTES=10)
    def test_rejects_oversize_file(self):
        response = self.post(xlsx_file())
        self.assertContains(response, "File is larger than 0 MB.")
        self.assertEqual(RosterUpload.objects.count(), 0)

    @override_settings(ROSTER_MAX_UPLOAD_BYTES=5 * 1048576)
    def test_oversize_message_uses_setting_in_mb(self):
        file = SimpleUploadedFile("big.xlsx", b"x" * (5 * 1048576 + 1))
        self.assertContains(self.post(file), "File is larger than 5 MB.")

    def test_rejects_corrupt_xlsx(self):
        file = SimpleUploadedFile("x.xlsx", b"not a zip")
        response = self.post(file)
        self.assertContains(response, "File is not a valid .xlsx workbook.")
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_rejects_missing_header_row(self):
        for rows in ([], [["Only one"]], [[None, "", "x"]]):
            with self.subTest(rows=rows):
                response = self.post(xlsx_file(rows))
                self.assertContains(response, "The first row must contain column headers.")
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_requires_group_number(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                response = self.post(xlsx_file(), group_number=value)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["group_number"])
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_rejects_invalid_group_number(self):
        for value in ("C 216", "C" * 21, "C/216"):
            with self.subTest(value=value):
                response = self.post(xlsx_file(), group_number=value)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors["group_number"])
        self.assertEqual(RosterUpload.objects.count(), 0)

    def test_group_number_starts_empty_after_previous_upload(self):
        self.assertEqual(self.post(xlsx_file()).status_code, 302)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"]["group_number"].value())

    def test_valid_upload_creates_staged_upload_and_redirects(self):
        content = make_xlsx([["Name", "ID"], ["Alice Ng", "1"]])
        file = SimpleUploadedFile("roster.xlsx", content, content_type=XLSX_TYPE)
        response = self.post(file, group_number="  c216  ")
        upload = RosterUpload.objects.get()
        self.assertRedirects(
            response, f"/roster/upload/{upload.pk}/columns/", fetch_redirect_response=False
        )
        self.assertEqual(upload.uploaded_by, self.admin)
        self.assertEqual(upload.original_filename, "roster.xlsx")
        self.assertEqual(bytes(upload.file_content), content)
        self.assertEqual(upload.group_number, "C216")
        self.assertEqual(upload.status, "uploaded")

    def test_valid_upload_logs_audit_event(self):
        self.post(xlsx_file())
        upload = RosterUpload.objects.get()
        event = AuditEvent.objects.get(action=actions.ROSTER_UPLOADED)
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(
            event.details,
            {
                "filename": "roster.xlsx",
                "size_bytes": len(bytes(upload.file_content)),
                "upload_id": upload.pk,
            },
        )


class ReadSheetTests(SimpleTestCase):
    def test_cell_text(self):
        cases = [
            (None, ""),
            (True, "True"),
            (216, "216"),
            (216.0, "216"),
            (2.5, "2.5"),
            ("  Alice \n  Ng ", "Alice Ng"),
            (datetime(2026, 1, 5, 9, 30), "2026-01-05"),
            (date(2026, 1, 5), "2026-01-05"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(cell_text(value), expected)

    def test_read_sheet_converts_numbers_and_pads_rows(self):
        content = make_xlsx([["Group", "Name", "Extra"], [216.0, "Alice"], ["C1", "Bob", "x"]])
        headers, rows = read_sheet(content)
        self.assertEqual(headers, ["Group", "Name", "Extra"])
        self.assertEqual(rows, [["216", "Alice", ""], ["C1", "Bob", "x"]])

    def test_read_sheet_raises_roster_error_on_garbage(self):
        with self.assertRaises(RosterError):
            read_sheet(b"not a zip")

    def test_sample_roster_headers(self):
        headers, rows = read_sheet(SAMPLE_ROSTER.read_bytes())
        self.assertEqual(
            headers,
            ["No.", "Cadet ID", "Full Name", "Course Group", "Sponsor", "Intake Date", "Email"],
        )
        self.assertEqual(len(rows), 15)
        self.assertEqual({row[3] for row in rows}, {"C216"})
