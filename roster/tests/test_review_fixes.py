from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster import services
from roster.models import Cadet, Group, RosterUpload
from roster.services import parse_rows, read_roster
from roster.tests.helpers import make_group, make_xlsx
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import Subject


def make_upload(admin, rows, group_number="C216"):
    """A parsed name-mode upload; rows go under a Name/X header."""
    content = make_xlsx([["Name", "X"]] + rows)
    sheet = read_roster(content)
    result = parse_rows(sheet.rows, group_number, 0, None, sheet.first_data_row)
    upload = RosterUpload.objects.create(
        uploaded_by=admin,
        original_filename="roster.xlsx",
        file_content=content,
        group_number=group_number,
        status="parsed",
        name_col=0,
        parsed={"id_mode": False, "groups": result.groups},
    )
    return result, upload


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class GroupDeleteRemovesCadetDataTests(TestCase):
    def test_delete_redacts_cadet_events_and_discards_open_uploads(self):
        instructor = make_user("inst")
        admin = make_user("boss", role="admin")
        subject = Subject.objects.create(name="Drill")
        group = make_group("C216")
        post = {"cadet_ids": ",".join(str(c.pk) for c in group.cadets.all())}
        for cadet in group.cadets.all():
            post.update({f"s-{cadet.pk}-{f}": "4" for f in ATTRIBUTE_FIELDS})
            post[f"c-{cadet.pk}"] = "Secret note"
        self.client.force_login(instructor)
        self.client.post(reverse("scoring:score_grid", args=["C216", subject.pk]), post)
        upload = RosterUpload.objects.create(
            uploaded_by=admin,
            original_filename="r.xlsx",
            file_content=b"XLSX",
            group_number="C216",
            status="parsed",
            parsed={"groups": {"C216": [{"name": "Alice Ng"}]}},
        )
        Group.objects.filter(pk=group.pk).update(status="archived")

        self.client.force_login(admin)
        self.client.post(reverse("roster:group_delete", args=["C216"]), {"confirm_number": "C216"})

        self.assertFalse(Group.objects.exists())
        for event in AuditEvent.objects.all():
            text = event.summary + str(event.details)
            self.assertNotIn("Alice", text, event.action)
            self.assertNotIn("Secret", text, event.action)
        redacted = AuditEvent.objects.filter(action=actions.SCORE_CHANGED)
        self.assertTrue(redacted.exists())
        self.assertEqual(redacted.first().actor, instructor)
        upload.refresh_from_db()
        self.assertEqual(upload.status, "discarded")
        self.assertEqual(bytes(upload.file_content), b"")
        self.assertEqual(upload.parsed, {})


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class StaleUploadTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")

    def make(self, age):
        upload = RosterUpload.objects.create(
            uploaded_by=self.admin, original_filename="r.xlsx", file_content=b"X", group_number="C1"
        )
        RosterUpload.objects.filter(pk=upload.pk).update(uploaded_at=timezone.now() - age)
        return upload

    def test_upload_page_discards_stale_and_keeps_fresh(self):
        old, new = self.make(timedelta(hours=25)), self.make(timedelta(hours=1))
        self.client.force_login(self.admin)
        self.client.get(reverse("roster:upload"))
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual(old.status, "discarded")
        self.assertEqual(bytes(old.file_content), b"")
        self.assertEqual(new.status, "uploaded")
        event = AuditEvent.objects.get(action=actions.ROSTER_DISCARDED)
        self.assertEqual(event.actor_label, "system")

    def test_command_discards_stale(self):
        old = self.make(timedelta(days=3))
        out = StringIO()
        call_command("discard_stale_uploads", stdout=out)
        old.refresh_from_db()
        self.assertEqual(old.status, "discarded")
        self.assertIn("Discarded 1 stale upload(s).", out.getvalue())


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class UploadRaceTests(TestCase):
    def test_group_created_by_another_upload_mid_apply_asks_to_confirm_again(self):
        admin = make_user("boss", role="admin")
        self.client.force_login(admin)
        _, upload = make_upload(admin, [["Alice Ng", ""]])
        real_diff = services._diff_upload
        calls = []

        def racing_diff(u):
            changes = real_diff(u)
            calls.append(1)
            if len(calls) == 2:  # inside apply_upload, after its diff and before the create
                make_group("C216", cadets=("Alice Ng",))
            return changes

        with mock.patch.object(services, "_diff_upload", racing_diff):
            response = self.client.post(reverse("roster:upload_preview", args=[upload.pk]))
        self.assertRedirects(
            response,
            reverse("roster:upload_preview", args=[upload.pk]),
            fetch_redirect_response=False,
        )
        upload.refresh_from_db()
        self.assertEqual(upload.status, "parsed")


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class NameIgnoresCaseTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def preview(self, upload):
        return self.client.get(reverse("roster:upload_preview", args=[upload.pk]))

    def test_duplicate_names_differing_in_case_rejected(self):
        result, _ = make_upload(self.admin, [["John Smith", ""], ["JOHN SMITH", ""]])
        self.assertTrue(
            any("more than one cadet named 'John Smith'" in e for e in result.errors), result.errors
        )

    def test_case_change_renames_the_existing_cadet(self):
        make_group("C216", cadets=("john smith", "Bob Ray"))
        _, upload = make_upload(self.admin, [["John Smith", ""], ["Bob Ray", ""]])
        self.assertContains(self.preview(upload), "john smith → John Smith")
        self.client.post(reverse("roster:upload_preview", args=[upload.pk]))
        self.assertEqual(
            sorted(Cadet.objects.values_list("name", "is_active")),
            [("Bob Ray", True), ("John Smith", True)],
        )

    def test_preview_flags_possible_respelling(self):
        make_group("C216", cadets=("Jon Smith", "Bob Ray"))
        _, upload = make_upload(self.admin, [["John Smith", ""], ["Bob Ray", ""]])
        response = self.preview(upload)
        self.assertContains(response, "Possible name corrections")
        self.assertContains(response, "Jon Smith → John Smith")

    def test_database_rejects_case_duplicate(self):
        group = make_group("C216", cadets=("Ann Lee",))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cadet.objects.create(group=group, name="ANN LEE", position=2)


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class TitleRowTests(TestCase):
    def test_title_rows_skipped_and_errors_use_spreadsheet_rows(self):
        content = make_xlsx(
            [["Course C216 roster"], [], ["Name", "ID"], ["Alice Ng", "1"], ["", "2"]]
        )
        sheet = read_roster(content)
        self.assertEqual(sheet.headers, ["Name", "ID"])
        self.assertEqual(sheet.header_row, 3)
        result = parse_rows(sheet.rows, "C216", 0, 1, sheet.first_data_row)
        self.assertEqual(result.errors, ["Row 5: name is blank."])

    def test_columns_page_says_which_row_holds_headers(self):
        admin = make_user("boss", role="admin")
        self.client.force_login(admin)
        file = SimpleUploadedFile(
            "r.xlsx", make_xlsx([["Course C216"], ["Name", "ID"], ["Alice Ng", "1"]])
        )
        response = self.client.post(
            reverse("roster:upload"), {"file": file, "group_number": "C216"}, follow=True
        )
        self.assertContains(response, "Column headers taken from row 2")
