from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import CadetScore, ScoreSet, Subject
from scoring.tests.helpers import make_score_set


def grid_url(group, subject):
    return reverse("scoring:score_grid", args=[group.number, subject.pk])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ScoreGridSaveTests(TestCase):
    def setUp(self):
        self.instructor = make_user("inst")
        self.client.force_login(self.instructor)
        self.subject = Subject.objects.create(name="Drill")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.alice, self.bob = self.group.cadets.all()
        self.url = grid_url(self.group, self.subject)

    def full_data(self, value="4", cadets=None):
        data = {}
        for cadet in cadets or self.group.cadets.filter(is_active=True):
            for field in ATTRIBUTE_FIELDS:
                data[f"s-{cadet.pk}-{field}"] = value
            data[f"c-{cadet.pk}"] = ""
        return data

    def test_save_requires_at_least_one_score(self):
        response = self.client.post(self.url, self.full_data(value=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter at least one score before saving.")
        self.assertFalse(ScoreSet.objects.exists())

    def test_invalid_score_value_rejected(self):
        data = self.full_data()
        data[f"s-{self.alice.pk}-teamwork"] = "9"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid score for Alice Ng / Teamwork.")
        self.assertFalse(ScoreSet.objects.exists())
        data[f"s-{self.alice.pk}-teamwork"] = "abc"
        response = self.client.post(self.url, data)
        self.assertContains(response, "Invalid score for Alice Ng / Teamwork.")

    def test_long_comment_rejected(self):
        data = self.full_data()
        data[f"c-{self.bob.pk}"] = "x" * 1001
        response = self.client.post(self.url, data)
        self.assertContains(response, "Comment for Bob Ray is longer than 1000 characters.")
        self.assertFalse(ScoreSet.objects.exists())
        data[f"c-{self.bob.pk}"] = "x" * 1000 + "   "
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)

    def test_errors_rerender_with_submitted_values(self):
        data = self.full_data()
        data[f"s-{self.alice.pk}-teamwork"] = "9"
        data[f"s-{self.bob.pk}-attire"] = "2"
        data[f"c-{self.bob.pk}"] = "typed comment"
        response = self.client.post(self.url, data)
        self.assertContains(response, "typed comment")
        bob_row = response.context["rows"][1]
        self.assertEqual(bob_row["cells"][3]["value"], 2)

    def existing_set(self):
        return make_score_set(self.instructor, self.subject, self.group, {})

    def test_first_save_fills_blank_cells_with_3_without_warning(self):
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        data[f"s-{self.bob.pk}-teamwork"] = ""
        response = self.client.post(self.url, data, follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Saved.")
        self.assertNotContains(response, "blank cell(s)")
        self.assertEqual(CadetScore.objects.get(cadet=self.alice).attire, 3)
        self.assertEqual(CadetScore.objects.get(cadet=self.bob).teamwork, 3)
        self.assertEqual(CadetScore.objects.get(cadet=self.alice).teamwork, 4)

    def test_first_save_filled_cells_show_3_and_are_audited(self):
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        response = self.client.post(self.url, data, follow=True)
        alice_row = response.context["rows"][0]
        self.assertEqual(alice_row["cells"][3]["value"], 3)
        event = AuditEvent.objects.get(
            action=actions.SCORE_CHANGED, details__cadet_id=self.alice.pk,
            details__attribute="attire",
        )
        self.assertEqual((event.details["old"], event.details["new"]), (None, 3))

    def test_first_save_all_blank_still_refused(self):
        response = self.client.post(self.url, self.full_data(value=""))
        self.assertContains(response, "Enter at least one score before saving.")
        self.assertFalse(CadetScore.objects.exists())

    def test_later_save_keeps_blank_cells_blank(self):
        self.client.post(self.url, self.full_data())
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        data["confirm_blanks"] = "1"
        self.client.post(self.url, data)
        self.assertIsNone(CadetScore.objects.get(cadet=self.alice).attire)

    def test_blank_warning_shown_on_later_save_and_nothing_changed(self):
        self.existing_set()
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        data[f"s-{self.alice.pk}-teamwork"] = ""
        data[f"s-{self.bob.pk}-teamwork"] = ""
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "3 blank cell(s) across 2 cadet(s) will be counted as 3. Click Save again to confirm.",
        )
        self.assertContains(response, '<input type="hidden" name="confirm_blanks" value="3">')
        self.assertFalse(CadetScore.objects.exists())
        self.assertEqual(AuditEvent.objects.filter(action=actions.SCORE_CHANGED).count(), 0)

    def test_confirm_with_matching_count_saves(self):
        self.existing_set()
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        data["confirm_blanks"] = "1"
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        row = CadetScore.objects.get(cadet=self.alice)
        self.assertIsNone(row.attire)
        self.assertEqual(row.teamwork, 4)

    def test_confirm_with_stale_count_warns_again(self):
        self.existing_set()
        data = self.full_data()
        data[f"s-{self.alice.pk}-attire"] = ""
        data[f"s-{self.alice.pk}-teamwork"] = ""
        data["confirm_blanks"] = "1"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 blank cell(s) across 1 cadet(s)")
        self.assertContains(response, 'name="confirm_blanks" value="2"')
        self.assertFalse(CadetScore.objects.exists())

    def test_full_grid_saves_without_warning(self):
        response = self.client.post(self.url, self.full_data(), follow=True)
        self.assertRedirects(response, self.url)
        self.assertContains(response, "Saved.")
        self.assertNotContains(response, "blank cell(s)")
        self.assertEqual(CadetScore.objects.count(), 2)

    def test_rows_created_for_every_active_cadet_including_all_blank(self):
        Cadet.objects.create(group=self.group, name="Gone Gary", position=0, is_active=False)
        data = self.full_data(cadets=[self.alice])
        # Bob's cells are all blank and become 3 on the first save.
        for field in ATTRIBUTE_FIELDS:
            data[f"s-{self.bob.pk}-{field}"] = ""
        response = self.client.post(self.url, data)
        self.assertRedirects(response, self.url)
        score_set = ScoreSet.objects.get()
        self.assertEqual(
            set(score_set.rows.values_list("cadet__name", flat=True)), {"Alice Ng", "Bob Ray"}
        )
        bob_row = score_set.rows.get(cadet=self.bob)
        self.assertTrue(all(getattr(bob_row, f) == 3 for f in ATTRIBUTE_FIELDS))

    def test_edit_updates_existing_set_not_new_one(self):
        make_score_set(
            self.instructor, self.subject, self.group,
            {self.alice: {"teamwork": 2}, self.bob: {"teamwork": 2}},
        )
        old = ScoreSet.objects.get()
        self.client.post(self.url, self.full_data(value="5"))
        self.assertEqual(ScoreSet.objects.count(), 1)
        self.assertEqual(CadetScore.objects.count(), 2)
        self.assertEqual(CadetScore.objects.get(cadet=self.alice).teamwork, 5)
        self.assertGreaterEqual(ScoreSet.objects.get().updated_at, old.updated_at)

    def test_score_change_audit_has_old_and_new(self):
        make_score_set(
            self.instructor, self.subject, self.group,
            {self.alice: {"teamwork": 2}},
        )
        data = self.full_data(cadets=[self.alice, self.bob])
        data[f"s-{self.alice.pk}-teamwork"] = "5"
        self.client.post(self.url, data)
        event = AuditEvent.objects.get(
            action=actions.SCORE_CHANGED, details__cadet_id=self.alice.pk, details__attribute="teamwork"
        )
        self.assertEqual(
            event.summary, "inst changed Teamwork for Alice Ng (Drill): 2 → 5"
        )
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(event.actor, self.instructor)
        score_set = ScoreSet.objects.get()
        self.assertEqual(
            event.details,
            {
                "cadet_id": self.alice.pk,
                "cadet": "Alice Ng",
                "subject": "Drill",
                "attribute": "teamwork",
                "old": 2,
                "new": 5,
                "score_set_id": score_set.pk,
            },
        )
        blank_to_value = AuditEvent.objects.get(
            action=actions.SCORE_CHANGED, details__cadet_id=self.alice.pk, details__attribute="attire"
        )
        self.assertIn("blank → 4", blank_to_value.summary)

    def test_unchanged_values_not_logged(self):
        self.client.post(self.url, self.full_data())
        before = AuditEvent.objects.count()
        self.client.post(self.url, self.full_data())
        self.assertEqual(AuditEvent.objects.count(), before)
        self.assertEqual(
            AuditEvent.objects.filter(action=actions.SCORE_CHANGED).count(),
            2 * len(ATTRIBUTE_FIELDS),
        )

    def test_comment_change_logged(self):
        data = self.full_data()
        data[f"c-{self.alice.pk}"] = "  Good work  "
        self.client.post(self.url, data)
        event = AuditEvent.objects.get(action=actions.COMMENT_CHANGED)
        self.assertEqual(
            event.details,
            {
                "cadet_id": self.alice.pk,
                "cadet": "Alice Ng",
                "subject": "Drill",
                "old": "",
                "new": "Good work",
                "score_set_id": ScoreSet.objects.get().pk,
            },
        )
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(CadetScore.objects.get(cadet=self.alice).comment, "Good work")
        self.assertEqual(AuditEvent.objects.filter(action=actions.COMMENT_CHANGED).count(), 1)

    def test_locked_group_post_forbidden(self):
        self.group.status = "locked"
        self.group.save()
        response = self.client.post(self.url, self.full_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ScoreSet.objects.exists())

    def test_inactive_cadet_fields_ignored(self):
        gone = Cadet.objects.create(group=self.group, name="Gone Gary", position=0, is_active=False)
        data = self.full_data()
        for field in ATTRIBUTE_FIELDS:
            data[f"s-{gone.pk}-{field}"] = "5"
        self.client.post(self.url, data)
        self.assertFalse(CadetScore.objects.filter(cadet=gone).exists())

    def test_badge_cleared_after_save(self):
        make_score_set(self.instructor, self.subject, self.group, {self.alice: {"teamwork": 3}})
        carol = Cadet.objects.create(group=self.group, name="Cara Lee", position=3)
        response = self.client.get(self.url)
        self.assertContains(response, "added since your last save")
        self.client.post(self.url, self.full_data())
        response = self.client.get(self.url)
        self.assertNotContains(response, "added since your last save")
        self.assertTrue(CadetScore.objects.filter(cadet=carol).exists())
