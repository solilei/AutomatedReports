from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Cadet, Group, RosterUpload
from roster.services import parse_rows, read_sheet
from roster.tests.helpers import SAMPLE_ROSTER, make_group, make_xlsx

HEADERS = ["Name", "ID"]


def make_parsed_upload(rows, id_col=None, group_number="C216", status="parsed"):
    """Create an upload already past the columns step (columns 0=name, 1=id)."""
    admin = User.objects.get(username="boss")
    content = make_xlsx([HEADERS] + rows)
    _, data = read_sheet(content)
    result = parse_rows(data, group_number, 0, id_col)
    assert not result.errors, result.errors
    return RosterUpload.objects.create(
        uploaded_by=admin,
        original_filename="roster.xlsx",
        file_content=content,
        group_number=group_number,
        status=status,
        name_col=0,
        id_col=id_col,
        parsed={"id_mode": id_col is not None, "groups": result.groups},
    )


def preview_url(upload):
    return reverse("roster:upload_preview", args=[upload.pk])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class UploadApplyTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def test_preview_lists_new_group_and_counts(self):
        upload = make_parsed_upload([["Alice Ng", ""], ["Bob Ray", ""]])
        response = self.client.get(preview_url(upload))
        self.assertContains(response, "New group")
        self.assertContains(response, "C216")
        self.assertContains(response, "Cadets added")
        self.assertContains(response, "Alice Ng")
        self.assertContains(response, "Confirm and apply")
        self.assertContains(response, "Cancel")
        (change,) = response.context["changes"]
        self.assertEqual(change.number, "C216")
        self.assertTrue(change.is_new)
        self.assertEqual(change.added, ["Alice Ng", "Bob Ray"])

    def test_preview_shows_existing_group_changes(self):
        make_group("C216", ["Alice Ng", "Bob Ray"])
        upload = make_parsed_upload([["Alice Ng", ""], ["Cy Poe", ""]])
        response = self.client.get(preview_url(upload))
        self.assertContains(response, "Existing group")
        self.assertContains(
            response, "Cadets no longer present (will be marked inactive, data kept)"
        )
        self.assertContains(response, "Unchanged: 1")
        change = response.context["changes"][0]
        self.assertEqual(change.added, ["Cy Poe"])
        self.assertEqual(change.deactivated, ["Bob Ray"])
        self.assertEqual(change.unchanged, 1)

    def test_nothing_changes_before_confirm(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.get(preview_url(upload))
        self.assertEqual(Group.objects.count(), 0)
        self.assertEqual(Cadet.objects.count(), 0)
        upload.refresh_from_db()
        self.assertEqual(upload.status, "parsed")

    def test_uploaded_status_redirects_to_columns(self):
        upload = make_parsed_upload([["Alice Ng", ""]], status="uploaded")
        response = self.client.get(preview_url(upload))
        self.assertRedirects(
            response,
            reverse("roster:upload_columns", args=[upload.pk]),
            fetch_redirect_response=False,
        )

    def test_get_shows_check_groups_errors(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        make_group("C216", ["Alice Ng"], status="locked")
        response = self.client.get(preview_url(upload))
        self.assertContains(response, "Group C216 is locked")

    def test_instructor_forbidden(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(preview_url(upload)).status_code, 403)
        self.assertEqual(self.client.post(preview_url(upload)).status_code, 403)

    def test_confirm_creates_group_and_cadets_with_positions(self):
        upload = make_parsed_upload([["Alice Ng", "11"], ["Bob Ray", "33"]], id_col=1)
        response = self.client.post(preview_url(upload))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertIn("Roster applied.", [str(m) for m in get_messages(response.wsgi_request)])
        c216 = Group.objects.get(number="C216")
        self.assertEqual(c216.identity_mode, "id")
        self.assertEqual(
            [(c.name, c.external_id, c.position) for c in c216.cadets.order_by("position")],
            [("Alice Ng", "11", 1), ("Bob Ray", "33", 2)],
        )
        upload.refresh_from_db()
        self.assertEqual(upload.status, "applied")

    def test_second_course_upload_creates_separate_group(self):
        first = make_parsed_upload([["Alice Ng", ""]])
        self.client.post(preview_url(first))
        second = make_parsed_upload([["Cy Poe", ""]], group_number="C217")
        self.client.post(preview_url(second))
        self.assertEqual(
            list(Group.objects.values_list("number", flat=True)), ["C216", "C217"]
        )
        self.assertEqual(Group.objects.get(number="C217").cadets.get().position, 1)
        self.assertEqual(Group.objects.get(number="C216").cadets.count(), 1)

    def test_name_mode_group_created_with_name_identity(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.post(preview_url(upload))
        self.assertEqual(Group.objects.get(number="C216").identity_mode, "name")

    def test_reupload_adds_and_deactivates_but_never_deletes(self):
        make_group("C216", ["Alice Ng", "Bob Ray"])
        before = Cadet.objects.count()
        upload = make_parsed_upload([["Alice Ng", ""], ["Cy Poe", ""]])
        self.client.post(preview_url(upload))
        group = Group.objects.get(number="C216")
        self.assertEqual(Cadet.objects.count(), before + 1)
        self.assertTrue(group.cadets.get(name="Alice Ng").is_active)
        self.assertTrue(group.cadets.get(name="Cy Poe").is_active)
        self.assertFalse(group.cadets.get(name="Bob Ray").is_active)
        self.assertEqual(group.cadets.get(name="Alice Ng").position, 1)
        self.assertEqual(group.cadets.get(name="Cy Poe").position, 2)

    def test_reupload_reactivates_returning_cadet(self):
        group = make_group("C216", ["Alice Ng", "Bob Ray"])
        Cadet.objects.filter(group=group, name="Bob Ray").update(is_active=False)
        upload = make_parsed_upload([["Alice Ng", ""], ["Bob Ray", ""]])
        response = self.client.get(preview_url(upload))
        self.assertContains(response, "Cadets returning (will be reactivated)")
        self.assertEqual(response.context["changes"][0].reactivated, ["Bob Ray"])
        self.client.post(preview_url(upload))
        self.assertTrue(group.cadets.get(name="Bob Ray").is_active)
        self.assertEqual(Cadet.objects.count(), 2)

    def test_reupload_id_mode_renames(self):
        group = Group.objects.create(number="C216", identity_mode="id")
        Cadet.objects.create(group=group, name="Alice Ng", external_id="11", position=1)
        upload = make_parsed_upload([["Alice Young", "11"]], id_col=1)
        response = self.client.get(preview_url(upload))
        self.assertContains(response, "Cadets renamed")
        self.assertEqual(
            response.context["changes"][0].renamed, [("Alice Ng", "Alice Young")]
        )
        self.client.post(preview_url(upload))
        self.assertEqual(Cadet.objects.count(), 1)
        self.assertEqual(Cadet.objects.get().name, "Alice Young")
        event = AuditEvent.objects.get(action=actions.CADET_RENAMED)
        self.assertEqual(event.details["old"], "Alice Ng")
        self.assertEqual(event.details["new"], "Alice Young")

    def test_reupload_to_existing_group_logs_no_group_created(self):
        make_group("C216", ["Alice Ng"])
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.post(preview_url(upload))
        self.assertFalse(AuditEvent.objects.filter(action=actions.GROUP_CREATED).exists())

    def test_confirm_twice_does_not_reapply(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.post(preview_url(upload))
        events = AuditEvent.objects.count()
        response = self.client.post(preview_url(upload))
        self.assertRedirects(response, reverse("roster:upload"), fetch_redirect_response=False)
        self.assertEqual(Cadet.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), events)

    def test_applied_upload_get_redirects_with_message(self):
        upload = make_parsed_upload([["Alice Ng", ""]], status="applied")
        response = self.client.get(preview_url(upload))
        self.assertRedirects(response, reverse("roster:upload"), fetch_redirect_response=False)
        self.assertTrue(list(get_messages(response.wsgi_request)))

    def test_group_locked_between_preview_and_confirm_blocks_apply(self):
        make_group("C216", ["Alice Ng"])
        upload = make_parsed_upload([["Alice Ng", ""], ["Cy Poe", ""]])
        self.client.get(preview_url(upload))
        Group.objects.filter(number="C216").update(status="locked")
        response = self.client.post(preview_url(upload))
        self.assertContains(response, "Group C216 is locked")
        self.assertEqual(Cadet.objects.count(), 1)
        upload.refresh_from_db()
        self.assertEqual(upload.status, "parsed")
        self.assertFalse(AuditEvent.objects.filter(action=actions.ROSTER_APPLIED).exists())

    def test_file_content_cleared_after_apply(self):
        upload = make_parsed_upload([["Alice Ng", ""]])
        self.client.post(preview_url(upload))
        upload.refresh_from_db()
        self.assertEqual(bytes(upload.file_content), b"")
        self.assertEqual(upload.parsed, {})

    def test_audit_events_written_for_each_change(self):
        group = make_group("C216", ["Alice Ng", "Bob Ray", "Dee Fox"])
        Cadet.objects.filter(group=group, name="Dee Fox").update(is_active=False)
        upload = make_parsed_upload([["Alice Ng", ""], ["Dee Fox", ""], ["Cy Poe", ""]])
        self.client.post(preview_url(upload))

        def events(action):
            return list(AuditEvent.objects.filter(action=action))

        self.assertEqual(events(actions.GROUP_CREATED), [])
        added = events(actions.CADET_ADDED)
        self.assertEqual({e.details["cadet"] for e in added}, {"Cy Poe"})
        self.assertEqual({e.group_number for e in added}, {"C216"})
        self.assertIn("external_id", added[0].details)
        self.assertEqual(
            [e.details["cadet"] for e in events(actions.CADET_REACTIVATED)], ["Dee Fox"]
        )
        self.assertEqual(
            [e.details["cadet"] for e in events(actions.CADET_DEACTIVATED)], ["Bob Ray"]
        )
        applied = events(actions.ROSTER_APPLIED)
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].summary, "Applied roster 'roster.xlsx' to groups C216")
        self.assertEqual(applied[0].details, {"upload_id": upload.pk, "groups": ["C216"]})
        self.assertEqual(applied[0].actor, self.admin)

    def test_new_group_logs_group_created(self):
        upload = make_parsed_upload([["Alice Ng", ""]], group_number="C217")
        self.client.post(preview_url(upload))
        (event,) = AuditEvent.objects.filter(action=actions.GROUP_CREATED)
        self.assertEqual(event.group_number, "C217")
        self.assertEqual(event.summary, "Group C217 created")

    def test_sample_roster_end_to_end(self):
        with open(SAMPLE_ROSTER, "rb") as handle:
            response = self.client.post(
                reverse("roster:upload"), {"file": handle, "group_number": "c216"}
            )
        upload = RosterUpload.objects.get()
        self.assertEqual(upload.group_number, "C216")
        self.assertRedirects(
            response,
            reverse("roster:upload_columns", args=[upload.pk]),
            fetch_redirect_response=False,
        )
        headers, _ = read_sheet(bytes(upload.file_content))
        response = self.client.post(
            reverse("roster:upload_columns", args=[upload.pk]),
            {
                "name_col": str(headers.index("Full Name")),
                "id_col": str(headers.index("Cadet ID")),
            },
        )
        self.assertRedirects(response, preview_url(upload), fetch_redirect_response=False)
        self.assertContains(self.client.get(preview_url(upload)), "New group")
        self.client.post(preview_url(upload))
        self.assertEqual(list(Group.objects.values_list("number", flat=True)), ["C216"])
        self.assertEqual(Cadet.objects.filter(is_active=True).count(), 15)
