import re

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from roster.models import Group
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS, ATTRIBUTES
from scoring.models import Subject
from scoring.tests.helpers import make_score_set


def scores(value=3, **overrides):
    values = {field: value for field in ATTRIBUTE_FIELDS}
    values.update(overrides)
    return values


def rows_of(html):
    return re.findall(r"<tr[^>]*>.*?</tr>", html, flags=re.S)


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ResultsPageTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.viewer = make_user("viewer", full_name="Vera Viewer")
        self.other = make_user("other", full_name="Otto Other")
        self.drill = Subject.objects.create(name="Drill")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray", "Cy Dee"))
        self.alice, self.bob, self.cy = self.group.cadets.all()
        self.url = reverse("scoring:results", args=["C216"])

    def get(self, user=None):
        self.client.force_login(user or self.viewer)
        return self.client.get(self.url)

    def test_columns_and_order(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(4), self.bob: scores(3)})
        response = self.get()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        headers = re.findall(r"<th[^>]*>(.*?)</th>", rows_of(html)[0], flags=re.S)
        self.assertEqual(
            [h.strip() for h in headers],
            ["No.", "Name"] + [label for _f, label, _h in ATTRIBUTES] + ["Total"],
        )
        self.assertLess(html.index("Alice Ng"), html.index("Bob Ray"))
        self.assertLess(html.index("Bob Ray"), html.index("Cy Dee"))

    def test_values_whole_numbers_and_band_classes(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(5, attire=2)})
        make_score_set(self.other, self.drill, self.group, {self.alice: scores(4, attire=3)})
        html = self.get().content.decode()
        alice_row = next(r for r in rows_of(html) if "Alice Ng" in r)
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", alice_row, flags=re.S)
        value_cells = cells[-7:]
        for attrs, text in value_cells:
            self.assertNotIn(".", text)
        self.assertEqual([t.strip() for _a, t in value_cells], ["5", "5", "5", "3", "5", "5", "28"])
        self.assertIn("band-5", value_cells[0][0])
        self.assertIn("band-3", value_cells[3][0])

    def test_no_data_row(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(4)})
        html = self.get().content.decode()
        bob_row = next(r for r in rows_of(html) if "Bob Ray" in r)
        self.assertIn('colspan="7"', bob_row)
        self.assertIn("no data", bob_row)

    def test_flag_marker(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(2), self.bob: scores(3)})
        html = self.get().content.decode()
        alice_row = next(r for r in rows_of(html) if "Alice Ng" in r)
        bob_row = next(r for r in rows_of(html) if "Bob Ray" in r)
        self.assertIn("flagged", alice_row)
        self.assertIn('<span class="flag">Below C – HGS consultation</span>', alice_row)
        self.assertNotIn("flagged", bob_row)
        self.assertNotIn("Below C", bob_row)

    def test_summary_count_and_key(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(4)})
        make_score_set(self.other, self.drill, self.group, {self.alice: scores(4)})
        response = self.get()
        self.assertContains(response, "Based on 2 saved score sets.")
        for word in ("Excellent", "Unacceptable"):
            self.assertContains(response, word)
        for hex_code in ("66FF33", "C6E0B4", "E2EFDA", "FFC000", "FF0000"):
            self.assertContains(response, hex_code)

    def test_summary_singular(self):
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(4)})
        self.assertContains(self.get(), "Based on 1 saved score set.")

    def test_inactive_cadets_hidden(self):
        self.cy.is_active = False
        self.cy.save()
        make_score_set(self.viewer, self.drill, self.group, {self.alice: scores(4)})
        response = self.get()
        self.assertNotContains(response, "Cy Dee")

    def test_page_does_not_contain_instructor_names(self):
        make_score_set(self.other, self.drill, self.group, {self.alice: scores(4)})
        response = self.get(self.viewer)
        self.assertNotContains(response, "other")
        self.assertNotContains(response, "Otto Other")

    def test_archived_group_admin_only(self):
        self.group.status = Group.Status.ARCHIVED
        self.group.save()
        self.assertEqual(self.get(self.viewer).status_code, 404)
        self.assertEqual(self.get(self.admin).status_code, 200)

    def test_unknown_group_404(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("scoring:results", args=["NOPE"]))
        self.assertEqual(response.status_code, 404)

    def test_group_page_links_to_results(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, self.url)
