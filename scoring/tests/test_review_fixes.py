from io import BytesIO

from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from accounts.tests.helpers import make_user
from roster.models import Cadet, Group
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import CadetScore, ScoreSet, Subject
from scoring.tests.helpers import make_score_set


def grid_post(cadets, value="4", comment="", cadet_ids=None):
    data = {
        "cadet_ids": cadet_ids if cadet_ids is not None else ",".join(str(c.pk) for c in cadets)
    }
    for cadet in cadets:
        data.update({f"s-{cadet.pk}-{field}": value for field in ATTRIBUTE_FIELDS})
        data[f"c-{cadet.pk}"] = comment
    return data


def scores(value):
    return {field: value for field in ATTRIBUTE_FIELDS}


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class GridRosterChangeTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("inst"))
        self.subject = Subject.objects.create(name="Drill")
        self.group = make_group("C216")
        self.url = reverse("scoring:score_grid", args=["C216", self.subject.pk])

    def test_page_carries_the_cadet_list(self):
        ids = ",".join(str(c.pk) for c in self.group.cadets.all())
        self.assertContains(self.client.get(self.url), f'name="cadet_ids" value="{ids}"')

    def test_cadet_added_after_page_load_blocks_first_save(self):
        shown = list(self.group.cadets.all())
        Cadet.objects.create(group=self.group, name="New Cadet", position=3)
        response = self.client.post(self.url, grid_post(shown))
        self.assertContains(response, "The cadet list changed")
        self.assertContains(response, "New Cadet")
        self.assertFalse(ScoreSet.objects.exists())
        # Saving from the refreshed page works, with the new cadet included.
        response = self.client.post(self.url, grid_post(list(self.group.cadets.all())))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CadetScore.objects.count(), 3)

    def test_unchanged_list_saves(self):
        response = self.client.post(self.url, grid_post(list(self.group.cadets.all())))
        self.assertEqual(response.status_code, 302)

    def test_garbled_cadet_list_counts_as_changed(self):
        response = self.client.post(
            self.url, grid_post(list(self.group.cadets.all()), cadet_ids="x,y")
        )
        self.assertContains(response, "The cadet list changed")


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class CommentLineBreakTests(TestCase):
    def test_crlf_comment_at_browser_limit_is_accepted_and_stored_with_lf(self):
        self.client.force_login(make_user("inst"))
        subject = Subject.objects.create(name="Drill")
        group = make_group("C216", cadets=("Alice Ng",))
        # 999 characters as the browser counts them; 1008 as sent, with \r\n line breaks.
        comment = (("a" * 99 + "\r\n") * 10)[:-2]
        response = self.client.post(
            reverse("scoring:score_grid", args=["C216", subject.pk]),
            grid_post(list(group.cadets.all()), comment=comment),
        )
        self.assertEqual(response.status_code, 302)
        stored = CadetScore.objects.get().comment
        self.assertNotIn("\r", stored)
        self.assertEqual(len(stored), 999)


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class SubjectScopedResultsTests(TestCase):
    """Instructors see results and colleagues' score sets only for subjects they scored."""

    def setUp(self):
        self.x = make_user("x", full_name="Xena X")
        self.y = make_user("y", full_name="Yuri Y")
        self.z = make_user("z", full_name="Zoe Z")
        self.admin = make_user("boss", role="admin")
        self.nav = Subject.objects.create(name="Navigation")
        self.law = Subject.objects.create(name="Air Law")
        self.group = make_group("C216", cadets=("Alice Ng",))
        alice = self.group.cadets.get()
        self.x_nav = make_score_set(self.x, self.nav, self.group, {alice: scores(5)})
        self.x_law = make_score_set(self.x, self.law, self.group, {alice: scores(1)})
        self.y_nav = make_score_set(self.y, self.nav, self.group, {alice: scores(4)})
        self.z_law = make_score_set(self.z, self.law, self.group, {alice: scores(2)})
        self.results = reverse("scoring:results", args=["C216"])

    def detail(self, score_set):
        return self.client.get(reverse("scoring:score_set_detail", args=[score_set.pk]))

    def test_instructor_sees_only_their_subjects(self):
        self.client.force_login(self.y)  # Navigation only: (5 + 4) / 2 rounds to 5
        response = self.client.get(self.results)
        self.assertContains(response, '<td class="band-5">5</td>')
        self.assertContains(response, "Based on 2 saved score sets.")
        self.assertContains(response, "Showing your subject only: Navigation.")

    def test_instructor_can_narrow_to_one_subject(self):
        self.client.force_login(self.x)
        response = self.client.get(self.results, {"subject": self.law.pk})  # (1 + 2) / 2 → 2
        self.assertContains(response, '<td class="band-2">2</td>')
        self.assertContains(response, "Showing Air Law only.")
        self.assertContains(response, "All my subjects")

    def test_subject_outside_own_subjects_is_ignored(self):
        self.client.force_login(self.y)
        response = self.client.get(self.results, {"subject": self.law.pk})
        self.assertContains(response, "Showing your subject only: Navigation.")

    def test_admin_sees_all_subjects(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.results)  # (5 + 1 + 4 + 2) / 4 = 3
        self.assertContains(response, '<td class="band-3">3</td>')
        self.assertContains(response, "Based on 4 saved score sets.")

    def test_instructor_without_scores_sees_message(self):
        self.client.force_login(make_user("new"))
        response = self.client.get(self.results)
        self.assertContains(response, "You haven't saved scores for this group yet")
        self.assertNotContains(response, "Alice Ng")

    def test_colleague_score_set_visible_for_shared_subject(self):
        self.client.force_login(self.y)
        response = self.detail(self.x_nav)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Xena X")

    def test_colleague_score_set_hidden_for_other_subject(self):
        self.client.force_login(self.y)
        self.assertEqual(self.detail(self.x_law).status_code, 403)
        self.assertEqual(self.detail(self.z_law).status_code, 403)

    def test_shared_subject_in_another_group_does_not_count(self):
        other_group = make_group("C217", cadets=("Bob Ray",))
        other_set = make_score_set(self.z, self.nav, other_group, {other_group.cadets.get(): scores(3)})
        self.client.force_login(self.y)
        self.assertEqual(self.detail(other_set).status_code, 403)

    def test_archived_group_hides_colleague_sets(self):
        Group.objects.filter(pk=self.group.pk).update(status=Group.Status.ARCHIVED)
        self.client.force_login(self.y)
        self.assertEqual(self.detail(self.x_nav).status_code, 403)

    def test_group_page_lists_colleague_sets_for_shared_subjects(self):
        self.client.force_login(self.y)
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, "Navigation — Xena X")
        self.assertContains(response, reverse("scoring:score_set_detail", args=[self.x_nav.pk]))
        self.assertNotContains(response, "Zoe Z")


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ExportRecalculationTests(TestCase):
    def test_export_asks_excel_to_calculate_totals_on_open(self):
        self.client.force_login(make_user("boss", role="admin"))
        make_group("C216")
        response = self.client.get(reverse("scoring:export", args=["C216"]))
        self.assertTrue(load_workbook(BytesIO(response.content)).calculation.fullCalcOnLoad)
