from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Cadet, DeletedGroupNumber, Group
from roster.services import check_groups
from roster.tests.helpers import make_group
from scoring.attributes import ATTRIBUTE_FIELDS
from scoring.models import CadetScore, ScoreSet, Subject
from scoring.tests.helpers import make_score_set

ACTION_NAMES = ["group_lock", "group_unlock", "group_archive", "group_unarchive", "group_delete"]


def url(name, number="C216"):
    return reverse(f"roster:{name}", args=[number])


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class GroupLifecycleTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def status_of(self, number="C216"):
        return Group.objects.get(number=number).status

    def test_instructor_forbidden_for_all_actions(self):
        make_group("C216")
        self.client.force_login(make_user("inst"))
        for name in ACTION_NAMES:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(url(name)).status_code, 403)
        self.assertEqual(self.client.get(url("group_delete")).status_code, 403)
        self.assertEqual(self.status_of(), "active")
        self.assertFalse(AuditEvent.objects.exists())

    def test_lock_unlock(self):
        make_group("C216")
        response = self.client.post(url("group_lock"))
        self.assertRedirects(response, url("group_detail"))
        self.assertEqual(self.status_of(), "locked")
        event = AuditEvent.objects.get(action=actions.GROUP_LOCKED)
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(event.actor, self.admin)
        self.assertRedirects(self.client.post(url("group_unlock")), url("group_detail"))
        self.assertEqual(self.status_of(), "active")
        self.assertTrue(AuditEvent.objects.filter(action=actions.GROUP_UNLOCKED).exists())

    def test_actions_are_post_only(self):
        make_group("C216")
        for name in ACTION_NAMES[:4]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(url(name)).status_code, 405)
        self.assertEqual(self.status_of(), "active")

    def test_locked_group_rejects_scoring_post(self):
        group = make_group("C216", cadets=("Alice Ng",))
        subject = Subject.objects.create(name="Drill")
        self.client.post(url("group_lock"))
        cadet = group.cadets.get()
        data = {f"s-{cadet.pk}-{field}": "4" for field in ATTRIBUTE_FIELDS}
        data[f"c-{cadet.pk}"] = ""
        grid = reverse("scoring:score_grid", args=["C216", subject.pk])
        self.assertEqual(self.client.post(grid, data).status_code, 403)
        self.assertFalse(ScoreSet.objects.exists())

    def test_archive_from_active_and_locked(self):
        make_group("C216")
        make_group("C217", status="locked")
        self.assertRedirects(self.client.post(url("group_archive")), url("group_detail"))
        self.assertRedirects(
            self.client.post(url("group_archive", "C217")), url("group_detail", "C217")
        )
        self.assertEqual(self.status_of("C216"), "archived")
        self.assertEqual(self.status_of("C217"), "archived")
        self.assertEqual(AuditEvent.objects.filter(action=actions.GROUP_ARCHIVED).count(), 2)

    def test_archived_hidden_from_home_dropdown(self):
        make_group("C216")
        make_group("C217")
        self.client.post(url("group_archive"))
        for user in (self.admin, make_user("inst")):
            self.client.force_login(user)
            response = self.client.get(reverse("home"))
            self.assertNotContains(response, "C216")
            self.assertContains(response, "C217")

    def test_unarchive(self):
        make_group("C216", status="archived")
        self.assertRedirects(self.client.post(url("group_unarchive")), url("group_detail"))
        self.assertEqual(self.status_of(), "active")
        self.assertTrue(AuditEvent.objects.filter(action=actions.GROUP_UNARCHIVED).exists())

    def test_unarchive_restores_locked_status(self):
        make_group("C216", status="locked")
        self.client.post(url("group_archive"))
        self.assertEqual(self.status_of(), "archived")
        self.client.post(url("group_unarchive"))
        self.assertEqual(self.status_of(), "locked")

    def test_unarchive_restores_active_status(self):
        make_group("C216")
        self.client.post(url("group_archive"))
        self.client.post(url("group_unarchive"))
        self.assertEqual(self.status_of(), "active")

    def test_invalid_transition_no_change(self):
        cases = [
            ("group_lock", "locked", "Cannot lock a group that is locked."),
            ("group_lock", "archived", "Cannot lock a group that is archived."),
            ("group_unlock", "active", "Cannot unlock a group that is active."),
            ("group_unlock", "archived", "Cannot unlock a group that is archived."),
            ("group_archive", "archived", "Cannot archive a group that is archived."),
            ("group_unarchive", "active", "Cannot unarchive a group that is active."),
            ("group_unarchive", "locked", "Cannot unarchive a group that is locked."),
        ]
        for name, status, message in cases:
            with self.subTest(name=name, status=status):
                Group.objects.all().delete()
                make_group("C216", status=status)
                response = self.client.post(url(name))
                self.assertRedirects(response, url("group_detail"))
                self.assertIn(message, messages_of(response))
                self.assertEqual(self.status_of(), status)
        self.assertFalse(AuditEvent.objects.exists())

    def test_delete_requires_archived(self):
        for status in ("active", "locked"):
            with self.subTest(status=status):
                Group.objects.all().delete()
                make_group("C216", status=status)
                response = self.client.post(url("group_delete"), {"confirm_number": "C216"})
                self.assertRedirects(response, url("group_detail"))
                self.assertIn(
                    f"Cannot delete a group that is {status}.", messages_of(response)
                )
                self.assertTrue(Group.objects.filter(number="C216").exists())
                self.assertEqual(self.client.get(url("group_delete")).status_code, 302)
        self.assertFalse(DeletedGroupNumber.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_delete_requires_typed_number(self):
        make_group("C216", status="archived")
        self.assertContains(self.client.get(url("group_delete")), "C216")
        for typed in ("", "c216", "C216 ", "C217"):
            with self.subTest(typed=typed):
                response = self.client.post(url("group_delete"), {"confirm_number": typed})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Type the group number to confirm.")
                self.assertTrue(Group.objects.filter(number="C216").exists())
        self.assertFalse(DeletedGroupNumber.objects.exists())

    def test_delete_removes_group_data_and_records_number(self):
        group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        make_group("C217", cadets=("Other",))
        subject = Subject.objects.create(name="Drill")
        alice, bob = group.cadets.all()
        make_score_set(self.admin, subject, group, {alice: {"teamwork": 4}, bob: {"teamwork": 3}})
        other = Group.objects.get(number="C217")
        make_score_set(self.admin, subject, other, {other.cadets.get(): {"teamwork": 5}})
        Group.objects.filter(number="C216").update(status="archived")
        response = self.client.post(url("group_delete"), {"confirm_number": "C216"})
        self.assertRedirects(response, reverse("roster:group_list"))
        self.assertFalse(Group.objects.filter(number="C216").exists())
        self.assertFalse(Cadet.objects.filter(name__in=["Alice Ng", "Bob Ray"]).exists())
        self.assertEqual(ScoreSet.objects.count(), 1)
        self.assertEqual(CadetScore.objects.count(), 1)
        self.assertTrue(DeletedGroupNumber.objects.filter(number="C216").exists())
        event = AuditEvent.objects.get(action=actions.GROUP_DELETED)
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(
            event.details, {"cadets": 2, "score_sets": 1}
        )

    def test_deleted_number_cannot_be_reused_by_upload(self):
        make_group("C216", status="archived")
        self.client.post(url("group_delete"), {"confirm_number": "C216"})
        errors = check_groups(["C216"], id_mode=False)
        self.assertEqual(errors, ["Group C216 was deleted and its number cannot be reused."])

    def test_audit_events_kept_after_delete(self):
        make_group("C216")
        self.client.post(url("group_lock"))
        self.client.post(url("group_archive"))
        self.client.post(url("group_delete"), {"confirm_number": "C216"})
        recorded = list(
            AuditEvent.objects.filter(group_number="C216")
            .order_by("pk")
            .values_list("action", flat=True)
        )
        self.assertEqual(
            recorded, [actions.GROUP_LOCKED, actions.GROUP_ARCHIVED, actions.GROUP_DELETED]
        )

    def test_unknown_group_404(self):
        for name in ACTION_NAMES:
            with self.subTest(name=name):
                self.assertEqual(self.client.post(url(name, "NOPE")).status_code, 404)

    def test_group_page_buttons_follow_status(self):
        cases = {
            "active": {"group_lock", "group_archive"},
            "locked": {"group_unlock", "group_archive"},
            "archived": {"group_unarchive", "group_delete"},
        }
        for status, shown in cases.items():
            with self.subTest(status=status):
                Group.objects.all().delete()
                make_group("C216", status=status)
                response = self.client.get(url("group_detail"))
                for name in ACTION_NAMES:
                    link = url(name)
                    if name in shown:
                        self.assertContains(response, f'"{link}"')
                    else:
                        self.assertNotContains(response, f'"{link}"')

    def test_group_page_hides_buttons_from_instructors(self):
        make_group("C216")
        self.client.force_login(make_user("inst"))
        response = self.client.get(url("group_detail"))
        for name in ACTION_NAMES:
            self.assertNotContains(response, f'"{url(name)}"')
