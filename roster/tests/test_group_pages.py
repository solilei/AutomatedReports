from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.models import Subject
from scoring.tests.helpers import make_score_set


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class GroupPageTests(TestCase):
    def setUp(self):
        self.instructor = make_user("inst")
        self.client.force_login(self.instructor)

    def test_home_dropdown_lists_active_and_locked_not_archived(self):
        make_group("C218", cadets=("A",))
        make_group("C216", cadets=("B",))
        make_group("C217", cadets=("C",), status="locked")
        make_group("C219", cadets=("D",), status="archived")
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'action="{reverse("roster:group_go")}"')
        self.assertContains(response, 'name="number"')
        self.assertContains(response, "C216 (course 216.18)")
        self.assertContains(response, "C217 (course 216.18) — locked")
        self.assertContains(response, "C218 (course 216.18)")
        self.assertNotContains(response, "C219")
        content = response.content.decode()
        self.assertLess(content.index("C216"), content.index("C217"))
        self.assertLess(content.index("C217"), content.index("C218"))
        self.assertNotContains(response, "No groups yet.")

    def test_home_no_groups(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "No groups yet.")
        self.assertNotContains(response, reverse("roster:upload"))
        self.client.force_login(make_user("boss", role="admin"))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "No groups yet.")
        self.assertContains(response, reverse("roster:upload"))

    def test_group_go_redirects(self):
        make_group("C216")
        response = self.client.get(reverse("roster:group_go"), {"number": "c216"})
        self.assertRedirects(response, reverse("roster:group_detail", args=["C216"]))

    def test_group_go_unknown_number(self):
        response = self.client.get(reverse("roster:group_go"), {"number": "NOPE"})
        self.assertRedirects(response, reverse("home"))
        self.assertIn("Group not found.", [str(m) for m in get_messages(response.wsgi_request)])
        response = self.client.get(reverse("roster:group_go"))
        self.assertRedirects(response, reverse("home"))

    def test_group_detail_shows_summary(self):
        group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        Cadet.objects.create(group=group, name="Gone", position=9, is_active=False)
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "C216")
        self.assertContains(response, "216.18")
        self.assertContains(response, "Active")
        self.assertContains(response, "2 active cadets")

    def test_group_detail_subject_dropdown_only_active_subjects(self):
        make_group("C216")
        Subject.objects.create(name="Drill")
        Subject.objects.create(name="Old Subject", is_active=False)
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, f'action="{reverse("scoring:score_go", args=["C216"])}"')
        self.assertContains(response, 'name="subject"')
        self.assertContains(response, "Drill")
        self.assertNotContains(response, "Old Subject")

    def test_group_detail_lists_only_my_score_sets(self):
        group = make_group("C216")
        drill = Subject.objects.create(name="Drill")
        tactics = Subject.objects.create(name="Tactics")
        make_score_set(self.instructor, drill, group, {})
        make_score_set(make_user("other"), tactics, group, {})
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, reverse("scoring:score_grid", args=["C216", drill.pk]))
        self.assertNotContains(response, reverse("scoring:score_grid", args=["C216", tactics.pk]))

    def test_archived_group_detail_404_for_instructor(self):
        make_group("C216", status="archived")
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertEqual(response.status_code, 404)
        self.client.force_login(make_user("boss", role="admin"))
        response = self.client.get(reverse("roster:group_detail", args=["C216"]))
        self.assertEqual(response.status_code, 200)

    def test_unknown_group_detail_404(self):
        self.assertEqual(self.client.get(reverse("roster:group_detail", args=["NOPE"])).status_code, 404)

    def test_group_list_admin_only_and_includes_archived(self):
        group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        Cadet.objects.create(group=group, name="Gone", position=9, is_active=False)
        make_group("C219", cadets=("D",), status="archived")
        make_score_set(self.instructor, Subject.objects.create(name="Drill"), group, {})
        self.assertEqual(self.client.get(reverse("roster:group_list")).status_code, 403)
        self.client.force_login(make_user("boss", role="admin"))
        response = self.client.get(reverse("roster:group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, reverse("roster:group_detail", args=["C219"]))
        self.assertContains(response, "Archived")
        row = next(r for r in response.context["groups"] if r.number == "C216")
        self.assertEqual((row.active_count, row.inactive_count, row.score_set_count), (2, 1, 1))

    def test_nav_groups_link_admin_only(self):
        self.assertNotContains(self.client.get(reverse("home")), reverse("roster:group_list"))
        self.client.force_login(make_user("boss", role="admin"))
        self.assertContains(self.client.get(reverse("home")), reverse("roster:group_list"))

    def test_score_go_missing_subject_redirects_to_group_detail(self):
        make_group("C216")
        detail = reverse("roster:group_detail", args=["C216"])
        self.assertRedirects(self.client.get(reverse("scoring:score_go", args=["C216"])), detail)
        self.assertRedirects(
            self.client.get(reverse("scoring:score_go", args=["C216"]), {"subject": "999"}), detail
        )

    def test_grid_links_back_to_group(self):
        group = make_group("C216")
        subject = Subject.objects.create(name="Drill")
        response = self.client.get(reverse("scoring:score_grid", args=[group.number, subject.pk]))
        self.assertContains(response, reverse("roster:group_detail", args=["C216"]))
        self.assertContains(response, "← Group C216")
