from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.tests.helpers import make_user
from roster.models import DeletedGroupNumber, Group, RosterColumnPreference, RosterUpload
from roster.services import parse_rows, read_sheet
from roster.tests.helpers import SAMPLE_ROSTER, make_group, make_xlsx

HEADERS = ["Group", "Name", "ID"]


def make_upload(rows, status="uploaded", **extra):
    admin = User.objects.get(username="boss")
    return RosterUpload.objects.create(
        uploaded_by=admin,
        original_filename="roster.xlsx",
        file_content=make_xlsx(rows),
        course_number="216.18",
        status=status,
        **extra,
    )


def columns_url(upload):
    return reverse("roster:upload_columns", args=[upload.pk])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class UploadColumnsTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def post(self, upload, group="0", name="1", id_col=""):
        return self.client.post(
            columns_url(upload), {"group_col": group, "name_col": name, "id_col": id_col}
        )

    def test_shows_headers_as_choices(self):
        upload = make_upload([["Group", "Name", None, "ID"], ["C216", "Alice Ng", "x", "1"]])
        response = self.client.get(columns_url(upload))
        self.assertContains(response, '<option value="0">Group</option>', html=True)
        self.assertContains(response, "(column C, no header)")
        self.assertContains(response, "— none —")
        self.assertContains(response, "Alice Ng")

    def test_preselects_remembered_columns(self):
        RosterColumnPreference.objects.create(
            pk=1, group_header=" group ", name_header="NAME", id_header="id"
        )
        upload = make_upload([["Name", "Group", "ID"], ["Alice Ng", "C216", "1"]])
        form = self.client.get(columns_url(upload)).context["form"]
        self.assertEqual(form["group_col"].value(), "1")
        self.assertEqual(form["name_col"].value(), "0")
        self.assertEqual(form["id_col"].value(), "2")

    def test_same_column_twice_rejected(self):
        upload = make_upload([HEADERS, ["C216", "Alice Ng", "1"]])
        for group, name, id_col in [("0", "0", ""), ("0", "1", "0"), ("0", "1", "1")]:
            response = self.post(upload, group, name, id_col)
            self.assertContains(
                response, "Group, Name and Cadet ID must be different columns."
            )
        upload.refresh_from_db()
        self.assertEqual(upload.status, "uploaded")

    def test_blank_group_and_name_rows_reported_with_row_numbers(self):
        upload = make_upload(
            [HEADERS, ["C216", "Alice Ng", "1"], ["", "Bob Ray", "2"], ["C216", "", "3"]]
        )
        response = self.post(upload, id_col="2")
        self.assertContains(response, "Row 3: group is blank.")
        self.assertContains(response, "Row 4: name is blank.")
        upload.refresh_from_db()
        self.assertEqual(upload.status, "uploaded")

    def test_blank_id_reported_when_id_column_chosen(self):
        upload = make_upload([HEADERS, ["C216", "Alice Ng", ""]])
        self.assertContains(self.post(upload, id_col="2"), "Row 2: cadet ID is blank.")

    def test_fully_blank_rows_skipped(self):
        result = parse_rows(
            [["C216", "Alice Ng", "1"], ["", "", ""], ["  ", " ", ""], ["C216", "Bob", "2"]],
            0,
            1,
            2,
        )
        self.assertEqual(result.errors, [])
        self.assertEqual([c["row"] for c in result.groups["C216"]], [2, 5])

    def test_no_cadets_error(self):
        upload = make_upload([HEADERS, ["", "", ""]])
        self.assertContains(self.post(upload), "The file contains no cadets.")

    def test_duplicate_names_without_id_rejected_with_rows(self):
        upload = make_upload(
            [HEADERS, ["C216", "Alice  Ng", ""], ["C216", "Bob", ""], ["c216", "Alice Ng", ""]]
        )
        response = self.post(upload)
        self.assertContains(
            response,
            "Group C216 has more than one cadet named &#x27;Alice Ng&#x27; (rows 2, 4). "
            "Fix the file and upload it again.",
        )

    def test_duplicate_names_allowed_with_id_column(self):
        upload = make_upload([HEADERS, ["C216", "Alice Ng", "1"], ["C216", "Alice Ng", "2"]])
        self.assertEqual(self.post(upload, id_col="2").status_code, 302)

    def test_duplicate_ids_rejected(self):
        upload = make_upload([HEADERS, ["C216", "A", "1"], ["C216", "B", "1"], ["C217", "C", "1"]])
        response = self.post(upload, id_col="2")
        self.assertContains(
            response, "Cadet ID &#x27;1&#x27; appears more than once in group C216 (rows 2, 3)."
        )
        self.assertNotContains(response, "group C217")

    def test_invalid_group_number_rejected(self):
        upload = make_upload([HEADERS, ["C 216", "Alice", ""], ["C" * 21, "Bob", ""]])
        response = self.post(upload)
        self.assertContains(response, "Row 2: group number &#x27;C 216&#x27; may only contain")
        self.assertContains(response, "(max 20 characters).")
        self.assertContains(response, "Row 3: group number")

    def test_group_number_uppercased(self):
        result = parse_rows([[" c216 ", "Alice  Ng", ""]], 0, 1, None)
        self.assertEqual(result.errors, [])
        self.assertEqual(
            result.groups, {"C216": [{"name": "Alice Ng", "external_id": "", "row": 2}]}
        )

    def test_locked_archived_deleted_groups_rejected(self):
        cases = [
            ("locked", "Group C216 is locked; unlock it before uploading."),
            ("archived", "Group C216 is archived and its number cannot be reused."),
            ("deleted", "Group C216 was deleted and its number cannot be reused."),
        ]
        for state, message in cases:
            with self.subTest(state=state):
                if state == "deleted":
                    DeletedGroupNumber.objects.create(number="C216")
                else:
                    make_group("C216", status=state)
                upload = make_upload([HEADERS, ["C216", "Alice Ng", ""]])
                response = self.post(upload)
                self.assertContains(response, message)
                upload.refresh_from_db()
                self.assertEqual(upload.status, "uploaded")
                DeletedGroupNumber.objects.all().delete()
                RosterUpload.objects.all().delete()
                Group.objects.all().delete()

    def test_identity_mode_mismatch_rejected(self):
        make_group("C216", identity_mode="name")
        upload = make_upload([HEADERS, ["C216", "Alice Ng", "1"]])
        self.assertContains(
            self.post(upload, id_col="2"),
            "Group C216 was first uploaded without a Cadet ID column; "
            "set Cadet ID to — none —.",
        )
        make_group("C217", identity_mode="id")
        upload = make_upload([HEADERS, ["C217", "Alice Ng", "1"]])
        self.assertContains(
            self.post(upload),
            "Group C217 was first uploaded with a Cadet ID column; choose a Cadet ID column.",
        )

    def test_success_saves_parsed_and_preference_and_redirects(self):
        upload = make_upload([["Course Group", "Full Name", "Cadet ID"], ["c216", "Alice", "9"]])
        response = self.post(upload, id_col="2")
        self.assertRedirects(
            response,
            reverse("roster:upload_preview", args=[upload.pk]),
            fetch_redirect_response=False,
        )
        upload.refresh_from_db()
        self.assertEqual(upload.status, "parsed")
        self.assertEqual((upload.group_col, upload.name_col, upload.id_col), (0, 1, 2))
        self.assertEqual(
            upload.parsed,
            {
                "id_mode": True,
                "groups": {"C216": [{"name": "Alice", "external_id": "9", "row": 2}]},
            },
        )
        pref = RosterColumnPreference.get()
        self.assertEqual(
            (pref.group_header, pref.name_header, pref.id_header),
            ("Course Group", "Full Name", "Cadet ID"),
        )

    def test_success_without_id_clears_id_preference(self):
        RosterColumnPreference.objects.create(pk=1, id_header="Cadet ID")
        upload = make_upload([HEADERS, ["C216", "Alice", ""]])
        self.post(upload)
        upload.refresh_from_db()
        self.assertIsNone(upload.id_col)
        self.assertFalse(upload.parsed["id_mode"])
        self.assertEqual(RosterColumnPreference.get().id_header, "")

    def test_sample_roster_parses_into_three_groups(self):
        headers, rows = read_sheet(SAMPLE_ROSTER.read_bytes())
        result = parse_rows(
            rows,
            headers.index("Course Group"),
            headers.index("Full Name"),
            headers.index("Cadet ID"),
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(
            {g: len(c) for g, c in result.groups.items()},
            {"C216": 15, "C217": 13, "C218": 16},
        )
        self.assertEqual(list(result.groups), ["C216", "C217", "C218"])

    def test_applied_upload_redirects(self):
        upload = make_upload([HEADERS, ["C216", "Alice", ""]], status="applied")
        response = self.client.get(columns_url(upload))
        self.assertRedirects(response, reverse("roster:upload"), fetch_redirect_response=False)
        self.assertIn(
            "This upload has already been applied.",
            [str(m) for m in get_messages(response.wsgi_request)],
        )

    def test_instructor_forbidden(self):
        upload = make_upload([HEADERS, ["C216", "Alice", ""]])
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(columns_url(upload)).status_code, 403)

    def test_upload_redirects_to_columns_url(self):
        upload = make_upload([HEADERS])
        self.assertEqual(columns_url(upload), f"/roster/upload/{upload.pk}/columns/")
