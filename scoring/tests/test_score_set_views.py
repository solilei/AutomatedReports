from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from roster.models import Cadet, Group
from roster.tests.helpers import make_group
from scoring.models import Subject
from scoring.tests.helpers import make_score_set


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class ScoreSetViewTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.instructor = make_user("inst", full_name="Ivy Instructor")
        self.other = make_user("other", full_name="Otto Other")
        self.drill = Subject.objects.create(name="Drill")
        self.pt = Subject.objects.create(name="PT")
        self.group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        self.alice, self.bob = self.group.cadets.all()

    def test_my_score_sets_only_mine(self):
        make_score_set(self.instructor, self.drill, self.group, {self.alice: {"teamwork": 3}})
        make_score_set(self.other, self.pt, self.group, {self.alice: {"teamwork": 4}})
        archived = make_group("C217", cadets=("Cy Dee",), status=Group.Status.ARCHIVED)
        make_score_set(self.instructor, self.pt, archived, {archived.cadets.get(): {"teamwork": 2}})
        self.client.force_login(self.instructor)
        response = self.client.get(reverse("scoring:my_score_sets"))
        self.assertEqual(response.status_code, 200)
        sets = list(response.context["score_sets"])
        self.assertEqual([(s.group.number, s.subject.name) for s in sets], [("C216", "Drill")])
        self.assertContains(response, reverse("scoring:score_grid", args=["C216", self.drill.pk]))
        self.assertNotContains(response, "C217")

        self.client.force_login(self.admin)
        make_score_set(self.admin, self.pt, archived, {archived.cadets.get(): {"teamwork": 2}})
        response = self.client.get(reverse("scoring:my_score_sets"))
        self.assertContains(response, "C217")

    def test_group_score_sets_admin_only(self):
        make_score_set(self.instructor, self.drill, self.group, {self.alice: {"teamwork": 3}})
        make_score_set(self.other, self.pt, self.group, {self.alice: {"teamwork": 4}})
        url = reverse("scoring:group_score_sets", args=["C216"])
        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ivy Instructor")
        self.assertContains(response, "Otto Other")
        self.assertContains(response, "Drill")
        self.assertContains(response, "PT")
        self.assertEqual(self.client.get(reverse("scoring:group_score_sets", args=["NOPE"])).status_code, 404)

    def test_score_set_detail_admin_only(self):
        inactive = Cadet.objects.create(group=self.group, name="Gone Gary", position=3, is_active=False)
        score_set = make_score_set(
            self.instructor, self.drill, self.group,
            {
                self.alice: {"attentiveness": 4, "comment": "Solid effort"},
                inactive: {"teamwork": 2},
                self.bob: {"teamwork": 5},
            },
        )
        url = reverse("scoring:score_set_detail", args=[score_set.pk])
        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Solid effort")
        self.assertContains(response, "—")
        self.assertContains(response, "Gone Gary (inactive)")
        content = response.content.decode()
        self.assertLess(content.index("Bob Ray"), content.index("Gone Gary"))
        self.assertEqual(self.client.get(reverse("scoring:score_set_detail", args=[9999])).status_code, 404)

    def test_instructor_cannot_view_other_set_by_id(self):
        score_set = make_score_set(self.other, self.drill, self.group, {self.alice: {"teamwork": 3}})
        self.client.force_login(self.instructor)
        response = self.client.get(reverse("scoring:score_set_detail", args=[score_set.pk]))
        self.assertEqual(response.status_code, 403)

    def test_deactivated_instructor_marked(self):
        make_score_set(self.other, self.drill, self.group, {self.alice: {"teamwork": 3}})
        self.other.is_active = False
        self.other.save()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("scoring:group_score_sets", args=["C216"]))
        self.assertContains(response, "Otto Other (deactivated)")
