from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.models import ScoreSet, Subject
from scoring.tests.helpers import make_score_set


def grid_url(group, subject):
    return reverse("scoring:score_grid", args=[group.number, subject.pk])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ScoreGridViewTests(TestCase):
    def setUp(self):
        self.instructor = make_user("inst")
        self.client.force_login(self.instructor)
        self.subject = Subject.objects.create(name="Drill")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.alice, self.bob = self.group.cadets.all()

    def test_lists_only_active_cadets_in_order(self):
        Cadet.objects.create(group=self.group, name="Gone Gary", position=0, is_active=False)
        Cadet.objects.create(group=self.group, name="Cara Lee", position=3)
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual([r["cadet"].name for r in rows], ["Alice Ng", "Bob Ray", "Cara Lee"])
        self.assertEqual([r["number"] for r in rows], [1, 2, 3])
        self.assertNotContains(response, "Gone Gary")
        self.assertContains(response, "C216")
        self.assertContains(response, "Drill")
        self.assertContains(response, "Not saved yet")
        self.assertContains(response, f'name="s-{self.alice.pk}-attentiveness"')
        self.assertContains(response, f'name="c-{self.alice.pk}"')
        self.assertContains(response, 'maxlength="1000"')

    def test_inactive_subject_cannot_start_a_new_score_set(self):
        self.subject.is_active = False
        self.subject.save()
        detail = reverse("roster:group_detail", args=["C216"])
        url = grid_url(self.group, self.subject)
        self.assertRedirects(self.client.get(url), detail, fetch_redirect_response=False)
        response = self.client.post(url, {f"s-{self.alice.pk}-attentiveness": "4"})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.assertFalse(ScoreSet.objects.exists())
        go = reverse("scoring:score_go", args=["C216"]) + f"?subject={self.subject.pk}"
        self.assertRedirects(self.client.get(go), detail, fetch_redirect_response=False)

    def test_existing_score_set_for_inactive_subject_stays_open(self):
        make_score_set(self.instructor, self.subject, self.group, {self.alice: {"attentiveness": 4}})
        self.subject.is_active = False
        self.subject.save()
        self.assertEqual(self.client.get(grid_url(self.group, self.subject)).status_code, 200)

    def test_prefills_own_existing_scores(self):
        make_score_set(
            self.instructor, self.subject, self.group,
            {self.alice: {"attentiveness": 4, "teamwork": 2, "comment": "Solid effort"}},
        )
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertContains(response, "Last saved:")
        self.assertNotContains(response, "Not saved yet")
        self.assertContains(response, "Solid effort")
        row = response.context["rows"][0]
        self.assertEqual(row["cells"][0]["value"], 4)
        self.assertEqual(row["cells"][4]["value"], 2)
        self.assertIsNone(row["cells"][1]["value"])
        self.assertContains(response, '<option value="4" selected>')

    def test_does_not_show_other_instructors_scores(self):
        other = make_user("other")
        make_score_set(
            other, self.subject, self.group,
            {self.alice: {"attentiveness": 5, "comment": "Secret remark"}},
        )
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertNotContains(response, "Secret remark")
        self.assertContains(response, "Not saved yet")
        self.assertIsNone(response.context["rows"][0]["cells"][0]["value"])

    def test_added_since_last_save_badge(self):
        make_score_set(self.instructor, self.subject, self.group, {self.alice: {}, self.bob: {}})
        Cadet.objects.create(group=self.group, name="Cara Lee", position=3)
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertContains(response, "added since your last save", count=1)
        rows = response.context["rows"]
        self.assertEqual([r["added"] for r in rows], [False, False, True])

    def test_no_badge_when_no_saved_set(self):
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertNotContains(response, "added since your last save")

    def test_locked_group_is_read_only(self):
        self.group.status = "locked"
        self.group.save()
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This group is locked and read-only.")
        self.assertContains(response, "disabled")
        self.assertNotContains(response, "Save</button>")

    def test_editable_group_has_save_button(self):
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertContains(response, "Save</button>")
        self.assertNotContains(response, "read-only")

    def test_archived_group_404_for_instructor_readonly_for_admin(self):
        self.group.status = "archived"
        self.group.save()
        self.assertEqual(self.client.get(grid_url(self.group, self.subject)).status_code, 404)
        self.client.force_login(make_user("boss", role="admin"))
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This group is archived and read-only.")

    def test_unknown_group_or_subject_404(self):
        missing_group = reverse("scoring:score_grid", args=["NOPE", self.subject.pk])
        self.assertEqual(self.client.get(missing_group).status_code, 404)
        missing_subject = reverse("scoring:score_grid", args=[self.group.number, 9999])
        self.assertEqual(self.client.get(missing_subject).status_code, 404)

    def test_score_go_redirects_to_grid(self):
        url = reverse("scoring:score_go", args=[self.group.number])
        response = self.client.get(url, {"subject": self.subject.pk})
        self.assertRedirects(response, grid_url(self.group, self.subject))

    def test_score_go_missing_or_invalid_subject_redirects_to_group_detail(self):
        url = reverse("scoring:score_go", args=[self.group.number])
        for query in ({}, {"subject": "abc"}, {"subject": "9999"}):
            with self.subTest(query=query):
                self.assertRedirects(
                    self.client.get(url, query),
                    reverse("roster:group_detail", args=[self.group.number]),
                    fetch_redirect_response=False,
                )

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(grid_url(self.group, self.subject))
        self.assertEqual(response.status_code, 302)
