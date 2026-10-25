from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Group
from roster.tests.helpers import make_group
from scoring.models import Subject
from scoring.tests.helpers import make_score_set


def url(name, subject=None):
    return reverse(f"scoring:{name}", args=[subject.pk] if subject else [])


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class SubjectTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def test_instructor_forbidden(self):
        subject = Subject.objects.create(name="Drill")
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(url("subject_list")).status_code, 403)
        self.assertEqual(self.client.get(url("subject_create")).status_code, 403)
        self.assertEqual(self.client.get(url("subject_edit", subject)).status_code, 403)
        self.assertEqual(self.client.post(url("subject_toggle", subject)).status_code, 403)

    def test_create_subject(self):
        response = self.client.post(url("subject_create"), {"name": "  Leadership  "})
        self.assertRedirects(response, url("subject_list"))
        subject = Subject.objects.get()
        self.assertEqual(subject.name, "Leadership")
        self.assertTrue(subject.is_active)
        self.assertEqual(str(subject), "Leadership")
        self.assertTrue(AuditEvent.objects.filter(action=actions.SUBJECT_CREATED).exists())

    def test_duplicate_name_case_insensitive_rejected(self):
        Subject.objects.create(name="Drill")
        response = self.client.post(url("subject_create"), {"name": "dRiLl"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A subject with this name already exists.")
        self.assertEqual(Subject.objects.count(), 1)

    def test_rename_to_own_name_with_different_case_allowed(self):
        subject = Subject.objects.create(name="drill")
        response = self.client.post(url("subject_edit", subject), {"name": "Drill"})
        self.assertRedirects(response, url("subject_list"))
        subject.refresh_from_db()
        self.assertEqual(subject.name, "Drill")

    def test_rename_subject_logs_old_and_new(self):
        subject = Subject.objects.create(name="Drill")
        response = self.client.post(url("subject_edit", subject), {"name": "Marching"})
        self.assertRedirects(response, url("subject_list"))
        subject.refresh_from_db()
        self.assertEqual(subject.name, "Marching")
        event = AuditEvent.objects.get(action=actions.SUBJECT_RENAMED)
        self.assertEqual(event.details, {"old": "Drill", "new": "Marching"})

    def test_rename_refused_when_used_by_locked_or_archived_group(self):
        for status in ("locked", "archived"):
            with self.subTest(status=status):
                Group.objects.all().delete()
                subject, _ = Subject.objects.get_or_create(name="Drill")
                group = make_group("C216", cadets=("Alice Ng",), status=status)
                make_score_set(self.admin, subject, group, {group.cadets.get(): {}})
                response = self.client.post(url("subject_edit", subject), {"name": "Marching"})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "cannot be renamed")
                subject.refresh_from_db()
                self.assertEqual(subject.name, "Drill")
        self.assertFalse(AuditEvent.objects.filter(action=actions.SUBJECT_RENAMED).exists())

    def test_rename_allowed_when_used_only_by_active_groups(self):
        subject = Subject.objects.create(name="Drill")
        group = make_group("C216", cadets=("Alice Ng",))
        make_score_set(self.admin, subject, group, {group.cadets.get(): {}})
        response = self.client.post(url("subject_edit", subject), {"name": "Marching"})
        self.assertRedirects(response, url("subject_list"))
        subject.refresh_from_db()
        self.assertEqual(subject.name, "Marching")

    def test_toggle_deactivates_and_reactivates(self):
        subject = Subject.objects.create(name="Drill")
        self.assertRedirects(self.client.post(url("subject_toggle", subject)), url("subject_list"))
        subject.refresh_from_db()
        self.assertFalse(subject.is_active)
        self.assertTrue(AuditEvent.objects.filter(action=actions.SUBJECT_DEACTIVATED).exists())
        self.client.post(url("subject_toggle", subject))
        subject.refresh_from_db()
        self.assertTrue(subject.is_active)
        self.assertTrue(AuditEvent.objects.filter(action=actions.SUBJECT_REACTIVATED).exists())

    def test_toggle_requires_post(self):
        subject = Subject.objects.create(name="Drill")
        self.assertEqual(self.client.get(url("subject_toggle", subject)).status_code, 405)

    def test_list_shows_subjects_and_nav_link_for_admin(self):
        Subject.objects.create(name="Drill")
        Subject.objects.create(name="Marching", is_active=False)
        response = self.client.get(url("subject_list"))
        self.assertContains(response, "Drill")
        self.assertContains(response, "Marching")
        self.assertContains(response, f'href="{url("subject_list")}"')

    def test_nav_link_hidden_from_instructor(self):
        self.client.force_login(make_user("inst"))
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, f'href="{url("subject_list")}"')

    def test_no_delete_url_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("scoring:subject_delete")
