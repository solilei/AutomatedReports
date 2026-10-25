from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from roster.models import Cadet
from roster.tests.helpers import make_group
from scoring.models import CadetScore, Subject
from scoring.tests.helpers import make_score_set

SCORES = {
    "attentiveness": 4,
    "motivation": 4,
    "discipline": 4,
    "attire": 4,
    "teamwork": 4,
    "communication": 4,
}


def list_url(number="C216"):
    return reverse("roster:cadet_list", args=[number])


def delete_url(pk):
    return reverse("roster:cadet_delete", args=[pk])


def messages_of(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class CadetManagementTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.client.force_login(self.admin)

    def test_instructor_forbidden(self):
        group = make_group("C216")
        cadet = group.cadets.first()
        self.client.force_login(make_user("inst"))
        self.assertEqual(self.client.get(list_url()).status_code, 403)
        self.assertEqual(self.client.get(delete_url(cadet.pk)).status_code, 403)
        self.assertEqual(self.client.post(delete_url(cadet.pk)).status_code, 403)
        self.assertTrue(Cadet.objects.filter(pk=cadet.pk).exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_list_includes_inactive(self):
        group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        Cadet.objects.filter(name="Bob Ray").update(is_active=False)
        response = self.client.get(list_url())
        self.assertContains(response, "Alice Ng")
        self.assertContains(response, "Bob Ray")
        self.assertContains(response, "Inactive")
        self.assertContains(response, "Active")
        self.assertContains(response, delete_url(group.cadets.get(name="Bob Ray").pk))

    def test_get_does_not_delete(self):
        group = make_group("C216", cadets=("Alice Ng",))
        cadet = group.cadets.get()
        response = self.client.get(delete_url(cadet.pk))
        self.assertContains(
            response,
            "Permanently delete Alice Ng from C216 and all 0 of their scores? "
            "This cannot be undone.",
        )
        self.assertTrue(Cadet.objects.filter(pk=cadet.pk).exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_post_deletes_cadet_and_scores_and_logs(self):
        group = make_group("C216", cadets=("Alice Ng", "Bob Ray"))
        alice, bob = group.cadets.all()
        Cadet.objects.filter(pk=alice.pk).update(external_id="A1")
        subject = Subject.objects.create(name="Drill")
        make_score_set(self.admin, subject, group, {alice: SCORES, bob: SCORES})
        response = self.client.post(delete_url(alice.pk))
        self.assertRedirects(response, list_url())
        self.assertFalse(Cadet.objects.filter(pk=alice.pk).exists())
        self.assertTrue(Cadet.objects.filter(pk=bob.pk).exists())
        self.assertEqual(CadetScore.objects.count(), 1)
        event = AuditEvent.objects.get(action=actions.CADET_DELETED)
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.group_number, "C216")
        self.assertEqual(
            event.details, {"cadet": "Alice Ng", "external_id": "A1", "score_rows": 1}
        )

    def test_locked_group_blocks_delete(self):
        for status in ("locked", "archived"):
            with self.subTest(status=status):
                group = make_group(f"G-{status}", cadets=("Alice Ng",), status=status)
                cadet = group.cadets.get()
                response = self.client.post(delete_url(cadet.pk))
                self.assertRedirects(response, list_url(group.number))
                self.assertEqual(
                    messages_of(response), [f"Group is {status}; cadets cannot be deleted."]
                )
                self.assertTrue(Cadet.objects.filter(pk=cadet.pk).exists())
        self.assertFalse(AuditEvent.objects.exists())
