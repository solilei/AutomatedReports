from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.tests.helpers import make_user
from roster.models import DeletedGroupNumber, Group, RosterColumnPreference, RosterUpload
from roster.services import parse_rows, read_sheet
from roster.tests.helpers import SAMPLE_ROSTER, make_group, make_xlsx

HEADERS = ["Name", "ID"]


def make_upload(rows, status="uploaded", group_number="C216", **extra):
    admin = User.objects.get(username="boss")
    return RosterUpload.objects.create(
        uploaded_by=admin,
        original_filename="roster.xlsx",
        file_content=make_xlsx(rows),
        group_number=group_number,
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

    def post(self, upload, name="0", id_col=""):
        return self.client.post(columns_url(upload), {"name_col": name, "id_col": id_col})

    def test_shows_headers_as_choices(self):
        upload = make_upload([["Name", None, "ID"], ["Alice Ng", "x", "1"]])
        response = self.client.get(columns_url(upload))
        self.assertContains(response, '<option value="0">Name</option>', html=True)
        self.assertContains(response, "(column B, no header)")
        self.assertContains(response, "— none —")
        self.assertContains(response, "Alice Ng")
        self.assertContains(response, "group C216")
        self.assertNotContains(response, "Group column")

    def test_preselects_remembered_columns(self):
        RosterColumnPreference.objects.create(pk=1, name_header="NAME", id_header=" id ")
        upload = make_upload([["ID", "Name"], ["1", "Alice Ng"]])
        form = self.client.get(columns_url(upload)).context["form"]
        self.assertEqual(form["name_col"].value(), "1")
        self.assertEqual(form["id_col"].value(), "0")

    def test_same_column_twice_rejected(self):
        upload = make_upload([HEADERS, ["Alice Ng", "1"]])
        response = self.post(upload, "0", "0")
        self.assertContains(response, "Name and Cadet ID must be different columns.")
        upload.refresh_from_db()
        self.assertEqual(upload.status, "uploaded")

    def test_blank_name_rows_reported_with_row_numbers(self):
        upload = make_upload([HEADERS, ["Alice Ng", "1"], ["", "2"], ["Cy Poe", ""]])
        response = self.post(upload, id_col="1")
        self.assertContains(response, "Row 3: name is blank.")
        self.assertContains(response, "Row 4: cadet ID is blank.")
        upload.refresh_from_db()
        self.assertEqual(upload.status, "uploaded")

    def test_blank_id_reported_when_id_column_chosen(self):
        upload = make_upload([HEADERS, ["Alice Ng", ""]])
        self.assertContains(self.post(upload, id_col="1"), "Row 2: cadet ID is blank.")

    def test_name_longer_than_200_characters_rejected(self):
        upload = make_upload([HEADERS, ["A" * 201, ""], ["Bob Ray", ""]])
        response = self.post(upload)
        self.assertContains(response, "Row 2: name is longer than 200 characters.")
        upload.refresh_from_db()
        self.assertEqual(upload.status, "uploaded")

    def test_cadet_id_longer_than_50_characters_rejected(self):
        result = parse_rows([["Alice Ng", "X" * 51], ["Bob Ray", "2"]], "C216", 0, 1)
        self.assertEqual(result.errors, ["Row 2: cadet ID is longer than 50 characters."])

    def test_name_and_id_at_the_length_limits_accepted(self):
        result = parse_rows([["A" * 200, "X" * 50]], "C216", 0, 1)
        self.assertEqual(result.errors, [])

    def test_digit_only_cadet_ids_ignore_leading_zeros(self):
        result = parse_rows(
            [["Alice Ng", "00123"], ["Bob Ray", "000"], ["Cy Poe", "A0012"], ["Dee Fox", "0042x"]],
            "C216", 0, 1,
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(
            [c["external_id"] for c in result.groups["C216"]], ["123", "0", "A0012", "0042x"]
        )

    def test_ids_equal_after_dropping_leading_zeros_are_duplicates(self):
        result = parse_rows([["Alice Ng", "0123"], ["Bob Ray", "123"]], "C216", 0, 1)
        self.assertEqual(
            result.errors, ["Cadet ID '123' appears more than once in group C216 (rows 2, 3)."]
        )

    def test_fully_blank_rows_skipped(self):
        result = parse_rows(
            [["Alice Ng", "1"], ["", ""], ["  ", ""], ["Bob", "2"]], "C216", 0, 1
        )
        self.assertEqual(result.errors, [])
        self.assertEqual([c["row"] for c in result.groups["C216"]], [2, 5])

    def test_no_cadets_error(self):
        upload = make_upload([HEADERS, ["", ""]])
        self.assertContains(self.post(upload), "The file contains no cadets.")

    def test_every_row_goes_to_the_uploads_group(self):
        result = parse_rows([["Alice Ng", ""], ["Bob Ray", ""]], "C217", 0, None)
        self.assertEqual(list(result.groups), ["C217"])
        self.assertEqual(len(result.groups["C217"]), 2)

    def test_duplicate_names_without_id_rejected_with_rows(self):
        upload = make_upload([HEADERS, ["Alice  Ng", ""], ["Bob", ""], ["Alice Ng", ""]])
        response = self.post(upload)
        self.assertContains(
            response,
            "Group C216 has more than one cadet named &#x27;Alice Ng&#x27; (rows 2, 4). "
            "Fix the file and upload it again.",
        )

    def test_duplicate_names_allowed_with_id_column(self):
        upload = make_upload([HEADERS, ["Alice Ng", "1"], ["Alice Ng", "2"]])
        self.assertEqual(self.post(upload, id_col="1").status_code, 302)

    def test_duplicate_ids_rejected(self):
        upload = make_upload([HEADERS, ["A", "1"], ["B", "1"]])
        response = self.post(upload, id_col="1")
        self.assertContains(
            response, "Cadet ID &#x27;1&#x27; appears more than once in group C216 (rows 2, 3)."
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
                upload = make_upload([HEADERS, ["Alice Ng", ""]])
                response = self.post(upload)
                self.assertContains(response, message)
                upload.refresh_from_db()
                self.assertEqual(upload.status, "uploaded")
                DeletedGroupNumber.objects.all().delete()
                RosterUpload.objects.all().delete()
                Group.objects.all().delete()

    def test_identity_mode_mismatch_rejected(self):
        make_group("C216", identity_mode="name")
        upload = make_upload([HEADERS, ["Alice Ng", "1"]])
        self.assertContains(
            self.post(upload, id_col="1"),
            "Group C216 was first uploaded without a Cadet ID column; "
            "set Cadet ID to — none —.",
        )
        make_group("C217", identity_mode="id")
        upload = make_upload([HEADERS, ["Alice Ng", "1"]], group_number="C217")
        self.assertContains(
            self.post(upload),
            "Group C217 was first uploaded with a Cadet ID column; choose a Cadet ID column.",
        )

    def test_success_saves_parsed_and_preference_and_redirects(self):
        upload = make_upload([["Full Name", "Cadet ID"], ["Alice", "9"]])
        response = self.post(upload, id_col="1")
        self.assertRedirects(
            response,
            reverse("roster:upload_preview", args=[upload.pk]),
            fetch_redirect_response=False,
        )
        upload.refresh_from_db()
        self.assertEqual(upload.status, "parsed")
        self.assertEqual((upload.name_col, upload.id_col), (0, 1))
        self.assertEqual(
            upload.parsed,
            {
                "id_mode": True,
                "groups": {"C216": [{"name": "Alice", "external_id": "9", "row": 2}]},
            },
        )
        pref = RosterColumnPreference.get()
        self.assertEqual((pref.name_header, pref.id_header), ("Full Name", "Cadet ID"))

    def test_success_without_id_clears_id_preference(self):
        RosterColumnPreference.objects.create(pk=1, id_header="Cadet ID")
        upload = make_upload([HEADERS, ["Alice", ""]])
        self.post(upload)
        upload.refresh_from_db()
        self.assertIsNone(upload.id_col)
        self.assertFalse(upload.parsed["id_mode"])
        self.assertEqual(RosterColumnPreference.get().id_header, "")

    def test_sample_roster_parses_into_one_group(self):
        headers, rows = read_sheet(SAMPLE_ROSTER.read_bytes())
        result = parse_rows(
            rows, "C216", headers.index("Full Name"), headers.index("Cadet ID")
        )
        self.assertEqual(result.errors, [])
        self.assertEqual({g: len(c) for g, c in result.groups.items()}, {"C216": 15})

    def test_applied_upload_redirects(self):
        upload = make_upload([HEADERS, ["Alice", ""]], status="applied")
        response = self.client.get(columns_url(upload))
        self.assertRedirects(response, reverse("roster:upload"), fetch_redirect_response=False)
        self.assertIn(
            "This upload has already been applied.",
            [str(m) for m in get_messages(response.wsgi_request)],
        )

    def test_instructor_forbidden(self):
        upload = make_upload([HEADERS, ["Alice", ""]])
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(columns_url(upload)).status_code, 403)

    def test_upload_redirects_to_columns_url(self):
        upload = make_upload([HEADERS])
        self.assertEqual(columns_url(upload), f"/roster/upload/{upload.pk}/columns/")
