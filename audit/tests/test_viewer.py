from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.tests.helpers import make_user
from audit import actions
from audit.models import AuditEvent
from audit.service import log


@override_settings(MFA_REQUIRED=False, LOGIN_MODE="local")
class AuditViewerTests(TestCase):
    def setUp(self):
        self.admin = make_user("boss", role="admin")
        self.instructor = make_user("teach")
        self.url = reverse("audit:event_list")

    def test_instructor_forbidden(self):
        self.client.force_login(self.instructor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_lists_newest_first(self):
        first = log(self.admin, actions.SUBJECT_CREATED, "first event")
        second = log(self.admin, actions.SUBJECT_RENAMED, "second event")
        AuditEvent.objects.filter(pk=first.pk).update(timestamp="2026-01-01T00:00:00Z")
        AuditEvent.objects.filter(pk=second.pk).update(timestamp="2026-02-01T00:00:00Z")
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e.pk for e in response.context["page"]], [second.pk, first.pk])
        content = response.content.decode()
        self.assertLess(content.index("second event"), content.index("first event"))

    def test_filter_by_action(self):
        log(self.admin, actions.SUBJECT_CREATED, "made subject")
        log(self.admin, actions.GROUP_LOCKED, "locked it")
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"action": actions.GROUP_LOCKED})
        self.assertContains(response, "locked it")
        self.assertNotContains(response, "made subject")

    def test_filter_by_group(self):
        log(self.admin, actions.GROUP_LOCKED, "locked c216", group_number="C216")
        log(self.admin, actions.GROUP_LOCKED, "locked c217", group_number="C217")
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"group": "c216"})
        self.assertContains(response, "locked c216")
        self.assertNotContains(response, "locked c217")

    def test_pagination_50_per_page(self):
        for i in range(55):
            log(self.admin, actions.GROUP_LOCKED, f"event {i}", group_number="C216")
        self.client.force_login(self.admin)
        response = self.client.get(self.url, {"group": "C216"})
        self.assertEqual(len(response.context["page"]), 50)
        response = self.client.get(self.url, {"group": "C216", "page": 2})
        self.assertEqual(len(response.context["page"]), 5)
        self.assertContains(response, "group=C216")
